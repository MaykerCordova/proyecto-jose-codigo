# Medidas DAX — Comercios No Seguros (E-commerce No 3DS)
# CPF · Centro de Prevención del Fraude

> Pegar cada bloque en Power BI: Modelado → Nueva medida

---

## BASE — Medidas fundamentales (todas las páginas las usan)

```dax
# Fraudes =
COUNTROWS('fraudes_comercios_no_seguros_features')
```

```dax
Monto Fraude =
SUM('fraudes_comercios_no_seguros_features'[IMPORTE])
```

```dax
Monto Fraude USD =
SUM('fraudes_comercios_no_seguros_features'[IMPORTE_USD])
```

```dax
Ticket Promedio =
DIVIDE(
    [Monto Fraude],
    [# Fraudes]
)
-- Formato: #,##0.00
```

```dax
Tarjetas Únicas =
DISTINCTCOUNT('fraudes_comercios_no_seguros_features'[TARJETA])
```

```dax
Comercios Únicos =
DISTINCTCOUNT('fraudes_comercios_no_seguros_features'[COMERCIO_ID])
```

```dax
MCC Únicos =
DISTINCTCOUNT('fraudes_comercios_no_seguros_features'[MCC])
```

```dax
Monto Promedio por Tarjeta =
DIVIDE(
    [Monto Fraude],
    [Tarjetas Únicas]
)
-- Formato: #,##0.00
```

---

## PÁGINA 1 — Resumen Ejecutivo

```dax
-- % participación del segmento / comercio / BIN seleccionado
-- sobre el total general (ignora filtros del visual para el denominador)
% Participación Monto =
DIVIDE(
    [Monto Fraude],
    CALCULATE([Monto Fraude], ALL('fraudes_comercios_no_seguros_features'))
)
-- Formato: 0.00%
```

```dax
-- Variación mes a mes del monto
Variación Monto MoM =
VAR mes_actual =
    CALCULATE(
        [Monto Fraude],
        DATESMTD(dim_Calendario[Date])
    )
VAR mes_anterior =
    CALCULATE(
        [Monto Fraude],
        DATEADD(DATESMTD(dim_Calendario[Date]), -1, MONTH)
    )
RETURN
    DIVIDE(mes_actual - mes_anterior, mes_anterior)
-- Formato: +0.0%;-0.0%
```

```dax
-- % Monto Alertado vs No Alertado
-- (ajusta el nombre de columna si tu campo se llama diferente)
% Monto Alertado =
DIVIDE(
    CALCULATE(
        [Monto Fraude],
        'fraudes_comercios_no_seguros_features'[CVV_DINAMICO] = "S"
    ),
    [Monto Fraude]
)
-- Formato: 0.0%
```

---

## PÁGINA 2 — Análisis Temporal

```dax
Hora Pico =
VAR resumen =
    ADDCOLUMNS(
        VALUES('fraudes_comercios_no_seguros_features'[HORA_DIA]),
        "conteo", CALCULATE(COUNTROWS('fraudes_comercios_no_seguros_features'))
    )
VAR hora_max =
    MAXX(TOPN(1, resumen, [conteo], DESC), [HORA_DIA])
RETURN
    hora_max & ":00 hrs"
```

```dax
% Madrugada =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[FRANJA_HORARIA] = "MADRUGADA"
    ),
    [# Fraudes]
)
-- Formato: 0.0%
```

```dax
% Fin de Semana =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[ES_FIN_SEMANA] = 1
    ),
    [# Fraudes]
)
-- Formato: 0.0%
```

```dax
% Horario Laboral =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[ES_HORARIO_LAB] = 1
    ),
    [# Fraudes]
)
-- Formato: 0.0%
```

```dax
Día Pico =
VAR resumen =
    ADDCOLUMNS(
        VALUES('fraudes_comercios_no_seguros_features'[DIA_SEMANA_NOM]),
        "conteo", CALCULATE(COUNTROWS('fraudes_comercios_no_seguros_features'))
    )
RETURN
    MAXX(TOPN(1, resumen, [conteo], DESC), [DIA_SEMANA_NOM])
```

