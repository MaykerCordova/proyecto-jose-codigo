"""
feature_engineering.py
──────────────────────
Lee data/consolidado.parquet y genera features de fraude para ecommerce.

Configuración clave en config.py:
  SOLO_APROBADAS = True  → journal solo tiene aprobadas (skip features de rechazo)
  SOLO_APROBADAS = False → journal tiene aprobadas + denegadas (análisis completo)

Bloques:
  A  Validación y tipos       → leer_archivo(), validar columnas, castear montos/texto
  B  Variables temporales     → HORA_DIA, FRANJA_HORARIA, ES_FIN_SEMANA, ES_MADRUGADA, etc.
  C  Estado / indicador       → ESTADO (APROBADA/DENEGADA), ES_FRAUDE, ES_FRAUDE_APROBADO, SEGURO
  D  Ventanas deslizantes     → TXN_CARD_2M/5M/10M/1H/24H  +  AMT_CARD_2M/5M/10M/1H/24H
  D2 Interacciones veloc×mont → RATIO_AMT_TXN_5M/10M/1H/24H, AMT_POR_TXN_MEDIA_1H
  E  Perfil tarjeta           → TOTAL_TXN_TRJ, MONTO_TOTAL_TRJ, reincidencia, ráfaga
  F  Perfil comercio/MCC      → ranking, concentración, tendencia diaria
  G  Señales de monto         → redondo, rango, desvío vs comercio, ratio saldo
  H  Cascada y rechazos CVV   → (skip si SOLO_APROBADAS=True)
  I  Score de riesgo          → SCORE_RIESGO (0-7), PERFIL_RIESGO BAJO/MEDIO/ALTO/MUY_ALTO
"""

import sys
import os
import warnings
import pandas as pd
import numpy as np
from pathlib import Path

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    COLS, SOLO_APROBADAS, PARQUET_CONSOLIDADO, PARQUET_FEATURES,
    COMERCIO_NOMBRE, SEG_NOMBRE, SEG_GRUPO, COD_RED_LABEL, clasificar_motivo,
)

C = COLS


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE A — CARGA Y VALIDACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

def leer_archivo(ruta):
    if not os.path.exists(ruta):
        print(f"\n❌  No se encontró: {ruta}")
        print("    Ejecuta primero: python scripts/consolidar.py")
        sys.exit(1)
    ext = os.path.splitext(ruta)[1].lower()
    if ext in (".parquet", ".pq", ""):
        try:
            df = pd.read_parquet(ruta); print("  Formato: Parquet ✅"); return df
        except Exception: pass
    if ext in (".csv", ".txt"):
        df = pd.read_csv(ruta, encoding="utf-8", low_memory=False, on_bad_lines="warn")
        print("  Formato: CSV ✅"); return df
    if ext in (".xlsx", ".xls", ".xlsm"):
        df = pd.read_excel(ruta); print("  Formato: Excel ✅"); return df
    try:
        df = pd.read_csv(ruta, encoding="utf-8", low_memory=False, on_bad_lines="warn")
        print(f"  Formato: CSV (extensión era {ext}) ✅"); return df
    except Exception: pass
    print(f"❌  No se pudo leer '{ruta}'. Formatos: .parquet .csv .xlsx"); sys.exit(1)


ruta_entrada = Path(sys.argv[1]) if len(sys.argv) > 1 else PARQUET_CONSOLIDADO

print("═" * 65)
print(f"FEATURE ENGINEERING — {COMERCIO_NOMBRE}")
print(f"  Modo: {'SOLO APROBADAS' if SOLO_APROBADAS else 'APROBADAS + DENEGADAS'}")
print("═" * 65)

df = leer_archivo(str(ruta_entrada))

