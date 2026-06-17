# Plan de Análisis — Base de Reclamos
# Scotiabank Peru — Prevención de Fraude
# Última actualización: junio 2026

---

## Contexto del problema

La base de reclamos contiene transacciones que pasaron como N (normal) en el
Monitor — no fueron detectadas por ninguna regla — y luego el tarjetahabiente
las reclamó como no reconocidas. Estas transacciones ingresan por el proceso
de "carga masiva" a la base 8850 y actualizan la marca en la 8750.

**Característica clave:** toda la data es fraude confirmado.
No hay variable objetivo binaria → no es un problema de clasificación.
Es un problema de **perfilamiento y segmentación**.

---

## Dos tipos de fraude en la base

### Fraude real (cliente genuinamente afectado)
- El tarjetahabiente no realizó la transacción
- Puede ser: clonación de tarjeta, robo de datos, fraude CNP
- El reclamo llega en días a semanas

### Autofraud / Friendly Fraud (posible)
- El tarjetahabiente SÍ realizó la transacción pero la reclama
- Motivación: recuperar el dinero de una compra que se arrepintió
- Señales: comercio habitual del cliente, monto dentro de su patrón,
  hora normal, sin actividad sospechosa alrededor
- El reclamo suele llegar tarde (>60 días)

---

## Segmentación del equipo

| Analista | Segmento | Foco |
|---|---|---|
| Jose (yo) | **TD MASTERCARD** | Clonación POS, ATM, contactless |
| Compañero A | TD VISA | Similar a TD MC, distinto perfil BIN |
| Compañero B | TC VISA + MASTERCARD | CNP, ecommerce, card testing |

**Recomendación:** hacer el EDA con la data completa primero,
luego filtrar por segmento para el análisis profundo.

---

## Plan de trabajo por fases

### FASE 1 — EDA completo (data sin filtrar)

**Objetivo:** entender la distribución global del fraude por reclamo

Análisis a realizar:
- Distribución de montos (min, max, mediana, P90, por deciles)
- Distribución por canal (POS, ATM, ecommerce, CNP, contactless)
- Distribución por marca (VISA TD, MC TD, VISA TC, MC TC)
- Top 20 comercios / MCC con mayor concentración de reclamos
- Distribución horaria y por día de semana
- Concentración geográfica (país de origen de la txn)
- Distribución por país del BIN
- **Tiempo entre txn y reclamo** (días de demora) — clave para detectar autofraud

**Output:** reporte EDA + gráficos base

---

### FASE 2 — Análisis profundo por segmento (TD MASTERCARD)

**Objetivo:** identificar tipologías de fraude específicas de TD MC

#### 2a. Feature Engineering
Variables a construir (similares al pipeline ecommerce):
- GAP_MINUTOS entre txn del mismo cliente
- Ventanas temporales: TRX_CLIENTE_1H, MNT_CLIENTE_24H
- FLAG_BIN12_REPETIDO_DIA (card testing / clonación masiva)
- FLAG_VEN_CONCENTRADA_BIN (tarjetas generadas algorítmicamente)
- ES_MADRUGADA, ES_FIN_SEMANA
- DIAS_HASTA_RECLAMO (tiempo entre fecha txn y fecha reclamo)
- FLAG_RECLAMO_TARDIO (DIAS_HASTA_RECLAMO > 60) → señal de autofraud
- ES_COMERCIO_HABITUAL (cliente había transaccionado antes en ese comercio)
- MONTO_VS_PATRON_CLI (monto dentro/fuera del patrón histórico del cliente)

#### 2b. Clustering — identificar tipologías
Algoritmos a aplicar:
- **HDBSCAN** (preferido): no requiere definir N clusters, maneja ruido
- **K-means** como referencia: para comparar con HDBSCAN

Tipologías esperadas para TD MC:
- Clonación de banda magnética en POS (mismos BIN, distintos comercios físicos)
- Fraude en cajero ATM (canal ATM, montos redondos, madrugada)
- Fraude contactless (monto bajo, comercio físico, múltiples txn)
- Fraude en ecommerce sin 3DS (canal CNP, sin tarjeta presente)
- Posible autofraud (comercio habitual, monto normal, reclamo tardío)

#### 2c. Anomalías dentro del fraude
Algoritmos: Isolation Forest + Local Outlier Factor
**Propósito:** detectar txn "raras dentro del fraude" = candidatas a autofraud

Señales de autofraud (txn que el IF/LOF marcaría como "no parece fraude"):
- Monto dentro del rango habitual del cliente en ese comercio
- Comercio donde el cliente ya había transaccionado antes
- Hora dentro del horario habitual del cliente
- Sin BIN comprometido (BIN sin otras txn fraudulentas ese día)
- Reclamo llegó después de 60 días

---

### FASE 3 — Comparativa vs fraude detectado por reglas

**Objetivo:** identificar el GAP de las reglas actuales

Preguntas a responder:
- ¿En qué se diferencia el fraude por reclamo del que sí capturaron las reglas?
- ¿Qué variables tenían los fraudes NO detectados?
- ¿Qué reglas adicionales podrían haber capturado estos reclamos?

**Output:** recomendación de nuevas reglas para Monitor basadas en el GAP

---

### FASE 4 — Presentación al gerente

Estructura sugerida del informe:
1. Volumen y monto del fraude por reclamo (global + por segmento)
2. Tipologías identificadas (con ejemplos de cada cluster)
3. Perfil del fraude TD MASTERCARD (canal, monto, horario, comercio)
4. Señales de posible autofraud detectadas
5. GAP de reglas: qué no se está capturando y por qué
6. Recomendaciones: nuevas reglas + proceso de validación de reclamos

---

## Estructura de archivos

```
analisis_reclamo/
├── data/
│   ├── reclamos_raw.parquet          ← base original (no subir a git)
│   ├── reclamos_td_mc.parquet        ← filtrado TD MASTERCARD
│   └── reclamos_features.parquet     ← con variables construidas
├── docs/
│   ├── plan_analisis.md              ← este archivo
│   └── diccionario_variables.md      ← variables del análisis de reclamos
├── scripts/
│   ├── consolidar.py                 ← carga y limpia la base de reclamos
│   ├── feature_engineering.py        ← construye variables
│   └── analisis_eda.py               ← EDA y exporta Excel
├── notebooks/
│   └── analisis_tipologias.ipynb     ← clustering + IF/LOF + profiling
└── output/
    ├── eda_reclamos_tdmc.xlsx         ← Excel de resultados
    └── tipologias_fraude_tdmc.csv     ← clusters exportados
```

---

## Preguntas pendientes antes de empezar

Antes de escribir el código, confirmar:
1. ¿En qué formato viene la base de reclamos? (Excel del Monitor, CSV, otro)
2. ¿Tiene las mismas columnas que el Monitor estándar (ACF-...)? 
3. ¿Tiene la columna de fecha del reclamo además de la fecha de la txn?
4. ¿El período de la base cuántos meses cubre?
5. ¿Cuántos registros aproximadamente tiene la base completa?

---

## Estado actual

- [x] Carpeta creada
- [x] Plan de análisis documentado
- [ ] Confirmar estructura de datos de reclamos
- [ ] Fase 1: EDA completo
- [ ] Fase 2: Feature engineering + clustering TD MC
- [ ] Fase 3: Comparativa vs fraude por reglas
- [ ] Fase 4: Presentación gerente
