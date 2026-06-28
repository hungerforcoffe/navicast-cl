"""Benchmark Big Data: pandas vs Polars vs DuckDB.

"La prueba de la competencia Big Data" (CLAUDE.md). Misma operacion pesada sobre
datos AIS de NOAA, midiendo wall-clock y pico de RAM.

Operacion (reconstruccion de trayectorias, 1er paso real de Silver):
  ordenar por (MMSI, BaseDateTime) -> distancia haversine entre puntos
  consecutivos de cada buque -> resumir (n_buques, n_puntos, km totales).

Diseño de medicion:
  - Cada motor corre en su PROPIO subproceso (RAM aislada). El padre muestrea el
    pico de RSS con psutil.
  - Presupuesto de memoria (SAFETY_GB): si un motor supera el tope, el padre lo
    MATA y lo marca OOM. Protege la laptop y demuestra el limite de pandas a escala.
  - Cada motor importa SOLO su libreria (import perezoso) para no inflar la RAM.
  - Los motores que terminan deben coincidir en los 3 escalares -> correccion.

El --path acepta un archivo o un glob de directorio (p.ej. 'data/.../*.parquet').

Uso:
  python -m navicast.benchmark --path "data/bronze/<snap>/*.parquet"
  python -m navicast.benchmark --engine duckdb --path "<glob>"   # modo hijo (JSON)
"""
from __future__ import annotations

import argparse
import glob as globlib
import json
import sys
import time
from pathlib import Path

from navicast.common import config

EARTH_R_KM = 6371.0088  # radio terrestre medio (km), igual en los 3 motores
SAFETY_GB = 8.0         # tope de RAM por motor; si lo supera -> kill + OOM

DEFAULT_PARQUET = str(
    config.REPO_ROOT / "data" / "bronze"
    / "snap_2024-01-15_noaa_national_v1" / "AIS_2024_01_15.parquet"
)
ENGINES = ["pandas", "polars", "duckdb"]

_COLS = ["MMSI", "BaseDateTime", "LAT", "LON"]


def _files(path: str) -> list[str]:
    return sorted(globlib.glob(path)) if "*" in path else [path]


# --------------------------------------------------------------------------- #
# Motores: misma logica, una libreria cada uno. Devuelven (n_vessels, n_points, total_km).
# --------------------------------------------------------------------------- #
def run_pandas(path: str) -> tuple[int, int, float]:
    """Linea base eager: concatena TODO en RAM, ordena y desplaza por grupo."""
    import numpy as np
    import pandas as pd

    df = pd.concat(
        [pd.read_parquet(f, columns=_COLS) for f in _files(path)],
        ignore_index=True,
    )
    df = df.sort_values(["MMSI", "BaseDateTime"], kind="stable")
    g = df.groupby("MMSI", sort=False)

    lat = np.radians(df["LAT"].to_numpy())
    lon = np.radians(df["LON"].to_numpy())
    plat = np.radians(g["LAT"].shift().to_numpy())
    plon = np.radians(g["LON"].shift().to_numpy())
    a = np.sin((lat - plat) / 2) ** 2 + np.cos(plat) * np.cos(lat) * np.sin((lon - plon) / 2) ** 2
    dist = np.nan_to_num(2 * EARTH_R_KM * np.arcsin(np.sqrt(a)))  # 1er punto/buque NaN -> 0

    return int(df["MMSI"].nunique()), int(len(df)), float(dist.sum())


def run_polars(path: str) -> tuple[int, int, float]:
    """Lazy + (si se puede) motor streaming: pushdown, paralelo, RAM acotada."""
    import polars as pl

    lf = (
        pl.scan_parquet(path)
        .select(_COLS)
        .sort(["MMSI", "BaseDateTime"])
        .with_columns(lat_r=pl.col("LAT").radians(), lon_r=pl.col("LON").radians())
        .with_columns(
            plat=pl.col("lat_r").shift(1).over("MMSI"),
            plon=pl.col("lon_r").shift(1).over("MMSI"),
        )
        .with_columns(
            a=((pl.col("lat_r") - pl.col("plat")) / 2).sin().pow(2)
            + pl.col("plat").cos()
            * pl.col("lat_r").cos()
            * (((pl.col("lon_r") - pl.col("plon")) / 2).sin().pow(2))
        )
        .with_columns(dist_km=(2 * EARTH_R_KM * pl.col("a").sqrt().arcsin()).fill_null(0.0))
    )
    agg = lf.select(
        n_vessels=pl.col("MMSI").n_unique(),
        n_points=pl.len(),
        total_km=pl.col("dist_km").sum(),
    )
    try:
        res = agg.collect(engine="streaming")
    except Exception:
        res = agg.collect()
    row = res.row(0, named=True)
    return int(row["n_vessels"]), int(row["n_points"]), float(row["total_km"])