```dax
-- Columna calculada para ordenar días correctamente en los visuales
-- Modelado → Nueva columna (no medida)
Orden Día =
SWITCH('fraudes_comercios_no_seguros_features'[DIA_SEMANA_NOM],
    "LUN", 1,
    "MAR", 2,
    "MIE", 3,
    "JUE", 4,
    "VIE", 5,
    "SAB", 6,
    "DOM", 7,
    7
)
-- Luego: clic en DIA_SEMANA_NOM → Ordenar por columna → Orden Día
```

```dax
-- Columna calculada para ordenar franjas horarias
-- Modelado → Nueva columna (no medida)
Orden Franja =
SWITCH('fraudes_comercios_no_seguros_features'[FRANJA_HORARIA],
    "MADRUGADA", 1,
    "MAÑANA",    2,
    "TARDE",     3,
    "NOCHE",     4,
    5
)
-- Luego: clic en FRANJA_HORARIA → Ordenar por columna → Orden Franja
```

```dax
-- Color condicional para barras de días (fin de semana en rojo)
-- Usar en: Formato del visual → Color de datos → fx → Valor de campo
Color Día =
IF(
    MAX('fraudes_comercios_no_seguros_features'[ES_FIN_SEMANA]) = 1,
    "#E63946",
    "#1D3557"
)
```

---

## PÁGINA 3 — Comercios & MCC

```dax
% Participación Comercio =
DIVIDE(
    [Monto Fraude],
    CALCULATE([Monto Fraude], ALLEXCEPT(
        'fraudes_comercios_no_seguros_features',
        'fraudes_comercios_no_seguros_features'[MES]
    ))
)
-- Formato: 0.00%
```

```dax
Tarjetas por Comercio =
DIVIDE(
    [Tarjetas Únicas],
    [Comercios Únicos]
)
-- Promedio de tarjetas distintas por comercio
```

```dax
Monto por MCC =
CALCULATE(
    [Monto Fraude],
    ALLEXCEPT(
        'fraudes_comercios_no_seguros_features',
        'fraudes_comercios_no_seguros_features'[MCC]
    )
)
```

---

## PÁGINA 3 — Comercios & MCC

```dax
-- KPI: nombre del comercio con más monto fraudulento
Top Comercio =
VAR resumen =
    ADDCOLUMNS(
        VALUES('fraudes_comercios_no_seguros_features'[COMERCIO_NOMBRE]),
        "monto", CALCULATE([Monto Fraude])
    )
RETURN
    MAXX(TOPN(1, resumen, [monto], DESC), [COMERCIO_NOMBRE])
```

```dax
-- KPI: MCC con más monto fraudulento
Top MCC =
VAR resumen =
    ADDCOLUMNS(
        VALUES('fraudes_comercios_no_seguros_features'[MCC]),
        "monto", CALCULATE([Monto Fraude])
    )
RETURN
    MAXX(TOPN(1, resumen, [monto], DESC), [MCC])
```

```dax
-- KPI: monto promedio de fraude por comercio
Monto Promedio por Comercio =
DIVIDE(
    [Monto Fraude],
    [Comercios Únicos]
)
-- Formato: #,##0.00
```

```dax
-- % que representa el comercio/MCC seleccionado sobre el total general
-- Usar en barras horizontales como etiqueta de participación
% Participación sobre Total =
DIVIDE(
    [Monto Fraude],
    CALCULATE(
        [Monto Fraude],
        ALL('fraudes_comercios_no_seguros_features')
    )
)
-- Formato: 0.00%
```

```dax
-- Concentración: % que acumulan los TOP N comercios
-- Usar con parámetro numérico o fijo en 10/20
% Top 10 Comercios =
VAR top10 =
    TOPN(
        10,
        VALUES('fraudes_comercios_no_seguros_features'[COMERCIO_ID]),
        CALCULATE([Monto Fraude]),
        DESC
    )
VAR monto_top10 =
    CALCULATE(
        [Monto Fraude],
        KEEPFILTERS(top10)
    )
RETURN
    DIVIDE(
        monto_top10,
        CALCULATE([Monto Fraude], ALL('fraudes_comercios_no_seguros_features'))
    )
-- Formato: 0.0%
-- Interpretación: si sale 65% → los 10 comercios más golpeados
--                 concentran el 65% del monto total defraudado
```

