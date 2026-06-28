"""Helpers de S3 (Boto3). Unico lugar del proyecto que habla con AWS.

Credenciales: se resuelven por la cadena estandar de boto3 (variables de
entorno AWS_*, ~/.aws/credentials, o rol de instancia). NADA se hardcodea aqui.

Diseño: funciones puras que reciben un `client` ya creado, para que sean
faciles de testear y reutilizar desde ingest/bootstrap/clean.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

# Reintentos con backoff: las subidas grandes a veces fallan de forma transitoria.
_RETRY_CONFIG = Config(retries={"max_attempts": 5, "mode": "standard"})


def get_client(region: str, profile: str | None = None) -> BaseClient:
    """Crea un cliente S3. `profile` opcional para perfiles con nombre de ~/.aws."""
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    return session.client("s3", region_name=region, config=_RETRY_CONFIG)


def bucket_exists(client: BaseClient, bucket: str) -> bool:
    """True si el bucket existe y tenemos acceso."""
    try:
        client.head_bucket(Bucket=bucket)
        return True
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("404", "NoSuchBucket"):
            return False
        # 403 = existe pero es de otra cuenta / sin permiso -> propagar, no asumir.
        raise


def create_bucket(client: BaseClient, bucket: str, region: str) -> None:
    """Crea el bucket. Cuidado: us-east-1 NO admite LocationConstraint (rareza de la API)."""
    if region == "us-east-1":
        client.create_bucket(Bucket=bucket)
    else:
        client.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": region},
        )


def enable_versioning(client: BaseClient, bucket: str) -> None:
    """Activa Versioning (requisito no negociable del proyecto)."""
    client.put_bucket_versioning(
        Bucket=bucket,
        VersioningConfiguration={"Status": "Enabled"},
    )


def object_exists(client: BaseClient, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


def upload_file(
    client: BaseClient,
    local_path: str | Path,
    bucket: str,
    key: str,
    extra_args: dict[str, Any] | None = None,
) -> str:
    """Sube un archivo (boto3 hace multipart solo para archivos grandes). Devuelve la s3 URI."""
    client.upload_file(str(local_path), bucket, key, ExtraArgs=extra_args or {})
    return s3_uri(bucket, key)


def download_file(client: BaseClient, bucket: str, key: str, local_path: str | Path) -> Path:
    dest = Path(local_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(bucket, key, str(dest))
    return dest


def put_json(client: BaseClient, bucket: str, key: str, obj: Any) -> str:
    """Escribe un dict como JSON (p.ej. manifest.json del snapshot)."""
    body = json.dumps(obj, indent=2, ensure_ascii=False, default=str).encode("utf-8")
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
    return s3_uri(bucket, key)


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    """Hash sha256 leyendo por bloques (no carga el archivo entero en RAM)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def s3_uri(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"
