# Guía Completa — E-commerce Fraude
## Variables de Ingeniería + Medidas DAX + Cómo Usarlo en Power BI

---

## CONTEXTO: ¿Qué datos estamos analizando?

Antes de entender las variables, necesitas saber qué hay en el dataset:

- **Todo el dataset es fraude.** No hay transacciones legítimas. Cada fila es un caso de fraude confirmado.
- **Son comercios "no seguros"**, es decir, comercios de e-commerce que **no tienen 3DS** (también llamado 3D Secure o TDS). El 3DS es ese paso extra donde el banco te pide confirmar la compra por SMS o app. Si el comercio no lo tiene, el fraude es más fácil porque no hay esa barrera.
- **Fuente:** Reportes del CPF (Centro de Prevención del Fraude).
- **Uso:** Entender patrones de fraude para bloquear tarjetas, alertar comercios, y armar un dashboard de monitoreo.

---

## PARTE 1 — Variables de Ingeniería

### ¿Qué es "ingeniería de variables"?

Es construir columnas nuevas a partir de las que ya tienes. Por ejemplo, si tienes la fecha y hora de la transacción, puedes crear "es de madrugada = sí/no". Eso es ingeniería de variables.

El script `feature_engineering.py` toma tu parquet original y le agrega ~50 columnas nuevas. A continuación, cada una explicada.

---

### BLOQUE A — Fechas procesadas

| Variable | Tipo | Qué significa | Ejemplo |
|---|---|---|---|
| `DATETIME_TRX` | Fecha+hora | Fecha y hora exacta del fraude | `2025-07-02 17:18:49` |
| `DATETIME_CIERRE` | Fecha | Fecha en que el caso fue cerrado/investigado | `2025-08-10` |

**¿Para qué sirven?**
- `DATETIME_TRX` es la base de todas las variables temporales.
- `DATETIME_CIERRE` se usa para calcular cuánto tardó el equipo en cerrar el caso.

---

### BLOQUE B — Variables temporales

Estas columnas se derivan de `DATETIME_TRX`. Te dicen **cuándo** ocurrió el fraude.

| Variable | Tipo | Qué significa | Valores posibles | Ejemplo |
|---|---|---|---|---|
| `HORA_DIA` | Número (0-23) | Hora del fraude | 0 a 23 | `3` (madrugada) |
| `DIA_SEMANA` | Número (0-6) | Día de la semana | 0=Lunes … 6=Domingo | `6` (domingo) |
| `DIA_SEMANA_NOM` | Texto | Nombre del día | LUN, MAR, MIE, JUE, VIE, SAB, DOM | `"DOM"` |
| `MES` | Número (1-12) | Mes del fraude | 1 a 12 | `7` (julio) |
| `MES_NOM` | Texto | Nombre del mes | ENE, FEB, MAR… | `"JUL"` |
| `ANIO` | Número | Año del fraude | 2024, 2025… | `2025` |
| `FECHA_DIA` | Fecha | Solo la fecha (sin hora) | `2025-07-02` | Para agrupar por día |
| `SEMANA_ISO` | Número | Semana del año (1-53) | 1 a 53 | `27` |
| `ES_FIN_SEMANA` | Flag (0/1) | ¿Ocurrió sábado o domingo? | 0 = No, 1 = Sí | `1` |
| `QUINCENA` | Texto | Primera o segunda quincena | `"Q1"` (días 1-15), `"Q2"` (días 16-31) | `"Q1"` |
| `FRANJA_HORARIA` | Texto | Parte del día | MADRUGADA, MAÑANA, TARDE, NOCHE | `"MADRUGADA"` |
| `ES_MADRUGADA` | Flag (0/1) | ¿Entre 00:00 y 05:59? | 0 = No, 1 = Sí | `1` |
| `ES_HORARIO_LAB` | Flag (0/1) | ¿Lunes-Viernes entre 8am y 5pm? | 0 = No, 1 = Sí | `0` |

**Franjas horarias:**
- `MADRUGADA`: 00:00 – 05:59
- `MAÑANA`: 06:00 – 11:59
- `TARDE`: 12:00 – 18:59
- `NOCHE`: 19:00 – 23:59

**¿Qué nos dicen estas variables?**

> Si ves que el 40% de los fraudes son de madrugada (`ES_MADRUGADA = 1`), eso indica que son fraudes automatizados (bots). Los humanos no se levantan a las 3am a comprar. Un bot sí.

> Si el 60% caen en fin de semana (`ES_FIN_SEMANA = 1`), quiere decir que los defraudadores aprovechan que hay menos monitoreo en esos días.

**¿Puedo usarlas directamente en Power BI?** Sí. Son columnas de texto o número que puedes arrastrar a cualquier visual sin necesidad de DAX.

---

### BLOQUE C — Días de investigación

| Variable | Tipo | Qué significa | Ejemplo |
|---|---|---|---|
| `DIAS_PARA_CIERRE` | Número | Días entre el fraude y el cierre del caso | `15` (tardó 15 días) |
| `RANGO_DIAS_CIERRE` | Texto | Categoría del tiempo de cierre | `"1_SEMANA"` |

**Valores de `RANGO_DIAS_CIERRE`:**
- `1_DIA` → cerrado en 1 día o menos (muy rápido)
- `1_SEMANA` → entre 2 y 7 días
- `1_MES` → entre 8 y 30 días
- `MAS_1_MES` → más de 30 días (tardó mucho)
- `SIN_CIERRE` → sin fecha de cierre (aún abierto o sin dato)

