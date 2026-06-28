"""Esquema canonico de los archivos diarios AIS de NOAA Marine Cadastre.

Bronze guarda el dato CRUDO: aqui NO se anulan centinelas ni se limpia nada.
La conversion de centinelas a NULL y la limpieza ocurren en clean.py (Silver).

Identidad estable de un buque = MMSI + IMO + Call Sign, porque el MMSI solo es
reutilizable/spoofable.
"""
from __future__ import annotations

import pyarrow as pa

# Centinelas AIS que significan "sin dato" (se tratan como NULL en Silver, NO aqui).
SENTINELS: dict[str, float] = {"SOG": 102.3, "COG": 360.0}

# Identidad estable del buque (para deduplicar/desambiguar en Silver).
IDENTITY_KEYS: list[str] = ["MMSI", "IMO", "CallSign"]

# Columnas publicadas por NOAA en el CSV diario, en orden.
AIS_COLUMNS: list[str] = [
    "MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "Heading",
    "VesselName", "IMO", "CallSign", "VesselType", "Status",
    "Length", "Width", "Draft", "Cargo", "TransceiverClass",
]

# Tipos explicitos para las columnas criticas al convertir CSV->Parquet.
# El resto se infiere (robustez ante variaciones menores entre dias).
# Nota: usamos float64 en columnas que pueden venir vacias para que ""->NULL.
BRONZE_COLUMN_TYPES: dict[str, pa.DataType] = {
    "MMSI": pa.int64(),
    "BaseDateTime": pa.timestamp("s"),
    "LAT": pa.float64(),
    "LON": pa.float64(),
    "SOG": pa.float64(),
    "COG": pa.float64(),
    "Heading": pa.float64(),
    "Length": pa.float64(),
    "Width": pa.float64(),
    "Draft": pa.float64(),
}

# Formatos de timestamp que aparecen en los CSV de NOAA.
TIMESTAMP_PARSERS: list[str] = ["%Y-%m-%dT%H:%M:%S"]
