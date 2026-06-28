"""Deriva el poligono del puerto LA/Long Beach de forma reproducible y lo congela
en config/port_laxlb.geojson (definicion oficial, versionada).

Metodo data-driven: pings atracados (SOG<1) dentro de la zona portuaria -> celdas
H3 res 8 -> las que acumulan el 90% del tiempo atracado -> union (geopandas).
Excluye fondeaderos mar afuera y carriles a proposito (llegada = atracar).

Uso: python scripts/build_port_polygon.py [--snapshot <silver_id>]
"""
from __future__ import annotations

import argparse

import duckdb
import geopandas as gpd
import h3
from shapely import union_all
from shapely.geometry import Polygon

from navicast.common import config

# Zona portuaria generosa (excluye fondeaderos); dentro de ella refinamos la FORMA.
PORT_ZONE = dict(lon0=-118.30, lon1=-118.10, lat0=33.70, lat1=33.80)
RES = 8            # ~0.46 km
COVERAGE = 0.90    # celdas que acumulan este % del tiempo atracado


def build(snapshot_id: str) -> Polygon:
    root = (config.REPO_ROOT / "data" / "silver" / snapshot_id).as_posix()
    glob = f"{root}/**/*.parquet"
    z = PORT_ZONE
    df = duckdb.connect().execute(f"""
        SELECT LAT, LON FROM read_parquet('{glob}', hive_partitioning=true)
        WHERE SOG < 1.0
          AND LON BETWEEN {z['lon0']} AND {z['lon1']}
          AND LAT BETWEEN {z['lat0']} AND {z['lat1']}
    """).df()

    counts: dict[str, int] = {}
    for lat, lon in zip(df.LAT.to_numpy(), df.LON.to_numpy()):
        c = h3.latlng_to_cell(lat, lon, RES)
        counts[c] = counts.get(c, 0) + 1

    total = sum(counts.values())
    keep, acc = [], 0
    for cell, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True):
        keep.append(cell)
        acc += n
        if acc >= COVERAGE * total:
            break

    polys = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in keep]
    port = union_all(polys)
    print(f"celdas H3 res{RES}: {len(counts)} ocupadas -> {len(keep)} en el puerto ({COVERAGE:.0%})")
    print(f"poligono: {port.geom_type}, bounds={tuple(round(b, 3) for b in port.bounds)}")
    return port


def main() -> None:
    ap = argparse.ArgumentParser(description="Congela el poligono del puerto en config/.")
    ap.add_argument("--snapshot", default="snap_2024-01-w3_laxlb_v1", help="snapshot Silver")
    args = ap.parse_args()
    port = build(args.snapshot)
    out = config.REPO_ROOT / "config" / "port_laxlb.geojson"
    gpd.GeoSeries([port], crs="EPSG:4326").to_file(out, driver="GeoJSON")
    print(f"congelado -> {out}")


if __name__ == "__main__":
    main()
