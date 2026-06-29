"""DAG de Airflow (Sprint 7): orquesta el pipeline NaviCast-CL.

Regla del proyecto: el DAG SOLO invoca los run() de cada etapa (logica desacoplada).
Airflow via Astro CLI (`astro dev start`), LocalExecutor, NUNCA Celery.
Fallback sin Docker: `python scripts/run_pipeline.py` o el Makefile.

Flujo:
    ingest(NAT) ->┬-> clean(MOD) -> features(MOD) -> model_eta(MOD)
                  └-> detect_dark(NAT)
    [features, detect_dark] -> viz

Los import de navicast van DENTRO de cada task para que el parseo del DAG sea ligero
y no falle si una dependencia no esta disponible en tiempo de parseo. Para Astro,
instalar el paquete navicast en la imagen (requirements.txt del proyecto Astro).
"""
from __future__ import annotations

import pendulum
from airflow.decorators import dag, task

NAT = "snap_2024-01-w3_noaa_national_v1"   # nacional (benchmark + buques oscuros)
MOD = "snap_2024-01-w3_laxlb_v1"           # modelado LA/Long Beach (Silver/Gold/ETA)


@dag(schedule=None, start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
     catchup=False, tags=["navicast"])
def navicast_pipeline():

    @task
    def ingest_national():
        from navicast import ingest
        ingest.run(NAT)

    @task
    def clean_silver():
        from navicast import clean
        clean.run(MOD)

    @task
    def features_gold():
        from navicast import features
        features.run(MOD)

    @task
    def model_eta_train():
        from navicast import model_eta
        model_eta.run(MOD)

    @task
    def detect_dark_run():
        from navicast import detect_dark
        detect_dark.run(NAT)

    @task
    def viz_maps():
        from navicast import viz
        viz.run()

    ing = ingest_national()
    sil = clean_silver()
    gold = features_gold()
    dark = detect_dark_run()

    ing >> sil >> gold >> model_eta_train()
    ing >> dark
    [gold, dark] >> viz_maps()


navicast_pipeline()
