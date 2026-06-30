"""Genera el snapshot SLIM publico para la app Streamlit (app/data/).

Lee la data local del pipeline y escribe agregados pequenos con colores ya precomputados,
para que la app sea autocontenida y de dependencias minimas (streamlit + pydeck + pandas
+ pyarrow), sin el stack pesado del pipeline. Total < 1 MB -> se versiona en el repo.

Uso: python scripts/build_app_data.py
"""
from __future__ import annotations

import json

import duckdb
import matplotlib
import numpy as np
import pandas as pd

from navicast.common import config

OUT = config.REPO_ROOT / "app" / "data"
OUT.mkdir(parents=True, exist_ok=True)


def _colors(values, cmap_name, vmin, vmax, alpha=190):
    cmap = matplotlib.colormaps[cmap_name]
    norm = matplotlib.colors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    rgba = cmap(norm(np.nan_to_num(np.asarray(values, dtype=float), nan=vmin)))
    return [[int(r * 255), int(g * 255), int(b * 255), alpha] for r, g, b, _ in rgba]


# --- 1. LA/LB: hexagonos H3 (trafico + ETA medio) ---
gold = (config.REPO_ROOT / "data" / "gold" / "snap_2024-01-w3_laxlb_v1").as_posix()
ph = duckdb.connect().execute(f"""
    SELECT h3_cell, count(*) AS traffic,
           round(avg(eta_min) FILTER (WHERE has_eta), 0) AS avg_eta
    FROM read_parquet('{gold}/**/*.parquet', hive_partitioning=true)
    GROUP BY h3_cell
""").df()
ph["avg_eta"] = ph["avg_eta"].astype(float)
ph["fill_color"] = _colors(ph["avg_eta"], "viridis",
                           np.nanpercentile(ph["avg_eta"], 5), np.nanpercentile(ph["avg_eta"], 95))
ph["elev"] = (ph["traffic"] / ph["traffic"].max() * 1400).round(0)
ph.to_parquet(OUT / "port_h3.parquet", index=False)

# --- 2. Buques oscuros US (nacional) ---
dk = pd.read_parquet(
    config.REPO_ROOT / "data" / "dark" / "snap_2024-01-w3_noaa_national_v1" / "dark_events.parquet",
    columns=["lon0", "lat0", "gap_h"]).dropna()
dk["gap_h"] = dk["gap_h"].round(1)
dk["color"] = _colors(dk["gap_h"], "inferno", 2.0, float(np.nanpercentile(dk["gap_h"], 95)))
dk["radius"] = (1500 + dk["gap_h"].clip(0, 72) * 400).astype(int)
dk.to_parquet(OUT / "dark_us.parquet", index=False)

# --- 3. Chile: SAR clasificado (dark vs corroborado) + muestra AIS ---
gdir = config.REPO_ROOT / "data" / "gfw_chile"
sar = pd.read_parquet(gdir / "sar_classified.parquet").dropna(subset=["lat", "lon"]).copy()
for c in ("ship_name", "flag", "vessel_type"):
    sar[c] = sar[c].fillna("?")
sar = sar[["lat", "lon", "dark", "ship_name", "flag", "vessel_type"]]
sar["fill"] = sar["dark"].map(lambda d: [255, 40, 40, 245] if d else [90, 170, 110, 150])
sar["radius"] = sar["dark"].map(lambda d: 1800 if d else 650)
sar["estado"] = sar["dark"].map(lambda d: "DARK (radar sin AIS)" if d else "corroborado por AIS")
sar.to_parquet(OUT / "chile_sar.parquet", index=False)

ais = pd.read_parquet(gdir / "ais_presence.parquet")[["lat", "lon"]].dropna()
ais.sample(min(len(ais), 4000), random_state=42).to_parquet(OUT / "chile_ais.parquet", index=False)

# --- 4. Benchmark (numeros validados) ---
bench = pd.DataFrame([
    {"escenario": "1 dia (7.3M filas)", "motor": "pandas", "wall_s": "4.24", "peak_mb": "1416"},
    {"escenario": "1 dia (7.3M filas)", "motor": "Polars", "wall_s": "1.63", "peak_mb": "786"},
    {"escenario": "1 dia (7.3M filas)", "motor": "DuckDB", "wall_s": "1.36", "peak_mb": "408"},
    {"escenario": "1 semana (50.3M, tope 6GB)", "motor": "pandas", "wall_s": "OOM", "peak_mb": ">6000"},
    {"escenario": "1 semana (50.3M, tope 6GB)", "motor": "Polars", "wall_s": "9.5", "peak_mb": "4200"},
    {"escenario": "1 semana (50.3M, tope 6GB)", "motor": "DuckDB", "wall_s": "7.5", "peak_mb": "2293"},
])
bench.to_csv(OUT / "benchmark.csv", index=False)

# --- 5. ETA (MAE test, buques nunca vistos) ---
pd.DataFrame([
    {"modelo": "naive (dist/SOG)", "mae_min": 136.4},
    {"modelo": "HistGradientBoosting", "mae_min": 96.0},
    {"modelo": "LSTM", "mae_min": 93.9},
]).to_csv(OUT / "eta.csv", index=False)

# --- 6. headline stats ---
stats = {
    "rows_national": 50272290,
    "vessels_laxlb": 966,
    "eta_labeled": 111727,
    "eta_mae_lstm": 93.9,
    "dark_us": int(len(dk)),
    "dark_recall": 0.74,
    "chile_sar": int(len(sar)),
    "chile_dark": int(sar["dark"].sum()),
}
(OUT / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")

print("snapshot slim ->", OUT)
for f in sorted(OUT.glob("*")):
    print(f"  {f.name}: {f.stat().st_size/1024:.1f} KB")
print("TOTAL:", f"{sum(f.stat().st_size for f in OUT.glob('*'))/1024:.1f} KB")
