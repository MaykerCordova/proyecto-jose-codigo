# Prompts para Copilot — Análisis Smart Fit Peru
# Modelo: GPT con razonamiento profundo (o1 / o3 / Copilot Pro)
# Uso: pegar el prompt + adjuntar los archivos/imágenes indicados en cada sección

---

## PROMPT 1 — Análisis del Excel de resultados (24 hojas)

> Usar cuando: tengas el Excel generado por analisis.py y el output del CMD del pipeline

```
Eres un analista senior de prevención de fraude bancario con experiencia en
ecommerce y comercios de suscripción. Voy a darte los resultados del análisis
de transacciones de Smart Fit Peru para que me ayudes a interpretar los
hallazgos y proponer reglas concretas de control.

## CONTEXTO DEL SISTEMA
- Banco: Scotiabank Peru
- Base analizada: transacciones aprobadas de Smart Fit Peru
  (mar-2026 a jun-2026, 54,271 txn, S/5,608,410)
- Tasa de fraude global: 0.64% (345 fraudes confirmados sobre 53,926 no-fraude)
- Indicadores: F=fraude confirmado, N=sin calificar (puede contener fraude
  no detectado), G=buena confirmada, D=descarte, P=pendiente
- Las reglas de control se implementan en un sistema llamado Monitor con
  lógica if-then. Soporta variables acumuladas, vínculos de cliente y
  ventanas temporales.

## VARIABLES CLAVE
- GAP_MINUTOS: minutos entre la txn actual y la anterior del mismo cliente
  en este comercio. Clientes legítimos: ~30 días (43,200 min).
  Card testers: 15-120 min.
- TIENE_FRAUDE_PREVIO_PERIODO: 1 si el cliente tuvo fraude ANTES de esta
  txn (cronológico, sin data leakage). 116 activaciones, captura 29% del
  fraude con solo 0.03% de falsos positivos.
- FLAG_BIN12_REPETIDO_DIA: 1 si ese BIN de 12 dígitos aparece con múltiples
  tarjetas distintas en el mismo día. Captura 73% del fraude.
- FLAG_PRIMERA_TRX_MONTO_ALTO: 1 si es la primera txn del cliente en este
  comercio con monto >= percentil 90 (S/119.90). Captura 42% del fraude.
- FLAG_MONTO_MULTIPLO_BASE: 1 si el monto = N meses × S/119.90.
- FLAG_GAP_ZONA_FRAUDE: 1 si GAP entre 15 y 120 minutos.
- TIPO_COBRO_SUSCRIPCION: PRECIO_BASE / MONTO_ANOMALO / MULTI_MES_NM /
  PLAN+ADICIONAL / MANTENIMIENTO_ANUAL
- BIN 448700: tasa de fraude 13.64% (135 fraudes / 990 txn) — BIN comprometido
- Precio base detectado automáticamente: S/119.90 (Plan Black Smart Fit)

## ARCHIVOS ADJUNTOS
[Adjunta aquí:]
- Capturas de las hojas: 6_Por_BIN, 9_Velocidad, 19_Recomendaciones,
  23_Reglas_Combinadas, 24_Suscripciones
- Output del pipeline CMD (texto plano)

## LO QUE NECESITO

1. INTERPRETACIÓN DE NEGOCIO
   Describe qué tipo de fraude está ocurriendo en Smart Fit. ¿Card testing?
   ¿Suscripciones fraudulentas? ¿Ataques coordinados? Fundamenta con los datos.

2. TOP VARIABLES DISCRIMINANTES
   Ordena las variables por capacidad de separar fraude de no-fraude,
   considerando precisión y alcance (% fraude capturado). Explica cada una.

3. REGLAS PROPUESTAS PARA MONITOR
   Entre 3 y 5 reglas concretas en formato if-then. Para cada regla:
   - Condición exacta
   - Acción: bloqueo directo / alerta revisión / alerta operativa
   - % fraude capturado estimado
   - % clientes legítimos afectados estimado
   - Justificación del umbral elegido

4. RIESGOS Y SESGOS DEL ANÁLISIS
   ¿Qué limitaciones tiene? (label N contaminado, solo aprobadas,
   período de 3.5 meses, G=4 muy bajo)

5. PRÓXIMOS PASOS
   ¿Qué análisis complementario harías antes de implementar en producción?

Responde con precisión técnica. Si algo no está claro en los datos,
señálalo explícitamente en lugar de asumir.
```

---

## PROMPT 2 — Análisis del notebook: Isolation Forest + HDBSCAN

> Usar cuando: tengas las imágenes/capturas de cada celda del notebook ejecutado

