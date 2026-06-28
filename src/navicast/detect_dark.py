"""Deteccion de buques oscuros (Sprint 5).

Analisis DETERMINISTA de gaps de transpondedor + IsolationForest/reglas.
NO usar LSTM aqui. Validacion contra la Events API de GFW (ground truth).
"""
from __future__ import annotations

from typing import Any


def run(snapshot_id: str, **kwargs: Any) -> dict:
    raise NotImplementedError("Sprint 5: gaps + IsolationForest; validar con GFW.")
