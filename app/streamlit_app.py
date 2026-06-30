"""NaviCast-CL — dashboard publico (Streamlit Community Cloud).

Lee el snapshot SLIM de app/data/ (colores ya precomputados). Autocontenido: solo
necesita streamlit + pydeck + pandas + pyarrow; NO corre el pipeline. Los mapas son
deck.gl via st.pydeck_chart.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

DATA = Path(__file__).parent / "data"
DOCS = Path(__file__).parent.parent / "docs"
GFW_ATTR = "Datos satelitales Chile: © Global Fishing Watch (CC BY-NC 4.0); actividad pesquera 'apparent'."

st.set_page_config(page_title="NaviCast-CL", page_icon="🚢", layout="wide")


@st.cache_data
def load():
    stats = json.loads((DATA / "stats.json").read_text(encoding="utf-8"))
    rd = pd.read_parquet
    return (stats, rd(DATA / "port_h3.parquet"), rd(DATA / "dark_us.parquet"),
            rd(DATA / "chile_sar.parquet"), rd(DATA / "chile_ais.parquet"),
            pd.read_csv(DATA / "benchmark.csv"), pd.read_csv(DATA / "eta.csv"))


stats, port, dark, csar, cais, bench, eta = load()

st.title("🚢 NaviCast-CL")
st.markdown(
    "**Pipeline geoespacial AIS de punta a punta** — ingesta → limpieza → features → "
    "ETA (LSTM) → detección de buques oscuros → mapas. Proyecto de curso (Big Data) sobre "
    "datos de referencia de **NOAA** a escala laptop; el foco son las **decisiones de "
    "ingeniería justificadas**, no inteligencia marítima de producción."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Filas AIS procesadas", f"{stats['rows_national'] / 1e6:.0f} M")
c2.metric("ETA LSTM (MAE test)", f"{stats['eta_mae_lstm']:.0f} min")
c3.metric("Buques oscuros (US)", f"{stats['dark_us']:,}")
c4.metric("Recall sintético", f"{stats['dark_recall'] * 100:.0f}%")

st.header("Benchmark Big Data — pandas vs Polars vs DuckDB")
st.markdown(
    "Misma operación pesada (reconstrucción de trayectorias) en los 3 motores. A escala de "
    "1 semana (50 M filas) con presupuesto de 6 GB, **pandas revienta (OOM)** mientras DuckDB "
    "lo resuelve en 2.3 GB. Métrica: wall-clock + pico de RAM."
)
b1, b2 = st.columns(2)
b1.dataframe(bench, hide_index=True, use_container_width=True)
if (DOCS / "benchmark_bigdata.png").exists():
    b2.image(str(DOCS / "benchmark_bigdata.png"))

st.header("ETA a puerto — LSTM vs baselines")
e1, e2 = st.columns(2)
e1.dataframe(eta, hide_index=True, use_container_width=True)
e1.caption(
    "MAE en **test = buques nunca vistos** (split por buque, sin fuga). El LSTM gana al baseline "
    "físico 1.45×. Limitación honesta: el tiempo de cola en fondeadero no está en la cinemática "
    "(de ahí las bandas en el scatter)."
)
if (DOCS / "eta_model_eval.png").exists():
    e2.image(str(DOCS / "eta_model_eval.png"))

st.header("Mapas")

st.subheader("Tráfico H3 — LA/Long Beach")
st.caption("Hexágonos H3 (res 7): altura = tráfico, color = ETA medio. Gira y haz zoom.")
st.pydeck_chart(pdk.Deck(
    layers=[pdk.Layer("H3HexagonLayer", port, get_hexagon="h3_cell",
                      get_fill_color="[r, g, b, a]", get_elevation="elev",
                      elevation_scale=1, extruded=True, opacity=0.7, pickable=True)],
    initial_view_state=pdk.ViewState(latitude=33.70, longitude=-118.20, zoom=8.4, pitch=40, bearing=10),
    map_provider="carto", map_style="dark",
    tooltip={"text": "tráfico: {traffic} pings\nETA medio: {avg_eta} min"}))

st.subheader("Buques oscuros — US (apagones de AIS)")
st.caption("Apagones de transpondedor (gaps + IsolationForest). Color/tamaño = duración del silencio.")
st.pydeck_chart(pdk.Deck(
    layers=[pdk.Layer("ScatterplotLayer", dark, get_position="[lon0, lat0]",
                      get_fill_color="[r, g, b, a]", get_radius="radius", opacity=0.6, pickable=True)],
    initial_view_state=pdk.ViewState(latitude=37, longitude=-100, zoom=3.1),
    map_provider="carto", map_style="dark", tooltip={"text": "apagón: {gap_h} h"}))

st.subheader("Chile — cruce SAR↔AIS (GFW satelital)")
st.caption("Verde = corroborado por AIS · **rojo = DARK** (radar sin AIS cerca).")
st.pydeck_chart(pdk.Deck(
    layers=[
        pdk.Layer("ScatterplotLayer", cais, get_position="[lon, lat]",
                  get_fill_color="[80, 140, 255, 45]", get_radius=500),
        pdk.Layer("ScatterplotLayer", csar, get_position="[lon, lat]",
                  get_fill_color="[r, g, b, a]", get_radius="radius", pickable=True),
    ],
    initial_view_state=pdk.ViewState(latitude=-33.3, longitude=-71.72, zoom=8.3),
    map_provider="carto", map_style="dark",
    tooltip={"text": "SAR: {ship_name}\n{flag} · {vessel_type}\n{estado}"}))
st.markdown(f"**Watchlist — {stats['chile_dark']} candidatos dark** (radar sin AIS cerca):")
st.dataframe(csar[csar["dark"]][["ship_name", "flag", "vessel_type", "lat", "lon"]],
             hide_index=True, use_container_width=True)

st.divider()
st.caption(f"{GFW_ATTR}  ·  Código: github.com/hungerforcoffe/navicast-cl (MIT)")
