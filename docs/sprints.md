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
| 3 | Features → Gold (geopandas + H3) | indexado hexagonal H3, target ETA | **completado** ✅ |
| 4 | Modelo ETA (LSTM) | redes sobre secuencias (regresión) | **completado** ✅ |
| 5 | Buques oscuros (gaps + IsolationForest) | detección de anomalías; validación sintética | **completado** ✅ |
| 6 | Visualización (pydeck/deck.gl HTML) | mapa H3 3D offline para la demo | **completado** ✅ |
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

## Sprint 3 — Definition of Done
- [x] Poligono de puerto data-driven, congelado: `scripts/build_port_polygon.py` -> `config/port_laxlb.geojson`.
- [x] `features.py` (`run()`): Silver -> Gold con geopandas (point-in-polygon) + H3 (res 7).
- [x] Features: `dist_to_port_km`, `bearing_to_port`, `inside_port`, `h3_cell`, cinematica.
- [x] Target `eta_min` (merge_asof a la proxima entrada a darsena) + `has_eta` (horizonte 12 h).
- [x] Gold particionado por `h3_res`/`date` en local + S3; reporte + histograma del target.

**Resultado:** 1.58 M pings; 3.025 llegadas; **111.727 muestras etiquetadas** (<12 h);
ETA mediana ~107 min. Decisiones: llegada=darsena (poligono), H3 res7, sin remuestreo.

## Sprint 4 — Definition of Done
- [x] `model_eta.py` (`run()`): secuencias K=16 por buque, split por buque sin fuga (70/15/15).
- [x] Baselines: fisico ingenuo (dist/SOG) + HistGradientBoosting.
- [x] LSTM (PyTorch CPU): target log1p(eta) + Huber; mejor epoca por val; artefacto a S3.
- [x] Evaluacion en test (buques nunca vistos) + scatter; reporte verificable.

**Resultado (MAE test):** naive 136 min -> GBM 96 -> **LSTM 93.9** (1.45x vs naive).
Limitacion diagnosticada: el tiempo de cola en fondeadero no esta en la cinematica.
Mejoras: mas datos (1 mes), feature de distancia-al-borde del poligono, mas buques.

## Sprint 5 — Definition of Done
- [x] `detect_dark.py` (`run()`): extraccion de gaps (DuckDB) sobre la semana NACIONAL.
- [x] Detector: reglas (silencio>=2h + movimiento + dist>=5km) + IsolationForest.
- [x] Validacion por inyeccion sintetica de apagones (recall). NO usa LSTM.
- [x] Capa de salida local + S3 (`dark/snapshot=.../dark_events.parquet`) + mapa nacional.

**Resultado:** 169.897 gaps candidatos -> 5.971 buques oscuros (regla|iso); recall sintetico **74%**.
**Pendiente (bonus):** validacion con GFW (token + congelar en S3; ground truth puede salir ralo).

## Sprint 6 — Definition of Done
- [x] Decision de stack revisada: Streamlit -> **pydeck/deck.gl** (kepler.gl no instala en 3.14).
- [x] `viz.py` (`run()`): genera HTML autocontenidos con datos embebidos (deck.gl por CDN).
- [x] `app/port_map.html`: hexagonos H3 (altura=trafico, color=ETA medio) + poligono del puerto.
- [x] `app/dark_map.html`: mapa nacional de apagones (tamano/color = duracion del silencio).

**Nota:** kepler.gl descartado por wheels (build fija pyarrow viejo). pydeck = mismo motor deck.gl.