**¿Qué nos dicen?**

> Si muchos casos están en `MAS_1_MES`, el equipo de investigación está tardando demasiado, lo que significa que el monto ya fue cobrado y es difícil de recuperar.

> Si la mayoría están en `SIN_CIERRE`, puede ser que el sistema de registro no está completo.

**¿Puedo usarlas directamente en Power BI?** Sí. En gráficos de barras o tablas directamente.

---

### BLOQUE D — Comportamiento de la tarjeta (historial total)

Estas variables responden a: **¿cuántas veces aparece esta tarjeta en el dataset?**

| Variable | Tipo | Qué significa | Ejemplo |
|---|---|---|---|
| `TOTAL_FRAUDES_TARJETA` | Número | Cuántos fraudes tiene esa tarjeta en todo el dataset | `5` (apareció 5 veces) |
| `MONTO_TOTAL_FRAUDE_TRJ` | Número | Suma total defraudada con esa tarjeta | `1,250.00` |
| `COMERCIOS_DISTINTOS_TRJ` | Número | En cuántos comercios distintos tuvo fraude | `3` |
| `MCC_DISTINTOS_TRJ` | Número | En cuántos rubros/MCC distintos tuvo fraude | `2` |
| `CANALES_DISTINTOS_TRJ` | Número | Por cuántos canales distintos (web, app, etc.) | `1` |
| `DIAS_ACTIVA_TRJ` | Número | En cuántos días distintos tuvo fraude | `2` (2 días diferentes) |
| `FRAUDES_TRJ_DIA` | Número | Fraudes de esa tarjeta en ESE DÍA específico | `3` |
| `MONTO_FRAUDE_TRJ_DIA` | Número | Monto defraudado ese día con esa tarjeta | `450.00` |
| `COMERCIOS_DISTINTOS_DIA` | Número | Comercios distintos ese día con esa tarjeta | `2` |

**Flags derivados:**

| Variable | Flag (0/1) | Significa | Cuándo se activa |
|---|---|---|---|
| `FLAG_TARJETA_REINCIDENTE` | 1 = Sí | La tarjeta apareció más de una vez | `TOTAL_FRAUDES_TARJETA > 1` |
| `FLAG_MULTI_COMERCIO_DIA` | 1 = Sí | Ese día la tarjeta usó 2+ comercios distintos | `COMERCIOS_DISTINTOS_DIA > 1` |
| `FLAG_RAFAGA_DIA` | 1 = Sí | Ese día la tarjeta tuvo 3 o más fraudes | `FRAUDES_TRJ_DIA >= 3` |

**¿Qué nos dicen?**

> `FLAG_TARJETA_REINCIDENTE = 1` significa que la tarjeta fue usada en fraude, nunca fue bloqueada, y volvió a ser usada. Alerta para el equipo de bloqueos.

> `FLAG_RAFAGA_DIA = 1` es una señal de fraude masivo: alguien (o un bot) usó la misma tarjeta 3 o más veces en un día. Típico de cuando clonan una tarjeta y la explotan al máximo antes de que la bloqueen.

> `FLAG_MULTI_COMERCIO_DIA = 1` indica que ese día la tarjeta fue a 2 comercios distintos. Patrón común: primero prueban con montos pequeños, luego hacen la compra grande.

**¿Puedo usarlas directamente en Power BI?** Sí. Los flags (0/1) se usan en filtros y como segmentadores. Los números se usan en tablas y scatter plots.

---

### BLOQUE D2 — Ventanas temporales deslizantes (variables más avanzadas)

Estas son las variables más potentes del script. Para **cada transacción**, calculan cuántas transacciones previas y cuánto monto acumuló esa tarjeta en las N horas/minutos anteriores a ese fraude.

**Importante:** "previas" significa las que ocurrieron ANTES de esa transacción. Si la tarjeta X hizo fraudes a las 10:00, 10:05 y 10:15, la fila de las 10:15 tendrá `TXN_CARD_1H = 2` (porque las dos anteriores caen dentro de la última hora).

#### Variables de conteo (¿cuántas transacciones previas?):

| Variable | Ventana | Qué mide | Señal de alerta |
|---|---|---|---|
| `TXN_CARD_2M` | 2 minutos | Fraudes previos de esa tarjeta en los últimos 2 min | ≥ 1 = sospechoso |
| `TXN_CARD_5M` | 5 minutos | Fraudes previos en los últimos 5 min | ≥ 2 = alerta |
| `TXN_CARD_10M` | 10 minutos | Fraudes previos en los últimos 10 min | ≥ 2 = alerta |
| `TXN_CARD_1H` | 1 hora | Fraudes previos en la última hora | ≥ 3 = crítico |
| `TXN_CARD_24H` | 24 horas | Fraudes previos en las últimas 24 horas | ≥ 5 = crítico |

#### Variables de monto acumulado (¿cuánto dinero previo?):

| Variable | Ventana | Qué mide | Ejemplo |
|---|---|---|---|
| `AMT_CARD_1H` | 1 hora | Monto total de fraudes previos en la última hora | `320.00` (ya robaron 320 antes de este fraude) |
| `AMT_CARD_24H` | 24 horas | Monto total de fraudes previos en las últimas 24 horas | `850.00` |

