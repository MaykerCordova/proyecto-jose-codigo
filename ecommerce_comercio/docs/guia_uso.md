# Guía de Uso — Pipeline Análisis Ecommerce por Comercio
## Scotiabank Perú — Prevención de Fraude

---

## Prerrequisitos

```bash
pip install pandas polars openpyxl pyarrow scikit-learn hdbscan
```

> `scikit-learn` y `hdbscan` son opcionales — solo se necesitan para el paso de ML.

---

## Flujo completo

```
data/journals/          ← aquí van los Excel descargados de Monitor
      ↓
1. consolidar.py        → data/consolidado.parquet
      ↓
2. feature_engineering.py → data/consolidado_features.parquet (~110 variables)
      ↓
3. analisis.py          → output/analisis_{COMERCIO}.xlsx (22 hojas)
      ↓  [opcional]
4. ml/clustering_fraude.py → data/consolidado_features_ml.parquet
                           → ml/output/ml_resumen_{COMERCIO}.xlsx (3 hojas)
      ↓  [opcional]
5. app.py (Streamlit)   → dashboard interactivo en el navegador
```

---

## Ejecución rápida (doble clic en Windows)

| Archivo .bat | Qué hace |
|---|---|
| `1_ejecutar_pipeline.bat` | Corre consolidar → features → analisis (pasos 1–3) |
| `2_abrir_app.bat` | Abre el dashboard Streamlit en el navegador |
| `3_ejecutar_ml.bat` | Corre el ML no supervisado (paso 4) |

---

## Paso 0 — Configurar el comercio

Editar `scripts/config.py` y cambiar:

```python
COMERCIO_NOMBRE = "ZARA"      # nombre del comercio que vas a analizar
SOLO_APROBADAS  = True        # True = solo txn aprobadas | False = incluye denegadas
```

Si las columnas del parquet tienen nombres distintos a los ACF por defecto,
actualizar el diccionario `COLS` en el mismo archivo.

---

## Paso 1 — Poner los journals en data/journals/

Descargar los journals de Monitor (Excel por quincena o mes) y colocarlos en:

```
ecommerce_comercio/
└── data/
    └── journals/
        ├── enero_q1.xlsx
        ├── enero_q2.xlsx
        ├── febrero_q1.xlsx
        └── ...
```

Los archivos se leen automáticamente (todos los `*.xlsx` de esa carpeta).

---

## Paso 2 — Ejecutar el pipeline

```bash
python scripts/consolidar.py
python scripts/feature_engineering.py
python scripts/analisis.py
```

El Excel de salida aparece en `output/analisis_{COMERCIO}.xlsx`.

---

## Paso 3 — ML no supervisado (opcional)

```bash
python ml/clustering_fraude.py
```

Requiere `scikit-learn` y `hdbscan`. Genera:
- `data/consolidado_features_ml.parquet` — parquet con ANOMALY_SCORE, FLAG_ANOMALIA_IF, CLUSTER_HDBSCAN
- `ml/output/ml_resumen_{COMERCIO}.xlsx` — resumen de anomalías y clusters (3 hojas)

---

## Paso 4 — Dashboard Streamlit (opcional)

```bash
streamlit run app.py
```

O doble clic en `2_abrir_app.bat`.

---

## Variables generadas por feature_engineering.py

### Bloque D — Ventanas deslizantes de velocidad

| Variable | Descripción |
|---|---|
| `TRX_CLIENTE_2MIN` | Txn del cliente en los 2 min previos |
| `TRX_CLIENTE_5MIN` | Txn del cliente en los 5 min previos |
| `TRX_CLIENTE_10MIN` | Txn del cliente en los 10 min previos |
| `TRX_CLIENTE_1H` | Txn del cliente en la última hora |
| `TRX_CLIENTE_24H` | Txn del cliente en las últimas 24h |
| `MNT_CLIENTE_2MIN` | Monto acumulado del cliente en 2 min previos |
| `MNT_CLIENTE_5MIN` | Monto acumulado en 5 min previos |
| `MNT_CLIENTE_10MIN` | Monto acumulado en 10 min previos |
| `MNT_CLIENTE_1H` | Monto acumulado en última hora |
| `MNT_CLIENTE_24H` | Monto acumulado en últimas 24h |
| `GAP_MINUTOS` | Minutos desde la txn anterior del mismo cliente |

### Bloque E — Interacciones velocidad × monto

