"""DAG de vigilancia Chile (stretch): monitoreo agendado de buques oscuros.

Cada 3 dias, sobre una ventana movil de 30 dias:
    fetch GFW (SAR + presencia AIS + AIS-off) -> cruce SAR<->AIS -> mapa deck.gl.
El DAG SOLO invoca monitor_chile.run() (logica desacoplada).

Requisitos en el worker de Airflow: token GFW (env GFW_API_TOKEN) y credenciales AWS.
Datos (c) Global Fishing Watch, CC BY-NC 4.0 ('apparent').
"""
from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.decorators import dag, task


@dag(schedule=timedelta(days=3), start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
     catchup=False, tags=["navicast", "monitor", "chile"])
def navicast_monitor_chile():

    @task
    def monitor():
        from datetime import date, timedelta as td
        from navicast import monitor_chile
        end = date.today()
        start = end - td(days=30)   # ventana movil
        return monitor_chile.run(start=start.isoformat(), end=end.isoformat(),
                                 upload=True, make_map=True)

    monitor()


navicast_monitor_chile()