def run_duckdb(path: str) -> tuple[int, int, float]:
    """SQL out-of-core: lee el/los Parquet directo, ventana LAG, todo en una query."""
    import duckdb

    p = path.replace("\\", "/")  # DuckDB prefiere '/' tambien en Windows
    q = f"""
    WITH base AS (
        SELECT MMSI, BaseDateTime, radians(LAT) AS lat_r, radians(LON) AS lon_r
        FROM read_parquet('{p}')
    ),
    lagged AS (
        SELECT MMSI, lat_r, lon_r,
               lag(lat_r) OVER (PARTITION BY MMSI ORDER BY BaseDateTime) AS plat,
               lag(lon_r) OVER (PARTITION BY MMSI ORDER BY BaseDateTime) AS plon
        FROM base
    ),
    dist AS (
        SELECT MMSI,
            CASE WHEN plat IS NULL THEN 0.0
                 ELSE 2 * {EARTH_R_KM} * asin(sqrt(
                     pow(sin((lat_r - plat) / 2), 2)
                     + cos(plat) * cos(lat_r) * pow(sin((lon_r - plon) / 2), 2)))
            END AS dist_km
        FROM lagged
    )
    SELECT count(DISTINCT MMSI) AS n_vessels, count(*) AS n_points, sum(dist_km) AS total_km
    FROM dist
    """
    n_vessels, n_points, total_km = duckdb.connect().execute(q).fetchone()
    return int(n_vessels), int(n_points), float(total_km)


_RUNNERS = {"pandas": run_pandas, "polars": run_polars, "duckdb": run_duckdb}


def _child(engine: str, path: str) -> None:
    """Modo hijo: corre 1 motor, mide wall-clock, imprime JSON en stdout."""
    t0 = time.perf_counter()
    n_vessels, n_points, total_km = _RUNNERS[engine](path)
    wall = time.perf_counter() - t0
    print(json.dumps({
        "engine": engine, "wall_s": wall,
        "n_vessels": n_vessels, "n_points": n_points, "total_km": total_km,
    }))


# --------------------------------------------------------------------------- #
# Orquestador: lanza cada motor como subproceso, muestrea RSS y aplica el tope.
# --------------------------------------------------------------------------- #
def _measure(engine: str, path: str, budget_gb: float = SAFETY_GB) -> dict:
    import subprocess

    import psutil

    cmd = [sys.executable, "-m", "navicast.benchmark", "--engine", engine, "--path", path]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ps = psutil.Process(proc.pid)
    peak = 0
    killed = False
    while proc.poll() is None:
        try:
            rss = ps.memory_info().rss
            for ch in ps.children(recursive=True):
                rss += ch.memory_info().rss
            peak = max(peak, rss)
            if peak > budget_gb * 1e9:
                proc.kill()
                killed = True
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        time.sleep(0.03)
    out, err = proc.communicate()

    if killed:
        return {"engine": engine, "ok": False, "oom": True, "peak_mb": peak / 1e6}
    if proc.returncode != 0:
        return {"engine": engine, "ok": False, "oom": False, "peak_mb": peak / 1e6,
                "error": (err or "").strip()[-300:]}
    line = [ln for ln in out.splitlines() if ln.strip().startswith("{")][-1]
    data = json.loads(line)
    data.update(ok=True, oom=False, peak_mb=peak / 1e6)
    return data


