# Prompt para Copilot / ChatGPT — Análisis de Fraude Ecommerce
> Scotiabank Perú — Prevención de Fraude  
> Usar con el Excel generado por `analisis.py` (output/analisis_{COMERCIO}.xlsx)

---

## CÓMO USARLO

1. Completar los campos entre corchetes `[...]` con los datos del análisis actual
2. Adjuntar el Excel al chat
3. Usar el **PROMPT COMPLETO** con modelos Think (o3, Gemini 2.0 Deep Research, Claude Opus)
4. Usar el **PROMPT CORTO** si el modelo es GPT-4o o Copilot estándar (sin subida de archivo)

---

## PROMPT CORTO
*(Pegar junto con el Excel adjunto — modelos estándar)*

```
Eres un analista experto en prevención de fraude para banca retail.

CONTEXTO:
- Banco: Scotiabank Perú — Unidad de Prevención de Fraude
- Comercio analizado: [NOMBRE COMERCIO] (ecommerce, SIN autenticación 3DS)
- Periodo: [completar rango de fechas]
- Universo: [N total txn] txn | [N fraudes F] fraudes | Tasa global: [X]%
- El archivo Excel tiene 22 hojas de análisis de transacciones con tarjeta

INDICADORES EN LOS DATOS:
- F = Fraude confirmado | G = Buena (revisada y liberada) | N = Normal (sin revisar, 97%+ del volumen)
- D = Descarte | P = Pendiente
- TASA_F% = fraudes / total txn
- Daño colateral de una regla = afectación sobre N + G + D + P (no solo G)

VARIABLE SCORE — IMPORTANTE:
- Solo aplica a tarjeta de CRÉDITO (débito no tiene score de Monitor)
- Visa: escala 0 a 99 | Mastercard: escala 0 a 999
- NO comparar score Visa vs Mastercard directamente — escalas distintas
- Ver hoja 21_Score_Marca para la distribución y threshold scan por marca

CRITERIO PARA EVALUAR UNA REGLA:
- Ratio_F_vs_noFraude = % fraude capturado / % no-fraude afectado → buena regla si ≥ 3
- Precision% = fraudes / total bloqueado (mayor = mejor)
- Ver hoja 19_Recomendaciones para la efectividad calculada de cada flag

TU TAREA:
1. Analiza las 22 hojas del Excel adjunto
2. Identifica el vector principal de fraude — BINs, segmento, producto, patrón temporal
3. Redacta un informe estructurado: Resumen Ejecutivo → Perfil del Fraude → Patrón del Ataque → Reglas
4. Propón mínimo 2 reglas con umbrales específicos, justificadas con los datos del Excel
5. Indica qué variables NO discriminan en este comercio y por qué

FORMATO: informe profesional en español, con tablas y secciones claras.
```

---

## PROMPT COMPLETO CON CONTEXTO
*(Para modelos Think / o3 / Claude Opus — máximo detalle)*

