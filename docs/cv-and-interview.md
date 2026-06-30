# NaviCast-CL — CV bullets y guion de entrevista

> Material para postular a roles **data/BI (Chile)**, mediano plazo **credit risk**, y
> **remotos en inglés**. Números reales del proyecto. Encuadre honesto: proyecto de curso
> sobre datos de referencia a escala laptop; el valor son las **decisiones de ingeniería**.
> Repo: github.com/hungerforcoffe/navicast-cl · Demo: navicast-cl.streamlit.app

---

## 1. CV bullets — English

- Built an **end-to-end geospatial data pipeline** (medallion: Bronze→Silver→Gold on **AWS S3**)
  processing **50M+ AIS records**, with frozen, versioned snapshots for full reproducibility.
- Benchmarked **pandas vs Polars vs DuckDB** on a 50M-row workload: out-of-core engines ran in
  **2.3 GB where pandas OOM'd** at a 6 GB budget (~3× less memory, no cluster) — measured
  wall-clock and peak RAM in isolated subprocesses.
- Engineered a leak-free ML dataset (**geopandas + H3** spatial indexing) and trained an **LSTM**
  for vessel ETA-to-port: **94-min MAE on unseen vessels** (by-vessel split), 1.45× better than a
  physics baseline; diagnosed the model's limits honestly.
- Built an **unsupervised anomaly-detection system** (**IsolationForest** + deterministic rules)
  over irregular event streams to flag suspicious "dark" behavior; **validated at 74% recall via
  synthetic injection** — directly transferable to fraud / credit early-warning.
- **Fused satellite radar (Sentinel-1 SAR) with AIS** to surface non-broadcasting vessels
  (multi-source cross-reference) and scheduled the monitoring loop with **Airflow**.
- Shipped a **public, reproducible Streamlit + deck.gl dashboard**; decoupled each pipeline stage
  (`run()` per module) with an Airflow DAG and a `make`/script fallback.

## 2. CV bullets — Español

- Construí un **pipeline de datos geoespacial de punta a punta** (medallion Bronze→Silver→Gold en
  **AWS S3**) procesando **50M+ registros AIS**, con snapshots congelados y versionados para
  reproducibilidad total.
- Comparé **pandas vs Polars vs DuckDB** sobre 50M filas: los motores out-of-core corrieron en
  **2.3 GB donde pandas se quedó sin memoria** (presupuesto 6 GB) — ~3× menos RAM, sin clúster;
  medí wall-clock y pico de memoria en subprocesos aislados.
- Diseñé un dataset de ML sin fuga de datos (**geopandas + H3**) y entrené un **LSTM** para el ETA
  a puerto: **MAE 94 min en buques nunca vistos** (split por buque), 1.45× mejor que un baseline
  físico; con diagnóstico honesto de sus límites.
- Construí un **detector de anomalías no supervisado** (**IsolationForest** + reglas) sobre flujos
  de eventos irregulares para marcar comportamiento sospechoso; **validado con 74% de recall por
  inyección sintética** — transferible a fraude / alerta temprana de riesgo.
- **Crucé radar satelital (Sentinel-1 SAR) con AIS** para detectar buques que no emiten
  (fusión multi-fuente) y agendé el monitoreo con **Airflow**.
- Publiqué un **dashboard Streamlit + deck.gl reproducible**; desacoplé cada etapa (`run()` por
  módulo) con un DAG de Airflow y un fallback `make`/scripts.

---

## 3. Pitch de 30 segundos

**ES:** "Construí un pipeline de datos de punta a punta sobre datos de tráfico marítimo (AIS):
ingesta a S3, limpieza out-of-core de 50 millones de filas con DuckDB, features geoespaciales,
un modelo de ETA y un detector de anomalías de 'buques oscuros'. Todo reproducible desde
snapshots congelados, con un dashboard público. Lo interesante no es el dominio marítimo, sino
las decisiones de ingeniería: por qué out-of-core, por qué no un LSTM para anomalías, cómo evité
fuga de datos, y cómo lo dejé reproducible."

**EN:** "I built an end-to-end data pipeline on vessel-tracking (AIS) data: S3 ingestion,
out-of-core cleaning of 50M rows with DuckDB, geospatial features, an ETA model, and a
'dark-ship' anomaly detector — all reproducible from frozen snapshots, with a public dashboard.
The point isn't the maritime domain; it's the engineering decisions behind each stage."

---

## 4. El puente a fraude / riesgo crediticio (la narrativa clave)

El detector de buques oscuros **es** un problema de **detección de anomalías no supervisada sobre
series de comportamiento irregulares** — exactamente la forma de muchos problemas de fraude y de
alerta temprana de riesgo crediticio. El mapeo es directo:

