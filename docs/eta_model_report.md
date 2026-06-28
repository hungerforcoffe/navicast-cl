# Modelo ETA — resultados (Sprint 4)

Snapshot: `snap_2024-01-w3_laxlb_v1` · ventana K=16 · 20 epocas · split por buque · target log1p + Huber.

MAE en **test** (buques nunca vistos), en minutos:

| Modelo | MAE (min) | Mejora vs naive |
|---|---:|---:|
| naive_fisico | 136.4 | 1.00x |
| hist_gbm | 96.0 | 1.42x |
| lstm | 93.9 | 1.45x |

Scatter predicho vs real: `docs/eta_model_eval.png`.