# Diccionario de Variables — Ecommerce Comercio
## Pipeline de Análisis de Comercios de Alta Transaccionalidad
### Scotiabank Peru — Prevención de Fraude

---

> **Cómo usar este diccionario**
> Cada variable tiene: **qué es**, **cómo se calcula**, **ejemplo numérico**, **cómo interpretar** y **cómo combinarla**.
> Para buscar una variable usa Ctrl+F con el nombre exacto.

---

## BLOQUE B — Variables Temporales
*¿CUÁNDO ocurrió la transacción?*

---

### `HORA_DIA`
- **Qué es:** Hora exacta de la transacción (0 a 23)
- **Cálculo:** `datetime.hour`
- **Ejemplo:** `3` → la txn ocurrió a las 3am
- **Interpretar:** Horas entre 0 y 5 son sospechosas (ver ES_MADRUGADA). Horas pico legítimas suelen ser 10am–8pm.
- **Combinar con:** `ES_MADRUGADA`, `FRANJA_HORARIA`, `FLAG_RAFAGA_5MIN` — ráfaga de madrugada = señal fuerte de bot.

---

### `FRANJA_HORARIA`
- **Qué es:** Parte del día en texto
- **Valores:** `MADRUGADA` (0–5h) | `MANANA` (6–11h) | `TARDE` (12–18h) | `NOCHE` (19–23h)
- **Ejemplo:** `MADRUGADA`
- **Interpretar:** MADRUGADA tiene alta concentración de fraude automatizado. Un humano no compra en PS Store a las 3am salvo que sea gamer, pero no en múltiples tiendas.
- **Combinar con:** `ES_TOKENIZADA` — fraude de madrugada sin billetera digital es más probable CNP puro.

---

### `ES_MADRUGADA`
- **Qué es:** Flag si la txn ocurrió entre las 0:00 y las 5:59am
- **Valores:** `1` = sí | `0` = no
- **Ejemplo:** Una txn a las 4:17am → `ES_MADRUGADA = 1`
- **Interpretar:** Si más del 30% del fraude tiene `ES_MADRUGADA=1`, hay bots activos. Para el mismo comercio, las txn buenas raramente son de madrugada.
- **Combinar con:** `FLAG_RAFAGA_5MIN` — si hay ráfaga de madrugada, probabilidad de fraude automatizado >90%.

---

### `ES_FIN_SEMANA`
- **Qué es:** Flag si la txn fue sábado o domingo
- **Valores:** `1` = fin de semana | `0` = día de semana
- **Interpretar:** Los defraudadores aprovechan que hay menos monitoreo humano los fines de semana. Si el % de fraude en fin de semana supera al % de txn buenas, es una señal.

---

### `ES_HORARIO_LAB`
- **Qué es:** Flag si la txn ocurrió lunes a viernes entre 8am y 5pm
- **Interpretar:** Fraude en horario laboral es más discreto — se mezcla con la actividad normal. Fraude fuera de horario laboral (especialmente madrugada) es más automatizado.

---

### `QUINCENA`
- **Qué es:** Primera o segunda quincena del mes
- **Valores:** `Q1` (días 1–15) | `Q2` (días 16–31)
- **Interpretar:** En días de pago (15 y fin de mes) el volumen sube. El fraude puede subir proporcionalmente o más si los defraudadores saben que los clientes tienen saldo disponible.
- **Combinar con:** `ES_DIA_PAGO` para ver si el fraude se concentra justo el día que pagan.

---

### `ES_FERIADO`
- **Qué es:** Flag si la fecha es feriado en Perú
- **Valores:** `1` = feriado | `0` = no
- **Interpretar:** Feriados = mayor volumen de compras legítimas. El fraude puede aumentar en términos absolutos pero baja en tasa si la vigilancia aumenta. Si la tasa de fraude en feriados es mayor, es señal de explotación de descuido.

---

### `ES_FECHA_ESPECIAL`
- **Qué es:** Flag si la fecha es de alta transaccionalidad (Día de la Madre, Black Friday, etc.)
- **Combinar con:** `NOMBRE_FECHA_ESP` para saber exactamente qué fecha especial es.

---

### `ES_DIA_PAGO`
- **Qué es:** Flag si el día del mes es 15, 30 o 31 (días típicos de pago de quincena/sueldo)
- **Interpretar:** Clientes con saldo recién abonado son blancos prioritarios para fraude. Si `ES_DIA_PAGO=1` y `FLAG_SALDO_AGOTADO=1`, el defraudador llegó justo cuando había dinero.

---

## BLOQUE C — Clasificación de la Transacción
*¿QUÉ pasó con la transacción?*

---

### `ESTADO`
- **Qué es:** Si la transacción fue aprobada o denegada por el autorizador
- **Valores:** `APROBADA` | `DENEGADA`
- **Cálculo:** `ACF-COD RPTA` en {`0`, `00`, `000`} → APROBADA; resto → DENEGADA
- **Interpretar:** Para análisis de fraude en ecommerce no seguro, la mayoría son APROBADAS. Las DENEGADAS revelan intentos fallidos y patrones de cascada CVV.

---

### `ES_FRAUDE`
- **Qué es:** Flag si la transacción fue marcada como fraude
- **Valores:** `1` = fraude | `0` = no fraude
- **Cálculo:** `ACF-INDICADOR DE FRAUDE == "F"`
- **Importante:** No todo fraude se descubre en el momento. Puede aparecer días después cuando el cliente reclama.

---

### `ES_FRAUDE_APROBADO`
- **Qué es:** Flag si el fraude fue aprobado (pasó el filtro del autorizador)
- **Interpretar:** Este es el fraude que costó dinero real. Un fraude denegado no generó pérdida. `ES_FRAUDE_APROBADO=1` significa que el control falló.

---

### `INDICADOR_TEXTO`
- **Qué es:** Descripción del indicador de fraude
- **Valores:** `Fraude` | `Buena` | `Pendiente` | `Descarte` | `Normal`
- **Interpretar:**
  - `Fraude`: confirmado como fraude
  - `Buena`: confirmado como transacción legítima
  - `Pendiente`: aún en investigación
  - `Descarte`: fue descartada del análisis
  - `Normal`: sin indicador especial (mayoría de txn)

---

### `SEGURO`
- **Qué es:** Si el comercio procesó la txn con 3DS (autenticación adicional)
- **Valores:** `Seguro` | `No Seguro`
- **Cálculo:** `ACF-ECI/UCAF` en {`2`, `02`} para Mastercard o {`5`, `05`} para Visa → Seguro
- **Interpretar:** En ecommerce NO SEGURO (sin 3DS), todos deberían ser `No Seguro`. Si ves `Seguro`, puede ser que el comercio tiene 3DS parcial o hubo un cambio en su configuración.

