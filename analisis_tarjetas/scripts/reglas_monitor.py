"""
reglas_monitor.py — Análisis de Efectividad de Reglas para Monitor
Tarjetas Comprometidas N7 Débito — Scotiabank Peru

Calcula para cada regla propuesta:
  - Transacciones capturadas: fraude vs legítimo
  - Clientes afectados: fraude vs legítimo
  - Monto capturado: fraude vs legítimo (S/)
  - Precision, Recall, % afectación cliente legítimo
  - Análisis en cascada: captura acumulada por regla

Ejecutar DESPUÉS de feature_engineering.py y ml_scoring.py:
    python scripts/reglas_monitor.py

Output:
    output/reglas_monitor_TARJETAS_COMPROMETIDAS_N7.xlsx
"""

import sys
import warnings
import pandas as pd
import numpy as np
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import COLS, PARQUET_FEATURES, ANALISIS_NOMBRE, BASE_DIR

C       = COLS
col_ind = C["indicador"]
col_mto = C["monto"]
col_cli = C["id_cliente"]
col_pais= C["pais"]
col_mcc = C["mcc"]

OUTPUT_REGLAS = BASE_DIR / "output" / f"reglas_monitor_{ANALISIS_NOMBRE}.xlsx"

print("═" * 65)
print(f"ANÁLISIS DE REGLAS MONITOR — {ANALISIS_NOMBRE}")
print("═" * 65)

# ─────────────────────────────────────────────────────────────────────────────
# CARGA
# ─────────────────────────────────────────────────────────────────────────────
ruta = PARQUET_FEATURES
if not ruta.exists():
    print(f"\n❌  No se encontró: {ruta}")
    print("    Ejecuta primero: python scripts/feature_engineering.py")
    sys.exit(1)

df = pd.read_parquet(ruta)
df[col_mto] = pd.to_numeric(df[col_mto], errors="coerce").fillna(0)

# Target
df["ES_FRAUDE"] = (df[col_ind] == "F").astype(int)

total_txn      = len(df)
total_fraude   = int(df["ES_FRAUDE"].sum())
total_legitimo = total_txn - total_fraude
monto_total_f  = df.loc[df["ES_FRAUDE"]==1, col_mto].sum()
monto_total_n  = df.loc[df["ES_FRAUDE"]==0, col_mto].sum()
clientes_f     = df.loc[df["ES_FRAUDE"]==1, col_cli].nunique()
clientes_n     = df.loc[df["ES_FRAUDE"]==0, col_cli].nunique()

print(f"\n  Total transacciones  : {total_txn:,}")
print(f"  Total fraudes        : {total_fraude:,}  ({total_fraude/total_txn*100:.2f}%)")
print(f"  Total legítimas      : {total_legitimo:,}")
print(f"  Monto fraude total   : S/ {monto_total_f:,.2f}")
print(f"  Clientes con fraude  : {clientes_f:,}")


# ─────────────────────────────────────────────────────────────────────────────
# DEFINICIÓN DE REGLAS
# ─────────────────────────────────────────────────────────────────────────────

MCC_ALTO_RIESGO_REGLA = {"5411", "4829", "4722", "4121"}

