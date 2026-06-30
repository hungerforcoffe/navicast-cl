# NaviCast-CL — Plan de portafolio (pieza estrella para empleo)

> Fase NO técnica: convertir un pipeline que "corre en la laptop" en una pieza que un
> reclutador entiende en 5 minutos. Roles objetivo: data/BI en Chile, mediano plazo en
> **credit risk**, y remotos en inglés.
>
> **Progreso:** #0 ✅ repo público (github.com/hungerforcoffe/navicast-cl) ·
> #1 ✅ demo en vivo (**navicast-cl.streamlit.app**). Siguiente: **#2 README-producto**.

## Encuadre (no negociable)
- Es un **proyecto de curso** sobre datos de referencia (NOAA) a escala laptop. Se enmarca
  como **"pipeline end-to-end con decisiones de ingeniería justificadas"**, NO como
  inteligencia marítima de producción. Honestidad > sobreventa.
- No sobre-ingenierizar: priorizar lo que más mueve la aguja para empleo con el menor esfuerzo.

---

## 1. Inventario honesto del estado actual

### Pipeline (lo técnico está sólido)
| Etapa | Estado | Evidencia |
|---|---|---|
| 0 Ingesta NOAA → Bronze | ✅ completo | Parquet + manifest + sha256 en S3 |
| 1 Benchmark pandas/Polars/DuckDB | ✅ completo | tabla + figura; pandas OOM @6 GB, DuckDB 2.3 GB |
| 2 Limpieza → Silver (DuckDB) | ✅ completo | clip LA/LB, P0–P2, 1.58 M filas en S3 |
| 3 Features → Gold (geopandas+H3) | ✅ completo | target ETA, 111.727 muestras |
| 4 ETA (LSTM + baselines) | ✅ funciona | MAE test 93.9 min (modesto, **bien diagnosticado**) |
| 5 Buques oscuros (gaps+IsolationForest) | ✅ completo | recall sintético 74% |
| 6 Visualización (pydeck/deck.gl) | ✅ completo | 3 mapas HTML (locales, **gitignored**) |
| 7 Orquestación (DAG + run_pipeline + Makefile) | ✅ código | Airflow-real requiere Docker (no levantado) |
| Extensión Chile (GFW SAR + AIS + cruce) | ✅ stretch hecho | mapa + watchlist (8 dark), monitor DAG |

**Veredicto técnico:** completo y coherente. El trabajo difícil ya está.

### Presentabilidad (aquí está el trabajo de esta fase)
| Aspecto | Estado hoy |
|---|---|
| **Repo en GitHub** | ❌ **solo local, sin remoto** (un reclutador no puede verlo) |
| **Demo público** | ❌ mapas HTML locales y gitignored; sin link clickeable |
| **README** | 🟡 funcional pero en **español**, orientado a *setup*; sin diagrama, sin screenshots, sin números, sin narrativa "qué/por qué"; dice "Streamlit" (desactualizado: hoy es pydeck) |
| **Resultados visibles** | ❌ benchmark, MAE, recall **enterrados** en `docs/` |
| **Tests / CI** | ❌ ninguno |
| **Reproducibilidad** | 🟡 excelente para ti (snapshots + manifest + S3 versioning) **pero** la data vive en un **bucket S3 privado** → nadie externo puede correrlo/verlo |
| **Docs internas** | 🟢 fuertes (`sprints.md`, reportes) pero en español y dev-facing |

---

## 2. Gaps: "corre en mi laptop" → "pieza de 5 minutos"

1. **No hay demo público** — lo primero que quiere ver un reclutador (que funcione, sin instalar nada).
2. **README no es producto** — sin diagrama, screenshots, números de un vistazo, ni narrativa; en español.
3. **Resultados invisibles** — los logros (50 M filas, pandas OOM vs DuckDB 2.3 GB, MAE, recall 74%) no se ven sin escarbar.
4. **Sin tests/CI** — señal de rigor que un revisor técnico busca.
5. **Data privada** — la demo necesita un **snapshot público slim** para ser reproducible/visible.
6. **Sin traducción a empleo** — falta el "¿y esto para qué sirve en un rol de datos/credit risk?".
7. **Repo no publicado** — prerrequisito de todo lo anterior.

---

## 3. Plan de alcance (priorizado por impacto-empleo / esfuerzo)

> Esfuerzo: **S** ≤ ½ día · **M** ~1 día · **L** 2+ días.

### #0 · Prerrequisito — Repo público en GitHub  `[MVP · S]`
- **Entregable:** repo público en GitHub, historia limpia, sin secretos.
- **DoD:** URL pública; verificado que `.aws`/`.gfw`/`data/`/`.venv` NO están; README renderiza; `git log` presentable.
- **Dependencias:** ninguna. **Bloquea todo lo demás.**
- **Nota:** revisar que ningún token/credencial se haya colado (están fuera del repo y en `.gitignore`, pero se verifica).

### #1 · Deploy público del dashboard  `[MVP · L]`  ← lo que más mueve la aguja
- **Qué:** app **Streamlit** en **Community Cloud** (o HF Spaces) que **hospeda** los mapas pydeck
  ya hechos (`st.pydeck_chart`) + los números clave + la watchlist dark.
  *Reconciliación con la decisión previa:* dejamos Streamlit como **shell de hosting gratis**;
  el "look" sigue siendo deck.gl. (Alternativa más barata si el tiempo aprieta: publicar los
  HTML estáticos en GitHub Pages / HF — pero pierde la narrativa alrededor.)
