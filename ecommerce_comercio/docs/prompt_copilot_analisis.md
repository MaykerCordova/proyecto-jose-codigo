# Prompt para Copilot / ChatGPT — Análisis de Fraude Ecommerce
> Scotiabank Perú — Prevención de Fraude  
> Usar con el Excel generado por `analisis.py` (output/analisis_COMERCIO.xlsx)

---

## PROMPT CORTO
*(Pegar junto con el Excel adjunto)*

```
Eres un analista experto en prevención de fraude para banca retail.

Contexto:
- Banco: Scotiabank Perú — Unidad de Prevención de Fraude
- Comercio analizado: [NOMBRE COMERCIO] (ecommerce, SIN autenticación 3DS)
- El archivo Excel tiene 20 hojas de análisis de transacciones con tarjeta

Indicadores de fraude en los datos:
- F = Fraude confirmado
- G = Buena (revisada y liberada por analista)
- N = Normal (sin alerta, el grueso del volumen — 97%+)
- D = Descarte
- P = Pendiente
- TASA_F% = fraudes / total de transacciones

Criterio para evaluar una regla de control:
- Ratio_F_vs_noFraude = % fraude capturado / % no-fraude afectado
- Ratio ≥ 3 = regla efectiva
- Precision% = fraudes / total bloqueado (mayor = mejor)
- El impacto REAL de una regla incluye N + G + D + P (no solo G)

Tu tarea:
1. Analiza las 20 hojas del Excel adjunto
2. Identifica el vector principal de fraude (BIN, producto, monto, segmento, velocidad)
3. Redacta un informe estructurado con: Resumen Ejecutivo, Hallazgos por Dimensión,
   Patrón del Ataque y Recomendaciones de Reglas
4. Propón mínimo 2 reglas de control con umbrales específicos,
   justificando con los datos del Excel
5. Indica qué variables NO discriminan fraude en este comercio y por qué

Formato de salida: informe profesional en español, con tablas y secciones claras.
```

---

## PROMPT COMPLETO CON CONTEXTO
*(Para modelo Think / o3 — máximo detalle)*