---

### `MARCA_TARJETA`
- **Qué es:** Franquicia de la tarjeta
- **Valores:** `VISA` | `MASTERCARD` | `OTRA`
- **Cálculo:** Primer dígito de la tarjeta o columna ACF-MARCA. `4xxxx` = Visa, `5xxxx` = Mastercard
- **Interpretar:** Permite comparar tasa de fraude por franquicia. Si Mastercard tiene tasa 2x mayor que Visa en el mismo comercio, puede haber una brecha específica de seguridad.

---

### `ES_TOKENIZADA`
- **Qué es:** Si la txn fue procesada con billetera digital (Apple Pay, Google Pay)
- **Valores:** `1` = sí | `0` = no
- **Cálculo:** `RESERVADO ALFA 2` primeros 5 chars ≠ `99999`
- **Interpretar:** Las txn tokenizadas son MENOS propensas a fraude porque el token protege el número real. Si ves fraude en txn tokenizadas, es más sofisticado (el defraudador enroló una tarjeta comprometida en la billetera).

---

### `BILLETERA_NOMBRE`
- **Qué es:** Nombre de la billetera digital
- **Valores:** `Google Pay VISA` | `Apple Pay VISA / MC` | `Apple Pay MC` | `No tokenizada` | `Tokenizada (no identificada)`
- **Cálculo:** Primeros 5 chars de RESERVADO ALFA 2 → diccionario

---

### `TIPO_ENTRADA`
- **Qué es:** Cómo se ingresó la tarjeta en la transacción
- **Ejemplos:** `Chip` | `Contactless / NFC` | `Manual / Digitada` | `Banda magnetica`
- **Interpretar:** En ecommerce debería ser siempre `Manual / Digitada` (modo 01) porque no hay tarjeta física. Si ves otros modos, puede haber un problema de mapeo o txn mezcladas con presencial.

---

### `ES_TARJETA_PRESENTE`
- **Qué es:** Flag si la tarjeta estuvo físicamente presente
- **Valores:** `1` = presente | `0` = no presente
- **Interpretar:** Para ecommerce, todas deberían ser `ES_TARJETA_PRESENTE=0`. Si hay `=1`, revisar si se está analizando data mezclada (POS + ecommerce).

---

### `ES_MOTO`
- **Qué es:** Flag si la txn es MOTO (Mail Order / Telephone Order)
- **Interpretar:** MOTO = el cliente dio su número de tarjeta por teléfono o correo. Mayor riesgo porque no hay ninguna autenticación física. Si hay fraude en MOTO, es robo de datos puro.

---

### `SEG_NOMBRE` / `SEG_GRUPO`
- **Qué es:** Segmento del cliente (nombre detallado y grupo agrupado)
- **Valores SEG_GRUPO:** `Mass` | `Top of Mass` | `Emerging Affluent` | `Affluent` | `Corporate` | `Commercial` | `Small Business`
- **Interpretar:** Los segmentos más altos (Affluent, Premium) tienen tarjetas con límites mayores → si hay fraude, el monto puede ser mayor. Mass tiene más volumen pero menor monto por txn.
- **Combinar con:** `TIPO_PRODUCTO_TEXTO` — el cruce Segmento × Producto (el que pidió tu especialista) es muy revelador.

---

### `TIPO_CVV`
- **Qué es:** Tipo de CVV que usó la tarjeta
- **Valores:** `Estatico (TD)` | `Dinamico (TD/TC)` | `Estatico (TC)` | `Sin CVV / No Match`
- **Interpretar:** CVV dinámico es más seguro (cambia con cada txn). CVV estático puede ser robado una vez y usado varias veces. `Sin CVV` = txn sin validación de CVV (riesgo alto).

---

### `MOTIVO_RECHAZO`
- **Qué es:** Por qué fue rechazada la txn (si fue DENEGADA)
- **Valores:** `CVV_FAIL` | `FONDOS_INSUF` | `EXCEDE_LIMITE` | `TARJETA_BLOQ` | `TARJETA_EXP` | `PIN_FAIL` | `AUTH_FAIL` | `DATO_INVALIDO` | `N/A` | `OTRO`
- **Interpretar:**
  - `CVV_FAIL` → el defraudador tiene el número pero no el CVV → card testing
  - `DATO_INVALIDO` → número de tarjeta generado o mal copiado
  - `TARJETA_BLOQ` → tarjeta ya en lista negra, fraude conocido
  - `FONDOS_INSUF` → puede ser fraude agotando saldo (ver `FLAG_SALDO_AGOTADO`)

---

### `ES_CODIGO_CRITICO`
- **Qué es:** Flag si el código de respuesta es uno de los 4 críticos
- **Valores:** `1` = código crítico | `0` = no
- **Códigos críticos:**
  - `N7` = CVV2 no coincide (intento de card testing)
  - `14` = Tarjeta inválida (número generado o clonado)
  - `04` = Capturar tarjeta (en lista negra, fraude confirmado)
  - `51` = Fondos insuficientes (puede indicar agotamiento por fraude)

---

## BLOQUE D — Ventanas Deslizantes
*¿Con qué VELOCIDAD y cuánto MONTO acumuló el cliente antes de esta txn?*

> **Concepto clave:** Para cada transacción, se mira hacia atrás en el tiempo y se cuenta cuántas txn y cuánto monto acumuló ese cliente en el intervalo previo. Si la txn actual es a las 10:15am, la ventana de 10 minutos mira las txn entre 10:05 y 10:14:59.

---

### `TRX_CLIENTE_2MIN`
- **Qué es:** Número de transacciones del cliente en los 2 minutos anteriores a esta txn
- **Ejemplo:** `TRX_CLIENTE_2MIN = 2` → el cliente hizo 2 txn antes en los últimos 2 min
- **Señal de alerta:** `≥ 1` ya es sospechoso. Ningún humano hace 2 compras en 2 minutos en tiendas distintas. Si ocurre, es bot.
- **Para la regla:** "Declinar si hay ≥1 txn previa en 2 minutos" captura fraude automatizado con muy poco colateral.

---

### `TRX_CLIENTE_5MIN`
- **Qué es:** Número de transacciones en los 5 minutos anteriores
- **Ejemplo:** `TRX_CLIENTE_5MIN = 3` → hizo 3 txn en los últimos 5 min
- **Señal de alerta:** `≥ 3` = ráfaga clara. Ver `FLAG_RAFAGA_5MIN`.
- **Para la regla:** "Declinar si hay ≥3 txn en 5 minutos" es la regla de velocidad más efectiva en ecommerce.