| NaviCast (buques oscuros) | Fraude / credit risk early-warning |
|---|---|
| Gap sospechoso en la emisión AIS de un buque | Patrón anómalo en el flujo de transacciones de un cliente / comportamiento de pago de un deudor |
| Features: duración del gap, velocidad, distancia, ubicación | Features: velocidad de transacciones, monto, hora, geo, ratio de uso |
| IsolationForest + reglas (híbrido) | Exactamente cómo operan los motores de fraude: reglas + ML no supervisado |
| **Sin etiquetas** → validación por **inyección sintética** (recall) | Fraude/default etiquetado es escaso → validación con datos sintéticos / weak labels, foco en **recall** |
| Salida = **watchlist** para revisión humana ("apparent") | Score para que un analista revise, no acción automática |
| Snapshots congelados + versioning = **auditable y reproducible** | Trazabilidad/auditoría: crítico en finanzas reguladas |

**Frase para la entrevista:** *"El mismo esqueleto —features de comportamiento sobre un stream
irregular, anomalía no supervisada, validación sin etiquetas y una watchlist para revisión— es el
que usaría para alerta temprana de mora o detección de fraude. Cambia el dominio, no el método."*

**EN one-liner:** *"Dark-ship detection is unsupervised anomaly detection on irregular behavioral
streams with scarce labels and a human-reviewed watchlist — the same skeleton as fraud detection
and credit early-warning. The domain changes; the method doesn't."*

---

## 5. Defensa de cada decisión de ingeniería (anticipa las repreguntas)

- **¿Por qué DuckDB/Polars y no pandas?** Porque lo medí: pandas revienta (OOM) con 50M filas a
  6 GB; DuckDB hace lo mismo en 2.3 GB. Es la diferencia entre "necesito un clúster" y "corre en
  una laptop". La decisión está respaldada por un benchmark, no por moda.
- **¿Por qué NO un LSTM para los buques oscuros?** Porque es otra clase de problema: detección de
  anomalías sin etiquetas, no regresión de secuencias. Un LSTM ahí sería sobre-ingeniería sin
  ganancia y menos interpretable. El LSTM lo reservé para el ETA, donde sí hay un target.
- **¿Por qué split por buque y no aleatorio?** Para evitar **fuga de datos**: si el mismo buque
  está en train y test, el modelo memoriza. Mido generalización a buques nuevos — el análogo a no
  filtrar un mismo cliente entre train y test en un modelo de riesgo.
- **¿Por qué snapshots congelados / versioning?** Reproducibilidad y **auditoría**: el pipeline lee
  un ID inmutable, nunca una API en vivo. (El versioning de S3 me salvó los datos tras una
  sobreescritura accidental.) En finanzas reguladas esto no es opcional.
- **¿Por qué documentas la limitación del ETA?** Porque saber qué un modelo **no** puede predecir
  (el tiempo de cola en fondeadero no está en la cinemática) es madurez, no debilidad. En riesgo,
  saber qué señales no son predictivas evita falsa confianza.

---

## 6. Preguntas probables + respuestas

- **"¿Es producción?"** → No, es un proyecto de curso sobre datos de referencia a escala laptop.
  Lo diseñé como si fuera a producción (etapas desacopladas, reproducibilidad, fallback), pero no
  lo sobrevendo como inteligencia marítima real.
- **"¿Qué fue lo más difícil?"** → Decidir bien con datos: el benchmark out-of-core, y diagnosticar
  por qué el ETA falla en fondeaderos (las bandas en el scatter) en vez de tapar el número.
- **"¿Qué harías distinto / a futuro?"** → Más datos (un mes) y un feature de 'tiempo esperando'
  para romper las bandas del ETA; una API FastAPI para servir el ETA; validar el detector contra
  ground truth real de GFW si la cobertura lo permite.
- **"¿Cómo escalarías esto?"** → Ya es out-of-core; el siguiente paso sería S3 + DuckDB/Polars sobre
  particiones más grandes y el DAG de Airflow corriendo en un scheduler real (Astro/Docker).

---

## 7. Encuadre honesto (qué NO decir)

- NO digas "sistema de inteligencia marítima en producción". SÍ: "pipeline end-to-end con
  decisiones de ingeniería justificadas, sobre datos de referencia".
- NO infles el ETA (94 min de MAE es modesto); preséntalo con su límite diagnosticado — eso suma
  credibilidad.
- SÍ enfatiza: reproducibilidad, out-of-core medido, anti-fuga, y el puente a anomalías/riesgo.