```
Eres un analista de datos con experiencia en machine learning para detección
de fraude bancario. Voy a pasarte los resultados visuales y tablas de un
notebook de análisis no supervisado corrido sobre Smart Fit Peru.

## CONTEXTO
- Banco: Scotiabank Peru | Comercio: Smart Fit Peru
- Dataset: 54,271 txn aprobadas (mar-jun 2026) | Tasa fraude global: 0.64%
- Indicadores: F=fraude, N=no calificado, G=buena confirmada
- Se corrieron dos algoritmos de detección de anomalías:
  * Isolation Forest (IF): detecta anomalías globales usando árboles aleatorios
  * Local Outlier Factor (LOF): detecta anomalías locales vs vecinos cercanos
  * CONSENSUS_ANOMALY = txn marcada como anómala por AMBOS algoritmos
- Se corrió HDBSCAN para clustering multivariable (no supervisado)
- Variables de entrada: velocidad, monto, BIN, recurrencia, suscripción, flags

## IMÁGENES QUE TE PASO
[Adjunta aquí las capturas de cada celda del notebook:]

CELDA IF+LOF (panel de 4 gráficos):
- Panel 1: Curva de sensibilidad — Threshold del ANOMALY_SCORE vs Recall/Precision
- Panel 2: ANOMALY_SCORE promedio por día (¿hay días con picos?)
- Panel 3: Scatter IF vs LOF — zona de consenso (ambos detectan)
- Panel 4: Tabla comparativa por indicador F/G/N

CELDA HDBSCAN (profiling de clusters):
- Tabla clusters: N_txn, Tasa_F%, Monto_prom por cluster
- Flags activos por cluster de fraude
- Variables continuas elevadas vs baseline
- Reglas candidatas extraídas automáticamente

CELDA HDBSCAN (boxplot):
- Distribución de montos por cluster de fraude

## LO QUE NECESITO

### A. ISOLATION FOREST + LOF

1. CURVA DE SENSIBILIDAD (Panel 1)
   - ¿En qué threshold el Recall de fraude cae bruscamente?
   - ¿Cuál es el punto óptimo precision/recall para este comercio?
   - ¿El IF discrimina bien entre F y N, o el score está mezclado?

2. SCORE POR DÍA (Panel 2)
   - ¿Hay días con ANOMALY_SCORE promedio inusualmente alto?
   - ¿Coinciden esos picos con fechas conocidas de ataques?
   - ¿La anomalía es estable en el tiempo o concentrada?

3. IF vs LOF — ZONA DE CONSENSO (Panel 3)
   - ¿Qué % de los fraudes confirmados (F) están en la zona de consenso?
   - ¿Hay transacciones N en la zona de consenso que deberían investigarse?
   - ¿El IF y LOF están alineados o detectan cosas distintas?

4. TABLA POR INDICADOR (Panel 4)
   - ¿El ANOMALY_SCORE promedio de F es significativamente mayor que N?
   - ¿Cuánto separa el modelo el fraude del no-fraude?

### B. HDBSCAN CLUSTERING

5. IDENTIFICACIÓN DE CLUSTERS DE FRAUDE
   - ¿Cuáles clusters tienen tasa F% > 20%? Nómbralos como "Cluster de ataque X"
   - ¿Qué caracteriza a cada cluster de fraude? (monto, hora, BIN, flags activos)
   - ¿El cluster -1 (ruido) tiene tasa similar al global? ¿O concentra fraude?

6. PERFIL DE CADA CLUSTER DE FRAUDE
   Para cada cluster con tasa F% alta:
   - ¿Qué flags están activos en >50% de sus txn?
   - ¿Qué variables continuas están elevadas vs el resto?
   - ¿Qué tipología de fraude representa? (card testing / suscripción
     fraudulenta / ataque coordinado de BIN / disputa por confusión)

7. REGLAS CANDIDATAS DEL CLUSTERING
   - ¿Las reglas que el algoritmo extrae automáticamente son implementables
     en Monitor (lógica if-then)?
   - ¿Algún cluster revela un patrón que los flags individuales no capturan?

8. BOXPLOT DE MONTOS (clusters de fraude)
   - ¿Los montos de los clusters de fraude son distintos entre sí?
   - ¿Hay clusters con montos muy concentrados (card testing exacto) vs
     dispersos (fraude de mayor monto)?

### C. SÍNTESIS FINAL

9. ¿El ML confirma o contradice lo que ya vimos en el Excel?
   (BIN 448700 comprometido, FLAG_PRIMERA_TRX_MONTO_ALTO como mejor señal,
   TIENE_FRAUDE_PREVIO_PERIODO como variable estrella)

10. TOP 3 INSIGHTS que solo el ML revela y que el análisis de reglas no vería

11. RECOMENDACIÓN FINAL
    Con toda la información (Excel + ML), ¿cuáles serían las 3 reglas
    prioritarias para implementar en Monitor este mes?

Sé específico con los números que ves en las imágenes. No generalices —
cita los valores exactos de las tablas y gráficos.
```

---

## NOTAS DE USO

- **Prompt 1**: para el análisis descriptivo/estadístico (Excel). Adjuntar hojas
  6, 9, 19, 23, 24 como capturas o texto.
- **Prompt 2**: para el análisis de ML (notebook). Adjuntar imágenes de cada
  celda ejecutada en orden.
- Ambos prompts se pueden combinar en una sola sesión si tienes toda la
  información disponible.
- El documento `flujo_operativo_y_modelo.md` de esta misma carpeta da el
  contexto operativo completo — pégalo al inicio de cualquier sesión con Copilot.