---

### `TRX_CLIENTE_10MIN`
- **Qué es:** Número de transacciones en los 10 minutos anteriores
- **Señal de alerta:** `≥ 3` = ráfaga. Ver `FLAG_RAFAGA_10MIN`.

---

### `TRX_CLIENTE_1H`
- **Qué es:** Número de transacciones en la última hora
- **Señal de alerta:** `≥ 5` = velocidad muy alta. Ver `FLAG_VEL_ALTA_1H`.
- **Contexto:** Un cliente legítimo puede comprar 2–3 cosas en una hora de shopping. Más de 5 es inusual.

---

### `TRX_CLIENTE_24H`
- **Qué es:** Número de transacciones en las últimas 24 horas
- **Señal de alerta:** `≥ 10` es crítico para ecommerce normal.
- **Para la regla:** Bueno para detectar ataques sostenidos del día completo.

---

### `MNT_CLIENTE_2MIN` / `MNT_CLIENTE_5MIN` / `MNT_CLIENTE_10MIN` / `MNT_CLIENTE_1H` / `MNT_CLIENTE_24H`
- **Qué es:** Monto acumulado (S/) por ese cliente en la ventana de tiempo
- **Ejemplo:** `MNT_CLIENTE_24H = 850` → antes de esta txn, ese cliente ya acumuló S/850 en las últimas 24h
- **Para la regla de monto acumulado:** "Declinar si MNT_CLIENTE_24H ≥ S/500" significa que si el cliente ya gastó más de S/500 ese día, se detiene la siguiente txn.
- **El umbral depende del ticket promedio del comercio:** Para Western Union con tickets de S/1,500, el umbral debería ser mayor. Para Saga Falabella con ticket de S/200, S/500 ya es 2.5x el promedio.

---

### `GAP_MINUTOS`
- **Qué es:** Minutos transcurridos desde la txn anterior del mismo cliente
- **Ejemplo:** `GAP_MINUTOS = 0.3` → solo 18 segundos desde la txn anterior
- **Señal de alerta:** `< 1 minuto` = bot. Los humanos tardan más en navegar, elegir y confirmar.
- **Sin valor (NaN):** Es la primera txn del cliente en el dataset.
- **Combinar con:** `TRX_CLIENTE_5MIN` — si el GAP es bajo Y hay ráfaga, es fraude automatizado con alta probabilidad.

---

## BLOQUE E — Interacciones Velocidad × Monto

---

### `MONTO_PROM_5MIN` / `MONTO_PROM_10MIN` / `MONTO_PROM_1H` / `MONTO_PROM_24H`
- **Qué es:** Monto promedio por transacción en esa ventana de tiempo
- **Fórmula:** `MNT_CLIENTE_Xmin ÷ TRX_CLIENTE_Xmin`
- **Ejemplo:** `MONTO_PROM_5MIN = 200` → en los últimos 5 min, cada txn promedió S/200
- **Interpretar:** Si `MONTO_PROM_5MIN >> MONTO_PROM_24H`, el cliente subió el monto de golpe en las últimas transacciones → escalada del ataque.

---

### `ACELERACION_MONTO`
- **Qué es:** Relación entre el monto promedio en 5 min vs el promedio de la última hora
- **Fórmula:** `MONTO_PROM_5MIN ÷ MONTO_PROM_1H`
- **Ejemplo:** `ACELERACION_MONTO = 3.0` → en los últimos 5 min, el monto promedio triplicó el de la hora
- **Interpretar:**
  - `> 2.0` → escalada agresiva. El defraudador probó con montos bajos y subió rápido.
  - `< 0.5` → empezó con montos grandes y bajó. Puede ser card testing inverso.
  - `≈ 1.0` → montos consistentes (perfil más normal).
- **Para la regla:** `ACELERACION_MONTO > 2.0` + `FLAG_RAFAGA_5MIN = 1` = combinación de altísimo riesgo.

---

### `CONCENTRACION_5MIN_1H`
- **Qué es:** Qué porcentaje del monto de la última hora se concentró en los últimos 5 minutos
- **Fórmula:** `MNT_CLIENTE_5MIN ÷ MNT_CLIENTE_1H`
- **Ejemplo:** `CONCENTRACION_5MIN_1H = 0.85` → el 85% del monto de la hora pasó en solo 5 min
- **Interpretar:**
  - `> 0.7` → ráfaga explosiva de monto. Muy sospechoso.
  - `≈ 0.2` → el monto está distribuido en el tiempo (más normal).

---

### `ZSCORE_MONTO_CLIENTE`
- **Qué es:** Cuántas desviaciones estándar se aleja esta txn del promedio histórico de ese cliente
- **Fórmula:** `(monto - media_cliente) ÷ desv_std_cliente`
- **Ejemplo:** `ZSCORE_MONTO_CLIENTE = 3.5` → esta txn es 3.5 desviaciones estándar por encima del promedio del cliente
- **Interpretar:**
  - `> 3.0` → txn atípica para ese cliente. Alta probabilidad de fraude o error.
  - `< -2.0` → monto mucho más bajo que su historial. Puede ser card testing.
  - `-1.0 a 1.0` → dentro del comportamiento normal del cliente.
- **Por qué importa:** Compara al cliente con SÍ MISMO, no con la media global. Un millonario comprando S/2,000 puede ser normal; para un cliente que siempre gasta S/50, es una anomalía.

---

### `RATIO_MONTO_VS_HIST_CLIENTE`
- **Qué es:** Cuántas veces el monto de esta txn supera al promedio histórico del cliente
- **Fórmula:** `monto ÷ media_histórica_cliente`
- **Ejemplo:** `RATIO_MONTO_VS_HIST_CLIENTE = 4.2` → esta txn es 4.2 veces mayor que su promedio
- **Señal:** `> 3.0` merece revisión.

---

## BLOQUE F — Perfil del Cliente

---

### `TOTAL_TRX_CLIENTE`
- **Qué es:** Total de transacciones del cliente en todo el dataset
- **Interpretar:** Un cliente con muchas txn puede ser legítimo frecuente o reincidente en fraude. Combinar con `ES_FRAUDE` para separar.

---

### `FLAG_REINCIDENTE`
- **Qué es:** Flag si el cliente aparece más de una vez en el dataset
- **Valores:** `1` = reincidente | `0` = solo apareció una vez
- **Interpretar:** Si `FLAG_REINCIDENTE=1` y `ES_FRAUDE=1` en múltiples filas, la tarjeta nunca fue bloqueada a tiempo → alerta de gestión de bloqueos.

