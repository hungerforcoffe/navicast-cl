"""Carga de config/snapshots.yml.

Un unico punto que resuelve la ruta del config y devuelve la definicion de un
snapshot. Asi el resto del codigo no hardcodea rutas ni IDs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# este archivo: src/navicast/common/config.py -> raiz del repo = parents[3]
REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "config" / "snapshots.yml"


def load(path: str | Path | None = None) -> dict[str, Any]:
    """Devuelve el YAML completo como dict."""
    p = Path(path) if path else CONFIG_PATH
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def snapshot(snapshot_id: str, path: str | Path | None = None) -> tuple[dict, dict]:
    """Devuelve (config_completo, definicion_del_snapshot).

    Lanza KeyError si el snapshot_id no existe en el YAML.
    """
    cfg = load(path)
    snaps = cfg.get("snapshots", {})
    if snapshot_id not in snaps:
        disponibles = ", ".join(snaps) or "(ninguno)"
        raise KeyError(f"snapshot '{snapshot_id}' no esta en {CONFIG_PATH}. Disponibles: {disponibles}")
    return cfg, snaps[snapshot_id]
