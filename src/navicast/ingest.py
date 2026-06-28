"""Ingesta -> Bronze.

Descarga 1+ archivos diarios NACIONALES de NOAA Marine Cadastre y los escribe
como Parquet INMUTABLE en la capa Bronze de S3. Bronze = crudo: NO se aplica
ninguna limpieza ni se anulan centinelas (eso es Silver/clean.py).

Por que streaming CSV->Parquet con pyarrow: el CSV nacional descomprimido pesa
~1.5-3 GB. Cargarlo entero (estilo pandas.read_csv) revienta la RAM de una
laptop -> justamente lo que el benchmark del Sprint 1 quiere demostrar. Aqui lo
hacemos por lotes (batches) con memoria acotada.

Esta etapa es geografia-agnostica (archivo nacional sin recortar): no depende de
la decision abierta #1.

Uso:
    python -m navicast.ingest --snapshot snap_2024-01-15_noaa_national_v1
    python -m navicast.ingest --snapshot <id> --no-upload   # solo local (probar sin AWS)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from navicast.common import config, io_s3, schema

NOAA_BASE = "https://coast.noaa.gov/htdata/CMSP/AISDataHandler"
USER_AGENT = "navicast-cl/0.1 (curso big data; contacto via repo)"


def noaa_url(date: str) -> str:
    """date en 'YYYY-MM-DD' -> URL del zip diario nacional."""
    y, m, d = date.split("-")
    return f"{NOAA_BASE}/{y}/AIS_{y}_{m}_{d}.zip"


def _download(url: str, dest: Path) -> Path:
    """Descarga en streaming con barra de progreso simple."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    print(f"  GET {url}")
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as out:
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        while True:
            buf = resp.read(1 << 20)  # 1 MB
            if not buf:
                break
            out.write(buf)
            done += len(buf)
            if total:
                print(f"\r  descargando {done/1e6:6.0f} / {total/1e6:.0f} MB", end="")
    print()
    return dest