```
Eres un analista senior de prevención de fraude en Scotiabank Perú.
Usas metodología de análisis de ecommerce no seguro (sin 3DS).

════════════════════════════════════════════════════════════
CONTEXTO DEL ANÁLISIS
════════════════════════════════════════════════════════════
Comercio: [NOMBRE COMERCIO]
Tipo: Ecommerce sin autenticación 3DS (fraude CNP — Card Not Present)
Periodo analizado: [completar con el rango de fechas del Excel]
Universo: [N total txn] transacciones | [N fraudes] fraudes | Tasa global: [X]%
Monto total fraude: S/ [completar]

Antigüedad del comercio:
- Periodo de búsqueda: [N meses]
- Meses con transaccionalidad real: [completar desde hoja 1_Resumen]
- Si meses activos < 50% del periodo buscado = comercio sospechoso
  (posible comercio creado para fraude o en fase de ataque inicial)

Indicadores del sistema Monitor (Scotiabank):
- F = Fraude confirmado por el analista
- G = Buena (analista revisó y liberó)
- N = Normal sin alerta — NO revisada por analista (es el 97%+ del volumen real)
- D = Descarte (descartada por criterio operativo)
- P = Pendiente de revisión
IMPORTANTE: al evaluar el impacto de una regla, el daño colateral
es F versus {N + G + D + P}, no solo versus G.

════════════════════════════════════════════════════════════
ESTRUCTURA DEL EXCEL (22 HOJAS)
════════════════════════════════════════════════════════════
1_Resumen:
  KPIs por mes (N txn, montos, tasa fraude). Ver tendencia mensual de tasa F%.
  Si la tasa sube mes a mes = ataque en escalada. Si es constante = endémico.

2_Por_Producto:
  TC (crédito) vs TD (débito). ¿Cuál tiene mayor tasa F%?
  Débito NO tiene score Monitor — las reglas de débito deben basarse en velocidad, BIN y monto.

3_Por_Segmento:
  Cruce por segmento cliente (Mass, Emerging Affluent, Affluent, etc.).
  Segmentos altos = montos mayores por fraude. Mass = mayor volumen.

4_Por_Marca:
  VISA vs MASTERCARD. Comparar tasa F% — si una marca tiene tasa 2x mayor,
  puede haber una brecha específica de esa red.

5_Por_ECI:
  Seguro (con 3DS) vs No Seguro (sin 3DS). En ecommerce no seguro, casi todo
  debería ser No Seguro. Si hay fraude en Seguro, es más sofisticado (bypass 3DS).

6_Por_BIN:
  Top 30 BINs por volumen y tasa de fraude. ANÁLISIS PRIORITARIO:
  - Listar BINs con tasa F% > 15% (umbral de alerta)
  - Para cada BIN caliente: cruzar con segmento, producto, rango de monto
  - BINs con muchas tarjetas distintas = posible card testing desde ese BIN
  - BIN identifica banco emisor, producto (TC/TD) y segmento sin variables adicionales

7_Cruce_Prod_Seg:
  Matriz Producto × Segmento. Buscar la celda con tasa F% más alta — ese es
  el vector principal (ej: "TC Affluent tiene tasa 18%").

8_Cruce_BIN_Prod:
  Matriz BIN × Producto. Confirma si los BINs calientes son TC o TD.

9_Velocidad:
  Dos sub-tablas:
  A) BUCKET_GAP: distribución de tiempo entre txn del mismo cliente.
     Si fraudes se concentran en ≤1min = ataque de bot o ráfaga.
     GAP largo (>60min) = fraude aislado, no ráfaga.
  B) Estadísticas de TRX_CLIENTE_5MIN/10MIN/1H/24H por indicador.
     Si F_mediana ≈ N_mediana = velocidad no discrimina bien en este comercio.
     Si F_mediana >> N_mediana = velocidad es el discriminador principal.
  NOTA: solo txn con GAP calculado aparecen en bucket (primera txn del cliente = NaN).

10_Monto_Acumulado:
  Variables MNT_CLIENTE_Xmin por indicador. Buscar en qué ventana temporal
  el monto acumulado de fraude difiere más del de normales.
  ACELERACION_MONTO > 2 = el defraudador escaló el monto en las últimas txn.

11_Estadisticas_Monto:
  Percentiles de monto por indicador. Comparar F_mediana vs N_mediana.
  Si F_mediana > N_mediana = fraude de montos altos.
  Si F_mediana < N_mediana = card testing con montos pequeños.

12_Deciles_Monto:
  Tasa fraude por decil (1=monto más bajo, 10=más alto).
  Sección A: deciles globales. Sección B: rangos del comercio.
  Sección C: árbol de decisión (cortes óptimos por monto).
  Sección D: cruces por BIN caliente. Sección E: interacciones monto × velocidad.
  Sección F: deciles filtrados por los BINs con mayor fraude.

13_Apertura_Decil10:
  Detalle del 10% de montos más altos. Si concentra mucho fraude, hay
  un ataque de montos altos. Si no, el fraude es de montos bajos-medios.

14_Motivos_Rechazo:
  CVV_FAIL: el defraudador tiene el número pero no el CVV → card testing.
  Muchos CVV_FAIL + txn aprobada posterior = cascada CVV activa.
  FONDOS_INSUF: puede ser agotamiento de saldo por fraude.

15_CVV_Tokenizadas:
  CVV dinámico vs estático. Si hay fraude con CVV dinámico = sofisticado.
  Tokenizadas con fraude = tarjeta comprometida enrolada en billetera digital.

16_Por_Pais:
  PE = local. Otros países = posible fraude transnacional.
  Si un país extranjero tiene TASA_F% > 20% con ≥5 fraudes = candidato a bloqueo por país.

17_Transac_Diaria:
  Bucket de txn por cliente por día (1 txn/día, 2 txn/día, etc.) × indicador.
  El bucket 2 txn/día suele concentrar el fraude en ataques de card testing sigiloso
  (el defraudador hace exactamente 2 intentos por tarjeta para no activar alertas de velocidad).
  Columnas: N_trx (total txn en ese bucket) y N_clientes (tarjetas únicas).

18_Perfil_Riesgo:
  Score compuesto 0–11 (suma de 11 flags de riesgo activos).
  Distribución por indicador y por perfil BAJO/MEDIO/ALTO/MUY_ALTO.
  Si F_media >> N_media en SCORE_RIESGO = el score discrimina bien.
  Si F_media ≈ N_media = el ataque es sigiloso (pocas señales clásicas).

19_Recomendaciones:
  Efectividad calculada de cada flag como regla de bloqueo:
  - Pct_fraude: % del fraude total que capturaría esta regla
  - Pct_no_fraude: % de txn buenas que afectaría (daño colateral)
  - Ratio_F_vs_noFraude: pct_fraude / pct_no_fraude (≥3 = regla efectiva)
  - Precision%: fraudes / total bloqueado
  - Para proponer una regla: Ratio ≥ 3 Y Pct_fraude ≥ 10% Y Precision ≥ 15%

20_Muestra:
  500 transacciones de fraude con todas sus variables. Útil para confirmar
  patrones cualitativos: leer 5-10 filas con SCORE_RIESGO alto y describir el perfil.

21_Score_Marca (NUEVA):
  Distribución del score Monitor por marca (Visa 0–99, Mastercard 0–999).
  Threshold scan: para cada umbral de score, muestra precisión y recall.
  Buscar el threshold donde la tasa F% en Fraudes supera 3x la tasa global.
  SOLO para tarjetas de crédito — débito no tiene score Monitor.

22_Vinculos (NUEVA):
  Sub-tabla A: distribución de N_FRAUDES_CLIENTE_PERIODO y ES_RESIDENTE por indicador.
  Sub-tabla B: reincidencia — clientes con 2+ fraudes en el período.
  Sub-tabla C: ZSCORE_MONTO_CLI_COMERCIO — desviación del monto respecto al historial del cliente en este comercio.
  Sub-tabla D: efectividad de flags de vínculo como reglas (mismo formato hoja 19).

════════════════════════════════════════════════════════════
VARIABLES CLAVE DE INGENIERÍA
════════════════════════════════════════════════════════════
GAP_MINUTOS:
  Tiempo en minutos entre la txn actual y la anterior del mismo cliente.
  Mediana fraude < 1 min = bot activo. Mediana fraude > 60 min = fraude aislado.
  NaN = primera txn del cliente en el dataset (no tiene anterior para comparar).

ZSCORE_MONTO_CLI_COMERCIO (hoja 22):
  Cuántas desviaciones estándar se aleja el monto de esta txn del promedio del
  cliente en ESTE comercio. Más discriminante que el zscore global porque
  compara al cliente con su propio comportamiento en el mismo lugar.

FLAG_PRIMERA_TRX_Y_DENEGADA (hoja 22):
  La primera txn del cliente hoy fue denegada antes de la txn actual.
  Patrón: ensayo-error del defraudador. Alta precisión cuando va acompañado de CVV_FAIL.

FLAG_HORA_FUERA_PERFIL_COMERCIO (hoja 18/19):
  La txn ocurrió en una hora atípica para ESTE comercio (>2 std del horario habitual).
  Mejor que ES_MADRUGADA porque se adapta al horario real del comercio.

SCORE_MON_NORM / FLAG_SCORE_RIESGO_MON_ALTO (hoja 21):
  Score Monitor normalizado 0–1. Solo crédito.
  > 0.7 = el propio sistema del banco ya lo marcó como riesgoso.

ANOMALY_SCORE / FLAG_ANOMALIA_IF (si está disponible):
  Score 0–1 del modelo Isolation Forest. Mayor = más anómalo.
  No depende de la etiqueta F. Puede detectar fraude aún no revisado por analistas.

════════════════════════════════════════════════════════════
TU TAREA — INFORME ESTRUCTURADO
════════════════════════════════════════════════════════════
Analiza el Excel adjunto y genera un informe profesional con estas secciones:

## 1. RESUMEN EJECUTIVO (media página)
- Magnitud: N fraudes, monto total fraude, tasa global y evolución mensual
- Vector principal: qué tipo de tarjeta, qué BIN, qué segmento, qué patrón
- Nivel de urgencia: BAJO / MEDIO / ALTO / CRÍTICO — justificar

## 2. PERFIL DEL FRAUDE
- Producto más afectado (TC o TD) con tasa F%
- Marca más afectada (VISA o MASTERCARD)
- Top 3-5 BINs críticos (listar con tasa F%, N fraudes, cruce segmento/producto)
- Segmento más golpeado (hoja 3 y 7)
- Patrón de monto: comparar mediana F vs mediana N (hoja 11)
  → F_mediana < N_mediana = card testing (montos bajos)
  → F_mediana > N_mediana = fraude de alto monto
- Patrón temporal: velocidad (ráfaga ≤5min, bucket 2 txn/día) o primera txn aislada
- Score Monitor: ¿los fraudes tienen score alto en hoja 21?
- Vínculos: ¿hay reincidentes? ¿ratio residente vs extranjero? (hoja 22)

## 3. PATRÓN DEL ATAQUE
Describir en 3-5 párrafos el modus operandi:
- ¿Cómo obtiene las tarjetas? (BIN repetido = generación secuencial; CVV_FAIL = robo parcial)
- ¿Qué montos usa y por qué? (¿redondos?, ¿bajos para card testing?, ¿altos para máximo daño?)
- ¿Cuándo ataca? (hora, día de semana, dentro o fuera del perfil horario del comercio)
- ¿Cuántas veces intenta antes de lograr el fraude? (cascada CVV, FLAG_PRIMERA_TRX_Y_DENEGADA)
- ¿Usa ráfaga (≤5min) o es sigiloso (bucket 2 txn/día en hoja 17)?
- ¿Los fraudes son de tarjetas ya comprometidas (TIENE_FRAUDE_PREVIO_PERIODO) o nuevas?

## 4. VARIABLES QUE NO DISCRIMINAN
Lista de variables donde F_media ≈ N_media, o flags con Ratio < 1 en hoja 19.
Para cada una: explicar por qué no sirve en ESTE comercio específico.
Ejemplo: "GAP_MINUTOS no discrimina porque el 70% del fraude es primera txn del cliente (sin GAP calculable)"

## 5. REGLAS DE CONTROL PROPUESTAS
Para cada regla incluir:
- Nombre y condición exacta con umbrales numéricos
- N fraudes capturados y % sobre total fraude
- N normales (N) afectadas y % sobre total N
- Precision% y Ratio_F_vs_noFraude (de hoja 19)
- Tipo de acción: BLOQUEO DIRECTO / REVISIÓN MANUAL / ALERTA OPERATIVA
- Justificación con los números exactos del Excel

Proponer mínimo:
  Regla 1 (alta confianza): Precision > 40%, aunque capture menos fraude
  Regla 2 (alto alcance): Captura ≥25% del fraude aunque Precision sea menor
  Regla 3 (complementaria, opcional): Para fraude residual no capturado por 1 y 2
  Regla de combinación (opcional): Combinar 2 flags con AND para mejorar Precision

## 6. RECOMENDACIONES AL COMERCIO
¿Qué debería hacer el comercio para reducir fraude sin bloquear legítimos?
(activar 3DS, CVV dinámico, tokenización, límites por BIN, monitoreo en tiempo real)

## 7. PRÓXIMOS PASOS
Lista priorizada de acciones para el equipo de fraude del banco.
Incluir: acción, responsable sugerido, urgencia (inmediata / esta semana / este mes).

════════════════════════════════════════════════════════════
TONO Y FORMATO
════════════════════════════════════════════════════════════
- Informe profesional bancario, en español
- Usa tablas cuando presentes datos numéricos
- Sé específico: no digas "alto fraude" sin dar el valor exacto
- Si encuentras anomalías inesperadas (txn Seguro con tasa alta, fraude con score bajo,
  reincidentes no bloqueados), menciónalas como hallazgos adicionales
- No repitas información entre secciones — cada sección agrega algo nuevo
```