```dax
-- Tarjetas distintas afectadas en el comercio seleccionado
Tarjetas en Comercio =
DISTINCTCOUNT('fraudes_comercios_no_seguros_features'[TARJETA])
```

```dax
-- Días distintos con al menos un fraude en el comercio
Días con Fraude =
DISTINCTCOUNT('fraudes_comercios_no_seguros_features'[FECHA_DIA])
```

```dax
-- Ticket mínimo del comercio
Ticket Mínimo =
MIN('fraudes_comercios_no_seguros_features'[IMPORTE])
-- Formato: #,##0.00
```

```dax
-- Ticket máximo del comercio
Ticket Máximo =
MAX('fraudes_comercios_no_seguros_features'[IMPORTE])
-- Formato: #,##0.00
```

```dax
-- % de transacciones del comercio que vienen de tarjetas en ráfaga
-- (tarjeta con 3+ fraudes ese día en cualquier comercio)
% Ráfaga en Comercio =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[FLAG_RAFAGA_DIA] = 1
    ),
    [# Fraudes]
)
-- Formato: 0.0%
-- Interpretación: 40% → 4 de cada 10 fraudes en ese comercio
--   vinieron de tarjetas que ese día cometieron 3+ fraudes en total
--   Señal: comercio siendo usado en operaciones de fraude masivo
```

```dax
-- % de fraudes del comercio con monto redondo (señal de card testing)
% Monto Redondo en Comercio =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[FLAG_MONTO_REDONDO] = 1
    ),
    [# Fraudes]
)
-- Formato: 0.0%
-- Interpretación: montos exactos (100.00, 50.00) son típicos de
--   pruebas automatizadas de tarjetas clonadas
```

```dax
-- Color condicional para barras del scatter o top comercios
-- Verde si pocos fraudes, rojo si muchos (relativo al promedio)
Color Comercio Riesgo =
VAR promedio_fraudes =
    AVERAGEX(
        VALUES('fraudes_comercios_no_seguros_features'[COMERCIO_ID]),
        CALCULATE([# Fraudes])
    )
VAR fraudes_actual = [# Fraudes]
RETURN
    IF(fraudes_actual > promedio_fraudes * 2, "#C00000",   -- rojo: muy por encima
    IF(fraudes_actual > promedio_fraudes,     "#FF8C00",   -- naranja: sobre promedio
                                             "#1D6F42"))   -- verde: bajo promedio
-- Usar en: Formato del visual → Color de datos → fx → Valor de campo
```

```dax
-- Para el scatter: tamaño de burbuja = tarjetas distintas por comercio
-- (ya existe como columna TARJETAS_DISTINTAS_COM, pero como medida
--  funciona mejor con filtros del visual)
Tarjetas Distintas Comercio =
CALCULATE(
    DISTINCTCOUNT('fraudes_comercios_no_seguros_features'[TARJETA])
)
```

```dax
-- Índice de concentración por comercio:
-- cuántas tarjetas distintas por cada fraude
-- Valor bajo → pocas tarjetas hacen muchos fraudes (más sospechoso)
Fraudes por Tarjeta en Comercio =
DIVIDE(
    [# Fraudes],
    [Tarjetas Distintas Comercio]
)
-- Formato: 0.00
-- Interpretación: 5.0 → en promedio cada tarjeta tiene 5 fraudes
--   en ese comercio → señal de ataque concentrado
```

---

### Configuración del Scatter (Comercios)
```
Visual   : Gráfico de dispersión
Eje X    : [# Fraudes]
Eje Y    : [Monto Fraude]
Tamaño   : [Tarjetas Distintas Comercio]
Leyenda  : MCC  (para colorear por rubro)
Detalles : COMERCIO_NOMBRE  (para tooltip e identificación)
Tooltips : [Ticket Promedio], [% Ráfaga en Comercio],
           [% Monto Redondo en Comercio], [Días con Fraude]
```

