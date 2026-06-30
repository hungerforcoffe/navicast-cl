"""Monitoreo de buques oscuros en Chile (vigilancia agendable).

Bucle: fetch GFW (SAR + presencia AIS + AIS-off) -> cruce SAR<->AIS -> mapa deck.gl.
`run()` es el punto de entrada que invoca el DAG (logica desacoplada del orquestador).

Atribucion: datos (c) Global Fishing Watch, CC BY-NC 4.0 (uso no comercial); 'apparent'.
Token: variable de entorno GFW_API_TOKEN o archivo ~/.gfw/token.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import gfwapiclient as gfw
import h3
import pandas as pd

from navicast.common import config, io_s3

BBOX = {"lon_min": -72.5, "lon_max": -71.0, "lat_min": -34.5, "lat_max": -32.5}
SNAP = "snap_chile_valpo_v1"
GAPS_DS = "public-global-gaps-events:latest"
H3_RES, K_RING = 8, 1   # cruce: misma celda H3 o vecina (~1.4 km)
_PREFIX = f"gold/source=gfw/snapshot={SNAP}"


def _token() -> str:
    t = os.environ.get("GFW_API_TOKEN")
    if t and t.strip():
        return t.strip()
    f = Path.home() / ".gfw" / "token"
    if f.exists():
        t = f.read_text(encoding="utf-8").strip()
        if t and not t.startswith("PEGA_AQUI"):
            return t
    raise SystemExit("Falta el token GFW (GFW_API_TOKEN o ~/.gfw/token).")


def _polygon() -> dict:
    b = BBOX
    return {"type": "Polygon", "coordinates": [[
        [b["lon_min"], b["lat_min"]], [b["lon_max"], b["lat_min"]],
        [b["lon_max"], b["lat_max"]], [b["lon_min"], b["lat_max"]],
        [b["lon_min"], b["lat_min"]],
    ]]}


async def _fetch_async(token: str, start: str, end: str) -> dict[str, pd.DataFrame]:
    client = gfw.Client(access_token=token, timeout=180.0)  # AIS HIGH-res es query pesada (>60s)
    poly = _polygon()
    out: dict[str, pd.DataFrame] = {}

    async def grab(name, factory, tries=3):
        for i in range(tries):
            try:
                out[name] = (await factory()).df()
                return
            except Exception as exc:
                print(f"  {name}: intento {i + 1}/{tries} fallo ({type(exc).__name__}); reintento")
                await asyncio.sleep(2)
        print(f"  {name}: sin datos tras {tries} intentos")
        out[name] = pd.DataFrame()

    await grab("sar_presence", lambda: client.fourwings.create_sar_presence_report(
        spatial_resolution="HIGH", temporal_resolution="ENTIRE",
        start_date=start, end_date=end, geojson=poly))
    await grab("ais_presence", lambda: client.fourwings.create_ais_presence_report(
        spatial_resolution="HIGH", temporal_resolution="ENTIRE",
        start_date=start, end_date=end, geojson=poly))
    await grab("ais_off_events", lambda: client.events.get_all_events(
        datasets=[GAPS_DS], types=["GAP"], start_date=start, end_date=end,
        geometry=poly, limit=2000))
    return out


def cross(sar: pd.DataFrame, ais: pd.DataFrame) -> pd.DataFrame:
    """Marca cada deteccion SAR como dark (sin AIS cerca) o corroborada."""
    if not len(sar) or "lat" not in sar.columns:
        sar = sar.copy()
        sar["dark"] = pd.Series(dtype=bool)
        return sar
    sar = sar.dropna(subset=["lat", "lon"]).copy()
    ais_cells = {
        h3.latlng_to_cell(float(la), float(lo), H3_RES)
        for la, lo in zip(ais.get("lat", []), ais.get("lon", []))
        if pd.notna(la) and pd.notna(lo)
    }
    if not ais_cells:                 # sin AIS de referencia no se puede clasificar dark
        sar["dark"] = False
        return sar

    def is_dark(la: float, lo: float) -> bool:
        cell = h3.latlng_to_cell(float(la), float(lo), H3_RES)
        return not any(n in ais_cells for n in h3.grid_disk(cell, K_RING))

    sar["dark"] = [is_dark(la, lo) for la, lo in zip(sar["lat"], sar["lon"])]
    return sar


def _save_upload(dfs: dict[str, pd.DataFrame], upload: bool) -> None:
    gdir = config.REPO_ROOT / "data" / "gfw_chile"
    gdir.mkdir(parents=True, exist_ok=True)
    s3 = bucket = None
    if upload:
        aws = config.load()["aws"]
        bucket = aws["bucket"]
        s3 = io_s3.get_client(aws["region"], aws.get("profile"))
    for name, df in dfs.items():
        if df is None or not len(df):
            print(f"  (omito {name}: vacio -> conservo el previo, no sobreescribo)")
            continue
        p = gdir / f"{name}.parquet"
        df.to_parquet(p, index=False)
        if s3 is not None:
            io_s3.upload_file(s3, p, bucket, f"{_PREFIX}/{name}.parquet")


def fetch(start: str = "2025-01-01", end: str = "2025-06-30", upload: bool = True) -> dict[str, pd.DataFrame]:
    """Solo descarga GFW (sin cruce). Para el CLI fetch_gfw_chile."""
    dfs = asyncio.run(_fetch_async(_token(), start, end))
    _save_upload(dfs, upload)
    return dfs


def run(start: str = "2025-01-01", end: str = "2025-06-30",
        upload: bool = True, make_map: bool = True, **_: Any) -> dict[str, Any]:
    """Bucle completo: fetch -> cruce -> (mapa). Punto de entrada del DAG."""
    dfs = asyncio.run(_fetch_async(_token(), start, end))
    dfs["sar_classified"] = cross(dfs.get("sar_presence", pd.DataFrame()),
                                  dfs.get("ais_presence", pd.DataFrame()))
    _save_upload(dfs, upload)

    cl = dfs["sar_classified"]
    n_dark = int(cl["dark"].sum()) if "dark" in cl.columns and len(cl) else 0
    stats = {"start": start, "end": end, "sar": int(len(cl)), "dark": n_dark,
             "ais": int(len(dfs.get("ais_presence", []))),
             "ais_off": int(len(dfs.get("ais_off_events", [])))}
    print(f"monitor_chile [{start}..{end}]: SAR={stats['sar']} dark={stats['dark']} "
          f"AIS={stats['ais']} AIS_off={stats['ais_off']}")
    if make_map:
        from navicast import viz
        viz._chile_map(config.REPO_ROOT / "app")
    return stats