---

### `FLAG_RAFAGA_DIA`
- **Qué es:** Flag si el cliente hizo ≥3 transacciones en el mismo día
- **Interpretar:** 3 o más compras en un día en ecommerce es inusual para un humano. Para un bot, es poco.
- **Combinar con:** `FLAG_RAFAGA_5MIN` — ráfaga diaria + ráfaga en 5 min = ataque masivo.

---

### `ES_CLIENTE_NUEVO_COMERCIO`
- **Qué es:** Flag si es la primera vez que ese cliente aparece en ese comercio
- **Valores:** `1` = primera vez | `0` = ya compró antes
- **Interpretar:** Primera compra + monto alto + madrugada = perfil de fraude clásico. Un cliente legítimo que compra por primera vez generalmente hace una compra de prueba pequeña.

---

### `DIAS_DESDE_ULT_TRX_COMERCIO`
- **Qué es:** Días transcurridos desde la última vez que ese cliente tuvo una txn en ese comercio
- **Ejemplo:** `DIAS_DESDE_ULT_TRX_COMERCIO = 180` → no compraba ahí desde hace 6 meses
- **Interpretar:** Reactivación después de mucho tiempo + monto alto = sospechoso. El cliente puede haber sido comprometido y el defraudador usa su historial para pasar los controles.

---

### `RATIO_MONTO_VS_SALDO`
- **Qué es:** Qué porcentaje del saldo disponible representa el monto de esta txn
- **Fórmula:** `monto ÷ saldo_disponible`
- **Ejemplo:** `RATIO_MONTO_VS_SALDO = 0.95` → usó el 95% del saldo
- **Señal:** Ver `FLAG_SALDO_AGOTADO`.

---

### `FLAG_SALDO_AGOTADO`
- **Qué es:** Flag si el fraude usó ≥90% del saldo disponible
- **Interpretar:** El defraudador fue al límite. Patrón de "última compra antes de que bloqueen" — alta urgencia para investigación.

---

## BLOQUE G — Perfil del Comercio

---

### `CATEGORIA_COMERCIO`
- **Qué es:** Tamaño del comercio según Q Transaccional (txn del mes anterior)
- **Valores:** `NUEVO` (0 txn) | `PEQUENO` (<500 txn) | `MEDIANO` (<5000) | `GRANDE` (≥5000)
- **Interpretar:** Comercios `NUEVO` son de alto riesgo — no tienen historial, los controles de fraude no están calibrados para ellos. Un comercio `GRANDE` como Saga Falabella puede absorber más fraude en términos de tasa, pero el monto absoluto es mayor.

---

### `TASA_FRAUDE_COMERCIO`
- **Qué es:** Porcentaje de fraudes sobre el total de txn del comercio en el dataset
- **Fórmula:** `FRAUDES_COMERCIO ÷ TOTAL_TRX_COMERCIO`
- **Ejemplo:** `TASA_FRAUDE_COMERCIO = 0.15` → 15% de las txn en ese comercio son fraude
- **Señal:** Una tasa >10% en ecommerce es muy alta. Puede indicar que el comercio está siendo usado exclusivamente para fraude (comercio fantasma).

---

### `RANKING_COMERCIO`
- **Qué es:** Posición del comercio por número de transacciones (1 = más transacciones)
- **Interpretar:** Los comercios con mayor ranking concentran más actividad. Útil para ordenar tablas en el Excel.

---

### `FLAG_PAIS_INUSUAL`
- **Qué es:** Flag si el país de la txn es distinto al país más frecuente de ese comercio
- **Ejemplo:** Saga Falabella Perú normalmente procesa de Perú. Si aparece una txn de Brasil → `FLAG_PAIS_INUSUAL = 1`
- **Interpretar:** Puede indicar fraude transnacional — el número de tarjeta fue robado y se usa desde otro país. Alta señal si va acompañado de `ES_MADRUGADA`.

---

### `DESVIO_MONTO_VS_COMERCIO`
- **Qué es:** Diferencia entre el monto de esta txn y el promedio del comercio
- **Fórmula:** `monto - MONTO_PROM_COMERCIO`
- **Ejemplo:** `DESVIO_MONTO_VS_COMERCIO = 800` → esta txn está S/800 por encima del promedio del comercio
- **Combinar con:** `ZSCORE_MONTO_COMERCIO` para ver si es outlier estadístico.

---

### `ZSCORE_MONTO_COMERCIO`
- **Qué es:** Cuántas desviaciones estándar se aleja esta txn del promedio del comercio
- **Ejemplo:** `ZSCORE_MONTO_COMERCIO = 4.1` → outlier extremo para ese comercio
- **Señal:** `> 3.0` merece revisión independientemente del indicador.

---

## BLOQUE H — Señales de Monto

---

### `FLAG_MONTO_REDONDO`
- **Qué es:** Flag si el monto es múltiplo exacto de 50 y ≥ S/50
- **Ejemplo:** `500.00` → flag = 1 | `523.40` → flag = 0
- **Interpretar:** Los bots usan montos exactos porque es más fácil programarlos. Un humano rara vez gasta exactamente S/100 o S/200. Si >20% del fraude tiene este flag, es card testing activo.
- **Combinar con:** `RANGO_MONTO = BAJO` + `FLAG_MONTO_REDONDO = 1` = patrón clásico de card testing (montos pequeños y redondos para probar tarjetas).

---

### `RANGO_MONTO`
- **Qué es:** Categoría del monto según cuartiles del dataset
- **Valores:** `BAJO` (≤P25) | `MEDIO_BAJO` (P25–P50) | `MEDIO_ALTO` (P50–P75) | `ALTO` (>P75)
- **Nota:** Los cortes cambian según el comercio analizado. Para Saga, ALTO puede ser S/800+. Para Netflix, ALTO puede ser S/150+.

---

### `RANGO_MONTO_PERCENTIL`
- **Qué es:** Categoría más detallada por percentiles
- **Valores:** `P0_10` | `P10_25` | `P25_50` | `P50_75` | `P75_90` | `P90_100`
- **Interpretar:** `P90_100` = el 10% de txn con mayor monto. Estas concentran el mayor riesgo por monto pero son las más inusuales.

---

