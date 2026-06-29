"""Grabador de AIS en vivo desde aisstream.io -> Bronze (extension Chile, Sprint stretch).

Se conecta por WebSocket, se suscribe a un bbox y guarda los mensajes AIS normalizados
al esquema Bronze del proyecto (mismo que NOAA), rotando archivos Parquet. El pipeline
(clean/features/viz) se reutiliza tal cual sobre el resultado.

Reproducibilidad: la grabacion ES la ingesta puntual (permitida); luego se congela el
snapshot en S3 y el pipeline lee de ahi (nunca API en vivo dentro del pipeline/demo).

Token: en la variable de entorno AISSTREAM_API_KEY (gratis en https://aisstream.io).
NADA de hardcodear el token.

Uso:
    $env:AISSTREAM_API_KEY="..."          # PowerShell
    python scripts/record_aisstream.py                 # graba hasta Ctrl+C
    python scripts/record_aisstream.py --minutes 10    # prueba corta
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
from pathlib import Path

import pandas as pd
import websockets

URL = "wss://stream.aisstream.io/v0/stream"
SNAP = "snap_chile_valpo_v1"
# bbox Valparaiso + San Antonio, formato aisstream [[lat1,lon1],[lat2,lon2]]
CHILE_BBOX = [[-34.5, -72.5], [-32.5, -71.0]]

BRONZE_COLS = ["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "Heading",
               "VesselName", "IMO", "CallSign", "VesselType", "Length", "Width", "Draft"]


def _parse_time(s: str) -> dt.datetime | None:
    # MetaData.time_utc: "2024-06-29 18:22:32.318353 +0000 UTC"
    try:
        return dt.datetime.strptime(s.split(" +")[0], "%Y-%m-%d %H:%M:%S.%f")
    except (ValueError, AttributeError):
        return None


def _flush(rows: list[dict], out_dir: Path) -> int:
    if not rows:
        return 0
    df = pd.DataFrame(rows, columns=BRONZE_COLS)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
    df.to_parquet(out_dir / f"AIS_chile_{stamp}.parquet", index=False)
    return len(df)


async def record(api_key: str, bbox: list, out_dir: Path, minutes: float | None,
                 flush_secs: int = 300) -> None:
    sub = {"APIKey": api_key, "BoundingBoxes": [bbox],
           "FilterMessageTypes": ["PositionReport", "ShipStaticData"]}
    static: dict[int, dict] = {}      # MMSI -> datos estaticos (nombre, IMO, etc.)
    rows: list[dict] = []
    n_msgs = total_saved = 0
    loop = asyncio.get_event_loop()
    t0 = loop.time()
    last_flush = t0
    deadline = t0 + minutes * 60 if minutes else None

    while True:
        try:
            async with websockets.connect(URL, ping_interval=20) as ws:
                await ws.send(json.dumps(sub))
                print(f"conectado; grabando bbox {bbox} -> {out_dir}", flush=True)
                async for raw in ws:
                    msg = json.loads(raw)
                    mtype = msg.get("MessageType")
                    meta = msg.get("MetaData", {})
                    mmsi = meta.get("MMSI")
                    body = msg.get("Message", {}).get(mtype, {})

                    if mtype == "ShipStaticData":
                        dim = body.get("Dimension", {}) or {}
                        static[mmsi] = {
                            "VesselName": body.get("Name"),
                            "IMO": str(body.get("ImoNumber") or "") or None,
                            "CallSign": body.get("CallSign"),
                            "VesselType": body.get("Type"),
                            "Length": (dim.get("A", 0) or 0) + (dim.get("B", 0) or 0) or None,
                            "Width": (dim.get("C", 0) or 0) + (dim.get("D", 0) or 0) or None,
                            "Draft": body.get("MaximumStaticDraught"),
                        }
                    elif mtype == "PositionReport":
                        st = static.get(mmsi, {})
                        rows.append({
                            "MMSI": mmsi,
                            "BaseDateTime": _parse_time(meta.get("time_utc", "")),
                            "LAT": body.get("Latitude", meta.get("latitude")),
                            "LON": body.get("Longitude", meta.get("longitude")),
                            "SOG": body.get("Sog"), "COG": body.get("Cog"),
                            "Heading": body.get("TrueHeading"),
                            "VesselName": st.get("VesselName"), "IMO": st.get("IMO"),
                            "CallSign": st.get("CallSign"), "VesselType": st.get("VesselType"),
                            "Length": st.get("Length"), "Width": st.get("Width"),
                            "Draft": st.get("Draft"),
                        })
                        n_msgs += 1

                    now = loop.time()
                    if now - last_flush >= flush_secs:
                        saved = _flush(rows, out_dir)
                        total_saved += saved
                        rows = []
                        last_flush = now
                        print(f"  +{saved} pings | total {total_saved} | buques {len(static)}", flush=True)
                    if deadline and now >= deadline:
                        raise KeyboardInterrupt
        except (KeyboardInterrupt, asyncio.CancelledError):
            break
        except Exception as exc:  # reconexion ante caidas de red
            print(f"  desconexion ({type(exc).__name__}: {exc}); reintento en 5s", flush=True)
            await asyncio.sleep(5)

    total_saved += _flush(rows, out_dir)
    print(f"\nFIN: {total_saved} pings guardados, {len(static)} buques con datos estaticos.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Graba AIS de aisstream.io -> Bronze (Chile).")
    ap.add_argument("--minutes", type=float, default=None, help="auto-parar tras N minutos (def: hasta Ctrl+C)")
    ap.add_argument("--flush-secs", type=int, default=300, help="cada cuanto vuelca a Parquet")
    ap.add_argument("--out", default=None, help="carpeta de salida (def: data/bronze/<snap>)")
    args = ap.parse_args()

    api_key = os.environ.get("AISSTREAM_API_KEY")
    if not api_key:
        raise SystemExit("Falta AISSTREAM_API_KEY en el entorno. Sacalo gratis en https://aisstream.io")

    from navicast.common import config
    out_dir = Path(args.out) if args.out else config.REPO_ROOT / "data" / "bronze" / SNAP
    try:
        asyncio.run(record(api_key, CHILE_BBOX, out_dir, args.minutes, args.flush_secs))
    except KeyboardInterrupt:
        print("\ninterrumpido.")


if __name__ == "__main__":
    main()
