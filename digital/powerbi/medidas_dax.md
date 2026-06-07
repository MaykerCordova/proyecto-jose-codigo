# Medidas DAX — Canal Digital

## KPIs principales

```dax
Total Fraudes =
COUNTROWS('MF_digital_features')

Monto Total Fraude =
SUM('MF_digital_features'[POS1_ACF-MONTO EN MONEDA LOCAL])

Monto Total Fraude USD =
SUM('MF_digital_features'[POS1_ACF-MONTO DOLLAR])

Tarjetas Únicas =
DISTINCTCOUNT('MF_digital_features'[POS1_ACF-TARJETA])

Cuentas Destino Únicas =
DISTINCTCOUNT('MF_digital_features'[POS1_ACF-CUENTA DESTINO])

Bancos Destino Únicos =
DISTINCTCOUNT('MF_digital_features'[POS1_ACF-COD BANCO DESTINO / ORG DESTINO])

Monto Promedio por Fraude =
DIVIDE([Monto Total Fraude], [Total Fraudes])
```

---

## Fraude por canal y operación

```dax
% Yape Plin QR =
DIVIDE(
    COUNTROWS(FILTER('MF_digital_features', 'MF_digital_features'[FLAG_ES_YAPE_PLIN_QR] = 1)),
    [Total Fraudes]
)

% Transferencias =
DIVIDE(
    COUNTROWS(FILTER('MF_digital_features', 'MF_digital_features'[FLAG_ES_TRANSFERENCIA] = 1)),
    [Total Fraudes]
)

% Pasarelas =
DIVIDE(
    COUNTROWS(FILTER('MF_digital_features', 'MF_digital_features'[FLAG_ES_PASARELA] = 1)),
    [Total Fraudes]
)

% Canal Externo (otro banco) =
DIVIDE(
    COUNTROWS(FILTER('MF_digital_features', 'MF_digital_features'[FLAG_CANAL_EXTERNO] = 1)),
    [Total Fraudes]
)
```

---

## Autenticación

```dax
% Sin Autenticador =
DIVIDE(
    COUNTROWS(FILTER('MF_digital_features', 'MF_digital_features'[FLAG_SIN_AUTENTICADOR] = 1)),
    [Total Fraudes]
)

% Con OTP =
DIVIDE(
    COUNTROWS(FILTER('MF_digital_features', 'MF_digital_features'[FLAG_OTP] = 1)),
    [Total Fraudes]
)

% Biométrico =
DIVIDE(
    COUNTROWS(FILTER('MF_digital_features', 'MF_digital_features'[FLAG_BIOMETRICO] = 1)),
    [Total Fraudes]
)
```

---

## Beneficiario / Cuentas mula

```dax
Cuentas Mula =
CALCULATE(
    DISTINCTCOUNT('MF_digital_features'[POS1_ACF-CUENTA DESTINO]),
    'MF_digital_features'[FLAG_CUENTA_MULA] = 1
)

% Mismo Titular =
DIVIDE(
    COUNTROWS(FILTER('MF_digital_features', 'MF_digital_features'[FLAG_MISMO_TITULAR] = 1)),
    [Total Fraudes]
)

% Tercero =
DIVIDE(
    COUNTROWS(FILTER('MF_digital_features', 'MF_digital_features'[FLAG_TERCERO] = 1)),
    [Total Fraudes]
)

Monto en Cuentas Mula =
CALCULATE(
    SUM('MF_digital_features'[POS1_ACF-MONTO EN MONEDA LOCAL]),
    'MF_digital_features'[FLAG_CUENTA_MULA] = 1
)
```

---

## Riesgo compuesto

```dax
% Perfil MUY_ALTO =
DIVIDE(
    COUNTROWS(FILTER('MF_digital_features', 'MF_digital_features'[PERFIL_RIESGO_DIG] = "MUY_ALTO")),
    [Total Fraudes]
)

% Tarjetas Reincidentes =
DIVIDE(
    COUNTROWS(FILTER('MF_digital_features', 'MF_digital_features'[FLAG_TARJETA_REINCIDENTE] = 1)),
    [Total Fraudes]
)

% Fraude Madrugada =
DIVIDE(
    COUNTROWS(FILTER('MF_digital_features', 'MF_digital_features'[ES_MADRUGADA] = 1)),
    [Total Fraudes]
)

Score Riesgo Promedio =
AVERAGE('MF_digital_features'[SCORE_RIESGO_DIG])
```

---

## Dispositivo

```dax
% iOS =
DIVIDE(
    COUNTROWS(FILTER('MF_digital_features', 'MF_digital_features'[TIPO_DISPOSITIVO] = "iOS")),
    [Total Fraudes]
)

% Android =
DIVIDE(
    COUNTROWS(FILTER('MF_digital_features', 'MF_digital_features'[TIPO_DISPOSITIVO] = "Android")),
    [Total Fraudes]
)

% Web =
DIVIDE(
    COUNTROWS(FILTER('MF_digital_features', 'MF_digital_features'[FLAG_WEB] = 1)),
    [Total Fraudes]
)
```

---

## Slicers recomendados

| Campo | Tipo |
|---|---|
| PERFIL_RIESGO_DIG | Lista (BAJO / MEDIO / ALTO / MUY_ALTO) |
| TIPO_OPERACION_GRUPO | Lista |
| CANAL_DIGITAL_GRUPO | Lista |
| TIPO_DISPOSITIVO | Lista |
| FRANJA_HORARIA | Lista |
| RANGO_MONTO | Lista |
| POS1_ACF-COD BANCO DESTINO / ORG DESTINO | Lista (con join a diccionario de bancos) |
| FECHA_DIA | Rango de fechas |
| MES_NOM | Lista |