def _report(results: list[dict], path: str, budget_gb: float = SAFETY_GB) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ok = [r for r in results if r.get("ok")]
    pandas_ok = next((r for r in ok if r["engine"] == "pandas"), None)
    base = pandas_ok["wall_s"] if pandas_ok else None

    # correccion sobre los que terminaron
    if ok:
        pts = {r["n_points"] for r in ok}
        ves = {r["n_vessels"] for r in ok}
        kms = [r["total_km"] for r in ok]
        km_ok = (max(kms) - min(kms)) / max(kms) < 1e-3 if max(kms) else True
        agree = len(pts) == 1 and len(ves) == 1 and km_ok
        veredicto = "OK (coinciden)" if agree else "DIFIEREN -> revisar"
        head = (f"filas: {ok[0]['n_points']:,}  buques: {ok[0]['n_vessels']:,}  "
                f"km totales: {ok[0]['total_km']:,.0f}")
    else:
        veredicto = "ningun motor termino"
        head = "(sin resultados)"

    n_files = len(_files(path))

    def fmt(r: dict) -> tuple[str, str, str]:
        if r.get("oom"):
            return "OOM", f"{r['peak_mb']:.0f} (>tope)", "-"
        if not r.get("ok"):
            return "ERROR", f"{r['peak_mb']:.0f}", "-"
        sp = f"{base / r['wall_s']:.1f}x" if base else "-"
        return f"{r['wall_s']:.2f}", f"{r['peak_mb']:.0f}", sp

    print("\n" + "=" * 78)
    print(f"BENCHMARK Big Data  |  {n_files} archivo(s)  |  tope RAM = {budget_gb:.0f} GB")
    print(head)
    print(f"correccion: {veredicto}")
    print("=" * 78)
    print(f"{'motor':<10}{'wall-clock (s)':>16}{'pico RAM (MB)':>18}{'speedup vs pandas':>20}")
    print("-" * 78)
    for r in results:
        w, m, s = fmt(r)
        print(f"{r['engine']:<10}{w:>16}{m:>18}{s:>20}")
    print("=" * 78)

    # markdown
    md = ["# Benchmark Big Data — pandas vs Polars vs DuckDB", "",
          f"Operacion: reconstruccion de trayectorias (sort por MMSI+tiempo, haversine "
          f"entre puntos consecutivos) sobre **{n_files} archivo(s)** NOAA.", "",
          f"Tope de RAM por motor: **{budget_gb:.0f} GB** (si lo supera -> matado y marcado OOM).", "",
          f"- {head}", f"- Correccion: **{veredicto}**", "",
          "| Motor | Wall-clock (s) | Pico RAM (MB) | Speedup vs pandas |",
          "|---|---:|---:|---:|"]
    for r in results:
        w, m, s = fmt(r)
        md.append(f"| {r['engine']} | {w} | {m} | {s} |")
    md += ["", "> Pico de RAM = RSS del subproceso del motor (incluye ~base del interprete).",
           "> OOM = supero el tope de RAM y fue interrumpido (no pudo con este volumen en RAM)."]
    md_path = config.REPO_ROOT / "docs" / "benchmark_results.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"\ntabla  -> {md_path}")

    # figura
    names = [r["engine"] for r in results]
    walls = [r["wall_s"] if r.get("ok") else 0.0 for r in results]
    mems = [r["peak_mb"] for r in results]
    colors = {"pandas": "#c44", "polars": "#48c", "duckdb": "#4a4"}
    bar_colors = [colors[n] for n in names]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    ax1.barh(names, walls, color=bar_colors)
    ax1.set_title("Wall-clock (s) — menor es mejor")
    ax1.invert_yaxis()
    ax2.barh(names, mems, color=bar_colors)
    ax2.set_title(f"Pico de RAM (MB) — tope {budget_gb:.0f} GB")
    ax2.invert_yaxis()
    for i, r in enumerate(results):  # marcar los que reventaron
        if r.get("oom"):
            ax1.text(0, i, "  OOM", va="center", color="#c44", fontweight="bold")
            ax2.text(r["peak_mb"], i, " OOM", va="center", color="#c44", fontweight="bold")
    fig.suptitle(f"Benchmark Big Data: reconstruccion de trayectorias AIS ({n_files} dia/s)")
    fig.tight_layout()
    png_path = config.REPO_ROOT / "docs" / "benchmark_bigdata.png"
    fig.savefig(png_path, dpi=120)
    print(f"figura -> {png_path}")


def run(path: str | None = None, budget_gb: float = SAFETY_GB) -> list[dict]:
    """Orquesta el benchmark completo. Punto de entrada reutilizable."""
    p = path or DEFAULT_PARQUET
    if not _files(p):
        raise FileNotFoundError(f"No hay Parquet en: {p}\nCorre antes la ingesta.")
    results = []
    for eng in ENGINES:
        print(f"-> midiendo {eng} ...", flush=True)
        results.append(_measure(eng, p, budget_gb))
        r = results[-1]
        if r.get("oom"):
            print(f"   {eng}: OOM (supero {budget_gb:.0f} GB, interrumpido)", flush=True)
    _report(results, p, budget_gb)
    return results


def _cli() -> None:
    ap = argparse.ArgumentParser(description="Benchmark pandas vs Polars vs DuckDB.")
    ap.add_argument("--engine", choices=ENGINES, help="modo hijo: corre 1 motor e imprime JSON")
    ap.add_argument("--path", default=None, help="archivo o glob de Parquet (def: Bronze 1 dia)")
    ap.add_argument("--budget-gb", type=float, default=SAFETY_GB,
                    help=f"presupuesto de RAM por motor en GB (def: {SAFETY_GB:.0f})")
    args = ap.parse_args()
    path = args.path or DEFAULT_PARQUET
    if args.engine:
        _child(args.engine, path)
    else:
        run(path, args.budget_gb)


if __name__ == "__main__":
    _cli()
