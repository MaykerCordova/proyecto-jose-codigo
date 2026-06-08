"""
generar_informe_html.py — Genera informe HTML sin paquetes adicionales
Tarjetas Comprometidas N7 Débito — Scotiabank Peru

No requiere instalación de paquetes extra.
Abrir el HTML en cualquier navegador. Desde ahí: Ctrl+P → Guardar como PDF.

Ejecutar:
    python scripts/generar_informe_html.py

Output:
    output/informe_scoring_TARJETAS_COMPROMETIDAS_N7.html
"""

import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import BASE_DIR, ANALISIS_NOMBRE

OUTPUT_HTML = BASE_DIR / "output" / f"informe_scoring_{ANALISIS_NOMBRE}.html"

# ─── Helpers ────────────────────────────────────────────────────────────────
def tabla_html(encabezados, filas, notas=""):
    th = "".join(f"<th>{h}</th>" for h in encabezados)
    rows = ""
    for i, fila in enumerate(filas):
        cls = "par" if i % 2 == 0 else "impar"
        tds = "".join(f"<td>{v}</td>" for v in fila)
        rows += f"<tr class='{cls}'>{tds}</tr>\n"
    nota_html = f"<p class='nota'>{notas}</p>" if notas else ""
    return f"""
<table>
  <thead><tr>{th}</tr></thead>
  <tbody>{rows}</tbody>
</table>
{nota_html}"""

