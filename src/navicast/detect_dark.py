"""Deteccion de buques oscuros (Sprint 5). Apagones de transpondedor AIS.

Sobre la semana NACIONAL (donde el fenomeno vive: mar abierto / transito).
Determinista + IsolationForest. NO usa LSTM (eso es exclusivo del ETA).

Un "gap" = par de pings consecutivos del mismo MMSI con silencio largo. Por cada
gap calculo: duracion, distancia recorrida en silencio, velocidad implicita, SOG
antes, posicion, hora. Dos capas:
  1. Reglas: gap largo + buque en movimiento antes + distancia significativa +
     velocidad implicita plausible (descarta glitches GPS).
  2. IsolationForest: score de anomalia no supervisado sobre esos features.

Validacion: INYECCION SINTETICA -- borro tramos de trazas reales (apagones
artificiales) y mido si el detector los recupera (recall). GFW = bonus pendiente.

Uso:
  python -m navicast.detect_dark --snapshot snap_2024-01-w3_noaa_national_v1
  python -m navicast.detect_dark --snapshot <id> --no-upload
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from navicast.common import config, io_s3

EARTH_R_KM = 6371.0088
SEED = 42

CAND_GAP_S = 1800        # candidatos: silencio > 30 min
GAP_HOURS_MIN = 2.0      # regla: silencio sospechoso
SOG_MOVING = 3.0         # regla: buque en movimiento antes del apagon (nudos)
DIST_MIN_KM = 5.0        # regla: recorrio algo durante el silencio
IMP_KN_LO, IMP_KN_HI = 1.0, 40.0   # velocidad implicita plausible (excluye glitches)
ISO_CONTAM = 0.02        # fraccion esperada de anomalias

_HAVERSINE = (
    "2*{R}*asin(sqrt(pow(sin(radians({la1}-{la0})/2),2)"
    "+cos(radians({la0}))*cos(radians({la1}))*pow(sin(radians({lo1}-{lo0})/2),2)))"
)


def _gap_sql(source: str) -> str:
    hav = _HAVERSINE.format(R=EARTH_R_KM, la0="plat", la1="LAT", lo0="plon", lo1="LON")
    return f"""
    WITH seq AS (
        SELECT MMSI, BaseDateTime, LAT, LON, SOG,
               lag(BaseDateTime) OVER w AS pt, lag(LAT) OVER w AS plat,
               lag(LON) OVER w AS plon, lag(SOG) OVER w AS psog
        FROM {source}
        WHERE MMSI IS NOT NULL AND MMSI > 99999999
          AND LAT BETWEEN -90 AND 90 AND LON BETWEEN -180 AND 180
        WINDOW w AS (PARTITION BY MMSI ORDER BY BaseDateTime)
    )
    SELECT MMSI, pt AS t_start, BaseDateTime AS t_end,
           date_diff('second', pt, BaseDateTime) / 3600.0 AS gap_h,
           {hav} AS dist_km,
           psog AS sog_before, plat AS lat0, plon AS lon0, LAT AS lat1, LON AS lon1,
           hour(pt) AS hour0
    FROM seq
    WHERE pt IS NOT NULL AND date_diff('second', pt, BaseDateTime) > {CAND_GAP_S}
    """


def extract_gaps(source: str) -> pd.DataFrame:
    """Extrae gaps candidatos (>30 min) con features. `source` = read_parquet(...)."""
    df = duckdb.connect().execute(_gap_sql(source)).df()
    df["implied_kn"] = df["dist_km"] / df["gap_h"] / 1.852
    return df


def _detect(g: pd.DataFrame) -> pd.DataFrame:
    """Anade rule_flag, iso_anomaly y dark (combinado)."""
    from sklearn.ensemble import IsolationForest

    # descartar glitches GPS imposibles antes de puntuar
    g = g[(g["implied_kn"] <= 60) & (g["dist_km"] >= 0)].copy()

    g["rule_flag"] = (
        (g["gap_h"] >= GAP_HOURS_MIN)
        & (g["sog_before"] >= SOG_MOVING)
        & (g["dist_km"] >= DIST_MIN_KM)
        & (g["implied_kn"].between(IMP_KN_LO, IMP_KN_HI))
    )

    feats = g[["gap_h", "dist_km", "implied_kn", "sog_before", "hour0"]].copy()
    feats["abs_lat"] = g["lat0"].abs()
    feats = feats.fillna(0.0)
    iso = IsolationForest(contamination=ISO_CONTAM, random_state=SEED, n_estimators=200)
    pred = iso.fit_predict(feats.to_numpy())
    g["iso_anomaly"] = pred == -1
    g["iso_score"] = -iso.score_samples(feats.to_numpy())  # mayor = mas anomalo
    g["dark"] = g["rule_flag"] | g["iso_anomaly"]
    return g


def _synthetic_recall(source_glob: str, n_inject: int = 200, win_h: float = 2.5) -> tuple[float, int]:
    """Inyecta apagones en trazas reales de buques en movimiento y mide recall."""
    rng = np.random.default_rng(SEED)
    # buques con traza densa y en movimiento (buenos candidatos para apagon claro)
    cands = duckdb.connect().execute(f"""
        SELECT MMSI FROM read_parquet('{source_glob}')
        WHERE SOG BETWEEN 3 AND 30
        GROUP BY MMSI HAVING count(*) > 800
        LIMIT 400
    """).df()["MMSI"].tolist()
    if not cands:
        return float("nan"), 0
    pick = rng.choice(cands, size=min(n_inject, len(cands)), replace=False)
    ids = ",".join(str(int(m)) for m in pick)
    df = duckdb.connect().execute(f"""
        SELECT MMSI, BaseDateTime, LAT, LON, SOG FROM read_parquet('{source_glob}')
        WHERE MMSI IN ({ids}) ORDER BY MMSI, BaseDateTime
    """).df()

    keep_parts, truth = [], []
    for mmsi, grp in df.groupby("MMSI", sort=False):
        grp = grp.reset_index(drop=True)
        t = grp["BaseDateTime"]
        # anclar el apagon a un ping EN MOVIMIENTO (lo que el detector busca),
        # con margen para una ventana de win_h horas por delante.
        last_ok = t.iloc[-1] - pd.Timedelta(hours=win_h)
        movers = grp[(grp["SOG"] >= SOG_MOVING) & (t <= last_ok)]
        if len(movers) == 0:
            keep_parts.append(grp)
            continue
        anchor = movers.iloc[int(rng.integers(len(movers)))]["BaseDateTime"]  # ping que se queda
        end = anchor + pd.Timedelta(hours=win_h)
        mask = (t > anchor) & (t <= end)          # borra los pings siguientes (apagon)
        if mask.sum() == 0:
            keep_parts.append(grp)
            continue
        truth.append((int(mmsi), anchor, end))    # sog_before = SOG del ancla (>=3)
        keep_parts.append(grp[~mask])

    mod = pd.concat(keep_parts, ignore_index=True)
    con = duckdb.connect()
    con.register("mod", mod)
    gaps = _detect(extract_gaps_from_rel(con, "mod"))

    # recall: por cada apagon inyectado, hay un gap rule_flag del mismo MMSI que lo cubre
    hits = 0
    flagged = gaps[gaps["rule_flag"]]
    by_mmsi = {m: grp for m, grp in flagged.groupby("MMSI")}
    for mmsi, start, end in truth:
        grp = by_mmsi.get(mmsi)
        if grp is None:
            continue
        cover = grp[(grp["t_start"] <= start) & (grp["t_end"] >= end)]
        if len(cover):
            hits += 1
    return (hits / len(truth) if truth else float("nan")), len(truth)


def extract_gaps_from_rel(con, rel: str) -> pd.DataFrame:
    """Como extract_gaps pero sobre una relacion ya registrada en `con`."""
    df = con.execute(_gap_sql(rel)).df()
    df["implied_kn"] = df["dist_km"] / df["gap_h"] / 1.852
    return df


def run(snapshot_id: str, config_path: str | Path | None = None, upload: bool = True) -> dict[str, Any]:
    cfg, _ = config.snapshot(snapshot_id, config_path)
    bronze = (config.REPO_ROOT / "data" / "bronze" / snapshot_id).as_posix()
    glob = f"{bronze}/*.parquet"
    if not list(Path(bronze).glob("*.parquet")):
        raise FileNotFoundError(f"No hay Bronze en {glob}. Ingiere {snapshot_id} primero.")

    print("extrayendo gaps candidatos (>30 min) ...", flush=True)
    gaps = _detect(extract_gaps(f"read_parquet('{glob}')"))
    print("validacion sintetica (inyectando apagones) ...", flush=True)
    recall, n_inj = _synthetic_recall(glob)

    dark = gaps[gaps["dark"]].sort_values("iso_score", ascending=False)
    out_root = config.REPO_ROOT / "data" / "dark" / snapshot_id
    out_root.mkdir(parents=True, exist_ok=True)
    out_path = out_root / "dark_events.parquet"
    dark.to_parquet(out_path, index=False)

    stats = {
        "candidatos_gaps": int(len(gaps)),
        "rule_flag": int(gaps["rule_flag"].sum()),
        "iso_anomaly": int(gaps["iso_anomaly"].sum()),
        "dark_total": int(gaps["dark"].sum()),
        "recall_sintetico": round(float(recall), 3),
        "apagones_inyectados": int(n_inj),
    }
    _report(snapshot_id, gaps, dark, stats)

    files = [{"file": "dark_events.parquet", "bytes": out_path.stat().st_size,
              "sha256": io_s3.sha256_file(out_path)}]
    if upload:
        aws = cfg["aws"]
        client = io_s3.get_client(aws["region"], aws.get("profile"))
        key = f"dark/snapshot={snapshot_id}/dark_events.parquet"
        files[0]["s3_uri"] = io_s3.upload_file(client, out_path, aws["bucket"], key)
        manifest = {"snapshot_id": snapshot_id, "kind": "dark",
                    "params": {"gap_hours_min": GAP_HOURS_MIN, "sog_moving": SOG_MOVING,
                               "dist_min_km": DIST_MIN_KM, "iso_contam": ISO_CONTAM},
                    "stats": stats, "files": files,
                    "built_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        io_s3.put_json(client, aws["bucket"], f"dark/snapshot={snapshot_id}/manifest.json", manifest)
        print(f"dark events -> {files[0]['s3_uri']}")
    return stats


def _report(snapshot_id, gaps, dark, stats) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    print("\n" + "=" * 60)
    print(f"BUQUES OSCUROS  |  {snapshot_id}")
    print("=" * 60)
    print(f"gaps candidatos (>30 min)     : {stats['candidatos_gaps']:,}")
    print(f"sospechosos por REGLAS        : {stats['rule_flag']:,}")
    print(f"anomalias IsolationForest     : {stats['iso_anomaly']:,}")
    print(f"DARK (regla | iso)            : {stats['dark_total']:,}")
    print(f"recall sintetico              : {stats['recall_sintetico']:.0%} "
          f"({stats['apagones_inyectados']} apagones inyectados)")
    print("=" * 60)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.scatter(gaps["lon0"], gaps["lat0"], s=2, alpha=0.05, color="#999", label="gaps")
    d = dark
    sc = ax.scatter(d["lon0"], d["lat0"], s=10, c=d["gap_h"], cmap="inferno",
                    vmax=np.percentile(d["gap_h"], 95), label="dark")
    fig.colorbar(sc, label="duracion del apagon (h)")
    ax.set_xlabel("LON"); ax.set_ylabel("LAT")
    ax.set_title(f"Buques oscuros detectados ({stats['dark_total']:,}) — semana nacional")
    ax.legend(loc="lower left", markerscale=2)
    fig.tight_layout()
    fig.savefig(config.REPO_ROOT / "docs" / "dark_ships_map.png", dpi=120)

    md = ["# Buques oscuros — reporte (Sprint 5)", "", f"Snapshot: `{snapshot_id}`", "",
          "| Metrica | Valor |", "|---|---:|",
          f"| Gaps candidatos (>30 min) | {stats['candidatos_gaps']:,} |",
          f"| Sospechosos por reglas | {stats['rule_flag']:,} |",
          f"| Anomalias IsolationForest | {stats['iso_anomaly']:,} |",
          f"| DARK (regla \\| iso) | {stats['dark_total']:,} |",
          f"| Recall sintetico | {stats['recall_sintetico']:.0%} ({stats['apagones_inyectados']} inyectados) |",
          "", "Reglas: silencio >=2 h, buque en movimiento antes (SOG>=3), distancia >=5 km, "
          "velocidad implicita plausible (1-40 kn). Validacion por inyeccion sintetica de "
          "apagones en trazas reales. **GFW pendiente** como bonus.",
          "", "Mapa: `docs/dark_ships_map.png`."]
    (config.REPO_ROOT / "docs" / "dark_ships_report.md").write_text("\n".join(md), encoding="utf-8")


def _cli() -> None:
    ap = argparse.ArgumentParser(description="Deteccion de buques oscuros (gaps + IsolationForest).")
    ap.add_argument("--snapshot", required=True, help="snapshot Bronze nacional")
    ap.add_argument("--config", default=None)
    ap.add_argument("--no-upload", action="store_true")
    args = ap.parse_args()
    run(args.snapshot, config_path=args.config, upload=not args.no_upload)


if __name__ == "__main__":
    _cli()