---

## INSTRUCCIONES ADICIONALES POR PATRÓN DETECTADO

Usa estos bloques si ya detectaste un patrón antes de subir el Excel — agréguelos al final del prompt completo:

### Si el fraude es card testing (muchos CVV_FAIL, montos bajos, BIN12 repetido):
```
CONTEXTO ADICIONAL: Se sospecha un ataque de card testing.
Enfocarse en:
- Hoja 6_Por_BIN: listar BINs con >3 tarjetas distintas el mismo día
- Hoja 14_Motivos_Rechazo: ratio CVV_FAIL vs total rechazos
- Hoja 9_Velocidad bucket ≤1min: % de fraude con GAP muy corto
- Hoja 12_Deciles sección A: si decil 1 y 2 concentran el fraude = montos bajos
Proponer regla específica de bloqueo por BIN12 repetido más regla de velocidad.
```

### Si el fraude es de montos altos y aislado (sin ráfaga, ZSCORE alto):
```
CONTEXTO ADICIONAL: El fraude parece ser de montos altos sin patrón de ráfaga.
Enfocarse en:
- Hoja 13_Apertura_Decil10: distribución exacta del decil más alto
- Hoja 22_Vinculos sección C: ZSCORE_MONTO_CLI_COMERCIO — ¿los fraudes son outliers del cliente?
- Hoja 21_Score_Marca: ¿tienen score Monitor alto estos fraudes?
- Hoja 17_Transac_Diaria: ¿están concentrados en bucket 1 txn/día (fraude sigiloso)?
Proponer regla basada en zscore de monto o en combinación score Monitor + monto.
```

