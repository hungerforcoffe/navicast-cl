# Benchmark Big Data — pandas vs Polars vs DuckDB

Operacion: reconstruccion de trayectorias (sort por MMSI+tiempo, haversine entre puntos consecutivos) sobre **7 archivo(s)** NOAA.

Tope de RAM por motor: **6 GB** (si lo supera -> matado y marcado OOM).

- filas: 50,272,290  buques: 21,616  km totales: 24,730,506
- Correccion: **OK (coinciden)**

| Motor | Wall-clock (s) | Pico RAM (MB) | Speedup vs pandas |
|---|---:|---:|---:|
| pandas | OOM | 6015 (>tope) | - |
| polars | 9.49 | 4233 | - |
| duckdb | 7.53 | 2294 | - |

> Pico de RAM = RSS del subproceso del motor (incluye ~base del interprete).
> OOM = supero el tope de RAM y fue interrumpido (no pudo con este volumen en RAM).