"""Fallback de orquestacion SIN Airflow (cross-platform, corre ya).

Ejecuta el pipeline completo en orden, invocando los run() de cada etapa.
Es la red de seguridad del CLAUDE.md: si el DAG/Astro se complica, esto siempre corre.

Uso:
    python scripts/run_pipeline.py                 # pipeline completo (sube a S3)
    python scripts/run_pipeline.py --no-upload     # todo local
    python scripts/run_pipeline.py --skip-ingest   # reusa el Bronze ya descargado
"""
from __future__ import annotations

import argparse

from navicast import clean, detect_dark, features, ingest, model_eta, viz

NAT = "snap_2024-01-w3_noaa_national_v1"   # nacional (buques oscuros)
MOD = "snap_2024-01-w3_laxlb_v1"           # modelado LA/Long Beach


def main() -> None:
    ap = argparse.ArgumentParser(description="Pipeline completo NaviCast-CL (fallback sin Airflow).")
    ap.add_argument("--no-upload", action="store_true", help="no subir a S3 (solo local)")
    ap.add_argument("--skip-ingest", action="store_true", help="reusar el Bronze ya descargado")
    args = ap.parse_args()
    up = not args.no_upload

    steps = []
    if not args.skip_ingest:
        steps.append(("ingest", lambda: ingest.run(NAT, upload=up)))
    steps += [
        ("clean -> Silver", lambda: clean.run(MOD, upload=up)),
        ("features -> Gold", lambda: features.run(MOD, upload=up)),
        ("model ETA (LSTM)", lambda: model_eta.run(MOD, upload=up)),
        ("buques oscuros", lambda: detect_dark.run(NAT, upload=up)),
        ("viz -> mapas HTML", lambda: viz.run()),
    ]
    for i, (name, fn) in enumerate(steps, 1):
        print(f"\n===== [{i}/{len(steps)}] {name} =====", flush=True)
        fn()
    print("\nPIPELINE COMPLETO")


if __name__ == "__main__":
    main()
