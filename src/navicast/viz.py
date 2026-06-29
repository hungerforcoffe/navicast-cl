"""Visualizacion -> mapas HTML (Sprint 6). deck.gl via pydeck.

Genera HTML autocontenidos (datos AIS embebidos = offline/reproducible; la libreria
deck.gl y el basemap Carto se cargan por CDN al renderizar). Lee Gold y la capa dark.

  app/port_map.html  -- LA/LB: hexagonos H3 (altura=trafico, color=ETA medio) + poligono.
  app/dark_map.html  -- nacional: puntos de apagones (tamano/color=duracion del silencio).

Uso: python -m navicast.viz
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import pydeck as pdk

from navicast.common import config

GOLD_SNAP = "snap_2024-01-w3_laxlb_v1"
DARK_SNAP = "snap_2024-01-w3_noaa_national_v1"


def _colors(values: np.ndarray, cmap_name: str, vmin: float, vmax: float) -> list[list[int]]:
    """Mapea valores a [r,g,b,a] con un colormap de matplotlib."""
    import matplotlib
    cmap = matplotlib.colormaps[cmap_name]
    norm = matplotlib.colors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    rgba = cmap(norm(np.nan_to_num(values, nan=vmin)))
    return [[int(r * 255), int(g * 255), int(b * 255), 180] for r, g, b, _ in rgba]


def _port_map(out_dir: Path) -> tuple[Path, int]:
    gold = (config.REPO_ROOT / "data" / "gold" / GOLD_SNAP).as_posix()
    df = duckdb.connect().execute(f"""
        SELECT h3_cell, count(*) AS traffic,
               round(avg(eta_min) FILTER (WHERE has_eta), 0) AS avg_eta
        FROM read_parquet('{gold}/**/*.parquet', hive_partitioning=true)
        GROUP BY h3_cell
    """).df()
    df["avg_eta"] = df["avg_eta"].astype(float)
    vmin, vmax = np.nanpercentile(df["avg_eta"], 5), np.nanpercentile(df["avg_eta"], 95)
    df["fill_color"] = _colors(df["avg_eta"].to_numpy(), "viridis", vmin, vmax)
    maxt = int(df["traffic"].max())

    hexes = pdk.Layer(
        "H3HexagonLayer", df, get_hexagon="h3_cell", get_fill_color="fill_color",
        get_elevation="traffic", elevation_scale=3000 / maxt, extruded=True,
        pickable=True, opacity=0.55, coverage=0.9,
    )
    gj = json.loads((config.REPO_ROOT / "config" / "port_laxlb.geojson").read_text(encoding="utf-8"))
    poly = pdk.Layer("GeoJsonLayer", gj, stroked=True, filled=False,
                     get_line_color=[255, 90, 90], line_width_min_pixels=2)
    view = pdk.ViewState(latitude=33.74, longitude=-118.22, zoom=10, pitch=50, bearing=20)
    deck = pdk.Deck(layers=[hexes, poly], initial_view_state=view,
                    map_provider="carto", map_style="dark",
                    tooltip={"text": "trafico: {traffic} pings\nETA medio: {avg_eta} min"})
    p = out_dir / "port_map.html"
    deck.to_html(str(p), notebook_display=False)
    return p, len(df)


def _dark_map(out_dir: Path) -> tuple[Path, int]:
    dark = config.REPO_ROOT / "data" / "dark" / DARK_SNAP / "dark_events.parquet"
    d = pd.read_parquet(dark, columns=["MMSI", "lat0", "lon0", "gap_h", "dist_km"])
    d["gap_h"] = d["gap_h"].round(1)
    d["dist_km"] = d["dist_km"].round(1)
    d["color"] = _colors(d["gap_h"].to_numpy(), "inferno", 2.0, float(np.nanpercentile(d["gap_h"], 95)))
    d["radius"] = 1500 + d["gap_h"].clip(0, 72) * 400

    layer = pdk.Layer("ScatterplotLayer", d, get_position="[lon0, lat0]",
                      get_fill_color="color", get_radius="radius", pickable=True, opacity=0.5)
    view = pdk.ViewState(latitude=37, longitude=-100, zoom=3.2, pitch=0)
    deck = pdk.Deck(layers=[layer], initial_view_state=view,
                    map_provider="carto", map_style="dark",
                    tooltip={"text": "MMSI: {MMSI}\napagon: {gap_h} h\ndistancia: {dist_km} km"})
    p = out_dir / "dark_map.html"
    deck.to_html(str(p), notebook_display=False)
    return p, len(d)


def run(**kwargs: Any) -> dict:
    out_dir = config.REPO_ROOT / "app"
    out_dir.mkdir(exist_ok=True)
    p1, n1 = _port_map(out_dir)
    print(f"port_map.html  ({n1} celdas H3)        -> {p1}")
    p2, n2 = _dark_map(out_dir)
    print(f"dark_map.html  ({n2} buques oscuros)   -> {p2}")
    return {"port_cells": n1, "dark_points": n2}


def _cli() -> None:
    argparse.ArgumentParser(description="Genera los mapas HTML (deck.gl/pydeck).").parse_args()
    run()


if __name__ == "__main__":
    _cli()