#### Flags derivados de las ventanas:

| Variable | Flag (0/1) | Se activa cuando |
|---|---|---|
| `FLAG_VEL_ALTA_1H` | 1 = Sí | La tarjeta ya tuvo 2 o más fraudes en la hora previa |
| `FLAG_VEL_ALTA_10M` | 1 = Sí | La tarjeta ya tuvo 2 o más fraudes en los últimos 10 minutos |
| `FLAG_ACUM_ALTO_1H` | 1 = Sí | El monto acumulado en 1 hora ya duplica el monto de este fraude |

**¿Qué nos dicen estas variables?**

> **Ejemplo real:** Una tarjeta hace 4 fraudes entre las 10:00 y 10:45. Para el cuarto fraude (10:45), el script registrará:
> - `TXN_CARD_1H = 3` (hubo 3 fraudes previos en esa hora)
> - `AMT_CARD_1H = 750` (ya habían robado 750 en esa hora)
> - `FLAG_VEL_ALTA_1H = 1` (sí, hubo velocidad alta)
>
> Esto te dice que esa tarjeta estaba siendo explotada activamente. Si el banco hubiera bloqueado en el segundo fraude, los dos últimos no habrían ocurrido.

> `TXN_CARD_2M >= 1` es señal de BOT: ningún humano hace dos compras separadas con la misma tarjeta en menos de 2 minutos. Eso es automatizado.

**¿Puedo usarlas directamente en Power BI?**

- `TXN_CARD_*` y `AMT_CARD_*`: Sí, en histogramas, tablas, y como ejes de gráficos.
- Los flags `FLAG_VEL_ALTA_*`: Sí, como filtros y en KPI cards con DAX (ver Parte 2).
- Para el **% de fraudes con velocidad alta**, necesitas DAX (ver medidas de Página 2).

---

### BLOQUE D2 — Variables de saldo

| Variable | Tipo | Qué significa | Ejemplo |
|---|---|---|---|
| `RATIO_MONTO_VS_SALDO` | Decimal (0-1+) | Monto del fraude ÷ saldo disponible de la tarjeta | `0.95` (usaron el 95% del saldo) |
| `FLAG_SALDO_AGOTADO` | Flag (0/1) | El fraude usó el 90% o más del saldo disponible | `1` = sí |

**¿Qué nos dicen?**

> `FLAG_SALDO_AGOTADO = 1` significa que el defraudador fue al límite: usó casi todo el saldo de la tarjeta. Patrón típico de "última compra antes de que la bloqueen". Alta urgencia para investigación.

---

### BLOQUE E — Perfil del comercio y del MCC

Estas variables describen **al comercio** donde ocurrió el fraude, no a la tarjeta.

| Variable | Tipo | Qué significa | Ejemplo |
|---|---|---|---|
| `TOTAL_FRAUDES_COMERCIO` | Número | Total de fraudes en ese comercio en todo el dataset | `85` |
| `MONTO_TOTAL_FRAUDE_COM` | Número | Monto total defraudado en ese comercio | `42,500.00` |
| `MONTO_PROM_FRAUDE_COM` | Número | Ticket promedio de fraude en ese comercio | `500.00` |
| `TARJETAS_DISTINTAS_COM` | Número | Cuántas tarjetas distintas tuvieron fraude ahí | `60` |
| `CANALES_DISTINTOS_COM` | Número | Por cuántos canales llegaron los fraudes | `2` |
| `DIAS_CON_FRAUDE_COM` | Número | Cuántos días distintos tuvo al menos un fraude | `30` |
| `FRAUDES_COM_DIA` | Número | Cuántos fraudes tuvo ese comercio en ESE DÍA | `5` |
| `RANKING_COMERCIO` | Número | Posición del comercio por # fraudes (1 = el más golpeado) | `3` |

**Variables del MCC (rubro del comercio):**

| Variable | Tipo | Qué significa | Ejemplo |
|---|---|---|---|
| `TOTAL_FRAUDES_MCC` | Número | Total de fraudes en ese rubro | `320` |
| `MONTO_TOTAL_MCC` | Número | Monto total defraudado en ese rubro | `160,000.00` |
| `COMERCIOS_EN_MCC` | Número | Cuántos comercios distintos tiene ese rubro | `12` |
| `TARJETAS_EN_MCC` | Número | Cuántas tarjetas distintas afectadas en ese rubro | `240` |
| `RANKING_MCC` | Número | Posición del rubro por # fraudes (1 = el más golpeado) | `1` |

**¿Qué nos dicen?**

> `RANKING_COMERCIO = 1` es el comercio más golpeado. Si además tiene `MONTO_PROM_FRAUDE_COM` alto, es un comercio de alto riesgo por monto. Si tiene `MONTO_PROM_FRAUDE_COM` bajo pero muchos fraudes, es probablemente card testing (prueban tarjetas con montos pequeños).

> `RANKING_MCC = 1` te dice qué rubro (tipo de negocio) concentra más fraude. En e-commerce sin 3DS suele ser retail, streaming, o digital goods.

**¿Puedo usarlas directamente en Power BI?** Sí. En rankings, barras horizontales, scatter plots. El `RANKING_COMERCIO` te ayuda a ordenar tablas.

---

