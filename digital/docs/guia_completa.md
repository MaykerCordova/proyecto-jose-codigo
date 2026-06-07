# Guía completa — Pipeline Canal Digital

## Qué hace este pipeline

Toma el parquet de fraudes confirmados del canal digital (banca móvil, internet, Yape/Plin, pasarelas) y genera un parquet enriquecido con variables de ingeniería listas para Power BI.

Todo el dataset de entrada es fraude (SUB_GRUPO='Digital', ESTADO='APROBADA', ORG='SBP', sin resultados EXTORNADO/RECHAZADO).

---

## Estructura de carpetas

```
digital/
  scripts/
    config.py              ← mapeo de columnas y rutas
    feature_engineering.py ← genera el parquet enriquecido
  powerbi/
    medidas_dax.md         ← medidas DAX listas para pegar en Power BI
  docs/
    guia_completa.md       ← este archivo
```

---

## Cómo ejecutar

```bash
cd digital/scripts

# con el parquet en la ruta configurada en config.py
python feature_engineering.py

# o pasando la ruta directamente
python feature_engineering.py C:\ruta\a\MF_digital.parquet
```

El script imprime un resumen al terminar. Revisa que todas las variables muestren ✅.

---

## Diferencias clave vs ecommerce_no_seguro

| Aspecto | ecommerce_no_seguro | digital |
|---|---|---|
| Fecha/hora | Una sola columna combinada | **Dos columnas separadas** — el bloque A las combina |
| Eje de análisis E | Comercio + MCC | **Beneficiario** (banco destino + cuenta destino) |
| Bloque G | CVV dinámico | **Autenticador** (OTP / biometría / clave digital / sin autenticador) |
| Variable nueva | — | **FLAG_MISMO_TITULAR**: transferencia a la propia cuenta del titular en otro banco |
| Variable nueva | — | **FLAG_CUENTA_MULA**: cuenta destino recibe fraude desde múltiples tarjetas |
| Variable nueva | — | **TIPO_DISPOSITIVO**: iOS / Android / Web (desde CANAL_JOY) |
| Score de riesgo | 6 componentes (con CVV) | **9 componentes** (sin CVV, con autenticador + tercero + cuenta mula + IP) |

---

## Bloques del feature_engineering.py

| Bloque | Variables generadas |
|---|---|
| A | DATETIME_TRX (fecha+hora combinadas), DATETIME_CIERRE |
| B | HORA_DIA, DIA_SEMANA, FRANJA_HORARIA, ES_MADRUGADA, ES_FIN_SEMANA, QUINCENA, ES_HORARIO_LAB |
| C | DIAS_PARA_CIERRE, RANGO_DIAS_CIERRE |
| D | TOTAL_FRAUDES_TARJETA, BENEFICIARIOS_DISTINTOS_TRJ, FRAUDES_TRJ_DIA, FLAG_TARJETA_REINCIDENTE, FLAG_RAFAGA_DIA, FLAG_MULTI_BENEFICIARIO_DIA |
| D2 | TXN_CARD_2M/5M/10M/1H/24H, AMT_CARD_1H/24H, FLAG_VEL_ALTA_1H, FLAG_VEL_ALTA_10M, FLAG_ACUM_ALTO_1H |
| E | TOTAL_FRAUDES_BANCO_DEST, RANKING_BANCO_DEST, TOTAL_FRAUDES_CUENTA_DEST, TARJETAS_EN_CUENTA_DEST, FLAG_CUENTA_MULA, FLAG_MISMO_TITULAR, FLAG_TERCERO |
| F | TIPO_OPERACION_GRUPO, CANAL_DIGITAL_GRUPO, FLAG_ES_YAPE_PLIN_QR, FLAG_ES_PASARELA, FLAG_ES_TRANSFERENCIA, FLAG_ES_PAGO, FLAG_CANAL_EXTERNO, FLAG_MONTO_REDONDO, RANGO_MONTO |
| G | FLAG_SIN_AUTENTICADOR, FLAG_OTP, FLAG_BIOMETRICO, FLAG_CLAVE_DIGITAL, TIPO_DISPOSITIVO, FLAG_WEB, FLAG_IP_REAL |
| H | SCORE_RIESGO_DIG (0–9), PERFIL_RIESGO_DIG (BAJO/MEDIO/ALTO/MUY_ALTO), FLAG_HORARIO_RIESGO |

---

## Categorías de operación (TIPO_OPERACION_GRUPO)

| Grupo | Operaciones que incluye |
|---|---|
| YAPE_PLIN_QR | Yape, Plin, BIM, Interoperabilidad, QR, Prinyape |
| PASARELA | Pasarelas de pago |
| TRANSFERENCIA | Transferencia CC inmediata, TIB, TIP, Transferencias terceros |
| PAGO | Pago TC, Pago préstamo, Pago servicios, Abono |
| OTRO | Resto |

---

## Canal digital (CANAL_DIGITAL_GRUPO)

| Grupo | Descripción |
|---|---|
| TRANSF_INMEDIATA | Transferencia a otro banco (externo) |
| TRANSF_TERCEROS | Transferencia dentro de Scotiabank |
| YAPE_PLIN | Billeteras digitales interoperables |
| PASARELA | Pasarelas tipo EasyPay |
| DESCONOCIDO | Sin dato (data en proceso de completar) |

---

## Score de riesgo digital — componentes

| Componente | Señal que captura |
|---|---|
| FLAG_TARJETA_REINCIDENTE | Tarjeta ya apareció antes en el dataset |
| FLAG_RAFAGA_DIA | 3+ fraudes en el mismo día |
| FLAG_VEL_ALTA_1H | 2+ fraudes en la última hora |
| FLAG_MONTO_REDONDO | Monto sin centavos |
| ES_MADRUGADA | Transacción entre 00:00 y 05:59 |
| FLAG_SIN_AUTENTICADOR | No hubo OTP, biometría ni clave digital |
| FLAG_TERCERO | Transferencia a persona distinta al titular |
| FLAG_CUENTA_MULA | Cuenta destino recibe fraude de ≥3 tarjetas distintas |
| FLAG_IP_REAL | Transacción vino por navegador web con IP real |

**PERFIL_RIESGO_DIG**: BAJO=0 / MEDIO=1-2 / ALTO=3-5 / MUY_ALTO=6+

---

## config.py — ajustes frecuentes

- `PARQUET_INPUT`: ruta al parquet de entrada
- `PARQUET_OUTPUT`: ruta al parquet enriquecido
- `UMBRAL_CUENTA_MULA`: nº mínimo de tarjetas distintas que llegan a la misma cuenta para considerarla mula (default: 3)
- `COLS`: si algún campo cambia de nombre en el parquet, actualiza solo el valor (lado derecho)
