# Atajos de cada etapa + pipeline completo (fallback del CLAUDE.md).
# En Windows el python del venv esta en .venv/Scripts; en Linux/Mac en .venv/bin.
# Si no tienes 'make' en Windows, usa los comandos equivalentes (ver README).

PY  := .venv/Scripts/python.exe       # Linux/Mac: .venv/bin/python
NAT ?= snap_2024-01-w3_noaa_national_v1
MOD ?= snap_2024-01-w3_laxlb_v1

.PHONY: setup bootstrap port-polygon ingest clean features model dark viz benchmark pipeline

setup:        ## crea venv e instala el paquete con todos los extras
	python -m venv .venv
	$(PY) -m pip install -U pip
	$(PY) -m pip install -e ".[bigdata,geo,ml,detect,app]"

bootstrap:    ## crea el bucket S3 con Versioning
	$(PY) scripts/bootstrap_s3.py

port-polygon: ## congela el poligono del puerto LA/LB en config/
	$(PY) scripts/build_port_polygon.py

ingest:       ## NOAA -> Bronze (semana nacional)
	$(PY) -m navicast.ingest --snapshot $(NAT)

clean:        ## Bronze -> Silver (clip LA/LB + limpieza)
	$(PY) -m navicast.clean --snapshot $(MOD)

features:     ## Silver -> Gold (H3 + target ETA)
	$(PY) -m navicast.features --snapshot $(MOD)

model:        ## entrena el LSTM de ETA + baselines
	$(PY) -m navicast.model_eta --snapshot $(MOD)

dark:         ## deteccion de buques oscuros (nacional)
	$(PY) -m navicast.detect_dark --snapshot $(NAT)

viz:          ## genera los mapas HTML (deck.gl)
	$(PY) -m navicast.viz

benchmark:    ## benchmark pandas vs Polars vs DuckDB
	$(PY) -m navicast.benchmark --path "data/bronze/$(NAT)/*.parquet"

pipeline:     ## pipeline completo sin Airflow (fallback)
	$(PY) scripts/run_pipeline.py
