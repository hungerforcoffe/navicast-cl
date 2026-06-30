"""CLI: cruce SAR <-> AIS (clasifica cada deteccion como dark o corroborada).

La logica vive en navicast.monitor_chile.cross (reutilizable por el DAG). Lee los Parquet
ya descargados en data/gfw_chile/ y escribe sar_classified.parquet.

Uso: python scripts/cross_sar_ais.py
"""
from __future__ import annotations

import pandas as pd

from navicast import monitor_chile
from navicast.common import config


def main() -> None:
    gdir = config.REPO_ROOT / "data" / "gfw_chile"
    sar = pd.read_parquet(gdir / "sar_presence.parquet")
    ais = pd.read_parquet(gdir / "ais_presence.parquet")
    cl = monitor_chile.cross(sar, ais)
    cl.to_parquet(gdir / "sar_classified.parquet", index=False)
    n_dark = int(cl["dark"].sum()) if len(cl) else 0
    print(f"cruce SAR<->AIS: {len(cl)} detecciones, {n_dark} dark -> sar_classified.parquet")


if __name__ == "__main__":
    main()