- **Sub-dependencia clave:** **snapshot público slim.** La app NO puede usar el S3 privado.
  Se pre-computan los agregados que los mapas necesitan (H3 Gold ~574 celdas, ~6 k eventos dark,
  Chile SAR/AIS reducido) → **se versionan en el repo** (pocos cientos de KB) → la app los lee.
  Esto además vuelve la demo reproducible.
- **Entregable:** link estable + **GIF/video corto** (30–60 s) para audiencia no técnica.
- **DoD:** la URL carga en <10 s, sin credenciales, muestra los 3 mapas + benchmark + ETA + watchlist;
  GIF grabado; link en el README.
- **Dependencias:** #0; snapshot slim; (idealmente) screenshots para #2.

### #2 · README como producto (en inglés)  `[MVP · M]`
- **Entregable:** README en inglés con: (a) párrafo **"what I built & why"** + encuadre honesto;
  (b) **diagrama de arquitectura** (medallion + loop de monitoreo) como imagen; (c) **tabla del
  benchmark** (wall-clock + pico de RAM: pandas OOM vs Polars 4.2 GB vs DuckDB 2.3 GB);
  (d) **screenshots** de los mapas; (e) **link a la demo**; (f) resultados de un vistazo
  (50 M filas, MAE ETA, recall 74%); (g) cómo correr (condensado); (h) stack + atribución GFW.
- **DoD:** un reclutador no técnico entiende qué/por qué/resultados en <5 min; un ingeniero ve
  el stack y las decisiones; renderiza bien en GitHub; corrige el "Streamlit" stale.
- **Dependencias:** #1 (screenshots/diagrama exportado a PNG/SVG/mermaid). Casi todo el material ya existe.

### #3 · Traducción a empleo  `[MVP · S]`
- **Entregable:** `docs/cv-and-interview.md` con: (a) **4–6 bullets de CV cuantificados**;
  (b) **guion de entrevista** que tienda el puente explícito **buques oscuros (IsolationForest
  sobre gaps en streams irregulares) → detección de fraude / early-warning de riesgo crediticio**
  (anomalías no supervisadas sobre series de comportamiento), + un "por qué" por cada decisión
  de ingeniería (DuckDB out-of-core, por qué NO LSTM para dark ships, split por buque sin fuga,
  reproducibilidad por snapshots).
- **DoD:** bullets cuantificados y relevantes al rol; el puente a credit risk es explícito y defendible.
- **Dependencias:** ninguna (tenemos todos los hechos).

### #4 · Writeup (LinkedIn / artículo)  `[nice-to-have · S–M]`
- **Entregable:** `docs/writeup-draft.md` (~600–900 palabras), **un** ángulo. Recomendado:
  *"por qué la detección de buques oscuros NO es un LSTM"* (contrarian, memorable, ideal para
  entrevista) — alternativa: el benchmark out-of-core. Con una figura y CTA al repo/demo.
- **DoD:** borrador publicable con gancho, la idea central, una figura y link.
- **Dependencias:** #1/#2 (para el link).

### #5 · Credibilidad de ingeniería — tests mínimos + CI  `[nice-to-have · S–M]`
- *(No estaba en tu lista; lo añado porque es un gap de rigor barato de cerrar.)*
- **Entregable:** un puñado de tests en `tests/` (URL NOAA, carga de config, esquema, haversine,
  lógica del cruce SAR↔AIS) + workflow de **GitHub Actions** + **badge** en el README.
- **DoD:** `pytest` verde local y en CI; badge visible.
- **Dependencias:** #0.
- **Por qué:** señal de rigor, sobre todo para roles remotos/eng-leaning. Mínimo, sin sobre-ingeniería.

### #6 · Stretches (OPCIONALES, baja prioridad)
| Stretch | Veredicto honesto |
|---|---|
| (a) Slice chileno vía **aisstream.io** | ❌ **callejón sin salida** — AIS terrestre ~0 cobertura en Chile (ya lo comprobamos). El path GFW satelital ya lo cubre. **Descartar.** |
| (b) Validación vs **AIS-disabling de GFW** (precision/recall) | 🟡 limitado: 0 eventos AIS-off en nuestra ventana chilena. La validación sintética (74%) ya cubre la metodología. Solo si se amplía a una región con eventos. **Bajo ROI.** |
| (c) **mini API FastAPI** para el ETA | 🟢 el stretch **más relevante** para empleo (skill de serving). ~½–1 día. **Opcional nice-to-have.** |

---

## 4. Secuencia recomendada

```
#0 GitHub (S)  →  #1 Deploy + snapshot slim (L)  →  #2 README inglés (M)  →  #3 CV/entrevista (S)
                                   └→ (en paralelo barato) #5 tests+CI (S-M)  →  #4 writeup (S-M)
```
- **Alcance acordado:** #0–#5 (núcleo #0–#3 ≈ 3–4 días + #4/#5 ≈ +1 día).
- **#6 stretches:** solo si sobra tiempo; (c) FastAPI es el único que recomiendo considerar.

## 5. Decisiones — VALIDADAS (2026-06-29)
1. **Host del demo:** ✅ **Streamlit Community Cloud** (hospeda los mapas pydeck + números + watchlist).
2. **Snapshot público:** ✅ **versionar agregados slim en el repo** (demo autocontenida y reproducible).
3. **Tests + CI (#5):** ✅ **incluido** en el alcance (rigor barato, badge verde).
4. **Writeup (#4):** ✅ ángulo **"por qué NO es un LSTM"**.
5. **GitHub:** repo **público** desde el inicio (#0).

**Alcance acordado: #0–#5** (todos). #6 stretches opcionales (solo FastAPI vale la pena considerar).
