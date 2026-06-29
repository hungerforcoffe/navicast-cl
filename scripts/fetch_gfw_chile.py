"""Descarga datos satelitales de GFW para Chile (extension stretch).

En vez de grabar AIS terrestre (que no cubre Chile), usamos la API de Global Fishing
Watch (cobertura satelital): detecciones SAR (Sentinel-1), presencia AIS, y eventos
AIS-off (GAP). Una sola pasada -> se congela en S3 (respeta rate limits + reproducibilidad).

Atribucion obligatoria (CC BY-NC 4.0): los datos son (c) Global Fishing Watch. La
actividad pesquera es "apparent". Ver docs y el mapa generado.

Token: env GFW_API_TOKEN o archivo ~/.gfw/token (gratis en globalfishingwatch.org).

Uso:
    python scripts/fetch_gfw_chile.py                      # ventana por defecto, local
    python scripts/fetch_gfw_chile.py --start 2025-01-01 --end 2025-06-30 --s3
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import gfwapiclient as gfw

from navicast.common import config, io_s3

BBOX = {"lon_min": -72.5, "lon_max": -71.0, "lat_min": -34.5, "lat_max": -32.5}
SNAP = "snap_chile_valpo_v1"
GAPS_DS = "public-global-gaps-events:latest"


def _token() -> str:
    t = os.environ.get("GFW_API_TOKEN")
    if t and t.strip():
        return t.strip()
    f = Path.home() / ".gfw" / "token"
    if f.exists():
        t = f.read_text(encoding="utf-8").strip()
        if t and not t.startswith("PEGA_AQUI"):
            return t
    raise SystemExit("Falta el token GFW: ponlo en GFW_API_TOKEN o en ~/.gfw/token")


def _polygon() -> dict:
    b = BBOX
    return {"type": "Polygon", "coordinates": [[
        [b["lon_min"], b["lat_min"]], [b["lon_max"], b["lat_min"]],
        [b["lon_max"], b["lat_max"]], [b["lon_min"], b["lat_max"]],
        [b["lon_min"], b["lat_min"]],
    ]]}


async def _fetch(token: str, start: str, end: str, upload: bool) -> None:
    client = gfw.Client(access_token=token)
    poly = _polygon()
    out = config.REPO_ROOT / "data" / "gfw_chile"
    out.mkdir(parents=True, exist_ok=True)

    async def sar():
        r = await client.fourwings.create_sar_presence_report(
            spatial_resolution="HIGH", temporal_resolution="ENTIRE",
            start_date=start, end_date=end, geojson=poly)
        return r.df()

    async def ais():
        r = await client.fourwings.create_ais_presence_report(
            spatial_resolution="HIGH", temporal_resolution="ENTIRE",
            start_date=start, end_date=end, geojson=poly)
        return r.df()

    async def gaps():
        r = await client.events.get_all_events(
            datasets=[GAPS_DS], types=["GAP"], start_date=start, end_date=end,
            geometry=poly, limit=2000)
        return r.df()

    jobs = {"sar_presence": sar, "ais_presence": ais, "ais_off_events": gaps}
    s3 = None
    if upload:
        aws = config.load()["aws"]
        s3 = io_s3.get_client(aws["region"], aws.get("profile"))
        bucket = aws["bucket"]

    for name, job in jobs.items():
        try:
            df = await job()
        except Exception as exc:  # reporta cual falla sin abortar el resto
            print(f"{name}: ERROR {type(exc).__name__}: {exc}")
            continue
        p = out / f"{name}.parquet"
        df.to_parquet(p, index=False)
        cols = list(df.columns)
        print(f"\n== {name}: {len(df)} filas ==")
        print("  columnas:", cols)
        if len(df):
            print(df.head(3).to_string())
        if s3 is not None:
            io_s3.upload_file(s3, p, bucket, f"gold/source=gfw/snapshot={SNAP}/{name}.parquet")
            print(f"  -> S3 gold/source=gfw/snapshot={SNAP}/{name}.parquet")


def main() -> None:
    ap = argparse.ArgumentParser(description="Descarga GFW (SAR + AIS-off) para Chile.")
    ap.add_argument("--start", default="2025-01-01", help="fecha inicio YYYY-MM-DD")
    ap.add_argument("--end", default="2025-06-30", help="fecha fin YYYY-MM-DD")
    ap.add_argument("--s3", action="store_true", help="subir a S3")
    args = ap.parse_args()
    asyncio.run(_fetch(_token(), args.start, args.end, args.s3))


if __name__ == "__main__":
    main()