### Configuración tabla detalle (Página 3)
```
Columnas:
  COMERCIO_NOMBRE     → nombre del comercio
  MCC                 → rubro
  [# Fraudes]         → conteo
  [Monto Fraude]      → suma  (formato S/ #,##0)
  [Tarjetas en Comercio]
  [Ticket Promedio]
  [Ticket Mínimo]
  [Ticket Máximo]
  [% Participación sobre Total]
  [Días con Fraude]
  [% Ráfaga en Comercio]
  [% Monto Redondo en Comercio]
  [Fraudes por Tarjeta en Comercio]

Ordenar por: Monto Fraude DESC
Formato condicional en [# Fraudes]: escala blanco → rojo
Formato condicional en [% Ráfaga]:  escala blanco → rojo
```

---

## PÁGINA 4 — Perfil de Tarjetas

```dax
% Tarjetas Reincidentes =
DIVIDE(
    CALCULATE(
        [Tarjetas Únicas],
        'fraudes_comercios_no_seguros_features'[FLAG_TARJETA_REINCIDENTE] = 1
    ),
    [Tarjetas Únicas]
)
-- Formato: 0.0%
```

```dax
% Ráfaga (3+ fraudes/día) =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[FLAG_RAFAGA_DIA] = 1
    ),
    [# Fraudes]
)
-- Formato: 0.0%
```

```dax
% Multi Comercio en un Día =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[FLAG_MULTI_COMERCIO_DIA] = 1
    ),
    [# Fraudes]
)
-- Formato: 0.0%
```

```dax
Monto Promedio por Tarjeta =
DIVIDE(
    [Monto Fraude],
    [Tarjetas Únicas]
)
-- Formato: #,##0.00
-- Cuánto se defraudó en promedio por tarjeta afectada
```

```dax
-- Tarjetas que aparecen más de una vez en el dataset
-- (tuvieron fraude en más de un evento/día)
Tarjetas Reincidentes =
CALCULATE(
    [Tarjetas Únicas],
    'fraudes_comercios_no_seguros_features'[FLAG_TARJETA_REINCIDENTE] = 1
)
```

```dax
-- Tarjetas que tuvieron fraude en 2+ comercios distintos el mismo día
Tarjetas Multi Comercio =
CALCULATE(
    [Tarjetas Únicas],
    'fraudes_comercios_no_seguros_features'[FLAG_MULTI_COMERCIO_DIA] = 1
)
```

```dax
-- Promedio de comercios distintos donde cada tarjeta tuvo fraude
Comercios Prom por Tarjeta =
AVERAGEX(
    VALUES('fraudes_comercios_no_seguros_features'[TARJETA]),
    CALCULATE(
        DISTINCTCOUNT('fraudes_comercios_no_seguros_features'[COMERCIO_ID])
    )
)
-- Formato: 0.00
-- Interpretación: 2.5 → cada tarjeta afectada tuvo fraude
--   en promedio en 2.5 comercios distintos
```

```dax
-- Fraudes promedio por tarjeta (qué tan recurrente es el fraude)
Fraudes Prom por Tarjeta =
DIVIDE(
    [# Fraudes],
    [Tarjetas Únicas]
)
-- Formato: 0.0
```

```dax
-- % de fraudes de tarjetas de crédito sobre el total
% Crédito =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[TIPO_TARJETA] = "CREDITO"
    ),
    [# Fraudes]
)
-- Formato: 0.0%
```

```dax
-- % de fraudes de tarjetas de débito sobre el total
% Débito =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[TIPO_TARJETA] = "DEBITO"
    ),
    [# Fraudes]
)
-- Formato: 0.0%
```

```dax
-- Monto promedio de fraude por tipo de tarjeta
-- Usar en tooltip del donut Crédito vs Débito
Ticket Promedio por Tipo =
DIVIDE(
    [Monto Fraude],
    [# Fraudes]
)
-- Formato: #,##0.00
```

