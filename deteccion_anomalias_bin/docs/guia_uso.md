# Detección y Caracterización de Anomalías Transaccionales por Rango de BIN

Scotiabank Peru — Prevención de Fraude

## El problema

Un BIN6 presenta incrementos atípicos en su transaccionalidad diaria por comercio
(ej. Saga Falabella: pasa de 2-6 trx/día a 30-100 trx/día sin patrón aparente).
El análisis se apertura de BIN6 a **rango BIN10** para localizar mejor el fenómeno
y decidir si es card testing / tarjetas comprometidas o un evento comercial legítimo.

Dos componentes:

- **Detección:** identificar el día/serie donde ocurre el incremento anómalo.
- **Atribución:** explicar el driver — comercio, MCC, rango BIN10, franja horaria
  o campaña legítima.

## Unidad de análisis

Serie diaria por `BIN_10 × COMERCIO × FECHA` (llave principal), con roll-ups a
`BIN_10 × MCC × FECHA` y `BIN_6 × FECHA`.

Métricas por fila: n° trx, tarjetas únicas, ratio trx/tarjeta, tasa de declinación,
ticket promedio, n° MCC distintos, % trx nocturnas.

## Secuencia lógica

**Detecto** (z-robusto) → **Explico** (contribución + chi-cuadrado) →
**Descarto legítimo** (calendario) → **Refino** (Isolation Forest).

## Cómo ejecutar

1. Pon 2 meses de journals de Monitor (Excel) en `data/journals/`.
   El journal debe incluir **aprobadas + denegadas** (la tasa de declinación
   es la firma principal de card testing).
2. Revisa `scripts/config.py`:
   - `COLS` — mismo diccionario de Monitor que `ecommerce_comercio` (ajusta si cambia).
   - `DETECCION` — ventana (14-28 días), umbral z (inicial 4.0), mínimos.
   - `EVENTOS_RANGO` — registra las campañas conocidas (Cyber Wow, etc.).
3. Doble clic en `1_ejecutar_pipeline.bat` (o corre los 4 scripts en orden).
4. Cuando el baseline esté validado, corre `2_ejecutar_isolation_forest.bat`.

## Qué hace cada script

| Script | Paso | Qué hace |
|---|---|---|
| `scripts/consolidar.py` | 0 | Journals → `consolidado.parquet`. Construye TARJETA, FECHA_HORA, BIN_6/10/11/12. |
| `scripts/agregacion.py` | 1 | Polars: series diarias por los 3 niveles, con calendario densificado (días sin actividad = 0 trx). |
| `scripts/deteccion.py` | 2-3 | Baseline mediana + MAD (ventana móvil, solo días previos) y z-score robusto. Alerta si z > umbral, con volumen mínimo. |
| `scripts/atribucion.py` | 4-5, 7 | Por alerta: share of excess (dónde está el incremento), chi-cuadrado de mezcla (¿cambió el comportamiento o solo el volumen?), cruce con calendario y **prioridad ALTA/MEDIA/BAJA**. Genera el Excel. |
| `ml/isolation_forest.py` | 6 | Fase 2: IF multivariado sobre BIN10×comercio×día; contrasta sus flags con el baseline. |

## Por qué cada técnica

- **Mediana + MAD** en vez de media + desviación: picos pasados no contaminan
  el baseline. La ventana usa `shift(1)`: el propio día evaluado nunca entra.
- **Share of excess:** descompone el exceso sobre baseline — qué % viene de cada
  comercio / MCC / BIN10. Responde *dónde* está concentrado.
- **Chi-cuadrado:** mezcla igual + más volumen → probable legítimo; mezcla distinta
  (nuevo MCC, giro nocturno) → sospechoso.
- **Calendario:** spike en fecha de campaña con mezcla estable → prioridad BAJA.
- **Isolation Forest:** detecta firmas que ningún umbral individual ve
  (volumen normal + 12 trx/tarjeta + 45% declinación).

## Salida

`output/alertas_<NOMBRE>.xlsx`:

| Hoja | Contenido |
|---|---|
| `0_Resumen` | Conteos por prioridad y parámetros usados |
| `1_Alertas` | Alertas enriquecidas: z, veces sobre baseline, driver (top comercio/MCC/BIN10), declinación día vs baseline, chi2, evento, **prioridad** |
| `2_Contribucion` | Descomposición completa del exceso por dimensión |
| `3_Series_Alertadas` | Serie diaria completa de cada llave alertada (para graficar / Power BI) |

Ejemplo de lectura de una alerta:
*"BIN10 XXXX subió 10x su baseline, 87% concentrado en Saga, decline rate 45%
(normal 8%), sin campaña vigente → posible testing"*.

## Productivización (control propuesto)

Job diario que ejecuta consolidar → agregación → detección → atribución,
genera las alertas enriquecidas para revisión del analista y alimenta Power BI
(los parquet de `data/` se conectan directo). El IF entra como capa
complementaria una vez validado el baseline.

## Diccionario de variables de Monitor

Es el mismo de `ecommerce_comercio/docs/diccionario_variables.md` — la data
viene de la misma extracción de Monitor (base 8750).
