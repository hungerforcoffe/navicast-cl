"""Features -> Gold (Sprint 3). Silver -> dataset ETA-ready para el LSTM.

Por cada ping calcula:
  - celda H3 (res 7) para indexado/mapa.
  - geometria hacia puerto: dist_to_port_km, bearing_to_port (al centroide del puerto),
    inside_port (point-in-polygon contra config/port_laxlb.geojson, via geopandas).
  - target eta_min: minutos hasta la PROXIMA entrada a la darsena (merge_asof forward por
    MMSI). has_eta marca las muestras usables (entra dentro del horizonte y aun fuera).

Decisiones validadas: llegada = entrar a la darsena (poligono data-driven); horizonte
12 h (ajustable viendo la distribucion); H3 res 7; sin remuestreo (dt_s es feature).

Uso:
  python -m navicast.features --snapshot snap_2024-01-w3_laxlb_v1
  python -m navicast.features --snapshot <id> --no-upload
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Any

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd

from navicast.common import config, io_s3
from navicast.common.h3utils import cells_for

EARTH_R_KM = 6371.0088
H3_RES = 7
HORIZON_MIN = 720   # 12 h: pings a mas de esto de la llegada no se etiquetan

OUT_COLS = [
    "MMSI", "BaseDateTime", "date", "LAT", "LON", "SOG", "COG", "Heading",
    "dt_s", "dist_km", "vessel_uid", "gap_flag",
    "h3_cell", "dist_to_port_km", "bearing_to_port", "inside_port",
    "VesselType", "Length", "Width", "Draft",
    "eta_min", "has_eta",
]


def _load_port():
    gj = config.REPO_ROOT / "config" / "port_laxlb.geojson"
    if not gj.exists():
        raise FileNotFoundError(f"Falta {gj}. Corre scripts/build_port_polygon.py")
    return gpd.read_file(gj).geometry.union_all()


def run(snapshot_id: str, config_path: str | Path | None = None, upload: bool = True,
        h3_res: int = H3_RES, horizon_min: int = HORIZON_MIN) -> dict[str, Any]:
    """Silver -> Gold para un snapshot de modelado. Punto de entrada del DAG."""
    cfg, _ = config.snapshot(snapshot_id, config_path)
    silver = (config.REPO_ROOT / "data" / "silver" / snapshot_id).as_posix()
    glob = f"{silver}/**/*.parquet"
    df = duckdb.connect().execute(
        f"SELECT * FROM read_parquet('{glob}', hive_partitioning=true)").df()

    # --- geometria hacia puerto + H3 ---
    port = _load_port()
    centroid = port.centroid
    plat, plon = centroid.y, centroid.x

    df["h3_cell"] = cells_for(df.LAT.to_numpy(), df.LON.to_numpy(), h3_res)

    pts = gpd.GeoSeries(gpd.points_from_xy(df.LON, df.LAT), crs="EPSG:4326")
    df["inside_port"] = pts.within(port).to_numpy()

    lat1 = np.radians(df.LAT.to_numpy()); lon1 = np.radians(df.LON.to_numpy())
    lat2 = np.radians(plat); lon2 = np.radians(plon)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    df["dist_to_port_km"] = 2 * EARTH_R_KM * np.arcsin(np.sqrt(a))
    bx = np.sin(dlon) * np.cos(lat2)
    by = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    df["bearing_to_port"] = (np.degrees(np.arctan2(bx, by)) + 360) % 360

    # --- target: minutos hasta la PROXIMA entrada a la darsena ---
    df = df.sort_values(["MMSI", "BaseDateTime"]).reset_index(drop=True)
    prev_inside = df.groupby("MMSI")["inside_port"].shift(fill_value=False)
    entry = df["inside_port"] & (~prev_inside)           # transicion fuera->dentro
    arrivals = (df.loc[entry, ["MMSI", "BaseDateTime"]]
                .rename(columns={"BaseDateTime": "arrival_time"})
                .sort_values("arrival_time"))

    df_t = df.sort_values("BaseDateTime")
    merged = pd.merge_asof(df_t, arrivals, by="MMSI",
                           left_on="BaseDateTime", right_on="arrival_time",
                           direction="forward")
    eta = (merged["arrival_time"] - merged["BaseDateTime"]).dt.total_seconds() / 60.0
    merged["eta_min"] = eta
    merged["has_eta"] = (merged["arrival_time"].notna() & (eta >= 0)
                         & (eta <= horizon_min) & (~merged["inside_port"]))

    out = merged[OUT_COLS].copy()
    n_arrivals = int(len(arrivals))   # eventos de entrada a la darsena en la semana

    # --- escribir Gold local, particionado por fecha bajo h3_res=<r> ---
    gold_root = config.REPO_ROOT / "data" / "gold" / snapshot_id / f"h3_res={h3_res}"
    if gold_root.exists():
        shutil.rmtree(gold_root)
    gold_root.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.register("g", out)
    con.execute(f"""
        COPY (SELECT * REPLACE (CAST(date AS DATE) AS date) FROM g) TO '{gold_root.as_posix()}'
        (FORMAT PARQUET, PARTITION_BY (date), COMPRESSION ZSTD, OVERWRITE_OR_IGNORE)
    """)
    con.close()

    # --- subir a S3 + manifest ---
    files_manifest = []
    client = None
    if upload:
        aws = cfg["aws"]
        client = io_s3.get_client(aws["region"], aws.get("profile"))
        if not io_s3.bucket_exists(client, aws["bucket"]):
            raise RuntimeError(f"El bucket '{aws['bucket']}' no existe. Corre scripts/bootstrap_s3.py")
    for f in sorted(gold_root.rglob("*.parquet")):
        rel = f.relative_to(gold_root).as_posix()
        entry_m = {"file": rel, "bytes": f.stat().st_size, "sha256": io_s3.sha256_file(f)}
        if client is not None:
            key = f"gold/snapshot={snapshot_id}/h3_res={h3_res}/{rel}"
            entry_m["s3_uri"] = io_s3.upload_file(client, f, cfg["aws"]["bucket"], key)
        files_manifest.append(entry_m)

    stats = _report(snapshot_id, merged, out, horizon_min, h3_res, upload, n_arrivals)
    manifest = {
        "snapshot_id": snapshot_id, "kind": "gold",
        "h3_res": h3_res, "horizon_min": horizon_min,
        "port_centroid": {"lat": round(plat, 5), "lon": round(plon, 5)},
        "stats": stats,
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "files": files_manifest,
    }
    (gold_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    if client is not None:
        mkey = f"gold/snapshot={snapshot_id}/h3_res={h3_res}/manifest.json"
        io_s3.put_json(client, cfg["aws"]["bucket"], mkey, manifest)
    return manifest


def _report(snapshot_id, merged, out, horizon_min, h3_res, upload, n_arrivals) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    total = len(out)
    future = merged[merged["arrival_time"].notna() & (~merged["inside_port"])
                    & ((merged["arrival_time"] - merged["BaseDateTime"]).dt.total_seconds() >= 0)]
    eta_future = (future["arrival_time"] - future["BaseDateTime"]).dt.total_seconds() / 60.0
    labeled = int(out["has_eta"].sum())
    n_cells = out["h3_cell"].nunique()
    q = eta_future.quantile([0.25, 0.5, 0.75, 0.9]) if len(eta_future) else pd.Series(dtype=float)

    print("\n" + "=" * 66)
    print(f"GOLD  |  {snapshot_id}  |  H3 res{h3_res}  |  horizonte {horizon_min/60:.0f} h")
    print("=" * 66)
    print(f"pings totales              : {total:,}")
    print(f"llegadas a darsena (eventos): {n_arrivals:,}")
    print(f"pings con llegada futura   : {len(future):,}")
    print(f"  ETA p25/p50/p75/p90 (min): "
          + (" / ".join(f"{q[x]:.0f}" for x in [0.25, 0.5, 0.75, 0.9]) if len(q) else "-"))
    print(f"muestras etiquetadas (<{horizon_min/60:.0f}h, has_eta): {labeled:,} "
          f"({100*labeled/total:.1f}% del total)")
    print(f"celdas H3 distintas        : {n_cells:,}")
    print("=" * 66)

    # histograma del target (solo etiquetadas)
    lab = out.loc[out["has_eta"], "eta_min"]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(lab, bins=48, color="#48c", edgecolor="white")
    ax.set_xlabel("eta_min (minutos hasta atracar)")
    ax.set_ylabel("pings etiquetados")
    ax.set_title(f"Distribucion del target ETA (<{horizon_min/60:.0f} h) — {snapshot_id}")
    fig.tight_layout()
    fig.savefig(config.REPO_ROOT / "docs" / "eta_distribution.png", dpi=120)

    stats = {
        "pings_total": total, "llegadas_darsena": n_arrivals,
        "pings_con_llegada_futura": len(future),
        "muestras_etiquetadas": labeled,
        "eta_future_quantiles_min": {str(k): round(float(v), 1) for k, v in q.items()},
        "celdas_h3": int(n_cells),
    }
    md = ["# Gold — features y target ETA", "", f"Snapshot: `{snapshot_id}` · H3 res{h3_res} · "
          f"horizonte {horizon_min/60:.0f} h", "",
          f"- Pings totales: **{total:,}**",
          f"- Llegadas a darsena (eventos): **{n_arrivals:,}**",
          f"- Con llegada futura (fuera del puerto): **{len(future):,}**",
          f"- Muestras etiquetadas (`has_eta`, <{horizon_min/60:.0f} h): **{labeled:,}**",
          f"- Celdas H3 distintas: **{n_cells:,}**", "",
          "ETA de pings con llegada futura (minutos):", "",
          "| p25 | p50 | p75 | p90 |", "|---:|---:|---:|---:|",
          ("| " + " | ".join(f"{q[x]:.0f}" for x in [0.25, 0.5, 0.75, 0.9]) + " |") if len(q) else "| - | - | - | - |",
          "", "Histograma: `docs/eta_distribution.png`. En S3: "
          + ("si" if upload else "no (solo local)")]
    (config.REPO_ROOT / "docs" / "gold_features_report.md").write_text(
        "\n".join(md), encoding="utf-8")
    return stats


def _cli() -> None:
    ap = argparse.ArgumentParser(description="Features Silver -> Gold (geopandas + H3).")
    ap.add_argument("--snapshot", required=True, help="snapshot de modelado de config/snapshots.yml")
    ap.add_argument("--config", default=None)
    ap.add_argument("--no-upload", action="store_true", help="solo local, sin subir a S3")
    ap.add_argument("--h3-res", type=int, default=H3_RES)
    ap.add_argument("--horizon-min", type=int, default=HORIZON_MIN)
    args = ap.parse_args()
    run(args.snapshot, config_path=args.config, upload=not args.no_upload,
        h3_res=args.h3_res, horizon_min=args.horizon_min)


if __name__ == "__main__":
    _cli()