def aplicar_regla(df, nombre, condicion, descripcion, logica):
    """Calcula métricas de efectividad para una regla."""
    marcadas  = condicion.astype(bool)
    fraudes   = (marcadas & (df["ES_FRAUDE"] == 1))
    legitimas = (marcadas & (df["ES_FRAUDE"] == 0))

    n_marc  = int(marcadas.sum())
    n_f     = int(fraudes.sum())
    n_l     = int(legitimas.sum())
    m_f     = df.loc[fraudes, col_mto].sum()
    m_l     = df.loc[legitimas, col_mto].sum()
    cli_f   = df.loc[fraudes,   col_cli].nunique()
    cli_l   = df.loc[legitimas, col_cli].nunique()
    prec    = n_f / n_marc   if n_marc > 0   else 0
    recall  = n_f / total_fraude if total_fraude > 0 else 0
    pct_af  = n_l / total_legitimo if total_legitimo > 0 else 0

    print(f"\n  {nombre}")
    print(f"  {'─'*55}")
    print(f"  Transacciones marcadas : {n_marc:>8,}")
    print(f"  Fraudes capturados     : {n_f:>8,}  ({recall*100:.1f}% del total fraude)")
    print(f"  Legítimas afectadas    : {n_l:>8,}  ({pct_af*100:.2f}% del total legítimo)")
    print(f"  Monto fraude capturado : S/ {m_f:>12,.2f}")
    print(f"  Monto legítimo afectado: S/ {m_l:>12,.2f}")
    print(f"  Clientes fraude        : {cli_f:>8,}")
    print(f"  Clientes legítimos     : {cli_l:>8,}")
    print(f"  Precision              : {prec*100:>7.1f}%  (de los marcados, % fraude real)")
    print(f"  Recall                 : {recall*100:>7.1f}%  (fraudes capturados del total)")

    return {
        "Regla"                    : nombre,
        "Descripcion"              : descripcion,
        "Logica_Monitor"           : logica,
        "N_Marcadas_Total"         : n_marc,
        "N_Fraudes_Capturados"     : n_f,
        "N_Legitimas_Afectadas"    : n_l,
        "Monto_Fraude_S/"          : round(m_f, 2),
        "Monto_Legitimo_S/"        : round(m_l, 2),
        "Clientes_Fraude"          : cli_f,
        "Clientes_Legitimos_Afect" : cli_l,
        "Precision_%"              : round(prec * 100, 2),
        "Recall_%"                 : round(recall * 100, 2),
        "Pct_Afectacion_Legitimo_%": round(pct_af * 100, 2),
        "Marcada"                  : marcadas,   # para cascada
    }


# ─────────────────────────────────────────────────────────────────────────────
# APLICAR REGLAS
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("ANÁLISIS POR REGLA")
print("─" * 65)

resultados = []

# ── REGLA 1: Velocidad extrema ───────────────────────────────────────────────
cond_r1 = pd.Series(False, index=df.index)
if "TRX_TARJETA_24H" in df.columns and "GAP_MINUTOS" in df.columns:
    cond_r1 = (df["TRX_TARJETA_24H"] >= 5) & (df["GAP_MINUTOS"] <= 10)

r1 = aplicar_regla(
    df, "REGLA 1 — Velocidad Extrema",
    cond_r1,
    "Tarjeta con 5+ transacciones en 24h Y menos de 10 minutos desde la última transacción",
    "COUNT(TRX_TARJETA_24H) >= 5 AND GAP_MINUTOS <= 10 → ALERTAR/DECLINAR"
)
resultados.append(r1)

# ── REGLA 2: MCC alto riesgo + monto ────────────────────────────────────────
cond_r2 = pd.Series(False, index=df.index)
if col_mcc in df.columns:
    mcc_str  = df[col_mcc].astype(str).str.strip()
    cond_r2  = mcc_str.isin(MCC_ALTO_RIESGO_REGLA) & (df[col_mto] >= 50)

r2 = aplicar_regla(
    df, "REGLA 2 — MCC Alto Riesgo",
    cond_r2,
    "Transacción en comercio de alto riesgo (supermercado, wire transfer, taxi) con monto >= S/50",
    "MCC IN (5411,4829,4722,4121) AND MONTO >= 50 → REVISAR/ALERTAR"
)
resultados.append(r2)

# ── REGLA 3: Score de riesgo alto ───────────────────────────────────────────
cond_r3 = pd.Series(False, index=df.index)
if "SCORE_RIESGO" in df.columns:
    cond_r3 = df["SCORE_RIESGO"] >= 7

r3 = aplicar_regla(
    df, "REGLA 3 — Score de Riesgo Alto",
    cond_r3,
    "Score de riesgo compuesto >= 7 (suma de flags: ráfaga, madrugada, multi-país, MCC riesgo, etc.)",
    "SCORE_RIESGO >= 7 → ALERTAR"
)
resultados.append(r3)

# ── REGLA 4: País Bolivia ────────────────────────────────────────────────────
cond_r4 = pd.Series(False, index=df.index)
if col_pais in df.columns:
    cond_r4 = df[col_pais].astype(str).str.strip().str.upper() == "BO"

r4 = aplicar_regla(
    df, "REGLA 4 — País Bolivia",
    cond_r4,
    "Transacción originada en Bolivia (BO) — 100% tasa de fraude histórica",
    "PAIS_TRANSACCION = 'BO' → DECLINAR AUTOMÁTICAMENTE"
)
resultados.append(r4)

# ── REGLA 5: Ráfaga en 5 minutos ────────────────────────────────────────────
cond_r5 = pd.Series(False, index=df.index)
if "FLAG_RAFAGA_5MIN" in df.columns:
    cond_r5 = df["FLAG_RAFAGA_5MIN"] == 1