### Si hay reincidentes no bloqueados:
```
CONTEXTO ADICIONAL: Se observan clientes con múltiples fraudes en el período.
Enfocarse en:
- Hoja 22_Vinculos sección B: distribución de N_FRAUDES_CLIENTE_PERIODO
- Calcular: ¿cuántos fraudes se habrían prevenido si se bloqueaba tras el primer fraude?
- Hoja 1_Resumen: ¿en qué mes empezaron los fraudes reincidentes?
Proponer proceso operativo de bloqueo inmediato tras primer fraude confirmado.
```

### Si la velocidad no discrimina bien (F_mediana ≈ N_mediana en hoja 9):
```
CONTEXTO ADICIONAL: Las variables de velocidad tienen poca separación entre F y N.
El defraudador probablemente es sigiloso (1-2 txn por tarjeta).
Enfocarse en:
- Hoja 22_Vinculos: ZSCORE_MONTO_CLI_COMERCIO y FLAG_PRIMERA_TRX_Y_DENEGADA
- Hoja 21_Score_Marca: si el score Monitor discrimina cuando la velocidad no lo hace
- Hoja 12_Deciles sección C (árbol de decisión): cortes de monto que separan F de N
- Hoja 18_Perfil_Riesgo: ¿qué flags individuales tienen mayor Ratio en hoja 19?
Proponer reglas basadas en monto + score Monitor en lugar de velocidad.
```

