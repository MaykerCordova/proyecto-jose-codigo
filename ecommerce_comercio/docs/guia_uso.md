# Guía de Uso — Pipeline Análisis Ecommerce por Comercio

## Prerrequisitos

```bash
pip install pandas polars openpyxl pyarrow
```

---

## Flujo completo (3 pasos)

```
data/journals/     ← aquí van los Excel de Monitor
      ↓
python scripts/consolidar.py          → data/consolidado.parquet
      ↓
python scripts/feature_engineering.py → data/consolidado_features.parquet
      ↓
python scripts/analisis.py            → output/analisis_COMERCIO.xlsx
```

---

## Paso 1 — Configurar el comercio

Edita `scripts/config.py` y cambia:

```python
COMERCIO_NOMBRE = "AMAZON"   # nombre del comercio que vas a analizar
```

Si las columnas de tu parquet tienen nombres distintos a los ACF por defecto,
actualiza el diccionario `COLS` en el mismo archivo.

---

## Paso 2 — Poner los journals en data/journals/

Descarga los journals de Monitor (Excel por quincena o mes) y colócalos en:

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
El nombre del archivo se usa como etiqueta en la columna `QUINCENA`.

---

## Paso 3 — Ejecutar los scripts

Desde la carpeta `ecommerce_comercio/`:

```bash
python scripts/consolidar.py
python scripts/feature_engineering.py
python scripts/analisis.py
```

El Excel de salida aparece en `output/analisis_NOMBRE_COMERCIO.xlsx`.

---

## Features generadas

| Feature | Descripción |
|---|---|
| N_TRX_5MIN | Transacciones del cliente en los 5 min previos |
| N_TRX_15MIN | Transacciones en los 15 min previos |
| N_TRX_1H | Transacciones en la 1 hora previa |
| N_TRX_24H | Transacciones en las 24 horas previas |
| GAP_MINUTOS | Minutos desde la transacción anterior del cliente |
| ES_RAFAGA | 1 si N_TRX_15MIN ≥ 2 (patrón ráfaga) |
| MONTO_ACUM_2H | Monto acumulado del cliente en las últimas 2 horas |
| MONTO_ACUM_24H | Monto acumulado en las últimas 24 horas |
| ZSCORE_MONTO_CLI | Z-score del monto vs historial del cliente |
| RATIO_MONTO_AVG_CLI | Ratio monto actual / promedio histórico cliente |
| RATIO_MONTO_SALDO | Ratio monto / saldo disponible |
| ES_MONTO_REDONDO | 1 si el monto es múltiplo de 50 y ≥ 50 |
| ES_MONTO_BAJO | 1 si monto < 20 (posible card testing) |
| ES_PRIMERA_VEZ_COMERCIO | 1 si es la primera compra del cliente en el comercio |
| N_TRX_HISTORICAS_COMERCIO | Número de compras previas del cliente en el comercio |
| DIAS_DESDE_PRIMERA_COMPRA | Días entre la primera compra y la actual |
| HUBO_FRAUDE_PREVIO_24H | 1 si el cliente tuvo un fraude aprobado en las últimas 24h |
| HUBO_FRAUDE_PREVIO_7D | 1 si el cliente tuvo un fraude aprobado en los últimos 7 días |
| PREV_FUE_FRAUDE | 1 si la transacción inmediatamente anterior fue fraude |
| MIN_DESDE_ULTIMO_FRAUDE | Minutos desde el último fraude aprobado del cliente |
| PAIS_DISTINTO_HABITUAL | 1 si el país de la trx es distinto al país habitual del cliente |
| CAMBIO_PAIS_VS_PREV | 1 si cambió de país vs la transacción anterior |
| N_PAISES_DISTINTOS_24H | Número de países distintos del cliente en 24h |
| IP_NUEVA_CLIENTE | 1 si es la primera vez que el cliente usa esa IP |
| N_CLIENTES_MISMA_IP_24H | Número de clientes distintos desde la misma IP en 24h |
| N_RECHAZOS_24H | Número de rechazos del cliente en las últimas 24h |
| N_CVV_FAIL_24H | Número de rechazos por CVV inválido en las últimas 24h |
| HUBO_CVV_FAIL_PREVIO | 1 si hubo al menos un CVV fail previo |
| MOTIVO_RECH | Clasificación del motivo de rechazo (CVV_FAIL, FONDOS_INSUF, etc.) |
| SCORE_RIESGO | Suma de 6 flags de riesgo (0–6) |
| PERFIL_RIESGO | BAJO / MEDIO / ALTO / MUY_ALTO según SCORE_RIESGO |

---

## Interpretación de indicadores

| Indicador | Significado |
|---|---|
| **F** | Fraude confirmado |
| **B** / **G** | Transacción buena (genuina) |
| **D** | Descarte (falso positivo descartado) |
| **P** | Pendiente de resolución |
| **N** | Normal / sin calificar |

---

## Estructura de carpetas

```
ecommerce_comercio/
├── scripts/
│   ├── config.py              ← configuración del comercio y columnas
│   ├── consolidar.py          ← journals Excel → parquet (pandas)
│   ├── feature_engineering.py ← features de fraude (polars)
│   └── analisis.py            ← Excel multi-hoja (openpyxl)
├── data/
│   ├── journals/              ← aquí van los Excel de Monitor
│   ├── consolidado.parquet    ← generado por consolidar.py
│   └── consolidado_features.parquet  ← generado por feature_engineering.py
├── output/
│   └── analisis_NOMBRE.xlsx   ← generado por analisis.py
└── docs/
    └── guia_uso.md            ← este archivo
```
