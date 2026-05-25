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

## Monto Aprobado Local
_Suma el monto en moneda local de las transacciones aprobadas y locales._
_Ajustar nombres de columna según como aparezcan en Power BI._

```dax
Monto Aprobado Local =
CALCULATE(
    SUMX(
        'historico_tp_consolidado',
        'historico_tp_consolidado'[MONTO MONEDA LOCAL]
    ),
    'historico_tp_consolidado'[CODIGO DE RESPUESTA VISION PLUS] IN {"0", "00", "000"},
    'historico_tp_consolidado'[MONTO ORIGINAL DE LA TRANSACCION]
        = 'historico_tp_consolidado'[MONTO MONEDA LOCAL]
)
```

## Monto Declinado Local
_Suma el monto en moneda local de las transacciones declinadas y locales._

```dax
Monto Declinado Local =
CALCULATE(
    SUMX(
        'historico_tp_consolidado',
        'historico_tp_consolidado'[MONTO MONEDA LOCAL]
    ),
    NOT('historico_tp_consolidado'[CODIGO DE RESPUESTA VISION PLUS] IN {"0", "00", "000"}),
    'historico_tp_consolidado'[MONTO ORIGINAL DE LA TRANSACCION]
        = 'historico_tp_consolidado'[MONTO MONEDA LOCAL]
)
```

## Monto Aprobado Dólar
_Suma el monto en dólar de las transacciones aprobadas y en dólar._

```dax
Monto Aprobado Dolar =
CALCULATE(
    SUMX(
        'historico_tp_consolidado',
        'historico_tp_consolidado'[MONTO DOLAR]
    ),
    'historico_tp_consolidado'[CODIGO DE RESPUESTA VISION PLUS] IN {"0", "00", "000"},
    'historico_tp_consolidado'[MONTO ORIGINAL DE LA TRANSACCION]
        = 'historico_tp_consolidado'[MONTO DOLAR]
)
```

## Monto Declinado Dólar
_Suma el monto en dólar de las transacciones declinadas y en dólar._

```dax
Monto Declinado Dolar =
CALCULATE(
    SUMX(
        'historico_tp_consolidado',
        'historico_tp_consolidado'[MONTO DOLAR]
    ),
    NOT('historico_tp_consolidado'[CODIGO DE RESPUESTA VISION PLUS] IN {"0", "00", "000"}),
    'historico_tp_consolidado'[MONTO ORIGINAL DE LA TRANSACCION]
        = 'historico_tp_consolidado'[MONTO DOLAR]
)
```

---

## Alertas
_Pendiente: confirmar lógica de cálculo._
