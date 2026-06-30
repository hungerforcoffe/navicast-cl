# Writeup — "Por qué los buques oscuros NO son un LSTM"

> Borrador para LinkedIn (ángulo: elegir el modelo correcto > el modelo de moda).
> Adjuntar `docs/dark_ships_map.png`. Demo: navicast-cl.streamlit.app ·
> Repo: github.com/hungerforcoffe/navicast-cl

---

## Versión en español (~450 palabras)

**Mi proyecto de datos tenía un LSTM entrenado. Para la parte más "sexy" —detectar buques
oscuros— decidí NO usarlo. Aquí el porqué, y por qué creo que importa para un rol de datos.**

Contexto: construí un pipeline end-to-end sobre datos AIS (tráfico marítimo). Una de las
tareas era detectar **"buques oscuros"**: barcos que apagan su transpondedor y desaparecen
de la vigilancia pública — a veces por mala cobertura, a veces a propósito.

La tentación obvia era tirarle deep learning: ya tenía un LSTM en el repo (lo usaba para
predecir el ETA a puerto). ¿Por qué no usarlo también aquí?

**Porque es otra clase de problema.** Detectar un apagón sospechoso es **detección de
anomalías no supervisada sobre un stream irregular**, no regresión de secuencias:

- **No hay etiquetas.** Nadie me dice "este gap fue malicioso". Un LSTM supervisado no tiene
  de dónde aprender. Un **IsolationForest + reglas** sí: aprende qué es "raro" sin etiquetas.
- **Interpretabilidad.** Un analista necesita saber *por qué* un barco está en la lista
  (silencio largo + en movimiento + lejos de puerto). Reglas + score de anomalía lo dan; un
  LSTM es una caja negra que nadie firmaría.
- **El LSTM tenía su lugar.** Lo reservé para el ETA, donde **sí** hay un target numérico.
  Usar la herramienta correcta para cada problema > usar la más llamativa en todo.

¿Resultado? Validé el detector con **inyección sintética** (borré tramos de trayectorias
reales y medí si los recuperaba): **74% de recall**. La salida no es una acusación, es una
**watchlist** para que un humano revise.

**Y aquí está el giro:** este esqueleto —features de comportamiento sobre un stream
irregular, anomalía no supervisada, validación sin etiquetas, watchlist para revisión— es
**exactamente** el de **detección de fraude** o **alerta temprana de riesgo crediticio**.
Cambia el dominio (transacciones en vez de barcos), no el método.

La lección que me llevo: a veces la decisión de ingeniería más madura es **no** usar el
modelo complejo. Saber *cuándo* un LSTM sobra dice más que saber entrenarlo.

🔗 Demo en vivo y repo en los comentarios.

#DataEngineering #MachineLearning #AnomalyDetection #DuckDB #Python

---

## English version (~430 words)

**My data project had a trained LSTM. For the flashiest part — detecting "dark ships" — I
chose NOT to use it. Here's why, and why I think it matters for a data role.**

I built an end-to-end pipeline on AIS (vessel-tracking) data. One task was spotting **"dark
ships"**: vessels that switch off their transponder and vanish from public tracking —
sometimes poor coverage, sometimes on purpose.

The obvious move was to throw deep learning at it: I already had an LSTM in the repo (for
predicting ETA to port). Why not reuse it here?

**Because it's a different class of problem.** Catching a suspicious blackout is
**unsupervised anomaly detection on an irregular stream**, not sequence regression:

- **No labels.** Nobody tells me "this gap was malicious." A supervised LSTM has nothing to
  learn from. **IsolationForest + rules** learns what's *unusual* without labels.
- **Interpretability.** An analyst needs to know *why* a vessel is flagged (long silence +
  underway + far from port). Rules + an anomaly score give that; an LSTM is a black box no
  one would sign off on.
- **The LSTM had its place.** I kept it for ETA, where there *is* a numeric target. Right
  tool per problem beats the fanciest tool everywhere.

The result: I validated the detector with **synthetic injection** (deleted segments of real
tracks and measured recovery): **74% recall**. The output isn't an accusation — it's a
**watchlist** for a human to review.

**Here's the twist:** this skeleton — behavioral features over an irregular stream,
unsupervised anomaly detection, label-free validation, a human-reviewed watchlist — is
**exactly** the one behind **fraud detection** and **credit-risk early-warning**. The domain
changes (transactions, not ships); the method doesn't.

My takeaway: sometimes the most senior engineering call is to **not** use the complex model.
Knowing *when* an LSTM is overkill says more than knowing how to train one.

🔗 Live demo and repo in the comments.

#DataEngineering #MachineLearning #AnomalyDetection #CreditRisk #Python

---

## Notas para publicar
- **Imagen:** adjunta `docs/dark_ships_map.png` (el mapa nacional de apagones) — visual y on-topic.
- **Comentario fijado:** links al demo (navicast-cl.streamlit.app) y al repo (no en el cuerpo,
  para no penalizar el alcance).
- **Encuadre honesto:** es un proyecto personal/de curso; el valor es la decisión, no el dominio.
- **Variante alternativa:** mismo formato pero con el ángulo del benchmark out-of-core
  (pandas OOM vs DuckDB 2.3 GB) si quieres rotar contenido.
