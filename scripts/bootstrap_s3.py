"""Crea el bucket S3 del proyecto con Versioning activado (idempotente).

Lee config/snapshots.yml (aws.bucket, aws.region). Requiere credenciales AWS en
el entorno: variables AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY, o ~/.aws/credentials.

Uso:
    python scripts/bootstrap_s3.py
"""
from __future__ import annotations

from navicast.common import config, io_s3


def main() -> None:
    cfg = config.load()
    aws = cfg["aws"]
    bucket, region, profile = aws["bucket"], aws["region"], aws.get("profile")

    if bucket.startswith("REEMPLAZAR"):
        raise SystemExit(
            "Edita config/snapshots.yml: pon un nombre de bucket global-unico en aws.bucket."
        )

    client = io_s3.get_client(region, profile)

    if io_s3.bucket_exists(client, bucket):
        print(f"Bucket ya existe: {bucket}")
    else:
        io_s3.create_bucket(client, bucket, region)
        print(f"Bucket creado: {bucket} ({region})")

    io_s3.enable_versioning(client, bucket)
    print("Versioning: Enabled")
    print("Listo. Ya puedes correr la ingesta.")


if __name__ == "__main__":
    main()