### `DECIL_MONTO`
- **Qué es:** Decil del monto (1 = menor, 10 = mayor)
- **Interpretar:** El decil 10 concentra los montos más altos. Importante analizar si en el decil 10 la tasa de fraude es mayor (defraudadores van por montos grandes) o menor (el comercio tiene controles adicionales para montos altos).
- **La apertura del último decil:** Si el decil 10 va de S/300 a S/10,000, el rango es muy disperso. Se puede "abrir" ese decil y hacer sub-deciles solo dentro de él para entender mejor la distribución.

---

### `RANGO_MONTO_ARBOL`
- **Qué es:** Rango calculado por árbol de decisión que busca los cortes que mejor separan fraude de no-fraude
- **Ejemplo:** `ARBOL_89` → la media del monto en esa hoja del árbol es ~S/89
- **Interpretar:** A diferencia de los cuartiles (que dividen el monto en partes iguales), el árbol busca los puntos donde la tasa de fraude cambia más. Ejemplo: puede que debajo de S/50 haya 60% de fraude (card testing), entre S/50 y S/300 solo 5%, y arriba de S/300 un 25% (montos altos comprometidos). El árbol detecta esos quiebres.
- **Requiere:** `scikit-learn` instalado (`pip install scikit-learn`)

---

## BLOQUE I — Card Testing (BIN Extendido)

---

### `BIN_10` / `BIN_11` / `BIN_12`
- **Qué es:** Primeros 10, 11 o 12 dígitos de la tarjeta (desencriptada)
- **Para qué sirve:** Detectar cuando el mismo prefijo de tarjeta se usa en múltiples tarjetas distintas el mismo día → señal de generación secuencial de tarjetas.

---

### `TARJETAS_MISMO_BIN12_DIA`
- **Qué es:** Cuántas tarjetas distintas comparten el mismo BIN12 en el mismo día
- **Ejemplo:** `TARJETAS_MISMO_BIN12_DIA = 5` → ese BIN12 apareció en 5 tarjetas distintas ese día
- **Interpretar:** Si el BIN12 se repite con distintos últimos dígitos, es muy probable que un bot esté generando números de tarjeta secuencialmente y probando cuáles son válidos.

---

### `FLAG_BIN12_REPETIDO_DIA`
- **Qué es:** Flag si el BIN12 de esta tarjeta se repitió en más de 1 tarjeta el mismo día
- **Valores:** `1` = sí | `0` = no
- **Señal:** Este flag = 1 es una de las señales más fuertes de fraude sistemático. No es fraude casual, es un ataque organizado.
- **Para la regla:** Bloquear todas las txn donde `FLAG_BIN12_REPETIDO_DIA = 1` captura card testing con prácticamente cero falsos positivos.

---

## BLOQUE J — Rechazos y Cascada CVV
*(Solo disponible si `SOLO_APROBADAS = False`)*

---

### `N_RECHAZOS_24H`
- **Qué es:** Cuántas txn denegadas tuvo ese cliente en las 24h previas a esta aprobación
- **Ejemplo:** `N_RECHAZOS_24H = 8` → antes de que le aprobaran, intentó 8 veces y falló
- **Interpretar:** Un cliente legítimo que falla muchas veces y luego le aprueban es sospechoso. El defraudador intenta distintas tarjetas/configuraciones hasta encontrar una que pase.

---

### `N_CVV_FAIL_24H`
- **Qué es:** Cuántos intentos con CVV incorrecto tuvo el cliente en las 24h previas
- **Señal:** `N_CVV_FAIL_24H ≥ 3` + txn aprobada = cascada CVV clásica. El bot probó varios CVVs hasta acertar.

---

### `HUBO_CVV_FAIL_PREVIO`
- **Qué es:** Flag si hubo al menos 1 fallo de CVV en las 24h previas a esta txn
- **Interpretar:** CVV_FAIL previo + txn aprobada = el defraudador tenía el número de tarjeta pero no el CVV, lo intentó varias veces y eventualmente pasó (quizá con una tarjeta diferente del mismo cliente).

---

### `HUBO_FRAUDE_PREVIO_24H`
- **Qué es:** Flag si ese cliente ya tuvo una txn marcada como fraude en las últimas 24h
- **Interpretar:** Si `HUBO_FRAUDE_PREVIO_24H = 1`, la tarjeta/cliente ya fue comprometida y no fue bloqueada a tiempo. Cada txn posterior es más fraude que debió haberse prevenido.

---

### `MIN_DESDE_ULTIMO_FRAUDE`
- **Qué es:** Minutos transcurridos desde el último fraude confirmado de ese cliente
- **Ejemplo:** `MIN_DESDE_ULTIMO_FRAUDE = 45` → hace 45 minutos hubo un fraude del mismo cliente
- **Interpretar:** Si este número es bajo (< 60 min), el atacante está activo. Regla inmediata: bloquear tarjeta si hay fraude confirmado y el tiempo es < 2h.

---

## BLOQUE K — Flags de Reglas Configurables

Estos flags se generan automáticamente desde los umbrales en `config.py → UMBRALES_REGLA`.

---

### `FLAG_MNT_ACUM_200_24H` / `FLAG_MNT_ACUM_300_24H` / `FLAG_MNT_ACUM_500_24H` / `FLAG_MNT_ACUM_1000_24H`
- **Qué es:** Flag si el cliente acumuló más de S/200/300/500/1000 en las últimas 24h (antes de esta txn)
- **Para la regla:** "Declinar si monto acumulado en 24h ≥ S/500" → ajustar el umbral en config.py
- **Cómo calibrar:** Ver la hoja `Recomendaciones_Regla` en el Excel — te muestra qué % de fraude captura cada umbral y cuántas txn buenas afecta.

---

### `FLAG_TRX_3_EN_5MIN` / `FLAG_TRX_4_EN_5MIN` / `FLAG_TRX_5_EN_5MIN`
- **Qué es:** Flag si el cliente tuvo ≥3/4/5 txn en los últimos 5 minutos
- **Para la regla:** "Declinar si ≥3 txn en 5 minutos" es la regla de velocidad más común en ecommerce.

---

### `FLAG_COMBO_MNT300_TRX3` / `FLAG_COMBO_MNT500_TRX3` / etc.
- **Qué es:** Combinación de umbral de monto + velocidad
- **Ejemplo:** `FLAG_COMBO_MNT500_TRX3 = 1` → el cliente acumuló >S/500 en 24h Y tuvo ≥3 txn en 5 min
- **Interpretar:** Las reglas combinadas capturan más fraude con menos falsos positivos. Una txn grande puede ser legítima; muchas txn seguidas pueden ser normales en un marketplace. Pero ambas cosas a la vez es altamente sospechoso.

---

