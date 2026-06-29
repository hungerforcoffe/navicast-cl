# NaviCast-CL

Pipeline geoespacial AIS sobre arquitectura **medallion** en S3: ingesta → limpieza
(DuckDB/Polars) → features (geopandas/H3) → ETA con LSTM + detección de buques oscuros
→ visualización Streamlit. Ver [`CLAUDE.md`](CLAUDE.md) (constitución del proyecto) y
[`docs/sprints.md`](docs/sprints.md) (ruta por sprints).

## Estructura
```
src/navicast/        # una etapa por modulo, cada una con run()
  common/            # io_s3.py (Boto3), schema.py (AIS), config.py, h3utils.py
  ingest.py          # NOAA -> Bronze  (Sprint 0)  <-- implementado
  clean.py           # Bronze -> Silver (Sprint 2)
  features.py        # Silver -> Gold  (Sprint 3)
  model_eta.py       # LSTM ETA        (Sprint 4)
  detect_dark.py     # buques oscuros  (Sprint 5)
scripts/bootstrap_s3.py   # crea el bucket S3 con Versioning
config/snapshots.yml      # snapshot IDs, bucket, region
dags/ notebooks/ app/ docs/
```

## Puesta en marcha (Sprint 0)

### 1. Entorno
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -U pip
.venv\Scripts\python -m pip install -e ".[bigdata,geo,ml,detect,app]"
# PyTorch CPU (rueda dedicada, sin CUDA):
.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### 2. Credenciales AWS
boto3 usa la cadena estándar. La forma más simple sin AWS CLI: crear
`%USERPROFILE%\.aws\credentials` con
```
[default]
aws_access_key_id = TU_KEY
aws_secret_access_key = TU_SECRET
```
(o exportar `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` en la sesión).

### 3. Configurar destino
Edita `config/snapshots.yml` → `aws.bucket` (nombre **global-único**) y `aws.region`.

### 4. Crear bucket + ingerir
```powershell
.venv\Scripts\python scripts/bootstrap_s3.py
.venv\Scripts\python -m navicast.ingest --snapshot snap_2024-01-15_noaa_national_v1
# Probar sin AWS (solo local):
.venv\Scripts\python -m navicast.ingest --snapshot snap_2024-01-15_noaa_national_v1 --no-upload
```

### 5. Pipeline completo y mapas
```powershell
# todo el pipeline: Bronze -> Silver -> Gold -> ETA -> buques oscuros -> mapas
.venv\Scripts\python scripts/run_pipeline.py --skip-ingest   # reusa el Bronze ya descargado
```
Etapas sueltas: `navicast.clean` / `.features` / `.model_eta` / `.detect_dark` / `.viz`.
Los mapas quedan en `app/port_map.html` y `app/dark_map.html` (abrir en el navegador).
Orquestación Airflow: `dags/navicast_dag.py` (vía Astro CLI `astro dev start` cuando tengas Docker).
Benchmark Big Data: `navicast.benchmark`. Mapas y reportes en `docs/`.

## Regla de oro
Reproducibilidad por **snapshots congelados**: todo lee un snapshot ID inmutable desde
`config/snapshots.yml`. Nunca se llama a una API en vivo dentro del pipeline ni en la demo.