r5 = aplicar_regla(
    df, "REGLA 5 — Ráfaga en 5 Minutos",
    cond_r5,
    "3 o más transacciones de la misma tarjeta en los últimos 5 minutos",
    "FLAG_RAFAGA_5MIN = 1 → ALERTAR/DECLINAR"
)
resultados.append(r5)


# ─────────────────────────────────────────────────────────────────────────────
# ANÁLISIS EN CASCADA
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("ANÁLISIS EN CASCADA (captura acumulada)")
print("─" * 65)

mascara_acum   = pd.Series(False, index=df.index)
rows_cascada   = []
fraudes_ya_cap = set()

orden_cascada = [
    ("REGLA 1 — Velocidad Extrema",    cond_r1),
    ("REGLA 5 — Ráfaga 5 Minutos",     cond_r5),
    ("REGLA 3 — Score Riesgo >= 7",    cond_r3),
    ("REGLA 2 — MCC Alto Riesgo",      cond_r2),
    ("REGLA 4 — País Bolivia",         cond_r4),
]

for nombre, cond in orden_cascada:
    nuevas       = cond & ~mascara_acum
    f_nuevos     = int((nuevas & (df["ES_FRAUDE"]==1)).sum())
    l_nuevos     = int((nuevas & (df["ES_FRAUDE"]==0)).sum())
    mascara_acum = mascara_acum | cond

    total_f_acum = int((mascara_acum & (df["ES_FRAUDE"]==1)).sum())
    total_l_acum = int((mascara_acum & (df["ES_FRAUDE"]==0)).sum())
    recall_acum  = total_f_acum / total_fraude * 100
    prec_acum    = total_f_acum / mascara_acum.sum() * 100 if mascara_acum.sum() > 0 else 0

    print(f"\n  + {nombre}")
    print(f"    Fraudes nuevos capturados  : {f_nuevos:,}")
    print(f"    Fraudes acumulados         : {total_f_acum:,}  ({recall_acum:.1f}% del total)")
    print(f"    Legítimas acumuladas       : {total_l_acum:,}")
    print(f"    Precision acumulada        : {prec_acum:.1f}%")

    rows_cascada.append({
        "Orden"                     : len(rows_cascada) + 1,
        "Regla"                     : nombre,
        "Fraudes_Nuevos"            : f_nuevos,
        "Legitimas_Nuevas"          : l_nuevos,
        "Fraudes_Acumulados"        : total_f_acum,
        "Legitimas_Acumuladas"      : total_l_acum,
        "Recall_Acumulado_%"        : round(recall_acum, 2),
        "Precision_Acumulada_%"     : round(prec_acum, 2),
    })

df_cascada = pd.DataFrame(rows_cascada)


