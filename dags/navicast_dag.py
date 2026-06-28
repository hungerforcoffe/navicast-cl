"""DAG de Airflow (Sprint 7) — placeholder.

Regla del proyecto: el DAG SOLO invoca los run() de cada etapa; nada de logica
de negocio aqui. Airflow via Astro CLI (LocalExecutor, NUNCA Celery).

Se activa en Sprint 7. Por ahora el pipeline se corre con scripts/Makefile para
que un DAG roto no bloquee la demo. Esqueleto previsto:

    from navicast import ingest, clean, features, model_eta, detect_dark
    # ingest.run(SNAP) >> clean.run(SNAP) >> features.run(SNAP) >> [model_eta.run, detect_dark.run]
"""