# Validar columnas
cols_reales  = set(df.columns)
cols_config  = {k: v for k, v in C.items() if v}
faltantes    = {k: v for k, v in cols_config.items() if v not in cols_reales}
if faltantes:
    print("\n⚠️  COLUMNAS NO ENCONTRADAS (features dependientes se omiten):")
    for k, v in faltantes.items():
        print(f"   COLS['{k}'] = '{v}'  ← no existe en el parquet")
    print("\n   Columnas disponibles:")
    for c in sorted(df.columns): print(f"     {c}")

# Castear montos
for col_key in ["monto", "monto_dolar", "saldo"]:
    col_val = C.get(col_key, "")
    if col_val and col_val in df.columns:
        df[col_val] = (
            df[col_val].astype(str).str.strip()
            .str.replace(",", ".", regex=False).str.replace(" ", "", regex=False)
        )
        df[col_val] = pd.to_numeric(df[col_val], errors="coerce")

# Castear texto
for col_key in ["tarjeta","id_cliente","comercio_nom","canal","tipo_producto",
                "segmento","organizacion","mcc","indicador","cod_respuesta",
                "cod_motivo","razon_respuesta","eci","cod_red_comercio",
                "pais","region","ciudad","ip","entry_mode"]:
    col_val = C.get(col_key, "")
    if col_val and col_val in df.columns:
        df[col_val] = df[col_val].astype(str).str.strip().str.upper()
if C.get("bin","") in df.columns:
    df[C["bin"]] = df[C["bin"]].astype(str).str.split(".").str[0].str.strip()

col_monto = C["monto"]
col_trj   = C["id_cliente"]     # usamos ID cliente como identificador de velocidad
col_com   = C["comercio_nom"]

