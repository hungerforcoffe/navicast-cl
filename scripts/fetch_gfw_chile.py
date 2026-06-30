"""CLI: descarga GFW para Chile (SAR + presencia AIS + AIS-off).

La logica vive en navicast.monitor_chile (reutilizable por el DAG). Esto es solo el CLI.

Uso:
    python scripts/fetch_gfw_chile.py --start 2025-01-01 --end 2025-06-30 --s3
"""
from __future__ import annotations

import argparse

from navicast import monitor_chile


def main() -> None:
    ap = argparse.ArgumentParser(description="Descarga GFW (SAR + AIS-off) para Chile.")
    ap.add_argument("--start", default="2025-01-01", help="fecha inicio YYYY-MM-DD")
    ap.add_argument("--end", default="2025-06-30", help="fecha fin YYYY-MM-DD")
    ap.add_argument("--s3", action="store_true", help="subir a S3")
    args = ap.parse_args()
    dfs = monitor_chile.fetch(args.start, args.end, upload=args.s3)
    for name, df in dfs.items():
        print(f"{name}: {len(df)} filas")


if __name__ == "__main__":
    main()