```dax
-- Distribución de PERFIL_RIESGO para gráfico de barras
-- (la columna ya existe, solo necesitas la medida de conteo)
-- Visual: Barras apiladas o agrupadas
-- Eje X: PERFIL_RIESGO  (ordenar: BAJO → MEDIO → ALTO → MUY_ALTO)
-- Valor: [# Fraudes] y [Monto Fraude]
-- Columna calculada para ordenar PERFIL_RIESGO:
Orden Perfil =
-- Modelado → Nueva columna (no medida)
SWITCH('fraudes_comercios_no_seguros_features'[PERFIL_RIESGO],
    "BAJO",     1,
    "MEDIO",    2,
    "ALTO",     3,
    "MUY_ALTO", 4,
    5
)
-- Luego: clic en PERFIL_RIESGO → Ordenar por columna → Orden Perfil
```

```dax
-- Score promedio de riesgo de tarjetas en el contexto seleccionado
Score Riesgo Promedio Tarjetas =
AVERAGEX(
    VALUES('fraudes_comercios_no_seguros_features'[TARJETA]),
    CALCULATE(
        AVERAGE('fraudes_comercios_no_seguros_features'[SCORE_RIESGO_TRJ])
    )
)
-- Formato: 0.00
-- Escala de 0 a 6 (suma de flags de riesgo)
```

```dax
-- % de tarjetas con perfil MUY_ALTO sobre total de tarjetas
% Tarjetas MUY ALTO Riesgo =
DIVIDE(
    CALCULATE(
        [Tarjetas Únicas],
        'fraudes_comercios_no_seguros_features'[PERFIL_RIESGO] = "MUY_ALTO"
    ),
    [Tarjetas Únicas]
)
-- Formato: 0.0%
```

```dax
-- Monto defraudado por tarjetas MUY ALTO riesgo
Monto Tarjetas MUY ALTO =
CALCULATE(
    [Monto Fraude],
    'fraudes_comercios_no_seguros_features'[PERFIL_RIESGO] = "MUY_ALTO"
)
-- Formato: #,##0.00
```

```dax
-- Para colorear el donut Crédito vs Débito o nivel de tarjeta
-- Verde = Débito (menor ticket promedio normalmente)
-- Rojo = Crédito (mayor exposición)
Color Tipo Tarjeta =
SWITCH(
    MAX('fraudes_comercios_no_seguros_features'[TIPO_TARJETA]),
    "CREDITO", "#C00000",
    "DEBITO",  "#1D6F42",
    "#808080"
)
```

```dax
-- Color por nivel de tarjeta (mayor nivel = más exposición potencial)
Color Nivel Tarjeta =
SWITCH(
    MAX('fraudes_comercios_no_seguros_features'[NIVEL_TARJETA]),
    "BLACK",    "#1A1A1A",
    "PLATINUM", "#A0A0A0",
    "GOLD",     "#C9A84C",
    "CLASSIC",  "#1D3557",
    "#808080"
)
```

---

### Configuración tabla Top Tarjetas (Página 4)
```
Columnas:
  TARJETA                       → número enmascarado
  TIPO_TARJETA                  → Crédito / Débito
  NIVEL_TARJETA                 → Classic / Gold / Platinum / Black
  SEGMENTO                      → segmento del cliente
  [# Fraudes]                   → total de fraudes de esa tarjeta
  [Monto Fraude]                → monto total  (formato S/ #,##0)
  [Comercios Distintos Tarjeta] → en cuántos comercios tuvo fraude
  DIAS_ACTIVA_TRJ               → días distintos con fraude
  PERFIL_RIESGO                 → BAJO/MEDIO/ALTO/MUY_ALTO
  SCORE_RIESGO_TRJ              → valor numérico 0-6

Ordenar por: [# Fraudes] DESC  o  [Monto Fraude] DESC
Formato condicional en SCORE_RIESGO_TRJ:
  0-1 → verde  |  2-3 → amarillo  |  4-6 → rojo

Filtro de página recomendado:
  TOTAL_FRAUDES_TARJETA > 1   (mostrar solo reincidentes)
  o dejar sin filtro y que el usuario use el slicer PERFIL_RIESGO
```

---

## PÁGINA 5 — Dashboard Accionable

```dax
Tarjetas MUY ALTO Riesgo =
CALCULATE(
    [Tarjetas Únicas],
    'fraudes_comercios_no_seguros_features'[PERFIL_RIESGO] = "MUY_ALTO"
)
```