print(f"\n  Filas              : {len(df):,}")
print(f"  Clientes únicos    : {df[col_trj].nunique():,}")
print(f"  Comercios únicos   : {df[col_com].nunique():,}")
print(f"  Monto total (S/)   : {df[col_monto].sum():,.2f}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE B — VARIABLES TEMPORALES
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[B] Variables temporales...")

col_fh = C["fecha_hora"]
df[col_fh]       = pd.to_datetime(df[col_fh], errors="coerce")
df               = df.sort_values(col_fh).reset_index(drop=True)

df["HORA_DIA"]       = df[col_fh].dt.hour
df["DIA_SEMANA"]     = df[col_fh].dt.dayofweek
df["DIA_SEMANA_NOM"] = df[col_fh].dt.strftime("%a").str.upper()
df["MES"]            = df[col_fh].dt.month
df["MES_NOM"]        = df[col_fh].dt.strftime("%b").str.upper()
df["ANIO"]           = df[col_fh].dt.year
df["FECHA_DIA"]      = df[col_fh].dt.normalize()
df["SEMANA_ISO"]     = df[col_fh].dt.isocalendar().week.astype(int)
df["ES_FIN_SEMANA"]  = (df["DIA_SEMANA"] >= 5).astype(int)
df["QUINCENA"]       = df.get("QUINCENA", np.where(df[col_fh].dt.day <= 15, "Q1", "Q2"))

_FRANJAS = [(0,6,"MADRUGADA"),(6,12,"MANANA"),(12,19,"TARDE"),(19,24,"NOCHE")]
def franja(h):
    for ini, fin, nom in _FRANJAS:
        if ini <= h < fin: return nom
    return "NOCHE"

df["FRANJA_HORARIA"]  = df["HORA_DIA"].map(franja)
df["ES_MADRUGADA"]    = (df["FRANJA_HORARIA"] == "MADRUGADA").astype(int)
df["ES_HORARIO_LAB"]  = ((df["DIA_SEMANA"] < 5) & df["HORA_DIA"].between(8,17)).astype(int)

print(f"  Distribución FRANJA_HORARIA:\n{df['FRANJA_HORARIA'].value_counts().to_string()}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE C — ESTADO / INDICADOR
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[C] Estado e indicador...")

col_ind  = C.get("indicador","")
col_resp = C.get("cod_respuesta","")
col_eci  = C.get("eci","")

if col_resp and col_resp in df.columns:
    df["ESTADO"] = df[col_resp].apply(
        lambda x: "APROBADA" if str(x).strip() in ["00","0000","000","0"] else "DENEGADA"
    )
elif SOLO_APROBADAS:
    df["ESTADO"] = "APROBADA"
else:
    df["ESTADO"] = "DESCONOCIDO"

df["ES_FRAUDE"]          = (df[col_ind] == "F").astype(int) if col_ind and col_ind in df.columns else 0
df["ES_FRAUDE_APROBADO"] = ((df["ES_FRAUDE"]==1) & (df["ESTADO"]=="APROBADA")).astype(int)

if col_eci and col_eci in df.columns:
    df["SEGURO"] = df[col_eci].apply(
        lambda x: "Seguro" if str(x).strip() in ["2","5","02","05"] else "No Seguro"
    )
else:
    df["SEGURO"] = "No Seguro"

col_seg    = C.get("segmento","")
col_cvv_r  = C.get("cod_red_comercio","")
col_razon  = C.get("razon_respuesta","")

df["SEG_NOMBRE"]    = df[col_seg].map(SEG_NOMBRE).fillna("Otro/Sin seg") if col_seg and col_seg in df.columns else "Otro/Sin seg"
df["SEG_GRUPO"]     = df[col_seg].map(SEG_GRUPO).fillna("Otro/Sin seg")  if col_seg and col_seg in df.columns else "Otro/Sin seg"
df["COD_RED_LABEL"] = df[col_cvv_r].map(COD_RED_LABEL).fillna("Otro")    if col_cvv_r and col_cvv_r in df.columns else "Otro"

if col_razon and col_razon in df.columns:
    df["MOTIVO_RECH"] = df[col_razon].apply(clasificar_motivo)
    df.loc[df["ESTADO"] == "APROBADA", "MOTIVO_RECH"] = "N/A"
else:
    df["MOTIVO_RECH"] = "N/A"

print(f"  ES_FRAUDE:          {df['ES_FRAUDE'].sum():,}")
print(f"  ES_FRAUDE_APROBADO: {df['ES_FRAUDE_APROBADO'].sum():,}")
if not SOLO_APROBADAS:
    print(f"  Denegadas:          {(df['ESTADO']=='DENEGADA').sum():,}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE D — VENTANAS DESLIZANTES (numpy searchsorted — rápido)
#  Para cada cliente: cuántas txn y cuánto monto acumuló en los N seg PREVIOS.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[D] Ventanas deslizantes por cliente...")

df = df.sort_values([col_trj, col_fh]).reset_index(drop=True)
df["_ts"] = df[col_fh].astype(np.int64) // 10**9

VENTANAS = {
    # Conteo de transacciones
    "TXN_CARD_2M" :  (  2*60,  "count"),
    "TXN_CARD_5M" :  (  5*60,  "count"),
    "TXN_CARD_10M":  ( 10*60,  "count"),
    "TXN_CARD_1H" :  ( 60*60,  "count"),
    "TXN_CARD_24H":  (24*3600, "count"),
    # Monto acumulado (mismas ventanas)
    "AMT_CARD_2M" :  (  2*60,  "sum"),
    "AMT_CARD_5M" :  (  5*60,  "sum"),
    "AMT_CARD_10M":  ( 10*60,  "sum"),
    "AMT_CARD_1H" :  ( 60*60,  "sum"),
    "AMT_CARD_24H":  (24*3600, "sum"),
}

def calcular_ventana(grupo, segundos, modo, col_monto_name):
    ts  = grupo["_ts"].values
    amt = grupo[col_monto_name].values if modo == "sum" else None
    n   = len(ts)
    res = np.zeros(n)
    for i in range(n):
        j = np.searchsorted(ts, ts[i] - segundos, side="left")
        res[i] = i - j if modo == "count" else amt[j:i].sum()
    return res

resultados = {col: np.zeros(len(df)) for col in VENTANAS}

for cliente, grupo in df.groupby(col_trj, sort=False):
    idx = grupo.index.values
    for col, (segs, modo) in VENTANAS.items():
        vals = calcular_ventana(grupo, segs, modo, col_monto)
        resultados[col][idx] = vals

for col, vals in resultados.items():
    df[col] = vals
    df[col] = df[col].round(2) if col.startswith("AMT_") else df[col].astype(int)

df.drop(columns=["_ts"], inplace=True)

# Flags de velocidad
df["FLAG_VEL_ALTA_5M"]  = (df["TXN_CARD_5M"]  >= 2).astype(int)
df["FLAG_VEL_ALTA_1H"]  = (df["TXN_CARD_1H"]  >= 3).astype(int)
df["FLAG_ACUM_ALTO_1H"] = (df["AMT_CARD_1H"]  >= df[col_monto] * 2).astype(int)
df["ES_RAFAGA"]         = (df["TXN_CARD_10M"] >= 3).astype(int)

# GAP vs transacción anterior
df["GAP_MINUTOS"] = (
    df.groupby(col_trj)[col_fh].diff().dt.total_seconds() / 60
).round(1)

print(f"  TXN_CARD_5M  media : {df['TXN_CARD_5M'].mean():.2f} txn previas en 5 min")
print(f"  TXN_CARD_1H  media : {df['TXN_CARD_1H'].mean():.2f} txn previas en 1h")
print(f"  AMT_CARD_1H  media : {df['AMT_CARD_1H'].mean():,.2f}")
print(f"  AMT_CARD_24H media : {df['AMT_CARD_24H'].mean():,.2f}")
print("  Ventanas OK ✅")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE D2 — INTERACCIONES VELOCIDAD × MONTO
#  Monto promedio por transacción en cada ventana temporal.
#  Sube → el cliente gasta más en cada txn (escalada).
#  Baja → card testing (montos pequeños primero).
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[D2] Interacciones velocidad × monto...")

for w in ["5M","10M","1H","24H"]:
    txn_col = f"TXN_CARD_{w}"
    amt_col = f"AMT_CARD_{w}"
    rat_col = f"RATIO_AMT_TXN_{w}"
    df[rat_col] = (
        df[amt_col] / df[txn_col].replace(0, np.nan)
    ).round(2)

# Aceleración de monto: ¿está gastando más en 5min que en 1h en promedio?
df["ACELERACION_MONTO"] = (df["RATIO_AMT_TXN_5M"] / df["RATIO_AMT_TXN_1H"].replace(0, np.nan)).round(2)
# Concentración: % del monto acumulado en 5min sobre el de 1h
df["CONCENT_MONTO_5M_1H"] = (df["AMT_CARD_5M"] / df["AMT_CARD_1H"].replace(0, np.nan)).round(4)

print("  Interacciones OK ✅")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE E — PERFIL DE TARJETA / CLIENTE
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[E] Perfil de cliente/tarjeta...")

totales_trj = (
    df.groupby(col_trj).agg(
        TOTAL_TXN_TRJ    = (col_monto, "count"),
        MONTO_TOTAL_TRJ  = (col_monto, "sum"),
        COMERCIOS_DIST   = (col_com,   "nunique"),
        DIAS_ACTIVA      = ("FECHA_DIA","nunique"),
    ).reset_index()
)
df = df.merge(totales_trj, on=col_trj, how="left")

trj_dia = (
    df.groupby([col_trj,"FECHA_DIA"]).agg(
        TXN_TRJ_DIA   = (col_monto,"count"),
        MONTO_TRJ_DIA = (col_monto,"sum"),
        COM_DIST_DIA  = (col_com,  "nunique"),
    ).reset_index()
)
df = df.merge(trj_dia, on=[col_trj,"FECHA_DIA"], how="left")

df["FLAG_REINCIDENTE"]    = (df["TOTAL_TXN_TRJ"] > 1).astype(int)
df["FLAG_MULTI_COM_DIA"]  = (df["COM_DIST_DIA"]  > 1).astype(int)
df["FLAG_RAFAGA_DIA"]     = (df["TXN_TRJ_DIA"]  >= 3).astype(int)

# Saldo
col_saldo = C.get("saldo","")
if col_saldo and col_saldo in df.columns:
    df["RATIO_MONTO_VS_SALDO"] = (df[col_monto] / df[col_saldo].replace(0, np.nan)).round(4)
    df["FLAG_SALDO_AGOTADO"]   = (df["RATIO_MONTO_VS_SALDO"] >= 0.9).astype(int)

print(f"  Clientes reincidentes: {df.loc[df['FLAG_REINCIDENTE']==1, col_trj].nunique():,}")
print(f"  Ráfagas en el día    : {df['FLAG_RAFAGA_DIA'].sum():,} transacciones")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE F — PERFIL DE COMERCIO Y MCC
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[F] Perfil de comercio y MCC...")

totales_com = (
    df.groupby(col_com).agg(
        TOTAL_TXN_COM   = (col_monto,"count"),
        MONTO_TOTAL_COM = (col_monto,"sum"),
        MONTO_PROM_COM  = (col_monto,"mean"),
        CLI_DIST_COM    = (col_trj,  "nunique"),
        DIAS_CON_TXN    = ("FECHA_DIA","nunique"),
    ).reset_index()
)
df = df.merge(totales_com, on=col_com, how="left")

com_dia = (
    df.groupby([col_com,"FECHA_DIA"])
    .agg(TXN_COM_DIA=(col_monto,"count"))
    .reset_index()
)
df = df.merge(com_dia, on=[col_com,"FECHA_DIA"], how="left")

rank_com = (
    totales_com[[col_com,"TOTAL_TXN_COM"]]
    .sort_values("TOTAL_TXN_COM", ascending=False)
    .reset_index(drop=True)
)
rank_com["RANKING_COM"] = rank_com.index + 1
df = df.merge(rank_com[[col_com,"RANKING_COM"]], on=col_com, how="left")

col_mcc = C.get("mcc","")
if col_mcc and col_mcc in df.columns:
    totales_mcc = (
        df.groupby(col_mcc).agg(
            TOTAL_TXN_MCC  = (col_monto,"count"),
            MONTO_TOTAL_MCC= (col_monto,"sum"),
            COM_EN_MCC     = (col_com,  "nunique"),
        ).reset_index()
    )
    df = df.merge(totales_mcc, on=col_mcc, how="left")
    rank_mcc = totales_mcc[[col_mcc,"TOTAL_TXN_MCC"]].sort_values("TOTAL_TXN_MCC",ascending=False).reset_index(drop=True)
    rank_mcc["RANKING_MCC"] = rank_mcc.index + 1
    df = df.merge(rank_mcc[[col_mcc,"RANKING_MCC"]], on=col_mcc, how="left")

print(f"  Top 3 comercios:\n{rank_com.head(3).to_string(index=False)}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE G — SEÑALES DE MONTO
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[G] Señales de monto...")

df["FLAG_MONTO_REDONDO"]   = (df[col_monto] % 50 == 0) & (df[col_monto] >= 50)
df["FLAG_MONTO_REDONDO"]   = df["FLAG_MONTO_REDONDO"].astype(int)
df["FLAG_MONTO_BAJO"]      = (df[col_monto] < 20).astype(int)
df["DESVIO_MONTO_VS_COM"]  = (df[col_monto] - df["MONTO_PROM_COM"]).round(2)
df["RATIO_MONTO_VS_COM"]   = (df[col_monto] / df["MONTO_PROM_COM"].replace(0, np.nan)).round(2)

q25, q50, q75 = df[col_monto].quantile([0.25, 0.50, 0.75])
def rango_monto(m):
    if   m <= q25: return "BAJO"
    elif m <= q50: return "MEDIO_BAJO"
    elif m <= q75: return "MEDIO_ALTO"
    else:          return "ALTO"
df["RANGO_MONTO"] = df[col_monto].map(rango_monto)

col_monto_usd = C.get("monto_dolar","")
if col_monto_usd and col_monto_usd in df.columns:
    df["TIPO_CAMBIO"] = (df[col_monto] / df[col_monto_usd].replace(0, np.nan)).round(4)

# Z-score monto por cliente
df["_mean_cli"] = df.groupby(col_trj)[col_monto].transform("mean")
df["_std_cli"]  = df.groupby(col_trj)[col_monto].transform("std").fillna(1)
df["ZSCORE_MONTO_CLI"] = ((df[col_monto] - df["_mean_cli"]) / df["_std_cli"]).round(3)
df["RATIO_MONTO_AVG"]  = (df[col_monto] / df["_mean_cli"].replace(0, np.nan)).round(2)
df.drop(columns=["_mean_cli","_std_cli"], inplace=True)

print(f"  Q25={q25:.2f} | Q50={q50:.2f} | Q75={q75:.2f}")
print(f"  Montos redondos: {df['FLAG_MONTO_REDONDO'].sum():,} ({df['FLAG_MONTO_REDONDO'].mean()*100:.1f}%)")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE H — CASCADA Y RECHAZOS CVV  (solo si SOLO_APROBADAS=False)
# ═══════════════════════════════════════════════════════════════════════════════
if SOLO_APROBADAS:
    print("\n[H] Rechazos CVV — OMITIDO (SOLO_APROBADAS=True)")
    df["N_RECHAZOS_24H"]     = 0
    df["N_CVV_FAIL_24H"]     = 0
    df["HUBO_CVV_FAIL_PREVIO"]= 0
    df["HUBO_FRAUDE_PREVIO_24H"] = 0
    df["PREV_FUE_FRAUDE"]    = 0
    df["MIN_DESDE_ULTIMO_FRAUDE"] = np.nan
else:
    print("\n[H] Cascada y rechazos CVV...")

    df_ap  = df[df["ESTADO"] == "APROBADA"].copy()
    df_den = df[df["ESTADO"] == "DENEGADA"].copy()

    # Fraude previo 24h (usando ventana en df_ap ordenado por cliente+fecha)
    df_ap_s = df_ap.sort_values([col_trj, col_fh]).reset_index(drop=True)
    df_ap_s["_ts2"] = df_ap_s[col_fh].astype(np.int64) // 10**9
    resultados_h = {"FRAUDE_ACUM_24H": np.zeros(len(df_ap_s))}
    for cli, g in df_ap_s.groupby(col_trj, sort=False):
        ts  = g["_ts2"].values
        esf = g["ES_FRAUDE_APROBADO"].values
        n   = len(ts)
        res = np.zeros(n)
        for i in range(n):
            j = np.searchsorted(ts, ts[i] - 24*3600, side="left")
            res[i] = esf[j:i].sum()
        resultados_h["FRAUDE_ACUM_24H"][g.index.values] = res
    df_ap_s["HUBO_FRAUDE_PREVIO_24H"] = (resultados_h["FRAUDE_ACUM_24H"] > 0).astype(int)
    df_ap_s["PREV_FUE_FRAUDE"] = df_ap_s.groupby(col_trj)["ES_FRAUDE_APROBADO"].shift(1).fillna(0).astype(int)
    df_ap_s["MIN_DESDE_ULTIMO_FRAUDE"] = np.nan
    idx_fraude = df_ap_s[df_ap_s["ES_FRAUDE_APROBADO"]==1].index
    for cli, g in df_ap_s.groupby(col_trj, sort=False):
        g_f = g[g["ES_FRAUDE_APROBADO"]==1]
        if len(g_f) == 0: continue
        for ix in g.index:
            t_actual = df_ap_s.loc[ix, col_fh]
            previos  = g_f[g_f[col_fh] < t_actual]
            if len(previos) > 0:
                ult = previos[col_fh].max()
                df_ap_s.loc[ix, "MIN_DESDE_ULTIMO_FRAUDE"] = (t_actual - ult).total_seconds() / 60

    # Rechazos CVV (de df_den)
    if len(df_den) > 0 and "MOTIVO_RECH" in df_den.columns:
        df_den_s = df_den.sort_values([col_trj, col_fh]).reset_index(drop=True)
        df_den_s["_ts3"] = df_den_s[col_fh].astype(np.int64) // 10**9
        rej_24h = np.zeros(len(df_ap_s))
        cvv_24h = np.zeros(len(df_ap_s))
        den_by_cli = {k: g for k, g in df_den_s.groupby(col_trj, sort=False)}
        ap_ts = df_ap_s[col_fh].astype(np.int64) // 10**9

        for i, (ix, row) in enumerate(df_ap_s.iterrows()):
            cli = row[col_trj]
            t   = ap_ts.iloc[i]
            if cli not in den_by_cli: continue
            gd = den_by_cli[cli]
            mask = (gd["_ts3"].values >= t - 24*3600) & (gd["_ts3"].values < t)
            sub  = gd[mask]
            rej_24h[i] = len(sub)
            cvv_24h[i] = (sub["MOTIVO_RECH"] == "CVV_FAIL").sum()

        df_ap_s["N_RECHAZOS_24H"]      = rej_24h.astype(int)
        df_ap_s["N_CVV_FAIL_24H"]      = cvv_24h.astype(int)
        df_ap_s["HUBO_CVV_FAIL_PREVIO"]= (cvv_24h > 0).astype(int)
    else:
        df_ap_s[["N_RECHAZOS_24H","N_CVV_FAIL_24H","HUBO_CVV_FAIL_PREVIO"]] = 0

    # Merge de vuelta al df principal
    cols_merge = ["N_RECHAZOS_24H","N_CVV_FAIL_24H","HUBO_CVV_FAIL_PREVIO",
                  "HUBO_FRAUDE_PREVIO_24H","PREV_FUE_FRAUDE","MIN_DESDE_ULTIMO_FRAUDE"]
    df_ap_s.index = df_ap_s.index  # ya está ordenado
    for c_ in cols_merge:
        df_ap_s_c = df_ap_s.set_index(df_ap_s.index)[c_]
        # merge by position in original df (aprobadas only)
    df = df.merge(
        df_ap_s[["N_RECHAZOS_24H","N_CVV_FAIL_24H","HUBO_CVV_FAIL_PREVIO",
                 "HUBO_FRAUDE_PREVIO_24H","PREV_FUE_FRAUDE","MIN_DESDE_ULTIMO_FRAUDE",
                 col_trj, col_fh]],
        on=[col_trj, col_fh], how="left"
    )
    for c_ in cols_merge:
        if c_ != "MIN_DESDE_ULTIMO_FRAUDE":
            df[c_] = df[c_].fillna(0).astype(int)

    print(f"  HUBO_FRAUDE_PREVIO_24H: {df['HUBO_FRAUDE_PREVIO_24H'].sum():,}")
    print(f"  N_RECHAZOS_24H media  : {df['N_RECHAZOS_24H'].mean():.2f}")
    print(f"  N_CVV_FAIL_24H        : {df['N_CVV_FAIL_24H'].sum():,}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE I — SCORE DE RIESGO COMPUESTO
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[I] Score de riesgo compuesto...")

flags = [
    df["ES_RAFAGA"],                              # ráfaga de transacciones
    df["FLAG_VEL_ALTA_1H"],                       # velocidad alta en 1h
    df.get("HUBO_FRAUDE_PREVIO_24H", pd.Series(0, index=df.index)),
    df.get("HUBO_CVV_FAIL_PREVIO",   pd.Series(0, index=df.index)),
    df["FLAG_MONTO_REDONDO"],
    df["ES_MADRUGADA"],
    df["FLAG_REINCIDENTE"],
]
df["SCORE_RIESGO"] = sum(f.fillna(0).astype(int) for f in flags)
df["PERFIL_RIESGO"] = pd.cut(
    df["SCORE_RIESGO"],
    bins=[-1, 0, 1, 3, 99],
    labels=["BAJO","MEDIO","ALTO","MUY_ALTO"]
)
df["FLAG_HORARIO_RIESGO"] = ((df["ES_MADRUGADA"]==1) | (df["ES_FIN_SEMANA"]==1)).astype(int)

print(f"  PERFIL_RIESGO:\n{df['PERFIL_RIESGO'].value_counts().sort_index().to_string()}")


# ═══════════════════════════════════════════════════════════════════════════════
#  RESUMEN DE VARIABLES CONSTRUIDAS
# ═══════════════════════════════════════════════════════════════════════════════
VARS_NUEVAS = [
    "HORA_DIA","DIA_SEMANA_NOM","ES_FIN_SEMANA","FRANJA_HORARIA","ES_MADRUGADA","ES_HORARIO_LAB",
    "ESTADO","ES_FRAUDE","ES_FRAUDE_APROBADO","SEGURO","SEG_NOMBRE","SEG_GRUPO","COD_RED_LABEL","MOTIVO_RECH",
    "TXN_CARD_2M","TXN_CARD_5M","TXN_CARD_10M","TXN_CARD_1H","TXN_CARD_24H",
    "AMT_CARD_2M","AMT_CARD_5M","AMT_CARD_10M","AMT_CARD_1H","AMT_CARD_24H",
    "FLAG_VEL_ALTA_5M","FLAG_VEL_ALTA_1H","FLAG_ACUM_ALTO_1H","ES_RAFAGA","GAP_MINUTOS",
    "RATIO_AMT_TXN_5M","RATIO_AMT_TXN_10M","RATIO_AMT_TXN_1H","RATIO_AMT_TXN_24H",
    "ACELERACION_MONTO","CONCENT_MONTO_5M_1H",
    "TOTAL_TXN_TRJ","MONTO_TOTAL_TRJ","COMERCIOS_DIST","DIAS_ACTIVA",
    "TXN_TRJ_DIA","MONTO_TRJ_DIA","FLAG_REINCIDENTE","FLAG_MULTI_COM_DIA","FLAG_RAFAGA_DIA",
    "RATIO_MONTO_VS_SALDO","FLAG_SALDO_AGOTADO",
    "TOTAL_TXN_COM","MONTO_TOTAL_COM","MONTO_PROM_COM","CLI_DIST_COM","RANKING_COM",
    "FLAG_MONTO_REDONDO","FLAG_MONTO_BAJO","DESVIO_MONTO_VS_COM","RATIO_MONTO_VS_COM",
    "RANGO_MONTO","ZSCORE_MONTO_CLI","RATIO_MONTO_AVG",
    "N_RECHAZOS_24H","N_CVV_FAIL_24H","HUBO_CVV_FAIL_PREVIO",
    "HUBO_FRAUDE_PREVIO_24H","PREV_FUE_FRAUDE","MIN_DESDE_ULTIMO_FRAUDE",
    "SCORE_RIESGO","PERFIL_RIESGO","FLAG_HORARIO_RIESGO",
]

print("\n" + "─" * 65)
print("VARIABLES NUEVAS AGREGADAS:")
for v in VARS_NUEVAS:
    estado = "✅" if v in df.columns else "——"
    print(f"  {estado}  {v}")
print(f"\nColumnas totales en el parquet enriquecido: {df.shape[1]}")


# ═══════════════════════════════════════════════════════════════════════════════
#  GUARDAR
# ═══════════════════════════════════════════════════════════════════════════════
PARQUET_FEATURES.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(PARQUET_FEATURES, index=False)
print(f"\n✅ Features guardadas en: {PARQUET_FEATURES}")
print(f"   {len(df):,} filas × {df.shape[1]} columnas")
print("─" * 65)