---

### Si tienes el output del análisis ML no supervisado (Bloque P / notebook):
```
CONTEXTO ADICIONAL: Se ejecutó el pipeline de ML no supervisado (Isolation Forest + HDBSCAN).
El parquet o CSV adjunto incluye las columnas: ANOMALY_SCORE, FLAG_ANOMALIA_IF, CLUSTER_HDBSCAN,
SCORE_SOSPECHA (y posiblemente: TRX_BIN_1H, FLAG_RAFAGA_BIN_1H, FLAG_MONTO_ROBOTICO_BIN,
FLAG_BIN10_REPETIDO_DIA, FLAG_VEN_CONCENTRADA_BIN).

CÓMO INTERPRETAR ANOMALY_SCORE (Isolation Forest):
- Escala 0–1. Cuanto más cercano a 1, más fácil fue "aislar" la txn del resto → más anómala.
- FLAG_ANOMALIA_IF = 1 marca el ~5% superior de anomalías.
- El modelo NO usó la etiqueta F para entrenarse — detecta anomalías puras.
- Casos peligrosos: indicador N con ANOMALY_SCORE > 0.70 → fraude aún no revisado por analista.
- No todo ANOMALY_SCORE alto es fraude: puede ser txn legítima con comportamiento inusual.
  Cruzar siempre con BIN, SCORE_RIESGO y flags de velocidad para confirmar.

CÓMO INTERPRETAR CLUSTER_HDBSCAN:
- Valores ≥ 0 (0, 1, 2, …): grupos de txn con comportamiento similar entre sí.
  Cada cluster tiene un "prototipo" — si un cluster tiene tasa F% alta, todas las txn de ese cluster comparten ese patrón de fraude.
- Valor -1 (ruido): txn que no encajan en ningún grupo — los más raros y atípicos.
  Son candidatos prioritarios de revisión porque el modelo los considera inclasificables.
  Un cluster -1 con indicador N = txn sospechosa fuera de cualquier patrón conocido.

CÓMO INTERPRETAR SCORE_SOSPECHA:
- Suma ponderada de: FLAG_RAFAGA_BIN_1H (peso 2), FLAG_MONTO_ROBOTICO_BIN (peso 2),
  FLAG_BIN10_REPETIDO_DIA, FLAG_BIN11_REPETIDO_DIA, FLAG_VEN_CONCENTRADA_BIN,
  FLAG_CLIENTES_BIN_ALTO, FLAG_ANOMALIA_IF (peso 2) + ANOMALY_SCORE escalado.
- Score ≥ 4 = alta sospecha. Score ≥ 6 = prioridad de revisión inmediata.
- A diferencia del SCORE_RIESGO (Bloque L), el SCORE_SOSPECHA se centra en señales de BIN y generación de tarjetas, no en velocidad del cliente.

SEÑALES DE ATAQUE ROBOTICO (Bloque R):
- CV_MONTO_BIN_DIA ≈ 0: todas las txn del BIN ese día tienen el mismo monto → generación automatizada.
- N_TARJETAS_MISMO_MONTO_BIN ≥ 3 + CV_MONTO_BIN_DIA < 0.05 = FLAG_MONTO_ROBOTICO_BIN = 1.
- Diferente al card testing clásico: aquí el monto es idéntico entre tarjetas (no aleatorio).

SEÑALES DE CARD TESTING POR BIN (Bloque I extendido):
- FLAG_BIN10_REPETIDO_DIA: varias tarjetas distintas comparten los primeros 10 dígitos el mismo día.
  BIN10 compartido = sospechoso (generación secuencial de tarjetas desde una misma fuente).
- FLAG_BIN11_REPETIDO_DIA: BIN11 compartido = muy sospechoso.
- FLAG_BIN12_REPETIDO_DIA: BIN12 compartido = casi certeza de generación programática.
- FLAG_VEN_CONCENTRADA_BIN: varias tarjetas del mismo BIN tienen la misma fecha de vencimiento.
  Tarjetas legítimas del mismo BIN tienen vencimientos distribuidos; las generadas comparten fecha.

TU TAREA (análisis ML):
1. Ordenar las txn con indicador N por SCORE_SOSPECHA desc. Describir el perfil de las top 10.
2. Identificar qué clusters (CLUSTER_HDBSCAN) tienen mayor tasa F%. Describir el patrón de cada cluster caliente.
3. Calcular LIFT del FLAG_ANOMALIA_IF: Precision% ÷ Tasa_global_fraude%.
   Si LIFT > 3 = el modelo detecta fraude 3x mejor que al azar.
4. Identificar BINs donde FLAG_MONTO_ROBOTICO_BIN = 1 y cruzar con indicador → ¿ya tienen fraudes F?
5. Comparar txn con FLAG_VEN_CONCENTRADA_BIN=1 vs las que no: ¿la tasa F% es mayor?
6. Proponer: ¿cuáles de estos flags del ML deberían convertirse en reglas en Monitor?
   Para cada uno: dar Precision%, Recall%, Ratio_F_vs_noFraude.
```