### `FLAG_ESCALADA_MONTO`
- **Qué es:** Flag si el monto promedio de los últimos 5 min duplica el promedio de las últimas 24h
- **Interpretar:** El atacante comenzó con montos pequeños (para probar) y ahora está escalando. Patrón de reconocimiento + explotación.

---

## BLOQUE L — Score de Riesgo Compuesto

---

### `SCORE_RIESGO`
- **Qué es:** Suma de señales de riesgo activas en la transacción (0 a 11)
- **Cómo se calcula:** Cada uno de los 11 flags suma 1 punto si está activo:
  1. `FLAG_RAFAGA_5MIN` — ráfaga en 5 min
  2. `FLAG_VEL_ALTA_1H` — velocidad alta en 1h
  3. `HUBO_FRAUDE_PREVIO_24H` — fraude previo
  4. `HUBO_CVV_FAIL_PREVIO` — cascada CVV
  5. `FLAG_MONTO_REDONDO` — monto exacto
  6. `ES_MADRUGADA` — de madrugada
  7. `FLAG_REINCIDENTE` — cliente reincidente
  8. `FLAG_PAIS_INUSUAL` — país atípico
  9. `FLAG_BIN12_REPETIDO_DIA` — BIN12 repetido
  10. `FLAG_SCORE_RIESGO_MON_ALTO` — score Monitor alto (solo crédito)
  11. `FLAG_HORA_FUERA_PERFIL_COMERCIO` — txn en hora atípica para el comercio

- **Interpretación:**
  - `0` → BAJO: sin señales.
  - `1–2` → MEDIO: señales leves. Monitoreo.
  - `3–5` → ALTO: varias señales. Revisar urgente.
  - `6+` → MUY_ALTO: múltiples señales simultáneas. Bloquear o intervención inmediata.

- **Ejemplo práctico:**
  ```
  Txn a las 3am (ES_MADRUGADA=1)
  + 4 txn en los últimos 5 min (FLAG_RAFAGA_5MIN=1)
  + Monto exacto de S/100 (FLAG_MONTO_REDONDO=1)
  + Mismo BIN12 en 3 tarjetas ese día (FLAG_BIN12_REPETIDO_DIA=1)
  + Score Visa = 85/99 (FLAG_SCORE_RIESGO_MON_ALTO=1)
  SCORE_RIESGO = 5 → ALTO
  ```

---

### `PERFIL_RIESGO`
- **Qué es:** Categoría del score en texto
- **Valores:** `BAJO` | `MEDIO` | `ALTO` | `MUY_ALTO`
- **En Power BI:** Usar como slicer para filtrar solo los perfiles de mayor riesgo. Ordenar con la columna calculada `Orden Perfil` (BAJO=1, MEDIO=2, ALTO=3, MUY_ALTO=4).

---

### `FLAG_HORARIO_RIESGO`
- **Qué es:** Flag si la txn ocurrió en madrugada O en fin de semana
- **Interpretar:** Horario con menor vigilancia humana. Si `FLAG_HORARIO_RIESGO=1` y `SCORE_RIESGO>=2`, el contexto de menor vigilancia amplifica el riesgo.

---

---

## BLOQUE M — Score Monitor Normalizado
*¿Qué tan riesgosa considera el sistema del banco a esta tarjeta?*

> **Solo aplica a tarjetas de CRÉDITO.** Débito no tiene score Monitor. Visa escala 0–99, Mastercard 0–999.

---

### `SCORE_MON_NORM`
- **Qué es:** Score del sistema Monitor normalizado a escala 0–1 para poder comparar Visa y Mastercard en la misma escala
- **Fórmula:** `SCORE_MON_NORM = score_original ÷ máximo_de_la_marca` (Visa: ÷99, MC: ÷999)
- **Ejemplo:** Visa con score 72 → `SCORE_MON_NORM = 72/99 = 0.73` | MC con score 650 → `SCORE_MON_NORM = 650/999 = 0.65`
- **Interpretar:** Mayor valor = el sistema de fraude del banco ya considera esa tarjeta más riesgosa. Un SCORE_MON_NORM > 0.7 significa que el propio sistema de alertas está encendido para esa tarjeta.
- **Importante:** Para débito, este campo es NaN — no usar en reglas de débito.
- **Combinar con:** `FLAG_RAFAGA_5MIN` — si el sistema ya la tiene como riesgosa Y hay ráfaga, es fraude con muy alta probabilidad.

---

### `FLAG_SCORE_RIESGO_MON_ALTO`
- **Qué es:** Flag si el `SCORE_MON_NORM ≥ 0.7` (score alto para la marca)
- **Valores:** `1` = score alto | `0` = score bajo o débito
- **Ejemplo:** Tarjeta Visa con score 80/99 → `FLAG_SCORE_RIESGO_MON_ALTO = 1`
- **Para la regla:** Este flag entra al `SCORE_RIESGO` compuesto (componente 10 de 11).

---

### `CATEGORIA_SCORE_MON`
- **Qué es:** Categoría del score en texto para facilitar la lectura
- **Valores:** `BAJO` (0–0.3) | `MEDIO` (0.3–0.5) | `MEDIO_ALTO` (0.5–0.7) | `ALTO` (0.7–0.85) | `MUY_ALTO` (>0.85) | `SIN_SCORE` (débito)
- **Usar en:** Hoja 21 del Excel (Score por marca) — ver la distribución de fraudes por categoría de score.

---

## BLOQUE N — Vínculos del Cliente
*¿El cliente tiene historial de fraude o comportamiento inusual en este comercio?*

---

### `N_FRAUDES_CLIENTE_PERIODO`
- **Qué es:** Cuántas transacciones marcadas como fraude tiene ese cliente en todo el período analizado
- **Ejemplo:** `N_FRAUDES_CLIENTE_PERIODO = 3` → ese cliente tiene 3 fraudes confirmados en el dataset
- **Interpretar:** Si es > 0, la tarjeta/cliente ha sido comprometida repetidamente y no fue bloqueada a tiempo. Cada fraude adicional es una falla en la gestión de bloqueos.
- **Combinar con:** `FLAG_PRIMERA_TRX_Y_DENEGADA` — si tiene fraudes previos Y la primera txn del día fue denegada, es un patrón de reintento de fraude conocido.

---

### `TIENE_FRAUDE_PREVIO_PERIODO`
- **Qué es:** Flag si el cliente tiene al menos 1 fraude previo en el período
- **Valores:** `1` = tiene antecedente | `0` = sin antecedente
- **Ejemplo:** Cliente con 2 fraudes marcados → `TIENE_FRAUDE_PREVIO_PERIODO = 1`
- **Para la regla:** Alta precisión, bajo recall. El 100% de las txn con este flag pertenecen a tarjetas ya comprometidas.

