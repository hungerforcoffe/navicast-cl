# NaviCast-CL — Contexto del proyecto

> Archivo de contexto para Claude Code. Es la "constitución" del proyecto: reglas
> estables y decisiones tomadas. No es documentación exhaustiva. Mantener < 200 líneas.

## Qué es
Proyecto final de un curso de Big Data. Pipeline geoespacial sobre datos AIS que:
1. Ingiere datos AIS masivos.
2. Reconstruye y limpia trayectorias de buques.
3. Predice el ETA a puerto con una red neuronal (LSTM).
4. Detecta anomalías de "apagón" de transpondedor (gaps sospechosos / buques oscuros).

Enfoque geográfico: costa de Chile / Pacífico Sur (ver decisión abierta #1).
Una sola persona, laptop (sin clúster), entregable presentable.

## Perfil del autor (calibra el tono a esto)
- Analista de datos: Python (pandas, NumPy, scikit-learn, Matplotlib), SQL, Git, Linux.
- Background en geoespacial y series temporales irregulares (astronomía). Nivel intermedio-avanzado.
- Prefiere recomendaciones directas y trazas de ejecución paso a paso, no menús de opciones.

## Restricciones NO negociables
- **Reproducibilidad por snapshots congelados.** NUNCA llamar a una API en vivo dentro
  del pipeline ni en la demo. Todo lee de Parquet congelado en S3.
- **Herramientas a lucir** (el curso las valora): DuckDB/Polars out-of-core con benchmark
  explícito vs pandas; AWS S3 + Boto3; geopandas + H3; LSTM.
- **Hardware limitado:** nada que exija clúster. Streaming/lazy para no reventar la RAM.

## Arquitectura (medallion, todo en Parquet sobre S3)
Columna izquierda = cómputo en laptop; columna derecha = capas S3.

- Ingesta (laptop, descarga batch puntual)  → Bronze (crudo inmutable)
- Limpieza (DuckDB + Polars lazy)            → Silver (limpio)
- Features (geopandas + H3)                  → Gold (features / ETA-ready)
- Modelado (LSTM ETA + detección de gaps)
- Visualización (Streamlit + mapa H3, lee Gold, offline)

## Decisiones de stack VALIDADAS
- **Motor principal:** DuckDB (SQL out-of-core sobre Parquet, lee S3 vía httpfs) +
  Polars (lazy, trayectorias agrupadas por buque/MMSI). FireDucks = 4ª barra opcional
  del benchmark (drop-in `import fireducks.pandas as pd`), solo "nice to have".
- **Benchmark OBLIGATORIO:** misma operación pesada en pandas (lento/OOM) vs Polars vs
  DuckDB, midiendo wall-clock y pico de RAM. Es la prueba de la competencia Big Data.
- **ETA:** LSTM (secuencia de puntos AIS recientes → tiempo a puerto; regresión).
- **Buques oscuros:** análisis determinista de gaps + IsolationForest/reglas.
  NO usar LSTM aquí. El LSTM es EXCLUSIVO del ETA.
- **Orquestación:** Airflow vía Astro CLI (`astro dev start`), LocalExecutor — NUNCA Celery.
  Desacoplar lógica del orquestador: cada etapa es un módulo con `run()`; el DAG solo invoca.
  Mantener fallback `make` / scripts numerados para que un DAG roto no bloquee la demo.
- **Almacenamiento:** AWS S3 real (free tier alcanza), con Versioning activado.

## Estrategia de datos
**Fuente primaria — NOAA Marine Cadastre** (AIS crudo de aguas US, referencia documentada):
- Formato: GeoParquet 2024 limpio en Azure blob, o CSV diario Zstd (desde 2015, 1 punto/min).
- Esquema: MMSI, lat/lon, SOG, COG, heading, timestamp, tipo de buque, eslora, manga, calado.
- Centinelas a tratar como nulos: `SOG == 102.3`, `COG == 360.0`.
- MMSI es reutilizado/spoofable → identidad estable = MMSI + IMO + Call Sign.

**GFW (Global Fishing Watch):** SOLO ground truth. Su descarga viene agregada (1 posición
por buque por hora), inútil como fuente cruda. Usar su Events API (AIS-disabling events)
para validar el detector de buques oscuros.

**Chile (stretch / "nice to have"):** grabar bbox de la costa central vía aisstream.io y
congelar un snapshot. Coverage más rala cerca de Chile; cuesta semanas de grabación.

**Recorte para laptop:**
- Benchmark: 1 archivo diario nacional de NOAA sin clipear (~1.5–3 GB) → rompe pandas.
- Modelado: clip a UNA aproximación portuaria + 1 mes.
  - Default (NOAA): LA/Long Beach, bbox lon[-118.6, -117.8] × lat[33.4, 34.0].
  - Si Chile: Valparaíso+San Antonio, bbox lon[-72.5, -71.0] × lat[-34.5, -32.5], 2–4 semanas.

## Versionado de snapshots (S3)
- Bucket con Versioning ON. Snapshot ID inmutable (ej. `snap_2024-03_laxlb_v1`) fijado en
  config; TODO el pipeline y la demo leen ese ID.
- Layout:
  ```
  s3://navicast-cl/bronze/source=<src>/snapshot=<id>/*.parquet
                  /silver/snapshot=<id>/date=<d>/*.parquet
                  /gold/snapshot=<id>/h3_res=<r>/*.parquet
  ```
- `manifest.json` por snapshot: fuente, rango de fechas, bbox, nº de filas, sha256 de cada
  archivo, timestamp de descarga, versión de esquema.
- Particionar para partition pruning: bronze por source/snapshot/region; silver/gold por date y h3_res.

## Layout de repo sugerido
```
navicast-cl/
├── CLAUDE.md
├── Makefile                 # fallback / atajos de cada etapa
├── pyproject.toml
├── config/snapshots.yml     # snapshot IDs, bboxes, rutas S3
├── src/navicast/
│   ├── ingest.py            # run()
│   ├── clean.py             # run()
│   ├── features.py          # run()
│   ├── model_eta.py         # LSTM
│   ├── detect_dark.py       # gaps + IsolationForest
│   └── common/              # io_s3.py, h3utils.py, schema.py
├── dags/navicast_dag.py     # invoca src/navicast/*.run()
├── notebooks/               # iteración del LSTM
├── app/streamlit_app.py
└── docs/                    # architecture.md, sprints.md (cuando se definan)
```

## DECISIONES ABIERTAS (no asumir)
1. **Geografía:** NOAA-primario + Chile-stretch  VS  Chile-puro vía aisstream. Pablo aún
   no confirma. La elección cambia el recorte y la lista de problemas de calidad.
2. **Puntos 3–5 del plan aún sin definir** (NO empezar el pipeline completo sin ellos):
   (3) plan priorizado de limpieza AIS (gaps, saltos GPS, MMSI duplicados/spoofed, interpolación);
   (4) cronograma por sprints con entregables verificables y definition of done;
   (5) riesgos y plan B (versión reducida que aún aprueba con nota alta).

## Reglas de trabajo
- Validar decisiones de arquitectura con Pablo ANTES de escribir código.
- No sobre-ingenierizar: un MVP funcional y presentable supera a la perfección.
- Explicar el porqué de cada elección, no solo el qué.
