"""NaviCast-CL: pipeline AIS (medallion en S3).

Cada etapa del pipeline es un modulo con una funcion run() para desacoplar la
logica del orquestador (Airflow solo invoca run()).
"""

__version__ = "0.1.0"