---

## GUÍA RÁPIDA DE INTERPRETACIÓN — ISOLATION FOREST Y HDBSCAN

> Referencia rápida para el analista — sin necesidad de subir archivos a un modelo.

### Isolation Forest — Preguntas clave al ver el output

| Pregunta | Cómo responder con los datos |
|---|---|
| ¿El modelo funciona bien? | Comparar ANOMALY_SCORE mediana F vs mediana N. Si F_mediana > N_mediana → discrimina bien. |
| ¿Cuánto LIFT tiene? | Precision_IF% ÷ Tasa_global_F%. Si LIFT ≥ 3 → útil como regla. |
| ¿Qué umbral usar? | Buscar el ANOMALY_SCORE donde Precision% > 30% sin sacrificar recall < 20%. |
| ¿Por qué una txn tiene score alto? | Revisar las variables del Bloque Q y R — generalmente `TRX_BIN_1H` alto o `CV_MONTO_BIN_DIA` ≈ 0. |
| ¿Es fraude el N con score 0.80? | Probablemente sí, pero necesita revisión manual — es la hipótesis, no la confirmación. |

### HDBSCAN — Qué buscar en cada cluster

| Cluster | Qué significa | Acción |
|---|---|---|
| -1 (ruido) | Txn que no encajan en ningún patrón | Revisar primero — son los más atípicos |
| Cluster con tasa F% alta | Grupo homogéneo de fraudes con patrón similar | Describir el patrón → candidato a regla |
| Cluster con tasa F% baja | Comportamiento normal agrupado | Usar como "perfil de lo legítimo" |
| Cluster con mezcla F y N | Patrón intermedio — fraude sigiloso mezclado | Revisar los N de ese cluster con ANOMALY_SCORE > 0.6 |