# ─────────────────────────────────────────────────────────────────────────────
# DICCIONARIO DE VARIABLES (para presentación)
# ─────────────────────────────────────────────────────────────────────────────
diccionario = [
    {
        "Variable"       : "TRX_TARJETA_24H",
        "Nombre_Negocio" : "Transacciones de la tarjeta en 24 horas",
        "Explicacion"    : "Cuántas veces se usó esta tarjeta en las últimas 24 horas",
        "Fraude_Promedio": "12.6 transacciones",
        "Legitimo_Promedio": "1.5 transacciones",
        "Señal"          : "Si es alto (>=5) → sospechoso: el defraudador gasta rápido antes del bloqueo",
    },
    {
        "Variable"       : "GAP_MINUTOS",
        "Nombre_Negocio" : "Minutos desde la última transacción",
        "Explicacion"    : "Tiempo transcurrido entre esta compra y la compra anterior de esa tarjeta",
        "Fraude_Promedio": "2,087 minutos (~1.4 días)",
        "Legitimo_Promedio": "6,718 minutos (~4.6 días)",
        "Señal"          : "Si es bajo (<=10 min) → sospechoso: compras en ráfaga muy seguidas",
    },
    {
        "Variable"       : "SCORE_RIESGO",
        "Nombre_Negocio" : "Score de riesgo compuesto",
        "Explicacion"    : "Puntaje de 0 a 11 que suma múltiples señales de alerta (ráfaga, madrugada, multi-país, MCC riesgo, etc.)",
        "Fraude_Promedio": "6.8 puntos",
        "Legitimo_Promedio": "4.0 puntos",
        "Señal"          : "Si es alto (>=7) → múltiples señales de alerta activas simultáneamente",
    },
    {
        "Variable"       : "FLAG_RAFAGA_5MIN",
        "Nombre_Negocio" : "Ráfaga de transacciones en 5 minutos",
        "Explicacion"    : "La tarjeta hizo 3 o más transacciones en los últimos 5 minutos",
        "Fraude_Promedio": "31.5% tasa de fraude cuando = 1",
        "Legitimo_Promedio": "1.2% tasa de fraude cuando = 0",
        "Señal"          : "El defraudador intenta hacer el mayor número de compras posible antes del bloqueo",
    },
    {
        "Variable"       : "MCC",
        "Nombre_Negocio" : "Código de categoría del comercio",
        "Explicacion"    : "Clasificación internacional del tipo de negocio donde se realizó la compra",
        "Fraude_Promedio": "5411 Supermercados: 6.6% fraude / 4829 Wire transfers: 5.5% fraude",
        "Legitimo_Promedio": "Tasa promedio general: 1.34%",
        "Señal"          : "Ciertos comercios son usados desproporcionadamente por defraudadores",
    },
    {
        "Variable"       : "MNT_CLIENTE_24H",
        "Nombre_Negocio" : "Monto acumulado del cliente en 24 horas",
        "Explicacion"    : "Suma total en soles de todas las transacciones del cliente en las últimas 24 horas",
        "Fraude_Promedio": "S/ 174.38",
        "Legitimo_Promedio": "S/ 99.29",
        "Señal"          : "Monto acumulado inusualmente alto en el día puede indicar múltiples compras fraudulentas",
    },
    {
        "Variable"       : "ES_SEGURO",
        "Nombre_Negocio" : "Transacción autenticada con 3DS",
        "Explicacion"    : "Indica si la transacción pasó por autenticación reforzada (Verified by Visa / Mastercard SecureCode)",
        "Fraude_Promedio": "El fraude tiende a ocurrir en transacciones NO autenticadas",
        "Legitimo_Promedio": "El cliente legítimo suele autenticarse normalmente",
        "Señal"          : "Sin 3DS = mayor riesgo. El defraudador evita canales con autenticación",
    },
    {
        "Variable"       : "ES_TOKENIZADA",
        "Nombre_Negocio" : "Transacción por billetera digital",
        "Explicacion"    : "La transacción se realizó mediante Google Pay, Apple Pay u otra billetera digital",
        "Fraude_Promedio": "A evaluar con los nuevos resultados",
        "Legitimo_Promedio": "A evaluar con los nuevos resultados",
        "Señal"          : "El uso de billetera puede ser señal de fraude si la tarjeta fue tokenizada sin autorización",
    },
    {
        "Variable"       : "FLAG_MULTI_PAIS_24H",
        "Nombre_Negocio" : "Transacciones en múltiples países en 24 horas",
        "Explicacion"    : "En las últimas 24 horas se detectaron transacciones de esa tarjeta en más de un país",
        "Fraude_Promedio": "A evaluar con datos actuales",
        "Legitimo_Promedio": "Poco frecuente en clientes normales",
        "Señal"          : "Imposible estar físicamente en dos países al mismo tiempo → señal de clonación o uso remoto",
    },
]

df_diccionario = pd.DataFrame(diccionario)


# ─────────────────────────────────────────────────────────────────────────────
# EXPORTAR EXCEL
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n[Exportando Excel: {OUTPUT_REGLAS}...]")

# Tabla resumen de reglas (sin la columna de máscara)
df_resumen = pd.DataFrame([
    {k: v for k, v in r.items() if k != "Marcada"}
    for r in resultados
])

OUTPUT_REGLAS.parent.mkdir(exist_ok=True)
try:
    with pd.ExcelWriter(OUTPUT_REGLAS, engine="openpyxl") as writer:
        df_resumen.to_excel(writer,     sheet_name="Resumen_Reglas",   index=False)
        df_cascada.to_excel(writer,     sheet_name="Cascada_Acumulada",index=False)
        df_diccionario.to_excel(writer, sheet_name="Diccionario_Variables", index=False)

    print(f"  ✅  Excel guardado: {OUTPUT_REGLAS}")
except Exception as e:
    print(f"  ⚠️  Error: {e}")

print("\n" + "═" * 65)
print("ANÁLISIS DE REGLAS COMPLETADO")
print("═" * 65)
