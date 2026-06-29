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
        get_elevation="traffic", elevation_scale=1400 / maxt, extruded=True,
        pickable=True, opacity=0.7, coverage=0.85,
    )
    gj = json.loads((config.REPO_ROOT / "config" / "port_laxlb.geojson").read_text(encoding="utf-8"))
    poly = pdk.Layer("GeoJsonLayer", gj, stroked=True, filled=False,
                     get_line_color=[255, 90, 90], line_width_min_pixels=2)
    view = pdk.ViewState(latitude=33.70, longitude=-118.20, zoom=9.3, pitch=40, bearing=10)
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


GFW_ATTR = ("Datos satelitales: &copy; Global Fishing Watch (CC BY-NC 4.0). "
            "Actividad pesquera 'apparent'. globalfishingwatch.org")


def _inject_caption(html_path: Path, text: str) -> None:
    """Inyecta un pie de atribucion en el HTML (requisito CC BY-NC de GFW)."""
    html = html_path.read_text(encoding="utf-8")
    footer = (f'<div style="position:fixed;bottom:0;left:0;right:0;background:rgba(0,0,0,.6);'
              f'color:#ccc;font:12px sans-serif;padding:5px 10px;z-index:9999">{text}</div>')
    html_path.write_text(html.replace("</body>", footer + "</body>"), encoding="utf-8")


def _chile_map(out_dir: Path) -> tuple[Path, int, int]:
    """Mapa Chile: detecciones SAR (radar) + presencia AIS, de GFW satelital."""
    gdir = config.REPO_ROOT / "data" / "gfw_chile"
    sar = pd.read_parquet(gdir / "sar_presence.parquet").dropna(subset=["lat", "lon"]).copy()
    sar["ship_name"] = sar["ship_name"].fillna("?")
    sar["flag"] = sar["flag"].fillna("?")
    sar["vessel_type"] = sar["vessel_type"].fillna("?")
    layers = []
    ais_path = gdir / "ais_presence.parquet"
    n_ais = 0
    if ais_path.exists():
        ais = pd.read_parquet(ais_path)[["lat", "lon"]].dropna()
        n_ais = len(ais)
        ais_plot = ais.sample(min(n_ais, 5000), random_state=42)  # muestra para no saturar el render
        layers.append(pdk.Layer("ScatterplotLayer", ais_plot, get_position="[lon, lat]",
                                get_fill_color="[80, 140, 255, 45]", get_radius=500))
    layers.append(pdk.Layer("ScatterplotLayer", sar, get_position="[lon, lat]",
                            get_fill_color="[255, 90, 60, 220]", get_radius=900, pickable=True))
    view = pdk.ViewState(latitude=-33.3, longitude=-71.72, zoom=8.4, pitch=0)
    deck = pdk.Deck(layers=layers, initial_view_state=view, map_provider="carto", map_style="dark",
                    tooltip={"text": "SAR: {ship_name}\nbandera: {flag}  tipo: {vessel_type}"})
    p = out_dir / "chile_map.html"
    deck.to_html(str(p), notebook_display=False)
    _inject_caption(p, GFW_ATTR)
    return p, len(sar), n_ais


def run(**kwargs: Any) -> dict:
    out_dir = config.REPO_ROOT / "app"
    out_dir.mkdir(exist_ok=True)
    p1, n1 = _port_map(out_dir)
    print(f"port_map.html  ({n1} celdas H3)        -> {p1}")
    p2, n2 = _dark_map(out_dir)
    print(f"dark_map.html  ({n2} buques oscuros)   -> {p2}")
    result = {"port_cells": n1, "dark_points": n2}
    if (config.REPO_ROOT / "data" / "gfw_chile" / "sar_presence.parquet").exists():
        p3, n_sar, n_ais = _chile_map(out_dir)
        print(f"chile_map.html ({n_sar} SAR + {n_ais} AIS)  -> {p3}")
        result.update(chile_sar=n_sar, chile_ais=n_ais)
    return result


def _cli() -> None:
    argparse.ArgumentParser(description="Genera los mapas HTML (deck.gl/pydeck).").parse_args()
    run()


if __name__ == "__main__":
    _cli()