### Señales de alarma que justifican revisión inmediata

```
ANOMALY_SCORE > 0.75  AND  indicador = N   → fraude probable no revisado
CLUSTER_HDBSCAN = -1  AND  FLAG_RAFAGA_BIN_1H = 1  → ataque fuera de patrón conocido
FLAG_MONTO_ROBOTICO_BIN = 1  AND  FLAG_BIN11_REPETIDO_DIA = 1  → generación automatizada activa
FLAG_VEN_CONCENTRADA_BIN = 1  AND  CLIENTES_BIN_DIA ≥ 5  → lote de tarjetas del mismo origen
SCORE_SOSPECHA ≥ 6  AND  indicador = N  → prioridad máxima de revisión
```

---

## GUÍA DE MODELO

| Modelo | Cuándo usarlo |
|---|---|
| **Claude Opus / Think / o3** | Prompt completo + Excel adjunto — analiza y cruza las 22 hojas solo. Mejor para patrones complejos y análisis multi-hoja. |
| **GPT-4o / Copilot estándar** | Prompt corto + pegar los datos clave en texto. Suficiente para un análisis rápido. |
| **Gemini 2.0 Deep Research** | Útil si también quieres que busque contexto externo (tendencias de fraude en el sector). |
| **Claude Opus / Think / o3** | Para el análisis ML: adjuntar el CSV de los top 50 sospechosos del notebook + el bloque ML adicional. |

**Recomendación general:** Think / Claude Opus + prompt completo + Excel adjunto + bloque adicional según el patrón detectado.

**Recomendación para ML:** Claude Opus + bloque ML + CSV exportado del notebook (`output/lista_revision_N_{COMERCIO}.csv`).
