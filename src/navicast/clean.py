"""Limpieza -> Silver (Sprint 2). Bronze nacional -> recorte LA/Long Beach + limpieza.

Plan P0->P2 (validado con Pablo):
  P0  centinelas->NULL (SOG=102.3, COG=360, Heading=511), clip al bbox, MMSI/tiempo no nulos.
  P1  identidad estable (vessel_uid = MMSI|IMO|CallSign), de-dup de pings, trayectoria por MMSI.
  P2  saltos GPS (descartar velocidad implicita > MAX_KNOTS), marcado de gaps (sin interpolar).

Motor: DuckDB (SQL out-of-core). Lee el Bronze local, escribe Silver particionado por
fecha en local + S3. La interpolacion/resampling se hara en Gold (Sprint 3), no aqui.

Nota de identidad: la trayectoria se agrupa por MMSI (presente en cada reporte de
posicion); IMO/CallSign son escasos en mensajes dinamicos, asi que se conservan como
columnas y se reporta cuantos MMSI tienen >1 IMO (senal de reuso/spoofing) como metrica.

Uso:
  python -m navicast.clean --snapshot snap_2024-01-w3_laxlb_v1
  python -m navicast.clean --snapshot <id> --no-upload   # solo local
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob as globlib
import json
import shutil
from pathlib import Path
from typing import Any

import duckdb

from navicast.common import config, io_s3

EARTH_R_KM = 6371.0088
GAP_SECONDS = 1800   # > 30 min entre pings consecutivos -> gap marcado (P2)
MAX_KNOTS = 60.0     # velocidad implicita mayor -> teleport (salto GPS) -> descartar (P2)


def _bronze_glob(from_bronze: str) -> str:
    d = config.REPO_ROOT / "data" / "bronze" / from_bronze
    return str(d / "*.parquet").replace("\\", "/")


def run(snapshot_id: str, config_path: str | Path | None = None, upload: bool = True) -> dict[str, Any]:
    """Bronze -> Silver para un snapshot de modelado. Punto de entrada del DAG."""
    cfg, snap = config.snapshot(snapshot_id, config_path)
    bbox = snap["bbox"]
    from_bronze = snap["from_bronze"]
    glob = _bronze_glob(from_bronze)
    if not globlib.glob(glob):
        raise FileNotFoundError(f"No hay Bronze en {glob}. Corre antes la ingesta de {from_bronze}.")

    con = duckdb.connect()

    # ---- P0: leer + centinelas->NULL + clip al bbox + no-nulos ----
    raw_total = con.execute(f"SELECT count(*) FROM read_parquet('{glob}')").fetchone()[0]
    con.execute(f"""
        CREATE TEMP TABLE t_clip AS
        SELECT
            MMSI,
            BaseDateTime,
            CAST(BaseDateTime AS DATE) AS date,
            LAT, LON,
            CASE WHEN SOG = 102.3 THEN NULL ELSE SOG END AS SOG,
            CASE WHEN COG = 360.0 THEN NULL ELSE COG END AS COG,
            CASE WHEN Heading = 511 THEN NULL ELSE Heading END AS Heading,
            VesselName, IMO, CallSign, VesselType, Length, Width, Draft,
            coalesce(CAST(MMSI AS VARCHAR), '') || '|' || coalesce(IMO, '') || '|'
                || coalesce(CallSign, '') AS vessel_uid
        FROM read_parquet('{glob}')
        WHERE LON BETWEEN {bbox['lon_min']} AND {bbox['lon_max']}
          AND LAT BETWEEN {bbox['lat_min']} AND {bbox['lat_max']}
          AND MMSI IS NOT NULL
          AND BaseDateTime IS NOT NULL
    """)
    clip_n = con.execute("SELECT count(*) FROM t_clip").fetchone()[0]

    # ---- P1: de-dup de pings exactos (mismo MMSI + timestamp) ----
    con.execute("""
        CREATE TEMP TABLE t_dedup AS
        SELECT * EXCLUDE (rn) FROM (
            SELECT *, row_number() OVER (PARTITION BY MMSI, BaseDateTime ORDER BY LAT, LON) AS rn
            FROM t_clip
        ) WHERE rn = 1
    """)
    dedup_n = con.execute("SELECT count(*) FROM t_dedup").fetchone()[0]

    # ---- P1/P2: trayectoria por MMSI + distancia/tiempo + velocidad implicita + gaps ----
    con.execute(f"""
        CREATE TEMP TABLE t_silver AS
        WITH seq AS (
            SELECT *,
                lag(LAT) OVER w AS plat,
                lag(LON) OVER w AS plon,
                lag(BaseDateTime) OVER w AS ptime
            FROM t_dedup
            WINDOW w AS (PARTITION BY MMSI ORDER BY BaseDateTime)
        ),
        calc AS (
            SELECT *,
                date_diff('second', ptime, BaseDateTime) AS dt_s,
                CASE WHEN plat IS NULL THEN 0.0
                     ELSE 2 * {EARTH_R_KM} * asin(sqrt(
                         pow(sin(radians(LAT - plat) / 2), 2)
                         + cos(radians(plat)) * cos(radians(LAT))
                           * pow(sin(radians(LON - plon) / 2), 2))) END AS dist_km
            FROM seq
        ),
        spd AS (
            SELECT *,
                CASE WHEN dt_s > 0 THEN (dist_km / (dt_s / 3600.0)) / 1.852 ELSE NULL END AS implied_kn,
                (dt_s > {GAP_SECONDS}) AS gap_flag
            FROM calc
        )
        SELECT * EXCLUDE (plat, plon, ptime)
        FROM spd
        WHERE implied_kn IS NULL OR implied_kn <= {MAX_KNOTS}   -- descarta saltos GPS
    """)
    final_n = con.execute("SELECT count(*) FROM t_silver").fetchone()[0]

    # metrica de calidad de identidad (P1): MMSI con mas de un IMO -> reuso/spoofing
    mmsi_multi_imo = con.execute("""
        SELECT count(*) FROM (
            SELECT MMSI FROM t_clip WHERE IMO IS NOT NULL
            GROUP BY MMSI HAVING count(DISTINCT IMO) > 1
        )
    """).fetchone()[0]
    n_vessels = con.execute("SELECT count(DISTINCT MMSI) FROM t_silver").fetchone()[0]

    # ---- escribir Silver local, particionado por fecha ----
    silver_root = config.REPO_ROOT / "data" / "silver" / snapshot_id
    if silver_root.exists():
        shutil.rmtree(silver_root)
    silver_root.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        COPY t_silver TO '{silver_root.as_posix()}'
        (FORMAT PARQUET, PARTITION_BY (date), COMPRESSION ZSTD, OVERWRITE_OR_IGNORE)
    """)
    con.close()

    # ---- subir Silver a S3 + manifest ----
    files_manifest = []
    client = None
    if upload:
        aws = cfg["aws"]
        client = io_s3.get_client(aws["region"], aws.get("profile"))
        if not io_s3.bucket_exists(client, aws["bucket"]):
            raise RuntimeError(f"El bucket '{aws['bucket']}' no existe. Corre scripts/bootstrap_s3.py")

    for f in sorted(silver_root.rglob("*.parquet")):
        rel = f.relative_to(silver_root).as_posix()   # date=YYYY-MM-DD/data_0.parquet
        entry = {"file": rel, "bytes": f.stat().st_size, "sha256": io_s3.sha256_file(f)}
        if client is not None:
            key = f"silver/snapshot={snapshot_id}/{rel}"
            entry["s3_uri"] = io_s3.upload_file(client, f, cfg["aws"]["bucket"], key)
        files_manifest.append(entry)

    stages = [
        ("raw (nacional)", raw_total),
        ("P0 clip LA/LB + centinelas", clip_n),
        ("P1 de-dup pings", dedup_n),
        ("P2 filtro saltos GPS (final)", final_n),
    ]
    manifest = {
        "snapshot_id": snapshot_id,
        "kind": "silver",
        "from_bronze": from_bronze,
        "bbox": bbox,
        "params": {"gap_seconds": GAP_SECONDS, "max_knots": MAX_KNOTS},
        "rows": {name: n for name, n in stages},
        "n_vessels": n_vessels,
        "mmsi_con_multiples_imo": mmsi_multi_imo,
        "cleaned_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "files": files_manifest,
    }
    (silver_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    if client is not None:
        mkey = f"silver/snapshot={snapshot_id}/manifest.json"
        io_s3.put_json(client, cfg["aws"]["bucket"], mkey, manifest)

    _report(snapshot_id, stages, final_n, n_vessels, mmsi_multi_imo, files_manifest, upload)
    return manifest


def _report(snapshot_id, stages, final_n, n_vessels, mmsi_multi_imo, files_manifest, upload) -> None:
    raw = stages[0][1]
    print("\n" + "=" * 66)
    print(f"SILVER  |  {snapshot_id}")
    print("=" * 66)
    print(f"{'etapa':<34}{'filas':>16}{'retenido':>12}")
    print("-" * 66)
    for name, n in stages:
        print(f"{name:<34}{n:>16,}{100 * n / raw:>11.2f}%")
    print("-" * 66)
    print(f"buques (MMSI distintos): {n_vessels:,}")
    print(f"MMSI con >1 IMO (posible reuso/spoofing): {mmsi_multi_imo}")
    print(f"archivos Silver: {len(files_manifest)} (particionados por fecha)")
    print("=" * 66)

    md = ["# Silver — reporte de limpieza", "", f"Snapshot: `{snapshot_id}`", "",
          "| Etapa | Filas | Retenido |", "|---|---:|---:|"]
    for name, n in stages:
        md.append(f"| {name} | {n:,} | {100 * n / raw:.2f}% |")
    md += ["", f"- Buques (MMSI distintos): **{n_vessels:,}**",
           f"- MMSI con >1 IMO (posible reuso/spoofing): **{mmsi_multi_imo}**",
           f"- En S3: **{'si' if upload else 'no (solo local)'}**"]
    (config.REPO_ROOT / "docs" / "silver_cleaning_report.md").write_text(
        "\n".join(md), encoding="utf-8")


def _cli() -> None:
    ap = argparse.ArgumentParser(description="Limpieza Bronze -> Silver (DuckDB).")
    ap.add_argument("--snapshot", required=True, help="snapshot Silver de config/snapshots.yml")
    ap.add_argument("--config", default=None, help="ruta alternativa a snapshots.yml")
    ap.add_argument("--no-upload", action="store_true", help="solo local, sin subir a S3")
    args = ap.parse_args()
    run(args.snapshot, config_path=args.config, upload=not args.no_upload)


if __name__ == "__main__":
    _cli()
