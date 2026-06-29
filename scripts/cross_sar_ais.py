"""Cruce SAR <-> AIS: el corazon del monitoreo de buques oscuros.

Por cada deteccion SAR (radar satelital), comprueba si hay presencia AIS cerca
(misma celda H3 res 8 o vecina, ~1.4 km). Clasificacion:
  - corroborada: el radar ve un barco Y el AIS tambien -> normal.
  - DARK: el radar ve un barco pero el AIS no muestra nada cerca -> candidato a buque oscuro.

Trabaja sobre los datos GFW de Chile (data/gfw_chile/). Es la logica reutilizable de
monitoreo; sirve igual con detecciones SAR no-matcheadas cuando se disponga de ellas.

Uso: python scripts/cross_sar_ais.py
"""
from __future__ import annotations

import h3
import pandas as pd

from navicast.common import config

H3_RES = 8       # ~0.46 km
K_RING = 1       # celda + vecinas -> ~1.4 km de tolerancia


def main() -> None:
    gdir = config.REPO_ROOT / "data" / "gfw_chile"
    sar = pd.read_parquet(gdir / "sar_presence.parquet").dropna(subset=["lat", "lon"]).copy()
    ais = pd.read_parquet(gdir / "ais_presence.parquet").dropna(subset=["lat", "lon"])

    # huella AIS = conjunto de celdas H3 con presencia AIS
    ais_cells = {h3.latlng_to_cell(float(la), float(lo), H3_RES)
                 for la, lo in zip(ais["lat"].to_numpy(), ais["lon"].to_numpy())}

    def is_dark(lat: float, lon: float) -> bool:
        cell = h3.latlng_to_cell(float(lat), float(lon), H3_RES)
        return not any(n in ais_cells for n in h3.grid_disk(cell, K_RING))

    sar["dark"] = [is_dark(la, lo) for la, lo in zip(sar["lat"], sar["lon"])]
    n_dark = int(sar["dark"].sum())

    out = gdir / "sar_classified.parquet"
    sar.to_parquet(out, index=False)

    print("=" * 56)
    print("CRUCE SAR <-> AIS (Chile)")
    print("=" * 56)
    print(f"detecciones SAR        : {len(sar):,}")
    print(f"celdas H3 con AIS      : {len(ais_cells):,}")
    print(f"corroboradas por AIS   : {len(sar) - n_dark:,}")
    print(f"DARK (SAR sin AIS cerca): {n_dark:,}  ({100*n_dark/len(sar):.1f}%)")
    print("=" * 56)
    if n_dark:
        print("\nTop candidatos dark (radar sin AIS cerca):")
        cols = [c for c in ["ship_name", "flag", "vessel_type", "lat", "lon"] if c in sar.columns]
        print(sar[sar["dark"]][cols].head(8).to_string(index=False))
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