### BLOQUE F — Señales de monto

| Variable | Tipo | Qué significa | Ejemplo |
|---|---|---|---|
| `FLAG_MONTO_REDONDO` | Flag (0/1) | El monto es un número entero exacto (sin centavos) | `1` si monto = 100.00 |
| `DESVIO_MONTO_VS_COM` | Número | Diferencia entre el monto y el promedio del comercio | `+350` (350 más que el promedio) |
| `RATIO_MONTO_VS_COM` | Decimal | Monto ÷ promedio del comercio | `1.7` (70% más que el promedio) |
| `RANGO_MONTO` | Texto | Categoría del monto según cuartiles | BAJO, MEDIO_BAJO, MEDIO_ALTO, ALTO |
| `TIPO_CAMBIO_IMPLICITO` | Decimal | Monto local ÷ monto en dólares (tasa implícita) | `3.72` |

**¿Qué nos dicen?**

> `FLAG_MONTO_REDONDO = 1` es una señal clásica de **card testing**: los bots usan montos exactos (50.00, 100.00, 200.00) porque así son más fáciles de programar. En comercios legítimos, los montos casi nunca son exactamente redondos.

> `RATIO_MONTO_VS_COM > 2.0` significa que ese fraude fue el doble del promedio de ese comercio. Outlier sospechoso: o fue una compra grande legítima que resultó fraude, o el defraudador escaló el monto.

> `RANGO_MONTO = "BAJO"` combinado con `FLAG_MONTO_REDONDO = 1` es el patrón más típico de card testing: montos pequeños y redondos para verificar si la tarjeta funciona.

**¿Puedo usarlas directamente en Power BI?**
- `FLAG_MONTO_REDONDO`: Sí, como filtro o en KPI con DAX.
- `RANGO_MONTO`: Sí, como segmentador (slicer) o eje de gráfico de barras.
- `RATIO_MONTO_VS_COM`: Sí, en tablas o scatter para ver outliers.

---

### BLOQUE G — Score de riesgo compuesto

Esta es la variable "resumen" que combina todas las señales anteriores.

| Variable | Tipo | Qué significa | Valores |
|---|---|---|---|
| `SCORE_RIESGO_TRJ` | Número (0-6) | Suma de 6 flags de riesgo | 0 = sin señales, 6 = todas las señales activas |
| `PERFIL_RIESGO` | Texto | Categoría del score | BAJO, MEDIO, ALTO, MUY_ALTO |
| `FLAG_CVV_ESTATICO` | Flag (0/1) | La tarjeta NO tiene CVV dinámico (menos segura) | 1 = CVV estático |
| `FLAG_HORARIO_RIESGO` | Flag (0/1) | Ocurrió en madrugada O fin de semana | 1 = Sí |

**Los 6 componentes del score:**
1. `FLAG_TARJETA_REINCIDENTE` — tarjeta usada más de una vez
2. `FLAG_MULTI_COMERCIO_DIA` — varios comercios en el mismo día
3. `FLAG_RAFAGA_DIA` — 3+ fraudes ese día
4. `FLAG_MONTO_REDONDO` — monto exacto (card testing)
5. `ES_MADRUGADA` — ocurrió entre 00:00 y 06:00
6. `FLAG_CVV_ESTATICO` — tarjeta sin CVV dinámico

**Clasificación del perfil:**
- `BAJO` → Score = 0 (ninguna señal)
- `MEDIO` → Score = 1
- `ALTO` → Score = 2
- `MUY_ALTO` → Score = 3 o más

**¿Qué nos dicen?**

> Una tarjeta con `PERFIL_RIESGO = "MUY_ALTO"` tiene 3 o más señales de alerta activas al mismo tiempo. Por ejemplo: es reincidente, hizo fraude de madrugada, y el monto fue redondo. Prioridad máxima para bloqueo.

> `SCORE_RIESGO_TRJ = 0` no significa que NO sea fraude (recuerda: todo el dataset es fraude). Significa que ese fraude no muestra patrones automatizados, puede ser fraude manual o con datos robados simples.

**¿Puedo usarlas directamente en Power BI?**
- `PERFIL_RIESGO`: Sí, como slicer y eje de gráfico de barras (usa la columna calculada `Orden Perfil` en DAX para ordenarlas correctamente).
- `SCORE_RIESGO_TRJ`: Sí, en tablas con formato condicional (verde → amarillo → rojo).
- Para porcentajes de cada perfil necesitas DAX (ver Parte 2).

---

## PARTE 2 — Medidas DAX para Power BI

### ¿Qué es una medida DAX?

Una medida DAX es un cálculo que haces dentro de Power BI. A diferencia de las columnas (que calculan un valor por fila), las medidas calculan sobre el contexto del visual: si filtraste por julio, la medida calcula solo julio.

**Cómo crearlas:** Power BI → Modelado → Nueva medida → pegar el código DAX.

> **Nombre de tabla:** En todos los ejemplos abajo la tabla se llama `fraudes_comercios_no_seguros_features`. Reemplaza ese nombre con el que aparezca en tu modelo de Power BI.

---

### BLOQUE 1 — Medidas BASE (todas las páginas las usan)

Estas son las medidas más simples. Son la base de todo. Créalas primero.