def _unzip_csv(zip_path: Path, out_dir: Path) -> Path:
    """Extrae el unico CSV del zip de NOAA y devuelve su ruta."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csvs:
            raise RuntimeError(f"No hay CSV dentro de {zip_path.name}")
        name = csvs[0]
        zf.extract(name, out_dir)
    return out_dir / name


def _csv_to_parquet(csv_path: Path, parquet_path: Path) -> int:
    """Convierte CSV->Parquet por lotes (RAM acotada). Devuelve nº de filas.

    Tipa explicitamente las columnas criticas (schema.BRONZE_COLUMN_TYPES) e
    infiere el resto. Comprime con zstd.
    """
    convert = pacsv.ConvertOptions(
        column_types=schema.BRONZE_COLUMN_TYPES,
        timestamp_parsers=schema.TIMESTAMP_PARSERS,
        strings_can_be_null=True,
    )
    read = pacsv.ReadOptions(block_size=64 << 20)  # lotes de ~64 MB
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    reader = pacsv.open_csv(csv_path, read_options=read, convert_options=convert)
    writer: pq.ParquetWriter | None = None
    rows = 0
    try:
        for batch in reader:
            if writer is None:
                writer = pq.ParquetWriter(parquet_path, batch.schema, compression="zstd")
            writer.write_batch(batch)
            rows += batch.num_rows
    finally:
        if writer is not None:
            writer.close()
        reader.close()
    return rows


def _bronze_key(snapshot_id: str, source: str, parquet_name: str) -> str:
    """Layout: bronze/source=<src>/snapshot=<id>/region=national/<archivo>.parquet"""
    return f"bronze/source={source}/snapshot={snapshot_id}/region=national/{parquet_name}"


def run(
    snapshot_id: str,
    config_path: str | Path | None = None,
    upload: bool = True,
    workdir: str | Path | None = None,
    keep_intermediate: bool = False,
) -> dict[str, Any]:
    """Ejecuta la ingesta de un snapshot. Punto de entrada que invoca el DAG.

    upload=False: hace todo en local (util para probar sin credenciales AWS).
    Devuelve el manifest (tambien lo sube a S3 si upload=True).
    """
    cfg, snap = config.snapshot(snapshot_id, config_path)
    source = snap["source"]
    root = Path(workdir) if workdir else config.REPO_ROOT / "data"
    stage = root / "bronze" / snapshot_id

    client = None
    if upload:
        aws = cfg["aws"]
        client = io_s3.get_client(aws["region"], aws.get("profile"))
        if not io_s3.bucket_exists(client, aws["bucket"]):
            raise RuntimeError(
                f"El bucket '{aws['bucket']}' no existe o no hay acceso. "
                f"Corre primero: python scripts/bootstrap_s3.py"
            )

    files_manifest = []
    for date in snap["dates"]:
        url = noaa_url(date)
        zip_path = stage / f"AIS_{date}.zip"
        parquet_name = f"AIS_{date.replace('-', '_')}.parquet"
        parquet_path = stage / parquet_name

        print(f"[{date}] descarga")
        _download(url, zip_path)
        print(f"[{date}] descomprime")
        csv_path = _unzip_csv(zip_path, stage)
        print(f"[{date}] CSV -> Parquet (streaming)")
        rows = _csv_to_parquet(csv_path, parquet_path)
        sha = io_s3.sha256_file(parquet_path)
        size = parquet_path.stat().st_size
        print(f"[{date}] {rows:,} filas | {size/1e6:.0f} MB parquet | sha256={sha[:12]}...")

        entry = {
            "date": date,
            "parquet": parquet_name,
            "rows": rows,
            "bytes": size,
            "sha256": sha,
            "source_url": url,
        }

        if upload and client is not None:
            key = _bronze_key(snapshot_id, source, parquet_name)
            uri = io_s3.upload_file(client, parquet_path, cfg["aws"]["bucket"], key)
            entry["s3_uri"] = uri
            print(f"[{date}] subido -> {uri}")

        files_manifest.append(entry)

        if not keep_intermediate:  # Bronze = parquet; el zip/csv son regenerables
            for tmp in (zip_path, csv_path):
                tmp.unlink(missing_ok=True)

    manifest = {
        "snapshot_id": snapshot_id,
        "source": source,
        "kind": snap.get("kind"),
        "dates": snap["dates"],
        "bbox": snap.get("bbox"),
        "schema_version": snap.get("schema_version", 1),
        "downloaded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "files": files_manifest,
    }

    # manifest local siempre
    manifest_local = stage / "manifest.json"
    manifest_local.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"manifest -> {manifest_local}")

    if upload and client is not None:
        mkey = f"bronze/source={source}/snapshot={snapshot_id}/manifest.json"
        io_s3.put_json(client, cfg["aws"]["bucket"], mkey, manifest)
        print(f"manifest -> {io_s3.s3_uri(cfg['aws']['bucket'], mkey)}")

    return manifest


def _cli() -> None:
    ap = argparse.ArgumentParser(description="Ingesta NOAA AIS -> Bronze (S3).")
    ap.add_argument("--snapshot", required=True, help="snapshot ID de config/snapshots.yml")
    ap.add_argument("--config", default=None, help="ruta alternativa a snapshots.yml")
    ap.add_argument("--no-upload", action="store_true", help="solo local, sin subir a S3")
    ap.add_argument("--workdir", default=None, help="carpeta de staging (def: ./data)")
    ap.add_argument("--keep-intermediate", action="store_true",
                    help="no borrar el zip/csv tras convertir a Parquet")
    args = ap.parse_args()
    run(args.snapshot, config_path=args.config, upload=not args.no_upload,
        workdir=args.workdir, keep_intermediate=args.keep_intermediate)


if __name__ == "__main__":
    _cli()