---

### `ES_RESIDENTE`
- **Qué es:** Flag si el cliente es residente en Perú según el país registrado en la tarjeta
- **Valores:** `1` = residente PE | `0` = no residente / extranjero
- **Interpretar:** La mayoría del fraude en ecommerce peruano viene de tarjetas locales comprometidas. Si hay fraude en tarjetas no residentes (`ES_RESIDENTE=0`), puede ser fraude transnacional — tarjetas extranjeras usadas en Perú.
- **Combinar con:** `FLAG_PAIS_INUSUAL` — si no es residente Y el país de la txn es inusual, es señal fuerte de fraude transnacional.

---

### `ZSCORE_MONTO_CLI_COMERCIO`
- **Qué es:** Cuántas desviaciones estándar se aleja el monto de esta txn del promedio histórico de ese cliente en **este comercio específico**
- **Diferencia vs `ZSCORE_MONTO_CLIENTE`:** El bloque E compara al cliente consigo mismo en todos los comercios. Este compara al cliente consigo mismo solo en este comercio.
- **Fórmula:** `(monto_actual - media_cliente_en_comercio) ÷ std_cliente_en_comercio`
- **Ejemplo:** Cliente que siempre gasta S/80 en ZARA → aparece una txn de S/450 → `ZSCORE_MONTO_CLI_COMERCIO = 4.6`
- **Interpretar:**
  - `> 3.0` → monto atípico para ese cliente en ese comercio específico. Muy sospechoso.
  - `0–1.5` → dentro del rango habitual del cliente en el comercio.
- **Por qué es mejor que el zscore global:** Un cliente puede gastar S/500 habitualmente en otros comercios, pero si en ZARA siempre gasta S/80 y aparece S/500, es inusual. El zscore global no detectaría eso.

---

### `TRX_DIA_PROM_CLIENTE_COMERCIO`
- **Qué es:** Promedio de transacciones por día que hace ese cliente en este comercio, calculado sobre su historial
- **Ejemplo:** `TRX_DIA_PROM_CLIENTE_COMERCIO = 1.2` → en promedio hace 1.2 txn por día cuando visita el comercio
- **Usar con:** `FLAG_TRX_EXCEDE_PATRON_CLI_COM`

---

### `FLAG_TRX_EXCEDE_PATRON_CLI_COM`
- **Qué es:** Flag si el número de txn del cliente en el día actual excede su promedio histórico en este comercio
- **Valores:** `1` = excede su patrón habitual | `0` = dentro de lo normal
- **Ejemplo:** Cliente que en promedio hace 1 txn por día en ZARA → hoy tiene 4 → `FLAG_TRX_EXCEDE_PATRON_CLI_COM = 1`
- **Interpretar:** Más discriminante que un umbral fijo (como "≥3 txn") porque se adapta a cada cliente. Un cliente frecuente con 3 txn puede ser normal; para otro con historial de 1 txn/visita, 3 es una anomalía.

---

### `FLAG_PRIMERA_TRX_Y_DENEGADA`
- **Qué es:** Flag si la primera transacción del cliente en el día fue denegada antes de la txn actual
- **Valores:** `1` = sí hubo un rechazo previo hoy | `0` = no
- **Ejemplo:** Cliente intenta a las 9am, le deniegan → vuelve a las 9:02am → `FLAG_PRIMERA_TRX_Y_DENEGADA = 1`
- **Interpretar:** El defraudador probó primero, falló, y reintentó con ajustes. Es el patrón de ensayo-error de card testing. La txn actual es el "segundo intento exitoso" luego de un fallo.
- **Combinar con:** `HUBO_CVV_FAIL_PREVIO` — si la primera fue denegada por CVV + esta tiene distinto CVV = cascada CVV activa.

---

## BLOQUE O — Perfil Horario del Comercio
*¿Esta txn está dentro del horario típico de actividad del comercio?*

---

### `HORA_PROM_COMERCIO`
- **Qué es:** Hora promedio a la que suelen ocurrir las transacciones en este comercio (en el dataset)
- **Ejemplo:** `HORA_PROM_COMERCIO = 14.3` → el comercio tiene actividad promedio a las 2:18pm
- **Usar con:** `FLAG_HORA_FUERA_PERFIL_COMERCIO` para entender qué tan lejos está la txn actual de la hora típica.

---

### `HORA_STD_COMERCIO`
- **Qué es:** Desviación estándar de la hora de actividad del comercio
- **Ejemplo:** `HORA_STD_COMERCIO = 3.2` → la actividad del comercio varía ±3.2 horas respecto al promedio
- **Interpretar:** Un comercio con `HORA_STD` bajo tiene actividad muy concentrada en un horario (ej: tienda de ropa, activa 10am–8pm). Un comercio con `HORA_STD` alto opera casi las 24h. Para los primeros, una txn a las 3am es más inusual.

---

### `FLAG_HORA_FUERA_PERFIL_COMERCIO`
- **Qué es:** Flag si la hora de la txn está a más de 2 desviaciones estándar del horario típico del comercio
- **Valores:** `1` = hora atípica para este comercio | `0` = dentro del perfil normal
- **Ejemplo:** Comercio activo habitualmente de 10am–9pm (HORA_PROM=15, HORA_STD=2.5) → txn a las 3am → `FLAG_HORA_FUERA_PERFIL_COMERCIO = 1`
- **Por qué es mejor que `ES_MADRUGADA`:** `ES_MADRUGADA` siempre marca de 0–5am sin importar el comercio. Este flag se adapta: si el comercio opera 24h (como Western Union online), una txn a las 3am puede ser normal y este flag = 0.
- **Para la regla:** Entra al `SCORE_RIESGO` compuesto (componente 11 de 11).

---

### `TRX_PROM_CLIENTE_DIA_COMERCIO`
- **Qué es:** Promedio de transacciones diarias que hace el cliente en el comercio, calculado sobre días en los que el cliente tuvo actividad
- **Usar con:** `FLAG_CLIENTE_SUPERA_PERFIL_COMERCIO`

---

### `FLAG_CLIENTE_SUPERA_PERFIL_COMERCIO`
- **Qué es:** Flag si el número de txn del cliente en el día actual supera el doble de su promedio diario en el comercio
- **Valores:** `1` = actividad anormalmente alta para ese cliente en ese comercio | `0` = normal
- **Ejemplo:** Cliente que promedia 1.5 txn/día en Amazon → hoy tiene 5 → `FLAG_CLIENTE_SUPERA_PERFIL_COMERCIO = 1`
- **Diferencia vs `FLAG_TRX_EXCEDE_PATRON_CLI_COM`:** Este usa "doble del promedio" como umbral; el otro solo verifica si excede el promedio. Este es más tolerante (requiere duplicar) pero más preciso.

