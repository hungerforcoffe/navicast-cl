# Ruta de aprendizaje por sprints

Orden de construcción del proyecto, pensado para aprender una competencia nueva por etapa.
Las dos primeras se pueden hacer **sin esperar** las decisiones abiertas del `CLAUDE.md`;
el resto del pipeline espera al cierre de esas decisiones.

| Sprint | Etapa | Qué aprendes | Estado |
|---|---|---|---|
| 0 | Cimientos: repo, S3 + Versioning, Boto3, NOAA → Bronze | S3 + Boto3, Parquet, capa Bronze | **completado** ✅ |
| 1 | Benchmark Big Data: pandas vs Polars vs DuckDB | out-of-core, lazy, medir RAM/tiempo | pendiente |
| — | **Compuerta:** decisiones #1 (geografía) y #2 (plan limpieza, sprints, plan B) | — | pendiente |
| 2 | Limpieza → Silver (DuckDB + Polars) | calidad AIS, identidad MMSI+IMO+CallSign | pendiente |
| 3 | Features → Gold (geopandas + H3) | indexado hexagonal H3 | pendiente |
| 4 | Modelo ETA (LSTM) | redes sobre secuencias (regresión) | pendiente |
| 5 | Buques oscuros (gaps + IsolationForest) | detección de anomalías; validar con GFW | pendiente |
| 6 | Visualización (Streamlit + mapa H3) | app offline para la demo | pendiente |
| 7 | Orquestación (Airflow/Astro, LocalExecutor) | DAG que solo invoca run() | pendiente |

## Por qué este orden
- **Sprints 0–1 van primero y no dependen de la geografía:** el benchmark usa el archivo
  nacional de NOAA **sin recortar**, así que sirve cualquiera sea la decisión #1.
- **La compuerta es deliberada:** la decisión #1 fija el bbox del recorte y la #2 define qué
  problemas de calidad ataca el Sprint 2. No arrancar Silver antes de cerrarlas.
- **Orquestación al final:** Airflow solo envuelve los `run()` ya escritos y probados.

## Sprint 0 — Definition of Done
- [x] Estructura de repo según el layout del `CLAUDE.md`.
- [x] `common/io_s3.py` (Boto3): crear bucket, versioning, upload/download, sha256.
- [x] `ingest.py`: NOAA → Parquet (streaming) → Bronze + `manifest.json`.
- [x] Bucket S3 `navicast-cl-pr2026` creado con Versioning (us-east-1).
- [x] 1 archivo diario nacional de NOAA ingerido y verificado en Bronze (2024-01-15: 7,284,415 filas, 192 MB parquet).
