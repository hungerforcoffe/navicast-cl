# Ruta de aprendizaje por sprints

Orden de construcción del proyecto, pensado para aprender una competencia nueva por etapa.
Las dos primeras se pueden hacer **sin esperar** las decisiones abiertas del `CLAUDE.md`;
el resto del pipeline espera al cierre de esas decisiones.

| Sprint | Etapa | Qué aprendes | Estado |
|---|---|---|---|
| 0 | Cimientos: repo, S3 + Versioning, Boto3, NOAA → Bronze | S3 + Boto3, Parquet, capa Bronze | **completado** ✅ |
| 1 | Benchmark Big Data: pandas vs Polars vs DuckDB | out-of-core, lazy, medir RAM/tiempo | **completado** ✅ |
| — | **Compuerta:** decisiones #1 (geografía) y #2 (plan limpieza, sprints, plan B) | — | **cerrada** ✅ |
| 2 | Limpieza → Silver (DuckDB) | calidad AIS, clip, trayectorias | **completado** ✅ |
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

## Sprint 1 — Definition of Done
- [x] `benchmark.py`: misma operacion (reconstruccion de trayectorias) en pandas vs Polars vs DuckDB.
- [x] Medicion rigurosa: cada motor en subproceso aislado, pico de RSS via psutil, watchdog de presupuesto de RAM.
- [x] Verificacion de correccion (los motores coinciden en buques/puntos/km).
- [x] Resultados presentables: `docs/benchmark_results.md` + `docs/benchmark_bigdata.png`.

**Resultado (1 semana NOAA, 50.3 M filas, presupuesto 6 GB):**

| Motor | Wall-clock | Pico RAM |
|---|---:|---:|
| pandas | **OOM** (>6 GB) | reventó |
| polars | 9.5 s | 4.2 GB |
| duckdb | **7.5 s** | **2.3 GB** |

A 1 dia (7.3 M filas, sin tope) pandas sí termina pero usa 3.5x mas RAM que DuckDB (1416 vs 408 MB).
Conclusion: DuckDB = motor por defecto de Silver; Polars para la logica por buque (lazy groupby).

## Sprint 2 — Definition of Done
- [x] `clean.py` (`run()`): Bronze nacional -> Silver LA/Long Beach, plan P0-P2 en DuckDB.
- [x] P0 centinelas->NULL + clip bbox; P1 identidad + de-dup; P2 saltos GPS + marcado de gaps.
- [x] Silver particionado por fecha en local + S3 (`snap_2024-01-w3_laxlb_v1`).
- [x] Reporte verificable: `docs/silver_cleaning_report.md` + manifest con conteos por etapa.

**Resultado:** 50.3 M nacional -> 1.58 M en LA/LB (3.14%); 966 buques; ~30 MB en S3.
La interpolacion/resampling para el LSTM se hace en Gold (Sprint 3), no en Silver.