```dax
% CVV Estático =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[FLAG_CVV_ESTATICO] = 1
    ),
    [# Fraudes]
)
-- Formato: 0.0%
```

```dax
% Monto Redondo =
DIVIDE(
    CALCULATE(
        [Monto Fraude],
        'fraudes_comercios_no_seguros_features'[FLAG_MONTO_REDONDO] = 1
    ),
    [Monto Fraude]
)
-- Formato: 0.0%
```

```dax
Score Riesgo Promedio =
AVERAGE('fraudes_comercios_no_seguros_features'[SCORE_RIESGO_TRJ])
-- Formato: 0.00
```

```dax
% Saldo Agotado =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[FLAG_SALDO_AGOTADO] = 1
    ),
    [# Fraudes]
)
-- Formato: 0.0%
```

---

## PÁGINA 6 — Gestión de Casos

```dax
Días Promedio Cierre =
AVERAGE('fraudes_comercios_no_seguros_features'[DIAS_PARA_CIERRE])
-- Formato: 0.0
```

```dax
Casos Cerrados en 1 Día =
CALCULATE(
    COUNTROWS('fraudes_comercios_no_seguros_features'),
    'fraudes_comercios_no_seguros_features'[RANGO_DIAS_CIERRE] = "1_DIA"
)
```

```dax
% Casos Cerrados en 1 Semana =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[RANGO_DIAS_CIERRE] IN {"1_DIA", "1_SEMANA"}
    ),
    [# Fraudes]
)
-- Formato: 0.0%
```

```dax
Monto Pendiente Cierre =
CALCULATE(
    [Monto Fraude],
    'fraudes_comercios_no_seguros_features'[RANGO_DIAS_CIERRE] = "SIN_CIERRE"
)
```

---

## DIM_CALENDARIO — Tabla de fechas
-- Modelado → Nueva tabla (pegar todo el bloque)

```dax
dim_Calendario =
VAR FechaMin = MIN('fraudes_comercios_no_seguros_features'[DATETIME_TRX])
VAR FechaMax = MAX('fraudes_comercios_no_seguros_features'[DATETIME_TRX])
RETURN
ADDCOLUMNS(
    CALENDAR(FechaMin, FechaMax),
    "Año",           YEAR([Date]),
    "Mes Num",       MONTH([Date]),
    "Mes Nombre",    FORMAT([Date], "MMM", "es-PE"),
    "Día Semana",    WEEKDAY([Date], 2),
    "Día Nombre",    FORMAT([Date], "ddd", "es-PE"),
    "Semana ISO",    WEEKNUM([Date], 2),
    "Es Fin Semana", IF(WEEKDAY([Date], 2) >= 6, 1, 0),
    "Quincena",      IF(DAY([Date]) <= 15, "Q1", "Q2"),
    "Año-Mes",       FORMAT([Date], "YYYY-MM"),
    "Año Fiscal",    IF(MONTH([Date]) >= 11,
                        "FY" & YEAR([Date]) + 1,
                        "FY" & YEAR([Date]))
)
-- Después: relacionar dim_Calendario[Date] → tabla[DATETIME_TRX]
```

---

## NOTAS DE IMPLEMENTACIÓN

1. Las medidas que dicen "columna calculada" van en
   **Modelado → Nueva columna** (no en Nueva medida)

2. Para aplicar color condicional en barras:
   Visual → Formato → Colores de datos → fx → Valor de campo
   y seleccionar la medida Color Día

3. Para el mapa de calor (Matriz):
   - Visual: Matriz
   - Filas: HORA_DIA
   - Columnas: DIA_SEMANA_NOM (ordenado por Orden Día)
   - Valores: [# Fraudes]
   - Formato → Valores de celda → activar escala de colores
     Mínimo: #FFFFFF  |  Máximo: #C00000

4. Reemplaza 'fraudes_comercios_no_seguros_features' con el nombre
   exacto que tiene la tabla en tu modelo de Power BI

5. Ajusta los nombres de columna (IMPORTE, IMPORTE_USD, etc.)
   si en tu config.py pusiste nombres diferentes
