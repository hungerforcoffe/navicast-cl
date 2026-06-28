# Fallback / atajos de cada etapa (para que un DAG roto no bloquee la demo).
# En Windows el python del venv esta en .venv/Scripts; en Linux/Mac en .venv/bin.
# Si no tienes 'make' en Windows, usa los comandos equivalentes del README.

PY := .venv/Scripts/python.exe   # Linux/Mac: .venv/bin/python
SNAP ?= snap_2024-01-15_noaa_national_v1

.PHONY: setup bootstrap ingest ingest-local

setup:                ## crea venv e instala el paquete (core)
	python -m venv .venv
	$(PY) -m pip install -U pip
	$(PY) -m pip install -e .

bootstrap:            ## crea el bucket S3 con Versioning
	$(PY) scripts/bootstrap_s3.py

ingest:               ## descarga NOAA -> Bronze (S3)
	$(PY) -m navicast.ingest --snapshot $(SNAP)

ingest-local:         ## descarga NOAA -> Bronze (solo local, sin S3)
	$(PY) -m navicast.ingest --snapshot $(SNAP) --no-upload