| Nombre DAX | Qué calcula | Formato sugerido |
|---|---|---|
| `# Fraudes` | Cuenta de filas (total de fraudes) | `#,##0` |
| `Monto Fraude` | Suma del campo IMPORTE | `#,##0.00` |
| `Monto Fraude USD` | Suma del campo IMPORTE_USD | `#,##0.00` |
| `Ticket Promedio` | Monto Fraude ÷ # Fraudes | `#,##0.00` |
| `Tarjetas Únicas` | Conteo distinto de TARJETA | `#,##0` |
| `Comercios Únicos` | Conteo distinto de COMERCIO_ID | `#,##0` |
| `MCC Únicos` | Conteo distinto de MCC | `#,##0` |
| `Monto Promedio por Tarjeta` | Monto Fraude ÷ Tarjetas Únicas | `#,##0.00` |

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
DIVIDE([Monto Fraude], [# Fraudes])
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
DIVIDE([Monto Fraude], [Tarjetas Únicas])
```

---

### BLOQUE 2 — Medidas de PARTICIPACIÓN y COMPARACIÓN

Estas miden qué tan concentrado está el fraude en un elemento específico.

| Nombre DAX | Qué calcula | Cuándo usarla |
|---|---|---|
| `% Participación Monto` | % del total general | KPI cards, barras con etiqueta |
| `% Participación Comercio` | % dentro del mes | Página 3 - Comercios |
| `% Top 10 Comercios` | Concentración de riesgo | KPI card Página 3 |
| `Variación Monto MoM` | Cambio mes a mes | Evolutivo mensual |

```dax
% Participación Monto =
DIVIDE(
    [Monto Fraude],
    CALCULATE([Monto Fraude], ALL('fraudes_comercios_no_seguros_features'))
)
```
> **Interpreta así:** Si ves 23% en un comercio, ese comercio representa el 23% de todo el monto defraudado en el dataset.

```dax
% Participación Comercio =
DIVIDE(
    [Monto Fraude],
    CALCULATE([Monto Fraude], ALLEXCEPT(
        'fraudes_comercios_no_seguros_features',
        'fraudes_comercios_no_seguros_features'[MES]
    ))
)
```

```dax
% Top 10 Comercios =
VAR top10 =
    TOPN(
        10,
        VALUES('fraudes_comercios_no_seguros_features'[COMERCIO_ID]),
        CALCULATE([Monto Fraude]),
        DESC
    )
VAR monto_top10 =
    CALCULATE([Monto Fraude], KEEPFILTERS(top10))
RETURN
    DIVIDE(
        monto_top10,
        CALCULATE([Monto Fraude], ALL('fraudes_comercios_no_seguros_features'))
    )
```
> **Interpreta así:** Si sale 65%, los 10 comercios más golpeados concentran el 65% del fraude total. Si ese número es muy alto (>70%), el problema está focalizado y es más fácil de atacar.

```dax
Variación Monto MoM =
VAR mes_actual =
    CALCULATE([Monto Fraude], DATESMTD(dim_Calendario[Date]))
VAR mes_anterior =
    CALCULATE([Monto Fraude], DATEADD(DATESMTD(dim_Calendario[Date]), -1, MONTH))
RETURN
    DIVIDE(mes_actual - mes_anterior, mes_anterior)
```
> Formato: `+0.0%;-0.0%`

---

### BLOQUE 3 — Medidas TEMPORALES (Página 2 — Análisis Temporal)

Responden a la pregunta: **¿cuándo ocurre el fraude?**

| Nombre DAX | Qué calcula | Visual sugerido |
|---|---|---|
| `Hora Pico` | La hora del día con más fraudes | KPI card (muestra "3:00 hrs") |
| `Día Pico` | El día de la semana con más fraudes | KPI card |
| `% Madrugada` | % de fraudes entre 00:00 y 05:59 | KPI card |
| `% Fin de Semana` | % de fraudes sábado y domingo | KPI card |
| `% Horario Laboral` | % de fraudes en horario de trabajo | KPI card |
| `% Monto Alertado` | % del monto con CVV dinámico activo | KPI card |

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
% Madrugada =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[FRANJA_HORARIA] = "MADRUGADA"
    ),
    [# Fraudes]
)
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
```

```dax
% Monto Alertado =
DIVIDE(
    CALCULATE(
        [Monto Fraude],
        'fraudes_comercios_no_seguros_features'[CVV_DINAMICO] = "S"
    ),
    [Monto Fraude]
)
```

#### Medidas de ventanas temporales (Página 2)

```dax
% Velocidad Alta 1H =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[FLAG_VEL_ALTA_1H] = 1
    ),
    [# Fraudes]
)
```
> **Interpreta así:** Si sale 18%, el 18% de los fraudes ocurrieron cuando esa tarjeta ya había tenido 2 o más fraudes en la hora previa. Son los casos más urgentes de bloquear.

```dax
% Velocidad Alta 10 Min =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[FLAG_VEL_ALTA_10M] = 1
    ),
    [# Fraudes]
)
```
> **Interpreta así:** % de fraudes que ocurrieron con otra transacción de la misma tarjeta en los últimos 10 minutos. Alta señal de automatización (bot).

#### Columnas calculadas para ordenar (Modelado → Nueva columna, NO medida)

```dax
Orden Día =
SWITCH('fraudes_comercios_no_seguros_features'[DIA_SEMANA_NOM],
    "LUN", 1, "MAR", 2, "MIE", 3, "JUE", 4,
    "VIE", 5, "SAB", 6, "DOM", 7, 7)
```
> Luego: clic en `DIA_SEMANA_NOM` → Ordenar por columna → `Orden Día`

```dax
Orden Franja =
SWITCH('fraudes_comercios_no_seguros_features'[FRANJA_HORARIA],
    "MADRUGADA", 1, "MAÑANA", 2, "TARDE", 3, "NOCHE", 4, 5)
```

```dax
Color Día =
IF(
    MAX('fraudes_comercios_no_seguros_features'[ES_FIN_SEMANA]) = 1,
    "#E63946",
    "#1D3557"
)
```
> Rojo para fin de semana, azul oscuro para días de semana. Usar en: Formato del visual → Color de datos → fx → Valor de campo.

---

### BLOQUE 4 — Medidas de COMERCIOS y MCC (Página 3)

Responden a: **¿en qué comercios y rubros se concentra el fraude?**

| Nombre DAX | Qué calcula | Visual sugerido |
|---|---|---|
| `Top Comercio` | Nombre del comercio con más monto | KPI card |
| `Top MCC` | Código MCC con más monto | KPI card |
| `Monto Promedio por Comercio` | Monto ÷ Comercios | KPI card |
| `Tarjetas por Comercio` | Tarjetas ÷ Comercios | KPI card |
| `Días con Fraude` | Días distintos con fraude | Tabla |
| `Ticket Mínimo` / `Ticket Máximo` | Menor y mayor fraude | Tabla |
| `% Ráfaga en Comercio` | % fraudes de tarjetas en ráfaga | Tabla, formato condicional |
| `% Monto Redondo en Comercio` | % fraudes con monto exacto | Tabla, formato condicional |
| `Fraudes por Tarjeta en Comercio` | Fraudes ÷ Tarjetas | Tabla |

```dax
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
Monto Promedio por Comercio =
DIVIDE([Monto Fraude], [Comercios Únicos])
```

```dax
Tarjetas por Comercio =
DIVIDE([Tarjetas Únicas], [Comercios Únicos])
```

```dax
Días con Fraude =
DISTINCTCOUNT('fraudes_comercios_no_seguros_features'[FECHA_DIA])
```

```dax
Ticket Mínimo =
MIN('fraudes_comercios_no_seguros_features'[IMPORTE])
```

```dax
Ticket Máximo =
MAX('fraudes_comercios_no_seguros_features'[IMPORTE])
```

```dax
% Ráfaga en Comercio =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[FLAG_RAFAGA_DIA] = 1
    ),
    [# Fraudes]
)
```
> **Interpreta así:** 40% → 4 de cada 10 fraudes en ese comercio vinieron de tarjetas que ese mismo día ya habían tenido 3 o más fraudes en total. El comercio está siendo usado en operaciones masivas.

```dax
% Monto Redondo en Comercio =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[FLAG_MONTO_REDONDO] = 1
    ),
    [# Fraudes]
)
```
> **Interpreta así:** Si > 20%, ese comercio está siendo usado para **card testing** (probar si tarjetas clonadas funcionan con montos exactos como 50.00 o 100.00).

```dax
Fraudes por Tarjeta en Comercio =
DIVIDE(
    [# Fraudes],
    CALCULATE(DISTINCTCOUNT('fraudes_comercios_no_seguros_features'[TARJETA]))
)
```
> **Interpreta así:** 5.0 → cada tarjeta en ese comercio tuvo en promedio 5 fraudes. Valor alto = ataque concentrado con pocas tarjetas pero muchos intentos.

```dax
Color Comercio Riesgo =
VAR promedio_fraudes =
    AVERAGEX(
        VALUES('fraudes_comercios_no_seguros_features'[COMERCIO_ID]),
        CALCULATE([# Fraudes])
    )
VAR fraudes_actual = [# Fraudes]
RETURN
    IF(fraudes_actual > promedio_fraudes * 2, "#C00000",
    IF(fraudes_actual > promedio_fraudes,     "#FF8C00",
                                             "#1D6F42"))
```
> Rojo = muy por encima del promedio, Naranja = sobre promedio, Verde = bajo promedio.

---

### BLOQUE 5 — Medidas de TARJETAS (Página 4)

Responden a: **¿cómo son las tarjetas afectadas?**

| Nombre DAX | Qué calcula |
|---|---|
| `% Tarjetas Reincidentes` | % de tarjetas con 2+ fraudes |
| `% Ráfaga (3+ fraudes/día)` | % de fraudes donde la tarjeta ya tenía 3+ ese día |
| `% Multi Comercio en un Día` | % de fraudes con tarjeta en 2+ comercios ese día |
| `Monto Promedio por Tarjeta` | Monto ÷ Tarjetas |
| `Tarjetas Reincidentes` | Conteo de tarjetas reincidentes |
| `Comercios Prom por Tarjeta` | Promedio de comercios por tarjeta |
| `Fraudes Prom por Tarjeta` | Fraudes ÷ Tarjetas |
| `% Crédito` / `% Débito` | Distribución por tipo |
| `Score Riesgo Promedio Tarjetas` | Promedio del score 0-6 por tarjeta |
| `% Tarjetas MUY ALTO Riesgo` | % de tarjetas con perfil MUY_ALTO |
| `Monto Tarjetas MUY ALTO` | Monto de tarjetas MUY_ALTO |

```dax
% Tarjetas Reincidentes =
DIVIDE(
    CALCULATE(
        [Tarjetas Únicas],
        'fraudes_comercios_no_seguros_features'[FLAG_TARJETA_REINCIDENTE] = 1
    ),
    [Tarjetas Únicas]
)
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
```

```dax
Comercios Prom por Tarjeta =
AVERAGEX(
    VALUES('fraudes_comercios_no_seguros_features'[TARJETA]),
    CALCULATE(
        DISTINCTCOUNT('fraudes_comercios_no_seguros_features'[COMERCIO_ID])
    )
)
```

```dax
Fraudes Prom por Tarjeta =
DIVIDE([# Fraudes], [Tarjetas Únicas])
```

```dax
% Crédito =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[TIPO_TARJETA] = "CREDITO"
    ),
    [# Fraudes]
)
```

```dax
% Débito =
DIVIDE(
    CALCULATE(
        COUNTROWS('fraudes_comercios_no_seguros_features'),
        'fraudes_comercios_no_seguros_features'[TIPO_TARJETA] = "DEBITO"
    ),
    [# Fraudes]
)
```

```dax
Score Riesgo Promedio Tarjetas =
AVERAGEX(
    VALUES('fraudes_comercios_no_seguros_features'[TARJETA]),
    CALCULATE(
        AVERAGE('fraudes_comercios_no_seguros_features'[SCORE_RIESGO_TRJ])
    )
)
```

```dax
% Tarjetas MUY ALTO Riesgo =
DIVIDE(
    CALCULATE(
        [Tarjetas Únicas],
        'fraudes_comercios_no_seguros_features'[PERFIL_RIESGO] = "MUY_ALTO"
    ),
    [Tarjetas Únicas]
)
```

```dax
Monto Tarjetas MUY ALTO =
CALCULATE(
    [Monto Fraude],
    'fraudes_comercios_no_seguros_features'[PERFIL_RIESGO] = "MUY_ALTO"
)
```

```dax
Color Tipo Tarjeta =
SWITCH(
    MAX('fraudes_comercios_no_seguros_features'[TIPO_TARJETA]),
    "CREDITO", "#C00000",
    "DEBITO",  "#1D6F42",
    "#808080"
)
```

```dax
Orden Perfil =
SWITCH('fraudes_comercios_no_seguros_features'[PERFIL_RIESGO],
    "BAJO", 1, "MEDIO", 2, "ALTO", 3, "MUY_ALTO", 4, 5)
```
> Columna calculada (no medida). Luego: clic en `PERFIL_RIESGO` → Ordenar por columna → `Orden Perfil`

---

### BLOQUE 6 — Medidas ACCIONABLES (Página 5)

Estas son las métricas que el equipo de fraude usa para tomar decisiones inmediatas.

| Nombre DAX | Qué calcula | Señal de alerta |
|---|---|---|
| `Tarjetas MUY ALTO Riesgo` | Conteo de tarjetas críticas | Listar para bloqueo |
| `% CVV Estático` | % de fraudes sin CVV dinámico | > 50% = vulnerabilidad estructural |
| `% Monto Redondo` | % de montos exactos | > 20% = card testing activo |
| `Score Riesgo Promedio` | Promedio del score 0-6 | > 3 = operación masiva |
| `% Saldo Agotado` | % de fraudes que usaron 90%+ del saldo | > 10% = defraudadores agresivos |

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
```

```dax
Score Riesgo Promedio =
AVERAGE('fraudes_comercios_no_seguros_features'[SCORE_RIESGO_TRJ])
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
```

---

### BLOQUE 7 — Medidas de GESTIÓN DE CASOS (Página 6)

Estas miden la eficiencia del equipo de investigación.

| Nombre DAX | Qué calcula |
|---|---|
| `Días Promedio Cierre` | Promedio de días para cerrar un caso |
| `Casos Cerrados en 1 Día` | Conteo de casos cerrados en ≤1 día |
| `% Casos Cerrados en 1 Semana` | % de casos cerrados en ≤7 días |
| `Monto Pendiente Cierre` | Monto de casos aún sin cerrar |

```dax
Días Promedio Cierre =
AVERAGE('fraudes_comercios_no_seguros_features'[DIAS_PARA_CIERRE])
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
```

```dax
Monto Pendiente Cierre =
CALCULATE(
    [Monto Fraude],
    'fraudes_comercios_no_seguros_features'[RANGO_DIAS_CIERRE] = "SIN_CIERRE"
)
```

---

### BLOQUE 8 — Tabla de Fechas (dim_Calendario)

Esta tabla es necesaria para las medidas de comparación temporal (MoM, evolutivos).

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
```
> Crear como: Modelado → Nueva tabla (pegar todo el bloque)
> Después: relacionar `dim_Calendario[Date]` → `tabla[DATETIME_TRX]`

---

## PARTE 3 — ¿Columna directo o necesito DAX?

Guía rápida para saber cómo usar cada variable en Power BI.

### Variables que puedes usar DIRECTAMENTE (arrastrar al visual)

| Variable | Cómo usarla |
|---|---|
| `HORA_DIA` | Eje X del mapa de calor, histograma de horas |
| `DIA_SEMANA_NOM` | Eje X de gráfico de barras (ordenar con `Orden Día`) |
| `FRANJA_HORARIA` | Eje X de barras (ordenar con `Orden Franja`) |
| `MES_NOM` | Eje X de evolutivo mensual |
| `ES_FIN_SEMANA` | Filtro/slicer (0/1) |
| `ES_MADRUGADA` | Filtro/slicer (0/1) |
| `QUINCENA` | Slicer o eje de barras |
| `RANGO_DIAS_CIERRE` | Eje de barras (Página 6) |
| `PERFIL_RIESGO` | Slicer, eje de barras (ordenar con `Orden Perfil`) |
| `RANGO_MONTO` | Slicer, eje de barras |
| `TIPO_TARJETA` | Eje de donut o barras |
| `NIVEL_TARJETA` | Eje de barras |
| `SEGMENTO` | Slicer o eje de barras |
| `SCORE_RIESGO_TRJ` | Columna de tabla (con formato condicional) |
| `DIAS_ACTIVA_TRJ` | Columna de tabla |
| `TXN_CARD_1H`, `TXN_CARD_24H` | Columnas de tabla (con formato condicional naranja) |
| `AMT_CARD_1H`, `AMT_CARD_24H` | Columnas de tabla (con formato condicional naranja) |
| `TOTAL_FRAUDES_TARJETA` | Columna de tabla |
| `RANKING_COMERCIO` | Para ordenar tablas de comercios |
| `RANKING_MCC` | Para ordenar tablas de MCC |
| `RATIO_MONTO_VS_COM` | Columna de tabla para ver outliers |

### Variables que NECESITAN DAX para ser útiles en un visual

| Variable | Por qué necesitas DAX | Medida DAX a usar |
|---|---|---|
| `FLAG_*` (cualquier flag) | Para sacar el % sobre el total | `% Ráfaga en Comercio`, `% CVV Estático`, etc. |
| `ES_FIN_SEMANA` | Para el % que representa | `% Fin de Semana` |
| `FRANJA_HORARIA` | Para la hora pico (texto dinámico) | `Hora Pico` |
| `DIA_SEMANA_NOM` | Para el día pico (texto dinámico) | `Día Pico` |
| `PERFIL_RIESGO` | Para el % de tarjetas MUY_ALTO | `% Tarjetas MUY ALTO Riesgo` |
| `SCORE_RIESGO_TRJ` | Para el promedio ponderado por tarjeta | `Score Riesgo Promedio Tarjetas` |
| `COMERCIO_ID` | Para la concentración Top 10 | `% Top 10 Comercios` |
| `IMPORTE` | Para totales, promedios, comparativos | `Monto Fraude`, `Ticket Promedio`, etc. |
| `DIAS_PARA_CIERRE` | Para el promedio de cierre | `Días Promedio Cierre` |

---

## PARTE 4 — Cómo organizar las medidas DAX en Power BI

Para mantener el modelo ordenado, crea una **tabla vacía solo para medidas**:

1. Power BI → Modelado → Nueva tabla
2. Escribe: `_Medidas = {""}`
3. Elimina la columna automática que crea
4. Crea todas tus medidas dentro de esa tabla `_Medidas`

Organiza las medidas en carpetas dentro de la tabla:

```
_Medidas/
├── 00_BASE/         → # Fraudes, Monto Fraude, Ticket Promedio…
├── 01_EJECUTIVO/    → % Participación, Variación MoM…
├── 02_TEMPORAL/     → Hora Pico, % Madrugada, % Fin de Semana…
├── 03_COMERCIOS/    → Top Comercio, % Ráfaga, % Monto Redondo…
├── 04_TARJETAS/     → % Reincidentes, Score Promedio…
├── 05_ACCIONABLE/   → Tarjetas MUY ALTO, % CVV Estático…
├── 06_GESTION/      → Días Promedio Cierre, % Cerrados 1 Semana…
└── _COLORES/        → Color Día, Color Comercio Riesgo…
```

Para crear carpeta: clic en una medida → en el panel derecho, campo "Carpeta de presentación" → escribe el nombre.

---

## RESUMEN RÁPIDO — Señales de alerta más importantes

| Señal | Variable o medida | Umbral de alerta |
|---|---|---|
| Bot / automatización | `TXN_CARD_2M >= 1` o `FLAG_VEL_ALTA_10M = 1` | ≥ 1 transacción en 2 min |
| Tarjeta explotada activamente | `FLAG_VEL_ALTA_1H = 1` | 2+ fraudes en la última hora |
| Card testing | `FLAG_MONTO_REDONDO = 1` + `RANGO_MONTO = BAJO` | Montos pequeños exactos |
| Comercio en operación masiva | `% Ráfaga en Comercio` | > 25% |
| Comercio usado para card testing | `% Monto Redondo en Comercio` | > 20% |
| Tarjeta sin bloquear | `FLAG_TARJETA_REINCIDENTE = 1` | Cualquier valor = 1 |
| Defraudador agresivo | `FLAG_SALDO_AGOTADO = 1` | Cualquier valor = 1 |
| Concentración de riesgo | `% Top 10 Comercios` | > 60% |
| Vulnerabilidad de tarjetas | `% CVV Estático` | > 50% |
| Prioridad para bloqueo | `PERFIL_RIESGO = "MUY_ALTO"` | Tarjetas con score ≥ 3 |
