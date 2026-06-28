# Modelo ETA — resultados (Sprint 4)

Snapshot: `snap_2024-01-w3_laxlb_v1` · ventana K=16 · 20 epocas · split por buque · target log1p + Huber.

MAE en **test** (buques nunca vistos), en minutos:

| Modelo | MAE (min) | Mejora vs naive |
|---|---:|---:|
| naive_fisico | 136.4 | 1.00x |
| hist_gbm | 96.0 | 1.42x |
| lstm | 93.9 | 1.45x |

Scatter predicho vs real: `docs/eta_model_eval.png`.

## Limitaciones y mejoras

El scatter muestra **bandas horizontales**: el modelo predice casi una constante para entradas casi identicas cuyo ETA real varia mucho. Causa principal: **buques fondeados esperando turno** -- su cinematica (quieto, SOG~0) es identica ping tras ping mientras el ETA real cuenta atras. Ese tiempo de cola NO esta en los datos AIS de posicion, asi que cualquier modelo choca con ese techo (no es un bug).

Mejoras (features que distingan los casos hoy indistinguibles):
1. **Tiempo esperando**: minutos desde que el buque bajo de ~1 nudo (la ventana K=16 solo ve ~16 min; barato y probablemente el de mayor impacto).
2. **Congestion del puerto**: nº de buques en darsena/cola en ese instante.
3. **Campo destino/ETA reportado en AIS** (mensajes estaticos; ruidoso pero util).
4. **Mas datos (1 mes)** y **distancia al borde** del poligono (no al centroide).