# ─── CSS ────────────────────────────────────────────────────────────────────
CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: Arial, sans-serif; font-size: 10pt; color: #222; background: #fff; padding: 20px 40px; }
h1 { font-size: 18pt; color: #1F3564; border-bottom: 3px solid #C00000; padding-bottom: 6px; margin: 24px 0 10px; }
h2 { font-size: 13pt; color: #C00000; margin: 20px 0 8px; }
h3 { font-size: 11pt; color: #1F3564; margin: 16px 0 6px; border-left: 4px solid #C00000; padding-left: 8px; }
p  { margin: 6px 0; line-height: 1.5; }
ul { margin: 6px 0 6px 20px; line-height: 1.7; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 9pt; }
thead tr { background: #1F3564; color: white; }
th { padding: 7px 8px; text-align: left; }
td { padding: 5px 8px; border-bottom: 1px solid #ddd; }
tr.par  { background: #F5F5F5; }
tr.impar{ background: #FFFFFF; }
.portada { text-align: center; padding: 30px 0; border-bottom: 2px solid #1F3564; margin-bottom: 30px; }
.portada h-title { display: block; font-size: 22pt; font-weight: bold; color: #1F3564; }
.portada h-sub   { display: block; font-size: 15pt; color: #C00000; font-weight: bold; margin-top: 8px; }
.portada h-info  { display: block; font-size: 11pt; color: #555; margin-top: 6px; }
.kpi-box { display: inline-block; background: #1F3564; color: white; border-radius: 6px;
           padding: 10px 20px; margin: 6px; text-align: center; min-width: 140px; }
.kpi-box .num { font-size: 16pt; font-weight: bold; display: block; }
.kpi-box .lbl { font-size: 8pt; }
.alerta  { background: #FFF3CD; border-left: 4px solid #FFC107; padding: 8px 12px; margin: 8px 0; }
.bien    { background: #D4EDDA; border-left: 4px solid #28A745; padding: 8px 12px; margin: 8px 0; }
.nota    { color: #666; font-size: 8.5pt; font-style: italic; margin-top: 4px; }
.badge-r { background: #C00000; color: white; border-radius: 4px; padding: 2px 6px; font-size: 8pt; }
.badge-g { background: #28A745; color: white; border-radius: 4px; padding: 2px 6px; font-size: 8pt; }
.badge-y { background: #FFC107; color: #333; border-radius: 4px; padding: 2px 6px; font-size: 8pt; }
hr { border: none; border-top: 1px solid #ddd; margin: 16px 0; }
@media print { body { padding: 10px 20px; } h1 { page-break-before: always; } }
"""

# ─── Contenido ──────────────────────────────────────────────────────────────
def build_html():
    hoy = date.today().strftime("%d/%m/%Y")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Sustento Scoring Fraude N7 — Scotiabank Perú</title>
<style>{CSS}</style>
</head>
<body>

<!-- PORTADA -->
<div class="portada">
  <span class="h-title">SUSTENTO TÉCNICO — SCORING DE FRAUDE</span>
  <span class="h-sub">Tarjetas Débito Comprometidas N7 / INE7</span>
  <span class="h-info">Scotiabank Perú | Prevención de Fraude Digital | {hoy}</span>
  <br><br>
  <div class="kpi-box"><span class="num">170,944</span><span class="lbl">Transacciones analizadas</span></div>
  <div class="kpi-box"><span class="num">2,288</span><span class="lbl">Fraudes (1.34%)</span></div>
  <div class="kpi-box"><span class="num">S/ 130,043</span><span class="lbl">Monto fraude total</span></div>
  <div class="kpi-box"><span class="num">387</span><span class="lbl">Clientes con fraude</span></div>
  <div class="kpi-box"><span class="num">Dic 2025 – May 2026</span><span class="lbl">Período analizado</span></div>
</div>

<!-- SECCIÓN 1 -->
<h1>1. Contexto del Problema</h1>
<p>Las tarjetas de débito comprometidas (código N7/INE7) son tarjetas cuyos datos fueron robados o clonados.
El banco las identifica y las segmenta para monitoreo especial. El desafío es que <strong>dos actores usan la misma tarjeta</strong>:</p>

{tabla_html(
    ["Actor", "Comportamiento", "Etiqueta en la base"],
    [
        ["Titular legítimo", "Compras espaciadas, montos normales, comercios habituales", "N / G (No fraude)"],
        ["Defraudador",      "Muchas compras seguidas, rápido, antes del bloqueo de la tarjeta", "F (Fraude)"],
    ]
)}

<h2>Hallazgos contraintuitivos confirmados</h2>
{tabla_html(
    ["Intuición común", "Realidad en este dataset", "Por qué"],
    [
        ["El fraude ocurre de madrugada", "Tasa TARDE (1.47%) &gt; MADRUGADA (1.11%)", "El defraudador actúa en horario comercial normal"],
        ["El fraude es en montos altos",  "Mediana fraude: S/38 vs S/22 legítimo",    "Evita llamar la atención con tickets extremos"],
        ["Multi-país = señal de fraude",  "Multi-país tiene MENOR tasa de fraude",    "El fraude N7 es mayoritariamente local (Perú)"],
        ["Bolivia = riesgo remoto",       "Bolivia = 100% tasa de fraude (9/9 txn)",  "Regla perfecta: declinar automáticamente"],
    ]
)}

<!-- SECCIÓN 2 -->
<h1>2. Metodología — Dos Enfoques Complementarios</h1>

<h2>2.1 Enfoque Operativo (Monitor — reglas IF-THEN)</h2>
<p>Se aplica una condición sobre <strong>TODA la base</strong> y se mide el impacto. Es el enfoque actual del equipo:</p>
<ul>
  <li>Se define una regla: <em>Si MCC = 5411 Y Monto &gt;= S/50 → Alertar</em></li>
  <li>Se cuenta cuántos fraudes captura y cuántos clientes buenos afecta</li>
  <li>No hay separación de datos: se prueba en toda la base histórica</li>
</ul>
<p class="nota">Ventaja: directo e implementable en Monitor. Limitación: cada regla es independiente, no aprende del comportamiento combinado de variables.</p>

<h2>2.2 Enfoque Machine Learning (modelo estadístico)</h2>
<p>El modelo aprende de los datos para asignar a <strong>cada transacción individual</strong> una probabilidad P(fraude) entre 0 y 1.
El proceso sigue 4 pasos:</p>

{tabla_html(
    ["Paso", "Qué hacemos", "Para qué sirve"],
    [
        ["1. Ingeniería de variables", "Creamos 30 variables de comportamiento (velocidad, z-scores, flags binarios)", "Darle al modelo señales ricas más allá de los datos crudos de Monitor"],
        ["2. Train/Test split (80/20)", "136,598 txn para entrenar — 34,150 txn para probar (nunca vistas)", "Simular cómo funciona con transacciones futuras"],
        ["3. Entrenamiento",           "El modelo aprende qué variables y en qué peso predicen el fraude",  "Obtener los coeficientes (pesos) de cada variable"],
        ["4. Evaluación y extrapolación", "Medimos AUC, KS, deciles en el test set y escalamos a la base", "Validar antes de producción"],
    ]
)}

<div class="bien">
  <strong>¿Por qué separar en Train y Test?</strong><br>
  Si entrenamos y evaluamos en la misma data, el modelo simplemente "memoriza" y parece perfecto.
  El Test simula exactamente transacciones futuras que el modelo nunca vio durante el entrenamiento.
  Nuestro Test: <strong>AUC Train=0.791 vs AUC Test=0.796</strong> — diferencia mínima = sin sobreajuste ✅
</div>

<!-- SECCIÓN 3 -->
<h1>3. El Modelo — Regresión Logística</h1>

<h2>3.1 ¿Qué es y cómo funciona?</h2>
<p>La Regresión Logística produce una <strong>ecuación matemática</strong> que combina 30 variables:</p>
<p style="text-align:center; font-size:12pt; margin:12px 0;">
  <strong>P(fraude) = 1 / (1 + e<sup>−Z</sup>)</strong><br>
  <em>Z = β₀ + β₁×Variable1 + β₂×Variable2 + ... + β₃₀×Variable30</em>
</p>
<p>Donde cada <strong>β (beta)</strong> es el peso que el modelo aprendió. Si β &gt; 0 → la variable sube el riesgo.
Si β &lt; 0 → la variable lo baja.</p>

<h2>3.2 ¿Cómo interpretar el Odds Ratio (OR)?</h2>
<p>El <strong>Odds Ratio = e<sup>β</sup></strong> es la forma más intuitiva de leer los coeficientes:</p>
{tabla_html(
    ["OR", "Qué significa", "Ejemplo real"],
    [
        ["OR &gt; 1", "Esta variable MULTIPLICA el riesgo de fraude", "TRX_TARJETA_24H OR=2.33 → más txn en 24h = 2.3x más riesgo"],
        ["OR = 1",  "Esta variable NO afecta el riesgo (neutro)",     "Variable sin poder predictivo"],
        ["OR &lt; 1", "Esta variable REDUCE el riesgo de fraude",     "ES_SEGURO OR=0.77 → con 3DS = 23% menos riesgo"],
    ]
)}

<h2>3.3 Variables del modelo — traducción a Monitor</h2>
{tabla_html(
    ["Variable", "OR", "Dirección", "Interpretación negocio", "Condición Monitor"],
    [
        ["TRX_TARJETA_24H",       "2.33", "↑ Riesgo", "Más txn en 24h = más riesgo. Fraude: 12.6 / Legítimo: 1.5 txn promedio", "COUNT(txn_tarjeta, 24h) &gt;= 5"],
        ["FLAG_ECOMMERCE",        "2.07", "↑ Riesgo", "Transacción online = 2x más riesgo", "CANAL = CNP (Card Not Present)"],
        ["TRX_CLIENTE_1H",        "1.45", "↑ Riesgo", "Más txn del cliente en 1h = más riesgo", "COUNT(txn_cliente, 1h) &gt;= 3"],
        ["FLAG_COD_TRX_10",       "1.45", "↑ Riesgo", "Código de transacción 10 asociado a fraude", "COD_TRX = '10'"],
        ["CONCENTRACION_5MIN_1H", "1.36", "↑ Riesgo", "Txn concentradas en ráfaga", "Derivar de velocidades Monitor"],
        ["FLAG_MCC_ALTO_RIESGO",  "1.17", "↑ Riesgo", "MCC en lista de alto riesgo histórico", "MCC IN (5411,4829,4121,4722)"],
        ["GAP_MINUTOS",           "0.68", "↓ Protege","Más tiempo entre compras = menos riesgo. Gap corto = sospechoso", "TIME_SINCE_LAST &lt;= 10min → alerta"],
        ["ES_SEGURO (3DS)",       "0.77", "↓ Protege","Con autenticación 3DS hay menos fraude", "ECI IN ('05','02') → reducir alerta"],
        ["FLAG_COD_TRX_92",       "0.48", "↓ Protege","Código 92 (reversión) reduce falsos positivos", "Excluir COD_TRX = '92' de alertas"],
        ["FLAG_MONTO_BAJO",       "0.56", "↓ Protege","Montos muy bajos tienen menos fraude en este segmento", "MONTO &lt; S/20 → menor prioridad"],
    ]
)}

<div class="alerta">
  <strong>Nota sobre SCORE_RIESGO:</strong> Esta variable (suma de flags individuales) fue <strong>excluida del modelo ML</strong>
  porque genera multicolinealidad — distorsiona los coeficientes de las variables que la componen.
  Sin embargo, <strong>sí se usa como regla de negocio en Monitor (Regla 3)</strong> porque como condición independiente
  es perfectamente válida: "si 7+ señales simultáneas → alertar".
</div>

<h2>3.4 Métricas del modelo</h2>
{tabla_html(
    ["Métrica", "Train", "Test", "Benchmark industria", "Evaluación"],
    [
        ["AUC-ROC",           "0.7913", "0.7960", "&gt;0.75 bueno / &gt;0.85 excelente", "✅ Bueno"],
        ["Gini",              "0.5826", "0.5919", "&gt;0.40 bueno / &gt;0.60 excelente", "✅ Bueno"],
        ["KS Statistic",      "0.4442", "0.4691", "&gt;0.30 bueno / &gt;0.50 excelente", "✅ Bueno"],
        ["Diferencia Train-Test","—",   "0.0047", "&lt;0.02 = sin sobreajuste",           "✅ Sin sobreajuste"],
    ]
)}

<h2>3.5 Matriz de Confusión — Lo que pasa en la práctica</h2>
<p>A umbral P &gt;= 0.70 sobre el test set (34,150 txn):</p>
{tabla_html(
    ["", "MODELO: Aprueba", "MODELO: Declina/Alerta"],
    [
        ["REAL: Legítima", "TN = 24,549 ✅ Aprobadas correctamente (~122,745 en base total)", "FP = 9,143 ⚠️ Afectadas por error (~45,715 en base total)"],
        ["REAL: Fraude",   "FN = 133 ❌ Fraudes que escapan (~665 en base total)",            "TP = 325 ✅ Fraudes capturados (~1,625 en base total)"],
    ]
)}

<h2>3.6 Análisis por deciles</h2>
<p>Los deciles ordenan transacciones de mayor a menor score y muestran concentración de fraude:</p>
{tabla_html(
    ["Decil", "Score", "Txn", "Fraudes", "Tasa fraude%", "Captura acumulada%", "Lift vs base"],
    [
        ["1 — más riesgoso", "0.65–1.00", "3,415", "209", "6.12%", "45.6%", "4.6x"],
        ["2",                "0.55–0.65", "3,415", "93",  "2.72%", "65.9%", "2.0x"],
        ["3",                "0.49–0.55", "3,415", "24",  "0.70%", "71.2%", "0.5x"],
        ["4 al 10",          "0.00–0.49", "23,905","132", "0.55%", "100%",  "&lt;1x"],
    ],
    notas="Revisando el TOP 20% de transacciones (mayor score) → capturamos el 65.9% del fraude."
)}

<!-- SECCIÓN 4 -->
<h1>4. Las 5 Reglas Simples — Sustento Individual</h1>

<h2>4.1 Tabla resumen de impacto</h2>
{tabla_html(
    ["Regla", "Condición", "Fraudes", "Recall%", "Legítimas afect.", "Monto fraude", "Precision", "Ratio FP/TP"],
    [
        ["<span class='badge-g'>R4</span> Bolivia",      "País = BO",                                   "9",     "0.4%",  "0",     "S/ 679",    "100.0%", "0.0x — Perfecto"],
        ["<span class='badge-g'>R5</span> Ráfaga 5min",  "3+ txn en 5 min",                            "182",   "8.0%",  "395",   "S/ 1,677",  "31.5%",  "2.2x — Excelente"],
        ["<span class='badge-y'>R1</span> Velocidad",    "5+ txn 24h Y GAP &lt;= 10min",              "306",   "13.4%", "3,424", "S/ 4,651",  "8.2%",   "11.2x"],
        ["<span class='badge-y'>R2</span> MCC riesgo",   "MCC {5411,4829,4121} Y monto&gt;=S/50",     "546",   "23.9%", "6,415", "S/ 54,262", "7.8%",   "11.7x"],
        ["<span class='badge-r'>R3</span> Score &gt;= 7","SCORE_RIESGO &gt;= 7",                       "1,072", "46.9%", "9,315", "S/ 44,859", "10.3%",  "8.7x"],
    ]
)}
<p class="nota">Ratio FP/TP = por cada fraude capturado, cuántas transacciones legítimas afectamos. Menor es mejor.</p>

<h2>4.2 Sustento por regla</h2>
<h3><span class="badge-g">R4</span> País Bolivia — PRIORIDAD ALTA: Implementar esta semana</h3>
<p>9 transacciones, 9 fraudes, 0 clientes buenos afectados. <strong>Precisión 100%</strong>. No existe ningún cliente
legítimo del banco que haya transaccionado desde Bolivia en el período dic 2025 – may 2026.
Esta regla es perfecta: <strong>declinar automáticamente sin costo operativo</strong>.</p>

<h3><span class="badge-g">R5</span> Ráfaga en 5 Minutos — PRIORIDAD ALTA: Mejor balance captura/costo</h3>
<p>Cuando una tarjeta hace 3+ transacciones en 5 minutos, la tasa de fraude sube al <strong>31.5%</strong> (vs 1.34% base).
El defraudador intenta maximizar compras antes del bloqueo. Ratio FP/TP = 2.2x —
<strong>por cada fraude capturado, afectamos solo 2.2 transacciones legítimas</strong>.</p>

<h3><span class="badge-y">R1</span> Velocidad Extrema — PRIORIDAD MEDIA</h3>
<p>El fraude promedia 12.6 txn en 24h vs 1.5 del legítimo, con gap de 2,087 min entre txn vs 6,718 del legítimo.
Cuando TRX_24H &gt;= 5 Y GAP &lt;= 10min se detecta al defraudador en plena ráfaga.
Ratio FP/TP = 11.2 — mayor costo que R5. Considerar combinar con MCC (ver sección 5).</p>

<h3><span class="badge-y">R2</span> MCC Alto Riesgo — PRIORIDAD MEDIA: Mayor monto protegido</h3>
<p>Los 3 MCCs con mayor tasa de fraude y volumen:
5411 Supermercados (6.58%, 3,905 txn),
4829 Wire transfers (5.47%, 6,856 txn),
4121 Taxis/Uber (2.50%, 30,409 txn).
Esta regla protege <strong>S/54,262</strong> — el 41.7% del monto total de fraude.</p>

<h3><span class="badge-r">R3</span> Score de Riesgo &gt;= 7 — PRIORIDAD ALTA: Mayor captura individual</h3>
<p>SCORE_RIESGO suma múltiples alertas simultáneas. Score &gt;= 7 significa que varias señales
activas a la vez en una sola transacción. Solo esta regla captura el <strong>46.9%</strong> del fraude total.
(Nota: para implementar en Monitor, traducir a sus componentes individuales.)</p>

<!-- SECCIÓN 5 -->
<h1>5. Reglas Combinadas — Mayor Precisión, Menor Afectación</h1>

<p>Combinar condiciones del modelo reduce significativamente los falsos positivos.
El modelo ML nos indica qué variables son más predictivas — combinamos las más potentes:</p>

{tabla_html(
    ["Regla combinada", "Condición Monitor", "Por qué esta combinación"],
    [
        ["COMB-A: Ráfaga + Sin 3DS",        "FLAG_RAFAGA_5MIN = 1 AND ECI NOT IN ('05','02')",                           "Ráfaga ya es señal fuerte; sin 3DS confirma evasión de autenticación"],
        ["COMB-B: Velocidad + MCC",          "TRX_24H &gt;= 5 AND GAP &lt;= 10min AND MCC IN (5411,4829,4121)",         "Velocidad en comercio de riesgo = patrón clásico del defraudador"],
        ["COMB-C: Ráfaga + MCC",             "FLAG_RAFAGA_5MIN = 1 AND MCC IN (5411,4829,4121)",                         "Combinación más potente del modelo: OR=2.07 y OR=1.17"],
        ["COMB-D: Ecommerce + Sin 3DS + Vel","FLAG_ECOMMERCE = 1 AND ECI NOT IN ('05','02') AND TRX_24H &gt;= 3",       "Ecommerce sin autenticación con velocidad = alto riesgo"],
        ["COMB-E: MCC + Velocidad + Monto",  "MCC IN (5411,4829,4121) AND TRX_24H &gt;= 3 AND MONTO &gt;= S/30",       "Comercio de riesgo + velocidad moderada + monto mínimo"],
    ]
)}

<div class="bien">
  <strong>Resultado esperado:</strong> Las reglas combinadas tienen mayor Precision (menos legítimas afectadas por fraude capturado)
  a costa de menor Recall (capturan menos fraudes en total). El trade-off ideal depende
  de cuánta fricción al cliente legítimo es aceptable para el negocio.
  Correr <code>3_ejecutar_ml.bat</code> muestra los números exactos de cada combinación.
</div>

<!-- SECCIÓN 6 -->
<h1>6. Cascada — Implementación por Fases</h1>

{tabla_html(
    ["Fase", "Reglas", "Fraudes acumulados", "% Total", "Legítimas acumuladas", "Precision acum."],
    [
        ["<span class='badge-g'>FASE 1</span>", "R4 Bolivia + R5 Ráfaga", "191", "8.4%",  "395",    "~48%"],
        ["<span class='badge-y'>FASE 2</span>", "+ R3 Score &gt;= 7",      "1,090", "47.6%", "11,644", "8.6%"],
        ["<span class='badge-r'>FASE 3</span>", "+ R2 MCC riesgo",         "1,476", "64.5%", "17,699", "7.7%"],
    ]
)}

<ul>
  <li><strong>FASE 1 — Esta semana:</strong> R4 + R5 → 8.4% del fraude, solo 395 legítimas afectadas. Riesgo operativo mínimo.</li>
  <li><strong>FASE 2 — Siguiente mes:</strong> + R3 → salta a 47.6% del fraude. Evaluar capacidad de revisión manual.</li>
  <li><strong>FASE 3 — Después de F2:</strong> + R2 → llega a 64.5%. Ajustar umbral de monto si afectación es alta.</li>
</ul>

<!-- SECCIÓN 7 -->
<h1>7. Hacia el Machine Learning en Fraude</h1>

<h2>7.1 Técnicas disponibles</h2>
{tabla_html(
    ["Técnica", "Cómo funciona", "Ventaja sobre reglas manuales", "Cuándo usarla"],
    [
        ["Regresión Logística (actual)", "Ecuación con pesos por variable",       "Combina 30 variables simultáneamente",        "Interpretabilidad — explicar a reguladores"],
        ["Árboles de Decisión",          "Genera reglas IF-THEN automáticamente", "Las reglas resultantes son directas y claras", "Para generar reglas Monitor automáticamente"],
        ["Random Forest",                "100+ árboles, promedia predicciones",   "Muy robusto, maneja bien el desbalance",       "Cuando precisión importa más que interpretabilidad"],
        ["XGBoost",                      "Árboles secuenciales que corrigen errores","Mejor AUC en mayoría de problemas de fraude","Máxima capacidad predictiva"],
        ["Isolation Forest (no superv.)","Detecta anomalías estadísticas",        "No necesita etiquetas de fraude histórico",   "Fraude nuevo sin patrones conocidos"],
    ]
)}

<h2>7.2 Metodología estándar</h2>
{tabla_html(
    ["Paso", "En este proyecto", "En general"],
    [
        ["1. Definir el problema",    "¿Qué txn son fraude en tarjetas N7?",                  "¿Qué quiero predecir?"],
        ["2. Recopilar datos",        "170,944 txn, 268 columnas, dic 2025–may 2026",          "Data histórica etiquetada"],
        ["3. Ingeniería variables",   "30 variables de comportamiento",                         "Señales ricas desde datos crudos"],
        ["4. Seleccionar técnica",    "Regresión Logística (AUC &gt;= 0.75)",                  "Interpretabilidad vs performance"],
        ["5. Entrenar y validar",     "Train 80% / Test 20% — AUC 0.796, KS 0.469",           "Métricas en datos nunca vistos"],
        ["6. Interpretar",            "Odds Ratios, deciles, umbrales operativos",              "¿Qué dice el modelo?"],
        ["7. Traducir a acciones",    "5 reglas Monitor con sustento de impacto",              "Reglas, alertas, producción"],
        ["8. Monitorear",             "PSI por feature — todas estables",                      "¿El modelo sigue siendo válido?"],
    ]
)}

<!-- SECCIÓN 8 -->
<h1>8. Conclusiones y Próximos Pasos</h1>

<h2>Lo que logramos</h2>
<ul>
  <li>✅ Modelo de scoring AUC=0.796, KS=0.469, sin sobreajuste (Train ≈ Test)</li>
  <li>✅ 5 reglas Monitor con sustento cuantitativo completo (fraudes/monto/clientes/costo)</li>
  <li>✅ Reglas combinadas para mayor precisión y menor afectación al cliente legítimo</li>
  <li>✅ Bolivia: regla perfecta (100% precisión, 0 afectados) lista para implementar</li>
  <li>✅ Identificación de variables más predictivas: TRX_24H, ECOMMERCE, RAFAGA_5MIN</li>
  <li>✅ Captura potencial del 64.8% del fraude con las 5 reglas combinadas</li>
</ul>

<h2>Próximos pasos</h2>
{tabla_html(
    ["Prioridad", "Acción", "Impacto esperado"],
    [
        ["<span class='badge-g'>INMEDIATO</span>", "Implementar R4 Bolivia en Monitor",                  "9 fraudes bloqueados, 0 costo"],
        ["<span class='badge-g'>INMEDIATO</span>", "Implementar R5 Ráfaga 5min en Monitor",             "182 fraudes, Precision 31.5%"],
        ["<span class='badge-y'>1 MES</span>",     "Implementar R3 Score &gt;= 7 con revisión manual",  "Captura acumulada 47.6%"],
        ["<span class='badge-y'>2 MESES</span>",   "Evaluar reglas combinadas (COMB-A, B, C)",          "Mayor precisión, menos FP"],
        ["<span class='badge-r'>3 MESES</span>",   "Reentrenar modelo con 6 meses adicionales",         "Incorporar nuevos patrones"],
        ["<span class='badge-r'>FUTURO</span>",    "Árboles de decisión para reglas automáticas",       "Escalabilidad a otros segmentos"],
    ]
)}

<hr>
<p class="nota" style="text-align:center; margin-top:20px;">
  Scotiabank Perú | Prevención de Fraude Digital | Generado con Python + Machine Learning<br>
  Para convertir a PDF: Ctrl+P → Guardar como PDF en el navegador
</p>

</body>
</html>"""
    return html

# ─── Guardar ────────────────────────────────────────────────────────────────
OUTPUT_HTML.parent.mkdir(exist_ok=True)
html = build_html()
OUTPUT_HTML.write_text(html, encoding="utf-8")
print(f"✅  Informe HTML guardado: {OUTPUT_HTML}")
print(f"    Abrirlo en el navegador y Ctrl+P para exportar a PDF")