---

## BLOQUE P — ML No Supervisado
*¿Es esta txn estadísticamente anómala respecto a todas las demás?*

> Estas variables las genera `ml/clustering_fraude.py` (paso opcional del pipeline).
> No requieren etiqueta F/N para funcionar — detectan patrones sin necesitar datos de fraude previo.

---

### `ANOMALY_SCORE`
- **Qué es:** Puntaje de anomalía asignado por Isolation Forest, en escala 0 a 1
- **Fórmula:** El modelo construye árboles de decisión aleatorios. Las transacciones que se "aíslan" rápido (en pocas divisiones) son más anómalas. El score se normaliza a [0, 1].
- **Ejemplo:** `ANOMALY_SCORE = 0.92` → esta txn está en el 8% más anómalo de todo el dataset
- **Interpretar:**
  - `> 0.8` → anomalía alta. Candidata a revisión aunque no esté marcada como fraude todavía.
  - `0.5–0.8` → zona gris. Inusual pero no extrema.
  - `< 0.5` → transacción típica del comercio.
- **Ventaja clave:** No depende de la etiqueta F — puede detectar fraude nuevo que el analista aún no revisó. Un fraude que acaba de ocurrir y está en N puede tener `ANOMALY_SCORE = 0.95`.
- **Ver en:** Hoja `IF_Anomalias` del Excel ML (`ml/output/ml_resumen_{COMERCIO}.xlsx`).

---

### `FLAG_ANOMALIA_IF`
- **Qué es:** Flag binario si el Isolation Forest clasificó la txn como anomalía
- **Valores:** `1` = anomalía | `0` = normal
- **Parámetro:** Controlado por `CONTAMINATION_IF = 0.05` en el script → aproximadamente el 5% de las txn serán marcadas como anomalía.
- **Ejemplo:** Con 4,453 txn totales → ~223 marcadas como anomalías.
- **Interpretar:** Si el porcentaje de fraudes (F) entre las anomalías es significativamente mayor que la tasa global, el modelo discrimina bien. Si la tasa de F en anomalías = 40% y la global = 6%, el modelo es 6.7x más preciso que el azar.
- **Ajuste:** Si hay muchos falsos positivos, subir `CONTAMINATION_IF` a 0.03. Si se pierden fraudes reales, bajar a 0.08.

---

### `CLUSTER_HDBSCAN`
- **Qué es:** Número de cluster asignado por HDBSCAN. `-1` indica ruido (outlier)
- **Valores:** `0`, `1`, `2`... (clusters) o `-1` (no pertenece a ningún cluster)
- **Ejemplo:** `CLUSTER_HDBSCAN = 2` → esta txn pertenece al cluster 2. `CLUSTER_HDBSCAN = -1` → transacción outlier, no encaja en ningún patrón.
- **Interpretar:**
  - **Cluster con alta TASA_F%:** El grupo de transacciones más concentrado en fraude. Revisar qué variables caracterizan ese cluster (ver hoja `HDBSCAN_Clusters`).
  - **Cluster -1 (ruido):** Transacciones que no encajan en ningún patrón → pueden ser fraudes muy específicos o errores de datos. Revisar manualmente.
  - Si todos los fraudes caen en cluster = -1, significa que no forman un patrón repetible — son fraudes muy diversos.
- **Diferencia con Isolation Forest:** IF busca anomalías individuales. HDBSCAN busca grupos de comportamiento similar. Ambos son complementarios: IF detecta lo raro, HDBSCAN agrupa lo similar.
- **Ver en:** Hoja `HDBSCAN_Clusters` del Excel ML.

---

## CÓMO INTERPRETAR EL ANÁLISIS COMPLETO PARA ESCRIBIR UNA REGLA

### Ejemplo de flujo de análisis:

1. **Ver hoja `Velocidad`** → ¿qué distribución tiene `TRX_CLIENTE_5MIN`? Si el percentil 90 es 0 (casi nadie tiene ráfaga), un threshold de 3 es muy agresivo. Si el P90 es 2, usar 3 es razonable.

2. **Ver hoja `Estadisticas_Monto`** → ¿cuánto es el monto promedio de fraude (indicador F) vs no fraude (G/N)? Si el fraude tiene monto promedio de S/150 y las buenas de S/80, un threshold de S/200 acumulado podría capturar más fraude que txn buenas.

3. **Ver hoja `Recomendaciones_Regla`** → para cada umbral, ¿qué % de fraude captura y qué % de txn buenas afecta? Buscar reglas con ratio >5x (capturan 5 veces más fraude del que afectan en buenas).

4. **Redactar el correo:**
   > "Basado en el análisis de [COMERCIO], se recomienda implementar las siguientes alertas:
   > 1. **Alerta de velocidad:** Declinar si el cliente tiene ≥3 txn en los últimos 5 minutos. Esta regla capturaría el 28% del fraude y afectaría solo el 2% de las txn buenas.
   > 2. **Alerta de monto acumulado:** Declinar si el monto acumulado en 24h supera S/500. Capturaría el 32% del fraude y afectaría el 6% de las txn buenas.
   > 3. **Combinación:** Declinar si hay ≥3 txn en 5 min Y monto acumulado >S/300. Capturaría el 22% del fraude con solo 1% de afectación a txn buenas."

---

## GLOSARIO RÁPIDO

| Término | Significado |
|---|---|
| Card testing | Probar tarjetas (a veces generadas) con montos pequeños para ver cuáles son válidas |
| Cascada CVV | Intentar múltiples CVVs hasta que uno pase |
| CNP | Card Not Present — transacción sin tarjeta física (ecommerce) |
| 3DS / TDS | 3D Secure — capa extra de autenticación (SMS, app bancaria) |
| BIN | Bank Identification Number — primeros 6+ dígitos de la tarjeta |
| MOTO | Mail Order / Telephone Order — txn por teléfono o correo |
| Tasa de fraude | Fraudes / Total txn |
| Colateral | Txn buenas que se afectarían si se aplica la regla |
| Percentil 90 | El 90% de los valores está por debajo de este número |
| Decil | Cada décima parte de la distribución (decil 10 = el 10% más alto) |
| Z-score | Número de desviaciones estándar desde la media |
| Ráfaga | Múltiples txn en un intervalo muy corto |
