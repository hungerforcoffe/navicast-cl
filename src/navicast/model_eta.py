"""Modelo de ETA (Sprint 4). LSTM: secuencia de puntos AIS recientes -> tiempo a puerto.

El LSTM es EXCLUSIVO del ETA (no se usa para buques oscuros). Framework a fijar
en Sprint 4 (recomendacion preliminar: PyTorch por soporte de wheels en Python 3.14).
"""
from __future__ import annotations

from typing import Any


def run(snapshot_id: str, **kwargs: Any) -> dict:
    raise NotImplementedError("Sprint 4: LSTM de ETA a puerto (regresion).")
