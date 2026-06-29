# Buques oscuros — reporte (Sprint 5)

Snapshot: `snap_2024-01-w3_noaa_national_v1`

| Metrica | Valor |
|---|---:|
| Gaps candidatos (>30 min) | 169,897 |
| Sospechosos por reglas | 4,493 |
| Anomalias IsolationForest | 3,398 |
| DARK (regla \| iso) | 5,971 |
| Recall sintetico | 74% (200 inyectados) |

Reglas: silencio >=2 h, buque en movimiento antes (SOG>=3), distancia >=5 km, velocidad implicita plausible (1-40 kn). Validacion por inyeccion sintetica de apagones en trazas reales. **GFW pendiente** como bonus.

Mapa: `docs/dark_ships_map.png`.