| Variable | Descripción |
|---|---|
| `MONTO_PROM_5MIN` / `1H` / `24H` | Monto promedio por txn en esa ventana |
| `ACELERACION_MONTO` | Monto prom 5min ÷ monto prom 1h (escalada del ataque) |
| `CONCENTRACION_5MIN_1H` | % del monto de la hora concentrado en 5 min |
| `ZSCORE_MONTO_CLIENTE` | Z-score del monto vs historial global del cliente |
| `RATIO_MONTO_VS_HIST_CLIENTE` | Monto actual ÷ promedio histórico del cliente |

### Bloque F — Perfil del cliente

| Variable | Descripción |
|---|---|
| `FLAG_REINCIDENTE` | 1 si el cliente aparece más de una vez en el dataset |
| `FLAG_RAFAGA_DIA` | 1 si el cliente tuvo ≥3 txn el mismo día |
| `ES_CLIENTE_NUEVO_COMERCIO` | 1 si es la primera vez que aparece en el comercio |
| `DIAS_DESDE_ULT_TRX_COMERCIO` | Días desde su última txn en este comercio |
| `FLAG_SALDO_AGOTADO` | 1 si el fraude usó ≥90% del saldo disponible |

### Bloque K — Flags de reglas configurables

| Variable | Descripción |
|---|---|
| `FLAG_RAFAGA_5MIN` | 1 si TRX_CLIENTE_5MIN ≥ 3 |
| `FLAG_RAFAGA_10MIN` | 1 si TRX_CLIENTE_10MIN ≥ 3 |
| `FLAG_VEL_ALTA_1H` | 1 si TRX_CLIENTE_1H ≥ 5 |
| `FLAG_ACUM_ALTO_1H` | 1 si MNT_CLIENTE_1H ≥ 2× monto de la txn actual |
| `FLAG_MONTO_REDONDO` | 1 si monto es múltiplo exacto de 50 y ≥ S/50 |
| `FLAG_PAIS_INUSUAL` | 1 si el país es distinto al más frecuente del comercio |
| `FLAG_BIN12_REPETIDO_DIA` | 1 si el BIN12 se repite en >1 tarjeta el mismo día |
| `FLAG_ESCALADA_MONTO` | 1 si monto prom 5min > 2× monto prom 24h |

### Bloque L — Score de riesgo compuesto

| Variable | Descripción |
|---|---|
| `SCORE_RIESGO` | Suma de 11 flags de riesgo activos (0–11) |
| `PERFIL_RIESGO` | BAJO (0) / MEDIO (1–2) / ALTO (3–5) / MUY_ALTO (6+) |

### Bloque M — Score Monitor normalizado *(solo crédito)*

| Variable | Descripción |
|---|---|
| `SCORE_MON_NORM` | Score Monitor normalizado 0–1 (Visa ÷99, MC ÷999) |
| `FLAG_SCORE_RIESGO_MON_ALTO` | 1 si SCORE_MON_NORM ≥ 0.7 |
| `CATEGORIA_SCORE_MON` | BAJO / MEDIO / MEDIO_ALTO / ALTO / MUY_ALTO / SIN_SCORE |

### Bloque N — Vínculos del cliente con el comercio

| Variable | Descripción |
|---|---|
| `N_FRAUDES_CLIENTE_PERIODO` | Fraudes del cliente en el período analizado |
| `TIENE_FRAUDE_PREVIO_PERIODO` | 1 si tiene al menos 1 fraude previo en el período |
| `ES_RESIDENTE` | 1 si el cliente es residente en Perú |
| `ZSCORE_MONTO_CLI_COMERCIO` | Z-score del monto vs historial del cliente en este comercio |
| `TRX_DIA_PROM_CLIENTE_COMERCIO` | Promedio histórico de txn/día del cliente en el comercio |
| `FLAG_TRX_EXCEDE_PATRON_CLI_COM` | 1 si hoy excede su promedio de txn/día en el comercio |
| `FLAG_PRIMERA_TRX_Y_DENEGADA` | 1 si la primera txn del cliente hoy fue denegada |

### Bloque O — Perfil horario del comercio

| Variable | Descripción |
|---|---|
| `HORA_PROM_COMERCIO` | Hora promedio de actividad del comercio |
| `HORA_STD_COMERCIO` | Desviación estándar de la hora de actividad |
| `FLAG_HORA_FUERA_PERFIL_COMERCIO` | 1 si la hora está a >2 std del perfil horario del comercio |
| `TRX_PROM_CLIENTE_DIA_COMERCIO` | Promedio de txn/día del cliente en el comercio |
| `FLAG_CLIENTE_SUPERA_PERFIL_COMERCIO` | 1 si la actividad del día duplica su promedio habitual |

