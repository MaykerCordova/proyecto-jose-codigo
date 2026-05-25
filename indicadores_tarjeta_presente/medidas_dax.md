# Medidas DAX — Matriz BIN x Indicador (Tarjeta Presente)

Tabla fuente: `historico_tp_consolidado`
Columna de filas en la matriz: `ACF BIN`

---

## Aprobadas

```dax
Aprobadas =
COUNTROWS(
    FILTER(
        'historico_tp_consolidado',
        'historico_tp_consolidado'[CODIGO DE RESPUESTA VISION PLUS] IN {"0", "00", "000"}
    )
)
```

## Declinadas

```dax
Declinadas =
COUNTROWS(
    FILTER(
        'historico_tp_consolidado',
        NOT('historico_tp_consolidado'[CODIGO DE RESPUESTA VISION PLUS] IN {"0", "00", "000"})
    )
)
```

## Tasa de Aprobación
_Formatear como porcentaje en Power BI._

```dax
Tasa Aprobacion =
DIVIDE([Aprobadas], [Aprobadas] + [Declinadas])
```

## Tasa de Declinación
_Formatear como porcentaje en Power BI._

```dax
Tasa Declinacion =
DIVIDE([Declinadas], [Aprobadas] + [Declinadas])
```

## Declinaciones por códigos de interés (59 / 63)

```dax
Declinaciones 59-63 =
COUNTROWS(
    FILTER(
        'historico_tp_consolidado',
        'historico_tp_consolidado'[CODIGO DE RESPUESTA VISION PLUS] IN {"59", "63"}
    )
)
```

## Fraude

```dax
Fraude =
COUNTROWS(
    FILTER(
        'historico_tp_consolidado',
        'historico_tp_consolidado'[INDICADOR DE FRAUDE] = "F"
    )
)
```

## Alertas
_Pendiente: confirmar lógica de cálculo._
