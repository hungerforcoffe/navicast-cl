"""Utilidades H3 (Sprint 3)."""
from __future__ import annotations

from collections.abc import Iterable

import h3


def cells_for(lats: Iterable[float], lons: Iterable[float], res: int) -> list[str]:
    """Asigna celda H3 (string) a cada par (lat, lon) en la resolucion dada."""
    return [h3.latlng_to_cell(float(la), float(lo), res) for la, lo in zip(lats, lons)]