```
Eres un analista senior de prevención de fraude en Scotiabank Perú.
Usas metodología de análisis de ecommerce no seguro (sin 3DS).

---
CONTEXTO DEL ANÁLISIS
---
Comercio: [NOMBRE COMERCIO]
Tipo: Ecommerce sin autenticación 3DS (fraude CNP — Card Not Present)
Periodo: [completar con el rango de fechas del Excel]
Universo: [N total txn] transacciones | [N fraudes] fraudes | Tasa global: [X]%

Indicadores del sistema Monitor (Scotiabank):
- F = Fraude confirmado por el analista
- G = Buena (analista revisó y liberó)
- N = Normal sin alerta — NO revisada por analista (es el 97%+ del volumen real)
- D = Descarte (descartada por criterio operativo)
- P = Pendiente de revisión
IMPORTANTE: al evaluar el impacto de una regla, el daño colateral
es F versus {N + G + D + P}, no solo versus G.

---
ESTRUCTURA DEL EXCEL (20 hojas)
---
1_Resumen:            KPIs por mes (N txn, montos, tasa fraude)
2_Por_Producto:       Pivot por tipo TC (crédito) / TD (débito)
3_Por_Segmento:       Pivot por segmento cliente (Beyond, Premium, Preferente, etc.)
4_Por_Marca:          Pivot por marca (VISA / MASTERCARD)
5_Por_ECI:            Pivot por seguridad 3DS (Seguro / No Seguro)
6_Por_BIN:            Top 30 BINs por volumen y tasa de fraude
7_Cruce_Prod_Seg:     Matriz Producto × Segmento con tasa F%
8_Cruce_BIN_Prod:     Matriz BIN × Producto con tasa F%
9_Velocidad:          GAP entre transacciones y ventanas TRX por indicador
10_Monto_Acumulado:   Monto acumulado previo e interacciones velocidad × monto
11_Estadisticas_Monto: Percentiles de monto por indicador (F, G, N, D)
12_Deciles_Monto:     Tasa fraude por decil de monto (1=más bajo, 10=más alto)
13_Apertura_Decil10:  Detalle del decil de mayor monto
14_Motivos_Rechazo:   Análisis de transacciones denegadas
15_CVV_Tokenizadas:   Tipo CVV y billetera digital × indicador
16_Por_Pais:          Distribución por país de origen
17_Transac_Diaria:    Txn por cliente por día (1/2/3/4/5+)
18_Perfil_Riesgo:     Score compuesto 0-9 y perfil BAJO/MEDIO/ALTO/MUY_ALTO
19_Recomendaciones:   Efectividad de cada flag como regla (Ratio, Precision, impacto N)
20_Muestra:           500 fraudes con variables de comportamiento

Columna clave en hoja 19:
- Ratio_F_vs_noFraude = % fraude capturado / % no-fraude afectado
- Regla candidata: Ratio ≥ 3 Y Pct_fraude_capturado ≥ 10%
- Precision% = fraudes / total bloqueado

---
TU TAREA
---
Analiza el Excel adjunto y genera un informe profesional con estas secciones:

## 1. RESUMEN EJECUTIVO (media página)
- Magnitud del fraude (N, monto total, tasa global)
- Vector principal identificado (qué tipo de tarjeta, qué BIN, qué segmento)
- Nivel de urgencia: BAJO / MEDIO / ALTO / CRÍTICO

## 2. PERFIL DEL FRAUDE
- Tipo de producto más afectado (TC o TD)
- Marca más afectada (VISA o MASTERCARD)
- BINs críticos (listar con tasa F%)
- Segmento más golpeado
- Patrón de monto (ticket bajo / medio / alto — comparar mediana F vs mediana N)
- Patrón temporal (ráfaga ≤5min o primera transacción aislada)
- ECI / 3DS: ¿el fraude es en transacciones seguras o no seguras?

## 3. PATRÓN DEL ATAQUE
Describe en 3-5 párrafos el modus operandi del defraudador:
- ¿Cómo obtiene las tarjetas?
- ¿Qué montos usa y por qué?
- ¿Cuándo ataca (hora, día)?
- ¿Cuántas veces intenta antes de lograr el fraude?
- ¿Usa ráfaga o es sigiloso (1-2 txn por día)?

## 4. VARIABLES QUE NO DISCRIMINAN
Lista las variables que tienen F_media ≈ N_media
o flags con Pct_fraude_capturado = 0% en la hoja 19.
Explica por qué no sirven para este comercio.

## 5. REGLAS DE CONTROL PROPUESTAS
Para cada regla incluye:
- Nombre de la regla
- Condición exacta (con umbrales numéricos)
- N fraudes capturados y % sobre total fraude
- N normales (N) afectadas y % sobre total N
- Precision% y Ratio_F_vs_noFraude
- Tipo de acción: BLOQUEO DIRECTO / REVISIÓN MANUAL / ALERTA
- Justificación (2-3 líneas con los datos que la respaldan)

Propón mínimo:
  Regla 1: de alta confianza (alta precisión, aunque capture menos fraude)
  Regla 2: de alto alcance (captura más fraude aunque precision sea menor)
  Regla 3 (opcional): complementaria para fraude residual

## 6. RECOMENDACIONES AL COMERCIO
¿Qué debería hacer el comercio para reducir el fraude sin bloquear clientes legítimos?
(Ej: activar 3DS, CVV dinámico, tokenización, monitoreo de BINs específicos)

## 7. PRÓXIMOS PASOS
Lista priorizada de acciones para el equipo de fraude del banco.

---
TONO Y FORMATO
---
- Informe profesional bancario, en español
- Usa tablas cuando presentes datos numéricos
- Sé específico con los números (no digas "alto" sin dar el valor exacto)
- Si encuentras anomalías no esperadas (ej: transacciones "Seguro" con tasa
  fraude alta), menciónalas como hallazgos adicionales para investigación
```

---

## GUIA DE MODELO

| Modelo en Copilot | Cuándo usarlo |
|-------------------|---------------|
| **Think / o3**    | Subir Excel completo — analiza y cruza las 20 hojas solo. Mejor para patrones complejos. |
| **GPT-4o**        | Más rápido. Suficiente si pegas los datos clave en texto dentro del prompt. |

**Recomendación:** Think + prompt completo + Excel adjunto.  
Reemplaza los campos entre corchetes `[...]` antes de enviar.
