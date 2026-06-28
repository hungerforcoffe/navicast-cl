"""Limpieza -> Silver (Sprint 2). DuckDB (SQL out-of-core) + Polars (lazy por MMSI).

Pendiente de la decision abierta #2 (plan priorizado de limpieza AIS):
centinelas SOG=102.3/COG=360 -> NULL, MMSI duplicado/spoofed, gaps, saltos GPS,
interpolacion. Identidad estable = MMSI+IMO+CallSign (ver common/schema.py).
"""
from __future__ import annotations

from typing import Any


def run(snapshot_id: str, **kwargs: Any) -> dict:
    raise NotImplementedError("Sprint 2: limpieza Bronze -> Silver (DuckDB + Polars).")