### Bloque P — ML no supervisado *(generado por clustering_fraude.py)*

| Variable | Descripción |
|---|---|
| `ANOMALY_SCORE` | Puntaje de anomalía Isolation Forest (0–1, mayor = más anómalo) |
| `FLAG_ANOMALIA_IF` | 1 si Isolation Forest lo clasifica como anomalía (~5% del total) |
| `CLUSTER_HDBSCAN` | Cluster asignado por HDBSCAN (-1 = ruido/outlier) |

---

## Hojas del Excel generado por analisis.py (22 hojas)

| Hoja | Contenido |
|---|---|
| 1_Resumen | KPIs por mes: N txn, montos, tasa fraude por indicador |
| 2_Por_Producto | Pivot por tipo TC (crédito) / TD (débito) |
| 3_Por_Segmento | Pivot por segmento cliente |
| 4_Por_Marca | Pivot por marca VISA / MASTERCARD |
| 5_Por_ECI | Pivot por seguridad 3DS (Seguro / No Seguro) |
| 6_Por_BIN | Top 30 BINs por volumen y tasa F% |
| 7_Cruce_Prod_Seg | Matriz Producto × Segmento con tasa F% |
| 8_Cruce_BIN_Prod | Matriz BIN × Producto con tasa F% |
| 9_Velocidad | GAP entre txn y ventanas TRX por indicador (media/mediana/P90) |
| 10_Monto_Acumulado | Monto acumulado previo e interacciones velocidad × monto |
| 11_Estadisticas_Monto | Percentiles de monto por indicador (F, G, N, D) |
| 12_Deciles_Monto | Tasa fraude por decil de monto + rangos + árbol de decisión + deciles por BIN caliente |
| 13_Apertura_Decil10 | Detalle del decil de mayor monto |
| 14_Motivos_Rechazo | Análisis de txn denegadas (CVV_FAIL, FONDOS_INSUF, etc.) |
| 15_CVV_Tokenizadas | Tipo CVV y billetera digital × indicador |
| 16_Por_Pais | Distribución por país de origen |
| 17_Transac_Diaria | Bucket de txn por cliente por día × indicador |
| 18_Perfil_Riesgo | Score compuesto 0–11 y perfil BAJO/MEDIO/ALTO/MUY_ALTO |
| 19_Recomendaciones | Efectividad de cada flag como regla (Ratio, Precision, impacto en N) |
| 20_Muestra | Muestra de fraudes con variables de comportamiento |
| **21_Score_Marca** | Score Monitor por marca: distribución Visa 0–99 / MC 0–999 con threshold scan |
| **22_Vinculos** | Análisis de vínculos del cliente: reincidencia, residente, zscore×comercio |

---

## Interpretación de indicadores

| Indicador | Significado |
|---|---|
| **F** | Fraude confirmado por analista |
| **G** | Buena — revisada y liberada por analista |
| **N** | Normal — sin alerta, sin revisar (97%+ del volumen) |
| **D** | Descarte (falso positivo descartado) |
| **P** | Pendiente de resolución |

> Al evaluar el impacto de una regla, el daño colateral es F versus {N + G + D + P}, **no solo G**.

---

## Estructura de carpetas

```
ecommerce_comercio/
├── 1_ejecutar_pipeline.bat     ← doble clic: corre pasos 1-3
├── 2_abrir_app.bat             ← doble clic: abre Streamlit
├── 3_ejecutar_ml.bat           ← doble clic: corre ML
├── app.py                      ← dashboard Streamlit (9 tabs)
├── scripts/
│   ├── config.py               ← configuración del comercio y columnas
│   ├── consolidar.py           ← journals Excel → parquet
│   ├── feature_engineering.py  ← ~110 variables de fraude → parquet
│   ├── analisis.py             ← Excel 22 hojas
│   └── diagnostico_columnas.py ← herramienta para mapear columnas del journal
├── ml/
│   └── clustering_fraude.py    ← Isolation Forest + HDBSCAN
├── data/
│   ├── journals/               ← aquí van los Excel de Monitor
│   ├── consolidado.parquet
│   ├── consolidado_features.parquet
│   └── consolidado_features_ml.parquet  (generado por el ML)
├── output/
│   └── analisis_{COMERCIO}.xlsx
├── ml/
│   └── output/
│       └── ml_resumen_{COMERCIO}.xlsx
└── docs/
    ├── diccionario_variables.md  ← descripción completa de todas las variables
    ├── guia_uso.md               ← este archivo
    └── prompt_copilot_analisis.md ← prompt para ChatGPT/Copilot
```
