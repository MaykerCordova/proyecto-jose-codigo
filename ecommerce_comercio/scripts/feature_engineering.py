"""
feature_engineering.py — Ingeniería de Variables
Comercios Ecommerce No Seguros (sin 3DS) — Scotiabank Peru

Lee data/consolidado.parquet y genera ~70 variables nuevas.
Ver docs/diccionario_variables.md para la explicación completa de cada variable.

Bloques:
  A  Carga y validación
  B  Variables temporales          → cuándo ocurrió la transacción
  C  Clasificación de la txn       → estado, fraude, seguridad, marca, billetera
  D  Ventanas deslizantes          → velocidad y monto acumulado por cliente
  E  Interacciones velocidad×monto → patrones de escalada y concentración
  F  Perfil del cliente            → historial, reincidencia, días activo
  G  Perfil del comercio y MCC     → ranking, tamaño, país inusual
  H  Señales de monto              → redondo, z-score, decil, rango
  I  Card testing (BIN extendido)  → BIN12 repetido mismo día
  J  Rechazos y cascada CVV        → solo si SOLO_APROBADAS = False
  K  Flags de reglas configurables → umbrales definidos en config.py
  L  Score de riesgo compuesto     → SCORE_RIESGO 0-11, PERFIL_RIESGO
  M  Score diferenciado por marca  → SCORE_MON_NORM, FLAG_SCORE_RIESGO_MON_ALTO (solo TC)
  N  Vínculos de cliente           → reincidencia de fraude, zscore cliente×comercio
  O  Perfil horario del comercio   → hora típica, FLAG_HORA_FUERA_PERFIL_COMERCIO
  Q  Velocidad por BIN             → TRX/MNT_BIN_1H/24H, CLIENTES_BIN_DIA, flags de ataque
  R  Generación robótica           → CV_MONTO_BIN_DIA, N_TARJETAS_MISMO_MONTO_BIN, FLAG_MONTO_ROBOTICO_BIN
  S  Moneda / divisa               → FLAG_TRX_EN_DOLAR, FLAG_MONEDA_OTRA, FLAG_CAMBIO_MONEDA_CLI, FLAG_AGOTAMIENTO_MONEDA_EXT
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
    COMERCIO_NOMBRE, UMBRALES_REGLA,
    SEG_NOMBRE, SEG_GRUPO, COD_RED_LABEL, BILLETERA_LABEL, BILLETERA_DEFAULT,
    ENTRY_MODE_LABEL, ENTRY_MODE_PRESENTE,
    MARCA_LABEL, TIPO_PROD_LABEL, CODIGOS_CRITICOS,
    ORG_NOMBRE, FERIADOS_PERU, FECHAS_ESPECIALES, DIAS_PAGO,
    SCORE_VISA_MAX, SCORE_MC_MAX, UMBRAL_SCORE_MON,
    clasificar_motivo,
)

C = COLS


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE A — CARGA Y VALIDACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

def leer_parquet(ruta):
    if not os.path.exists(ruta):
        print(f"\n❌  No se encontró: {ruta}")
        print("    Ejecuta primero: python scripts/consolidar.py")
        sys.exit(1)
    return pd.read_parquet(ruta)


ruta_entrada = Path(sys.argv[1]) if len(sys.argv) > 1 else PARQUET_CONSOLIDADO

print("═" * 65)
print(f"FEATURE ENGINEERING — {COMERCIO_NOMBRE}")
print(f"  Modo: {'SOLO APROBADAS' if SOLO_APROBADAS else 'APROBADAS + DENEGADAS'}")
print("═" * 65)

df = leer_parquet(str(ruta_entrada))

# Reportar columnas faltantes
cols_reales = set(df.columns)
faltantes   = {k: v for k, v in C.items() if v and v not in cols_reales}
if faltantes:
    print("\n⚠️  COLUMNAS NO ENCONTRADAS (features dependientes se omiten):")
    for k, v in faltantes.items():
        print(f"   COLS['{k}'] = '{v}'  ← no existe")

# Castear montos
for col_key in ["monto", "monto_dolar", "saldo"]:
    col_val = C.get(col_key, "")
    if col_val and col_val in df.columns:
        df[col_val] = (
            df[col_val].astype(str).str.strip()
            .str.replace(",", ".", regex=False)
            .str.replace(" ", "", regex=False)
        )
        df[col_val] = pd.to_numeric(df[col_val], errors="coerce")

col_monto = C["monto"]
col_cli   = C["id_cliente"]
col_com   = C["comercio_nom"]
col_fh    = C["fecha_hora"]
col_bin   = C.get("bin", "")

# FECHA_HORA la crea consolidar.py — si no existe, crear columna vacía y avisar
if col_fh not in df.columns:
    print(f"\n⚠️  '{col_fh}' no encontrada en el parquet.")
    print(f"   Causa: consolidar.py no encontró la columna de fecha del Monitor.")
    print(f"   Solución: ejecuta diagnostico_columnas.py para ver los nombres reales")
    print(f"   y actualiza config.py → 'fecha_trx' y 'hora_trx'.")
    print(f"   Continuando sin fechas (ventanas temporales quedarán en 0/NaT)...\n")
    df[col_fh] = pd.NaT
else:
    df[col_fh] = pd.to_datetime(df[col_fh], errors="coerce")

# Solo ordenar si hay fechas válidas
if df[col_fh].notna().any():
    df = df.sort_values(col_fh).reset_index(drop=True)

# Columnas clave con fallback
if col_cli not in df.columns:
    print(f"⚠️  id_cliente '{col_cli}' no encontrado — usando índice como cliente")
    df[col_cli] = df.index.astype(str)
if col_com not in df.columns:
    print(f"⚠️  comercio_nom '{col_com}' no encontrado — usando 'SIN_COMERCIO'")
    df[col_com] = "SIN_COMERCIO"
if col_monto not in df.columns:
    print(f"⚠️  monto '{col_monto}' no encontrado — usando 0")
    df[col_monto] = 0.0

print(f"\n  Filas            : {len(df):,}")
print(f"  Clientes únicos  : {df[col_cli].nunique():,}")
print(f"  Comercios únicos : {df[col_com].nunique():,}")
print(f"  Monto total (S/) : {df[col_monto].sum():,.2f}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE B — VARIABLES TEMPORALES
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[B] Variables temporales...")

df["HORA_DIA"]        = df[col_fh].dt.hour
df["DIA_SEMANA"]      = df[col_fh].dt.dayofweek
df["DIA_SEMANA_NOM"]  = df[col_fh].dt.strftime("%a").str.upper()
df["MES"]             = df[col_fh].dt.month
df["MES_NOM"]         = df[col_fh].dt.strftime("%b").str.upper()
df["ANIO"]            = df[col_fh].dt.year
df["FECHA_DIA"]       = df[col_fh].dt.normalize()
df["SEMANA_ISO"]      = df[col_fh].dt.isocalendar().week.astype(int)
df["ES_FIN_SEMANA"]   = (df["DIA_SEMANA"] >= 5).astype(int)
df["QUINCENA"]        = np.where(df[col_fh].dt.day <= 15, "Q1", "Q2")

_FRANJAS = [(0,6,"MADRUGADA"),(6,12,"MANANA"),(12,19,"TARDE"),(19,24,"NOCHE")]
def franja(h):
    for ini, fin, nom in _FRANJAS:
        if ini <= h < fin: return nom
    return "NOCHE"

df["FRANJA_HORARIA"]    = df["HORA_DIA"].map(franja)
df["ES_MADRUGADA"]      = (df["FRANJA_HORARIA"] == "MADRUGADA").astype(int)
df["ES_HORARIO_LAB"]    = ((df["DIA_SEMANA"] < 5) & df["HORA_DIA"].between(8, 17)).astype(int)

df["_fecha_str"] = df[col_fh].dt.strftime("%Y-%m-%d")
df["ES_FERIADO"] = df["_fecha_str"].isin(FERIADOS_PERU).astype(int)

df["_mes_dia"] = df[col_fh].dt.strftime("%m-%d")
df["ES_FECHA_ESPECIAL"] = df["_mes_dia"].isin(set(FECHAS_ESPECIALES.keys())).astype(int)
df["NOMBRE_FECHA_ESP"]  = df["_mes_dia"].map(FECHAS_ESPECIALES).fillna("")

df["ES_DIA_PAGO"] = df[col_fh].dt.day.isin(DIAS_PAGO).astype(int)
df.drop(columns=["_fecha_str", "_mes_dia"], inplace=True)

print(f"  FRANJA_HORARIA:\n{df['FRANJA_HORARIA'].value_counts().to_string()}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE C — CLASIFICACIÓN DE LA TRANSACCIÓN
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[C] Clasificación de la transacción...")

col_resp  = C.get("cod_respuesta", "")
col_ind   = C.get("indicador", "")
col_eci   = C.get("eci", "")
col_marca = C.get("marca", "")
col_bil   = C.get("billetera", "")
col_em    = C.get("entry_mode", "")
col_moto  = C.get("ind_recurrente", "")
col_seg   = C.get("segmento", "")
col_org_c = C.get("organizacion", "")
col_cvvr  = C.get("cod_red_comercio", "")
col_razon = C.get("razon_respuesta", "")

CODIGOS_APROBADO = {"0", "00", "000"}
if col_resp and col_resp in df.columns:
    df["ESTADO"] = df[col_resp].apply(
        lambda x: "APROBADA" if str(x).strip() in CODIGOS_APROBADO else "DENEGADA"
    )
elif SOLO_APROBADAS:
    df["ESTADO"] = "APROBADA"
else:
    df["ESTADO"] = "DESCONOCIDO"

INDICADOR_LABEL = {"F": "Fraude", "G": "Buena", "P": "Pendiente", "D": "Descarte", "N": "Normal"}
if col_ind and col_ind in df.columns:
    df["ES_FRAUDE"]       = (df[col_ind].str.upper() == "F").astype(int)
    df["INDICADOR_TEXTO"] = df[col_ind].map(INDICADOR_LABEL).fillna("Otro")
else:
    df["ES_FRAUDE"]       = 0
    df["INDICADOR_TEXTO"] = "Sin dato"

df["ES_FRAUDE_APROBADO"] = ((df["ES_FRAUDE"] == 1) & (df["ESTADO"] == "APROBADA")).astype(int)

CODIGOS_SEGURO = {"2", "02", "5", "05"}
if col_eci and col_eci in df.columns:
    df["SEGURO"] = df[col_eci].apply(
        lambda x: "Seguro" if str(x).strip() in CODIGOS_SEGURO else "No Seguro"
    )
else:
    df["SEGURO"] = "No Seguro"

if col_marca and col_marca in df.columns:
    df["MARCA_TARJETA"] = df[col_marca].astype(str).str.strip().str[:1].map(MARCA_LABEL).fillna("OTRA")
elif "TARJETA" in df.columns:
    df["MARCA_TARJETA"] = df["TARJETA"].astype(str).str[:1].map(MARCA_LABEL).fillna("OTRA")
else:
    df["MARCA_TARJETA"] = "DESCONOCIDA"

col_tp = C.get("tipo_producto", "")
if col_tp and col_tp in df.columns:
    df["TIPO_PRODUCTO_TEXTO"] = df[col_tp].map(TIPO_PROD_LABEL).fillna(df[col_tp])
else:
    df["TIPO_PRODUCTO_TEXTO"] = "Sin dato"

if col_bil and col_bil in df.columns:
    df["_bil5"]            = df[col_bil].astype(str).str.strip().str[:5].str.upper()
    df["ES_TOKENIZADA"]    = (df["_bil5"] != "99999").astype(int)
    df["BILLETERA_NOMBRE"] = df["_bil5"].map(BILLETERA_LABEL).fillna(BILLETERA_DEFAULT)
    df.drop(columns=["_bil5"], inplace=True)
else:
    df["ES_TOKENIZADA"]    = 0
    df["BILLETERA_NOMBRE"] = "Sin dato"

if col_em and col_em in df.columns:
    df["TIPO_ENTRADA"]        = df[col_em].map(ENTRY_MODE_LABEL).fillna(df[col_em])
    df["ES_TARJETA_PRESENTE"] = df[col_em].isin(ENTRY_MODE_PRESENTE).astype(int)
else:
    df["TIPO_ENTRADA"]        = "Sin dato"
    df["ES_TARJETA_PRESENTE"] = 0

if col_moto and col_moto in df.columns:
    _ind = df[col_moto].astype(str).str.strip().str.upper()
    # R = suscripción/cargo automático recurrente (se separa de MOTO)
    # M/O/T = Mail Order / Online / Telephone Order (Card Not Present manual)
    df["ES_RECURRENTE"] = (_ind == "R").astype(int)
    df["ES_MOTO"]       = (_ind.isin({"M", "O", "T", "S", "SI", "1", "TRUE", "Y", "YES"})).astype(int)
else:
    df["ES_RECURRENTE"] = 0
    df["ES_MOTO"]       = 0

if col_seg and col_seg in df.columns:
    seg_s = df[col_seg].astype(str).str.strip().str.split(".").str[0]
    df["SEG_NOMBRE"] = seg_s.map(SEG_NOMBRE).fillna("Otro/Sin seg")
    df["SEG_GRUPO"]  = seg_s.map(SEG_GRUPO).fillna("Otro/Sin seg")
else:
    df["SEG_NOMBRE"] = "Sin dato"
    df["SEG_GRUPO"]  = "Sin dato"

if col_org_c and col_org_c in df.columns:
    org_s = df[col_org_c].astype(str).str.strip()
    df["ORG_NOMBRE"] = org_s.map(ORG_NOMBRE).fillna(org_s)
else:
    df["ORG_NOMBRE"] = "Sin dato"

if col_cvvr and col_cvvr in df.columns:
    df["TIPO_CVV"] = df[col_cvvr].map(COD_RED_LABEL).fillna("Otro")
else:
    df["TIPO_CVV"] = "Sin dato"

if col_razon and col_razon in df.columns:
    df["MOTIVO_RECHAZO"] = df[col_razon].apply(clasificar_motivo)
    df.loc[df["ESTADO"] == "APROBADA", "MOTIVO_RECHAZO"] = "N/A"
else:
    df["MOTIVO_RECHAZO"] = "Sin dato"

if col_resp and col_resp in df.columns:
    df["ES_CODIGO_CRITICO"] = df[col_resp].isin(CODIGOS_CRITICOS).astype(int)
else:
    df["ES_CODIGO_CRITICO"] = 0

print(f"  ES_FRAUDE / ES_FRAUDE_APROBADO: {df['ES_FRAUDE'].sum():,} / {df['ES_FRAUDE_APROBADO'].sum():,}")
print(f"  Aprobadas / Denegadas: {(df['ESTADO']=='APROBADA').sum():,} / {(df['ESTADO']=='DENEGADA').sum():,}")
print(f"  Seguro / No Seguro   : {(df['SEGURO']=='Seguro').sum():,} / {(df['SEGURO']=='No Seguro').sum():,}")
print(f"  Tokenizadas          : {df['ES_TOKENIZADA'].sum():,}")
print(f"  ES_RECURRENTE        : {df['ES_RECURRENTE'].sum():,}  ← cargos automáticos")
print(f"  ES_MOTO              : {df['ES_MOTO'].sum():,}  ← CNP manual (M/O/T)")
print(f"  Marca: {df['MARCA_TARJETA'].value_counts().to_dict()}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE M — SCORE DIFERENCIADO POR MARCA (solo Tarjeta de Crédito)
#  Monitor entrega un score nativo:
#    Visa Crédito       → 0–99    (mayor = menor riesgo)
#    Mastercard Crédito → 0–999   (mayor = menor riesgo)
#  Se normaliza a [0,1]. Para débito no llega → SCORE_MON_NORM = NaN.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[M] Score diferenciado por marca...")

col_scm = C.get("score_riesgo_mon", "")
if col_scm and col_scm in df.columns:
    s = pd.to_numeric(df[col_scm], errors="coerce")

    # TIPO_PRODUCTO_TEXTO mapea "TC"→"Credito", por eso se busca "Credito" (no "TC")
    mask_tc   = df["TIPO_PRODUCTO_TEXTO"].isin({"TC", "Credito"})
    mask_visa = (df["MARCA_TARJETA"] == "VISA")
    mask_mc   = (df["MARCA_TARJETA"] == "MASTERCARD")

    df["SCORE_MON_NORM"] = np.nan
    df.loc[mask_tc & mask_visa, "SCORE_MON_NORM"] = (
        s[mask_tc & mask_visa] / SCORE_VISA_MAX
    ).round(4)
    df.loc[mask_tc & mask_mc, "SCORE_MON_NORM"] = (
        s[mask_tc & mask_mc] / SCORE_MC_MAX
    ).round(4)

    df["FLAG_SCORE_RIESGO_MON_ALTO"] = (
        df["SCORE_MON_NORM"].notna() & (df["SCORE_MON_NORM"] < UMBRAL_SCORE_MON)
    ).astype(int)

    def _cat_score(norm):
        if pd.isna(norm):  return "SIN_SCORE"
        elif norm < 0.33:  return "ALTO_RIESGO"
        elif norm < 0.66:  return "MEDIO"
        else:              return "BAJO_RIESGO"

    df["CATEGORIA_SCORE_MON"] = df["SCORE_MON_NORM"].map(_cat_score)

    n_con_score = df["SCORE_MON_NORM"].notna().sum()
    print(f"  Txn con score de marca     : {n_con_score:,}")
    print(f"  FLAG_SCORE_RIESGO_MON_ALTO : {df['FLAG_SCORE_RIESGO_MON_ALTO'].sum():,}")
    print(f"  CATEGORIA_SCORE_MON:\n{df['CATEGORIA_SCORE_MON'].value_counts().to_string()}")
else:
    df["SCORE_MON_NORM"]             = np.nan
    df["FLAG_SCORE_RIESGO_MON_ALTO"] = 0
    df["CATEGORIA_SCORE_MON"]        = "SIN_SCORE"
    print(f"  '{col_scm or 'score_riesgo_mon'}' no disponible — SCORE_MON_NORM = NaN")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE D — VENTANAS DESLIZANTES POR CLIENTE
#  Para cada txn: cuántas txn y cuánto monto acumuló ese cliente
#  en los N segundos ANTERIORES a esa transacción.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[D] Ventanas deslizantes por cliente...")

df = df.sort_values([col_cli, col_fh]).reset_index(drop=True)
df["_ts"] = df[col_fh].astype(np.int64) // 10**9

VENTANAS = {
    "TRX_CLIENTE_2MIN" :  (  2 * 60, "count"),
    "TRX_CLIENTE_5MIN" :  (  5 * 60, "count"),
    "TRX_CLIENTE_10MIN":  ( 10 * 60, "count"),
    "TRX_CLIENTE_1H"   :  ( 60 * 60, "count"),
    "TRX_CLIENTE_24H"  :  (24 * 3600,"count"),
    "MNT_CLIENTE_2MIN" :  (  2 * 60, "sum"),
    "MNT_CLIENTE_5MIN" :  (  5 * 60, "sum"),
    "MNT_CLIENTE_10MIN":  ( 10 * 60, "sum"),
    "MNT_CLIENTE_1H"   :  ( 60 * 60, "sum"),
    "MNT_CLIENTE_24H"  :  (24 * 3600,"sum"),
}

def calcular_ventana(grupo, segundos, modo, col_m):
    ts  = grupo["_ts"].values
    amt = grupo[col_m].fillna(0).values if modo == "sum" else None
    n   = len(ts)
    res = np.zeros(n)
    for i in range(n):
        j = np.searchsorted(ts, ts[i] - segundos, side="left")
        res[i] = i - j if modo == "count" else amt[j:i].sum()
    return res

resultados = {col: np.zeros(len(df)) for col in VENTANAS}
for cliente, grupo in df.groupby(col_cli, sort=False):
    idx = grupo.index.values
    for col, (segs, modo) in VENTANAS.items():
        vals = calcular_ventana(grupo, segs, modo, col_monto)
        resultados[col][idx] = vals

for col, vals in resultados.items():
    df[col] = vals
    df[col] = df[col].round(2) if col.startswith("MNT_") else df[col].astype(int)

df.drop(columns=["_ts"], inplace=True)

df["GAP_MINUTOS"] = (
    df.groupby(col_cli)[col_fh].diff().dt.total_seconds() / 60
).round(1)

df["FLAG_RAFAGA_5MIN"]  = (df["TRX_CLIENTE_5MIN"]  >= 3).astype(int)
df["FLAG_RAFAGA_10MIN"] = (df["TRX_CLIENTE_10MIN"] >= 3).astype(int)
df["FLAG_VEL_ALTA_1H"]  = (df["TRX_CLIENTE_1H"]   >= 5).astype(int)
df["FLAG_ACUM_ALTO_1H"] = (df["MNT_CLIENTE_1H"]   >= df[col_monto] * 2).astype(int)

print(f"  TRX_CLIENTE_5MIN  media : {df['TRX_CLIENTE_5MIN'].mean():.2f}")
print(f"  MNT_CLIENTE_24H   media : {df['MNT_CLIENTE_24H'].mean():,.2f}")
print(f"  FLAG_RAFAGA_5MIN        : {df['FLAG_RAFAGA_5MIN'].sum():,} txn")
print("  Ventanas OK ✅")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE E — INTERACCIONES VELOCIDAD × MONTO
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[E] Interacciones velocidad × monto...")

for w in ["5MIN", "10MIN", "1H", "24H"]:
    df[f"MONTO_PROM_{w}"] = (
        df[f"MNT_CLIENTE_{w}"] / df[f"TRX_CLIENTE_{w}"].replace(0, np.nan)
    ).round(2)

# ACELERACION > 1: el monto de las últimas txn es mayor que el promedio de la hora
# ACELERACION < 1: empezó con montos bajos (card testing)
df["ACELERACION_MONTO"]    = (df["MONTO_PROM_5MIN"] / df["MONTO_PROM_1H"].replace(0, np.nan)).round(2)
# CONCENTRACION > 0.8: el 80%+ del monto de la hora se gastó en solo 5 min
df["CONCENTRACION_5MIN_1H"] = (df["MNT_CLIENTE_5MIN"] / df["MNT_CLIENTE_1H"].replace(0, np.nan)).round(4)

df["_mean_cli"] = df.groupby(col_cli)[col_monto].transform("mean")
df["_std_cli"]  = df.groupby(col_cli)[col_monto].transform("std").fillna(1).replace(0, 1)
df["ZSCORE_MONTO_CLIENTE"]       = ((df[col_monto] - df["_mean_cli"]) / df["_std_cli"]).round(3)
df["RATIO_MONTO_VS_HIST_CLIENTE"] = (df[col_monto] / df["_mean_cli"].replace(0, np.nan)).round(2)
df.drop(columns=["_mean_cli", "_std_cli"], inplace=True)

print("  Interacciones OK ✅")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE F — PERFIL DEL CLIENTE
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[F] Perfil del cliente...")

totales_cli = (
    df.groupby(col_cli).agg(
        TOTAL_TRX_CLIENTE  = (col_monto, "count"),
        MONTO_TOTAL_CLIENTE = (col_monto, "sum"),
        COMERCIOS_DISTINTOS = (col_com,   "nunique"),
        DIAS_ACTIVO         = ("FECHA_DIA","nunique"),
    ).reset_index()
)
df = df.merge(totales_cli, on=col_cli, how="left")

cli_dia = (
    df.groupby([col_cli, "FECHA_DIA"]).agg(
        TRX_CLIENTE_DIA  = (col_monto, "count"),
        MONTO_CLIENTE_DIA = (col_monto, "sum"),
        COMERCIOS_DIA     = (col_com,   "nunique"),
    ).reset_index()
)
df = df.merge(cli_dia, on=[col_cli, "FECHA_DIA"], how="left")

df["FLAG_REINCIDENTE"]        = (df["TOTAL_TRX_CLIENTE"] > 1).astype(int)
df["FLAG_MULTI_COMERCIO_DIA"] = (df["COMERCIOS_DIA"] > 1).astype(int)
df["FLAG_RAFAGA_DIA"]         = (df["TRX_CLIENTE_DIA"] >= 3).astype(int)
df["FREC_DIARIA_CLIENTE"]     = (df["TOTAL_TRX_CLIENTE"] / df["DIAS_ACTIVO"].replace(0, 1)).round(2)

# Primera vez del cliente en ese comercio
df_s = df.sort_values([col_cli, col_com, col_fh])
df["_rango_cc"] = df_s.groupby([col_cli, col_com]).cumcount()
df["ES_CLIENTE_NUEVO_COMERCIO"] = (df["_rango_cc"] == 0).astype(int)
df.drop(columns=["_rango_cc"], inplace=True)

# Días desde última txn en ese comercio
df_prev = df.sort_values([col_cli, col_com, col_fh]).copy()
df["DIAS_DESDE_ULT_TRX_COMERCIO"] = (
    df_prev.groupby([col_cli, col_com])[col_fh].diff().dt.days
)

col_saldo = C.get("saldo", "")
if col_saldo and col_saldo in df.columns:
    df["RATIO_MONTO_VS_SALDO"] = (df[col_monto] / df[col_saldo].replace(0, np.nan)).round(4)
    df["FLAG_SALDO_AGOTADO"]   = (df["RATIO_MONTO_VS_SALDO"] >= 0.9).astype(int)
else:
    df["RATIO_MONTO_VS_SALDO"] = np.nan
    df["FLAG_SALDO_AGOTADO"]   = 0

print(f"  Clientes reincidentes      : {df.loc[df['FLAG_REINCIDENTE']==1, col_cli].nunique():,}")
print(f"  Primeras visitas a comercio: {df['ES_CLIENTE_NUEVO_COMERCIO'].sum():,} txn")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE N — VÍNCULOS DE CLIENTE
#  Comportamiento histórico del cliente EN EL PERÍODO analizado.
#  "Vínculo" = señales de que este cliente ya tuvo fraude, o se desvía
#  de su patrón habitual de consumo en este comercio.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[N] Vínculos de cliente...")

# Fraudes ANTERIORES del cliente (cronológicamente antes de cada txn).
# Se ordena por fecha y se hace expanding().sum().shift(1) para que cada txn
# solo vea los fraudes que YA ocurrieron antes — sin incluirse a sí misma.
# Esto evita data leakage: una txn F no se cuenta en su propio historial.
col_fh_sort = C.get("fecha_hora", "")
if col_fh_sort and col_fh_sort in df.columns:
    df_sorted = df.sort_values([col_cli, col_fh_sort])
    _fraudes_acum = (
        df_sorted.groupby(col_cli)["ES_FRAUDE"]
        .transform(lambda x: x.shift(1).expanding().sum())
        .fillna(0)
    )
    df["N_FRAUDES_CLIENTE_PERIODO"]   = _fraudes_acum.reindex(df.index).fillna(0).astype(int)
else:
    # Sin columna de fecha: fallback al conteo total (menos preciso, pero no rompe)
    fraudes_por_cli = (
        df.groupby(col_cli)["ES_FRAUDE"].sum()
        .reset_index()
        .rename(columns={"ES_FRAUDE": "N_FRAUDES_CLIENTE_PERIODO"})
    )
    df = df.merge(fraudes_por_cli, on=col_cli, how="left")
    df["N_FRAUDES_CLIENTE_PERIODO"] = df["N_FRAUDES_CLIENTE_PERIODO"].fillna(0).astype(int)
df["TIENE_FRAUDE_PREVIO_PERIODO"] = (df["N_FRAUDES_CLIENTE_PERIODO"] > 0).astype(int)

# Residente = cliente con historial (≥2 txn en el dataset)
df["ES_RESIDENTE"] = (df["TOTAL_TRX_CLIENTE"] >= 2).astype(int)

# Z-score del monto del cliente DENTRO de ese comercio específico
# (distinto de ZSCORE_MONTO_CLIENTE que es global del cliente)
df["_mean_cli_com"] = df.groupby([col_cli, col_com])[col_monto].transform("mean")
df["_std_cli_com"]  = (
    df.groupby([col_cli, col_com])[col_monto].transform("std").fillna(1).replace(0, 1)
)
df["ZSCORE_MONTO_CLI_COMERCIO"] = (
    (df[col_monto] - df["_mean_cli_com"]) / df["_std_cli_com"]
).round(3)
df.drop(columns=["_mean_cli_com", "_std_cli_com"], inplace=True)

# Promedio de txn/día del cliente en ese comercio (su patrón habitual)
_trx_cli_com_dia = (
    df.groupby([col_cli, col_com, "FECHA_DIA"]).size()
    .reset_index(name="_n")
)
_prom_cli_com = (
    _trx_cli_com_dia.groupby([col_cli, col_com])["_n"].mean()
    .reset_index()
    .rename(columns={"_n": "TRX_DIA_PROM_CLIENTE_COMERCIO"})
)
_prom_cli_com["TRX_DIA_PROM_CLIENTE_COMERCIO"] = (
    _prom_cli_com["TRX_DIA_PROM_CLIENTE_COMERCIO"].round(2)
)
df = df.merge(_prom_cli_com, on=[col_cli, col_com], how="left")

df["FLAG_TRX_EXCEDE_PATRON_CLI_COM"] = (
    df["TRX_CLIENTE_24H"] > (df["TRX_DIA_PROM_CLIENTE_COMERCIO"].fillna(1) * 2)
).astype(int)

# Primera transacción del cliente en este comercio + fue denegada
df["FLAG_PRIMERA_TRX_Y_DENEGADA"] = (
    (df["ES_CLIENTE_NUEVO_COMERCIO"] == 1) & (df["ESTADO"] == "DENEGADA")
).astype(int)

print(f"  TIENE_FRAUDE_PREVIO_PERIODO   : {df['TIENE_FRAUDE_PREVIO_PERIODO'].sum():,} txn")
print(f"  ES_RESIDENTE                  : {df['ES_RESIDENTE'].sum():,} txn")
print(f"  FLAG_PRIMERA_TRX_Y_DENEGADA   : {df['FLAG_PRIMERA_TRX_Y_DENEGADA'].sum():,} txn")
print(f"  FLAG_TRX_EXCEDE_PATRON_CLI_COM: {df['FLAG_TRX_EXCEDE_PATRON_CLI_COM'].sum():,} txn")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE G — PERFIL DEL COMERCIO Y MCC
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[G] Perfil del comercio y MCC...")

col_q = C.get("q_transaccional", "")
if col_q and col_q in df.columns:
    df[col_q] = pd.to_numeric(df[col_q], errors="coerce")
    def cat_com(q):
        if pd.isna(q) or q == 0: return "NUEVO"
        elif q < 500:             return "PEQUENO"
        elif q < 5000:            return "MEDIANO"
        else:                     return "GRANDE"
    df["CATEGORIA_COMERCIO"] = df[col_q].map(cat_com)
    df["ES_COMERCIO_NUEVO"]  = (df["CATEGORIA_COMERCIO"] == "NUEVO").astype(int)
else:
    df["CATEGORIA_COMERCIO"] = "Sin dato"
    df["ES_COMERCIO_NUEVO"]  = 0

totales_com = (
    df.groupby(col_com).agg(
        TOTAL_TRX_COMERCIO    = (col_monto, "count"),
        MONTO_TOTAL_COMERCIO   = (col_monto, "sum"),
        MONTO_PROM_COMERCIO    = (col_monto, "mean"),
        CLIENTES_DIST_COMERCIO = (col_cli,   "nunique"),
        DIAS_CON_TRX           = ("FECHA_DIA","nunique"),
        FRAUDES_COMERCIO       = ("ES_FRAUDE","sum"),
    ).reset_index()
)
totales_com["TASA_FRAUDE_COMERCIO"] = (
    totales_com["FRAUDES_COMERCIO"] / totales_com["TOTAL_TRX_COMERCIO"]
).round(4)
df = df.merge(totales_com, on=col_com, how="left")

com_dia = (
    df.groupby([col_com, "FECHA_DIA"])
    .agg(TRX_COMERCIO_DIA=(col_monto,"count"))
    .reset_index()
)
df = df.merge(com_dia, on=[col_com,"FECHA_DIA"], how="left")

rank_com = (
    totales_com[[col_com,"TOTAL_TRX_COMERCIO"]]
    .sort_values("TOTAL_TRX_COMERCIO", ascending=False)
    .reset_index(drop=True)
)
rank_com["RANKING_COMERCIO"] = rank_com.index + 1
df = df.merge(rank_com[[col_com,"RANKING_COMERCIO"]], on=col_com, how="left")

df["DESVIO_MONTO_VS_COMERCIO"] = (df[col_monto] - df["MONTO_PROM_COMERCIO"]).round(2)
df["RATIO_MONTO_VS_COMERCIO"]  = (df[col_monto] / df["MONTO_PROM_COMERCIO"].replace(0, np.nan)).round(2)

col_pais = C.get("pais", "")
if col_pais and col_pais in df.columns:
    pais_pred = (
        df.groupby(col_com)[col_pais]
        .agg(lambda x: x.mode()[0] if len(x) > 0 else "SIN_DATO")
        .reset_index()
        .rename(columns={col_pais: "PAIS_PREDOMINANTE_COMERCIO"})
    )
    df = df.merge(pais_pred, on=col_com, how="left")
    df["FLAG_PAIS_INUSUAL"] = (df[col_pais] != df["PAIS_PREDOMINANTE_COMERCIO"]).astype(int)
else:
    df["PAIS_PREDOMINANTE_COMERCIO"] = "Sin dato"
    df["FLAG_PAIS_INUSUAL"] = 0

col_mcc = C.get("mcc", "")
if col_mcc and col_mcc in df.columns:
    totales_mcc = (
        df.groupby(col_mcc).agg(
            TOTAL_TRX_MCC   = (col_monto,   "count"),
            MONTO_TOTAL_MCC = (col_monto,   "sum"),
            COM_EN_MCC      = (col_com,     "nunique"),
            FRAUDES_MCC     = ("ES_FRAUDE", "sum"),
        ).reset_index()
    )
    totales_mcc["TASA_FRAUDE_MCC"] = (
        totales_mcc["FRAUDES_MCC"] / totales_mcc["TOTAL_TRX_MCC"]
    ).round(4)
    df = df.merge(totales_mcc, on=col_mcc, how="left")
    rank_mcc = totales_mcc[[col_mcc,"TOTAL_TRX_MCC"]].sort_values(
        "TOTAL_TRX_MCC", ascending=False
    ).reset_index(drop=True)
    rank_mcc["RANKING_MCC"] = rank_mcc.index + 1
    df = df.merge(rank_mcc[[col_mcc,"RANKING_MCC"]], on=col_mcc, how="left")
else:
    df["TASA_FRAUDE_MCC"] = np.nan

print(f"  Top 3 comercios:\n{rank_com.head(3).to_string(index=False)}")
print(f"  FLAG_PAIS_INUSUAL: {df['FLAG_PAIS_INUSUAL'].sum():,}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE O — PERFIL HORARIO DEL COMERCIO
#  Identifica si una transacción ocurre fuera de la franja horaria habitual
#  del comercio (más de 2 desviaciones estándar de la hora promedio).
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[O] Perfil horario del comercio...")

hora_perfil_com = (
    df.groupby(col_com)["HORA_DIA"].agg(
        HORA_PROM_COMERCIO="mean",
        HORA_STD_COMERCIO="std",
    ).reset_index()
)
hora_perfil_com["HORA_PROM_COMERCIO"] = hora_perfil_com["HORA_PROM_COMERCIO"].round(1)
hora_perfil_com["HORA_STD_COMERCIO"]  = (
    hora_perfil_com["HORA_STD_COMERCIO"].fillna(2).round(1).clip(lower=1)
)
df = df.merge(hora_perfil_com, on=col_com, how="left")

df["FLAG_HORA_FUERA_PERFIL_COMERCIO"] = (
    (df["HORA_DIA"] < (df["HORA_PROM_COMERCIO"] - 2 * df["HORA_STD_COMERCIO"])) |
    (df["HORA_DIA"] > (df["HORA_PROM_COMERCIO"] + 2 * df["HORA_STD_COMERCIO"]))
).astype(int)

# Promedio de txn por cliente por día en ese comercio (perfil del comercio, no del cliente)
_trx_cli_dia_com = (
    df.groupby([col_com, col_cli, "FECHA_DIA"]).size()
    .reset_index(name="_n2")
)
_prom_trx_com = (
    _trx_cli_dia_com.groupby(col_com)["_n2"].mean()
    .reset_index()
    .rename(columns={"_n2": "TRX_PROM_CLIENTE_DIA_COMERCIO"})
)
_prom_trx_com["TRX_PROM_CLIENTE_DIA_COMERCIO"] = (
    _prom_trx_com["TRX_PROM_CLIENTE_DIA_COMERCIO"].round(2)
)
df = df.merge(_prom_trx_com, on=col_com, how="left")

df["FLAG_CLIENTE_SUPERA_PERFIL_COMERCIO"] = (
    df["TRX_CLIENTE_24H"] > (df["TRX_PROM_CLIENTE_DIA_COMERCIO"].fillna(1) * 2)
).astype(int)

print(f"  FLAG_HORA_FUERA_PERFIL_COMERCIO  : {df['FLAG_HORA_FUERA_PERFIL_COMERCIO'].sum():,} txn")
print(f"  FLAG_CLIENTE_SUPERA_PERFIL_COMERCIO: {df['FLAG_CLIENTE_SUPERA_PERFIL_COMERCIO'].sum():,} txn")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE H — SEÑALES DE MONTO
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[H] Señales de monto...")

df["FLAG_MONTO_REDONDO"] = ((df[col_monto] % 50 == 0) & (df[col_monto] >= 50)).astype(int)
df["FLAG_MONTO_BAJO"]    = (df[col_monto] < 20).astype(int)

df["_mean_com"] = df.groupby(col_com)[col_monto].transform("mean")
df["_std_com"]  = df.groupby(col_com)[col_monto].transform("std").fillna(1).replace(0, 1)
df["ZSCORE_MONTO_COMERCIO"] = ((df[col_monto] - df["_mean_com"]) / df["_std_com"]).round(3)
df.drop(columns=["_mean_com", "_std_com"], inplace=True)

q25, q50, q75 = df[col_monto].quantile([0.25, 0.50, 0.75])
p10, p90      = df[col_monto].quantile([0.10, 0.90])

def rango_std(m):
    if   m <= q25: return "BAJO"
    elif m <= q50: return "MEDIO_BAJO"
    elif m <= q75: return "MEDIO_ALTO"
    else:          return "ALTO"

def rango_perc(m):
    if   m <= p10: return "P0_10"
    elif m <= q25: return "P10_25"
    elif m <= q50: return "P25_50"
    elif m <= q75: return "P50_75"
    elif m <= p90: return "P75_90"
    else:          return "P90_100"

df["RANGO_MONTO"]          = df[col_monto].map(rango_std)
df["RANGO_MONTO_PERCENTIL"] = df[col_monto].map(rango_perc)
df["DECIL_MONTO"]          = pd.qcut(df[col_monto], q=10, labels=False, duplicates="drop").astype("Int64") + 1

try:
    from sklearn.tree import DecisionTreeClassifier
    if df["ES_FRAUDE"].sum() >= 10 and (df["ES_FRAUDE"] == 0).sum() >= 10:
        X = df[[col_monto]].fillna(0)
        y = df["ES_FRAUDE"]
        arbol = DecisionTreeClassifier(max_depth=3, min_samples_leaf=20, random_state=42)
        arbol.fit(X, y)
        df["_hoja"] = arbol.apply(X)
        hoja_map = {}
        for h in df["_hoja"].unique():
            mask = df["_hoja"] == h
            hoja_map[h] = f"ARBOL_{int(df.loc[mask, col_monto].mean()):,}"
        df["RANGO_MONTO_ARBOL"] = df["_hoja"].map(hoja_map)
        df.drop(columns=["_hoja"], inplace=True)
        print("  RANGO_MONTO_ARBOL ✅ (sklearn)")
    else:
        df["RANGO_MONTO_ARBOL"] = df["RANGO_MONTO"]
except ImportError:
    df["RANGO_MONTO_ARBOL"] = df["RANGO_MONTO"]
    print("  RANGO_MONTO_ARBOL = cuartiles (pip install scikit-learn para árbol)")

col_musd = C.get("monto_dolar", "")
if col_musd and col_musd in df.columns:
    df["TIPO_CAMBIO"] = (df[col_monto] / df[col_musd].replace(0, np.nan)).round(4)

print(f"  Q25={q25:.2f} | Q50={q50:.2f} | Q75={q75:.2f} | P90={p90:.2f}")
print(f"  FLAG_MONTO_REDONDO: {df['FLAG_MONTO_REDONDO'].sum():,} ({df['FLAG_MONTO_REDONDO'].mean()*100:.1f}%)")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE I — CARD TESTING (BIN extendido)
#  Cuando el mismo prefijo largo del número de tarjeta aparece en múltiples
#  tarjetas distintas el mismo día, indica generación algorítmica de tarjetas.
#
#  Escala de sospecha por longitud de BIN compartido:
#    BIN_6  repetido → normal (mismo banco/producto)
#    BIN_10 repetido → sospechoso   → FLAG_BIN10_REPETIDO_DIA
#    BIN_11 repetido → muy sospechoso → FLAG_BIN11_REPETIDO_DIA
#    BIN_12 repetido → casi seguro generado → FLAG_BIN12_REPETIDO_DIA
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[I] Card testing (BIN extendido)...")

_tiene_tarjeta = "TARJETA" in df.columns
_tiene_bin12   = "BIN_12"  in df.columns

# Derivar BIN_10 y BIN_11 desde BIN_12 o TARJETA
if _tiene_bin12:
    df["BIN_10"] = df["BIN_12"].astype(str).str[:10]
    df["BIN_11"] = df["BIN_12"].astype(str).str[:11]
elif _tiene_tarjeta:
    df["BIN_10"] = df["TARJETA"].astype(str).str[:10]
    df["BIN_11"] = df["TARJETA"].astype(str).str[:11]

if _tiene_tarjeta and ("BIN_10" in df.columns):
    for _blen, _col_bin, _col_tar, _col_flag in [
        (10, "BIN_10", "TARJETAS_MISMO_BIN10_DIA", "FLAG_BIN10_REPETIDO_DIA"),
        (11, "BIN_11", "TARJETAS_MISMO_BIN11_DIA", "FLAG_BIN11_REPETIDO_DIA"),
    ]:
        _grp = (
            df.groupby([_col_bin, "FECHA_DIA"])["TARJETA"]
            .nunique().reset_index()
            .rename(columns={"TARJETA": _col_tar})
        )
        df = df.merge(_grp, on=[_col_bin, "FECHA_DIA"], how="left")
        df[_col_flag] = (df[_col_tar] > 1).astype(int)
        print(f"  {_col_flag}: {df[_col_flag].sum():,} txn")
else:
    for _col_tar, _col_flag in [
        ("TARJETAS_MISMO_BIN10_DIA", "FLAG_BIN10_REPETIDO_DIA"),
        ("TARJETAS_MISMO_BIN11_DIA", "FLAG_BIN11_REPETIDO_DIA"),
    ]:
        df[_col_tar]  = 0
        df[_col_flag] = 0
    print("  BIN_10/BIN_11 no disponibles — requiere BIN_12 o TARJETA en parquet")

if _tiene_bin12 and _tiene_tarjeta:
    bin12_dia = (
        df.groupby(["BIN_12","FECHA_DIA"])["TARJETA"]
        .nunique().reset_index()
        .rename(columns={"TARJETA": "TARJETAS_MISMO_BIN12_DIA"})
    )
    df = df.merge(bin12_dia, on=["BIN_12","FECHA_DIA"], how="left")
    df["FLAG_BIN12_REPETIDO_DIA"] = (df["TARJETAS_MISMO_BIN12_DIA"] > 1).astype(int)
    print(f"  FLAG_BIN12_REPETIDO_DIA: {df['FLAG_BIN12_REPETIDO_DIA'].sum():,} txn")
else:
    df["TARJETAS_MISMO_BIN12_DIA"] = 0
    df["FLAG_BIN12_REPETIDO_DIA"]  = 0
    print("  BIN_12 no disponible — ejecuta consolidar.py")

# ── Fecha de vencimiento × BIN ─────────────────────────────────────────────────
# Tarjetas generadas por algoritmo suelen compartir la misma fecha de vencimiento.
# En lotes nuevos la columna puede venir vacía o en cero — se normaliza a NaN.
col_ven = C.get("fecha_vencimiento", "")
if col_ven and col_ven in df.columns and col_bin and col_bin in df.columns:
    _VACIOS_VEN = {"0", "00", "0000", "00/00", "0/0", "", "nan", "none", "null"}
    df["_VEN"] = (
        df[col_ven].astype(str).str.strip().str.lower()
        .where(lambda x: ~x.isin(_VACIOS_VEN), other=np.nan)
    )

    # Fechas de vencimiento distintas por BIN×día (baja = sospechoso)
    _ven_dist = (
        df[df["_VEN"].notna()].groupby([col_bin, "FECHA_DIA"])["_VEN"]
        .nunique().reset_index()
        .rename(columns={"_VEN": "FECHAS_VEN_DIST_BIN_DIA"})
    )
    df = df.merge(_ven_dist, on=[col_bin, "FECHA_DIA"], how="left")
    df["FECHAS_VEN_DIST_BIN_DIA"] = df["FECHAS_VEN_DIST_BIN_DIA"].fillna(0).astype(int)

    # Cuántas tarjetas distintas comparten el mismo BIN + misma fecha de vencimiento
    if "TARJETA" in df.columns:
        _ven_tar = (
            df[df["_VEN"].notna()].groupby([col_bin, "FECHA_DIA", "_VEN"])["TARJETA"]
            .nunique().reset_index()
            .rename(columns={"TARJETA": "TARJETAS_MISMO_VEN_BIN"})
        )
        df = df.merge(_ven_tar, on=[col_bin, "FECHA_DIA", "_VEN"], how="left")
        df["TARJETAS_MISMO_VEN_BIN"] = df["TARJETAS_MISMO_VEN_BIN"].fillna(0).astype(int)
    else:
        df["TARJETAS_MISMO_VEN_BIN"] = 0

    # Flag: ≥3 tarjetas del mismo BIN con misma fecha de vencimiento → generadas
    df["FLAG_VEN_CONCENTRADA_BIN"] = (df["TARJETAS_MISMO_VEN_BIN"] >= 3).astype(int)
    df.drop(columns=["_VEN"], inplace=True)

    print(f"  FECHAS_VEN_DIST_BIN_DIA  máx: {df['FECHAS_VEN_DIST_BIN_DIA'].max()}")
    print(f"  TARJETAS_MISMO_VEN_BIN   máx: {df['TARJETAS_MISMO_VEN_BIN'].max()}")
    print(f"  FLAG_VEN_CONCENTRADA_BIN    : {df['FLAG_VEN_CONCENTRADA_BIN'].sum():,} txn")
else:
    df["FECHAS_VEN_DIST_BIN_DIA"]  = 0
    df["TARJETAS_MISMO_VEN_BIN"]   = 0
    df["FLAG_VEN_CONCENTRADA_BIN"] = 0
    _motivo = "no configurado en config.py" if not col_ven else f"'{col_ven}' no encontrado en parquet"
    print(f"  fecha_vencimiento {_motivo} — variables VEN en 0")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE J — RECHAZOS Y CASCADA CVV  (solo si SOLO_APROBADAS = False)
# ═══════════════════════════════════════════════════════════════════════════════
_cols_j = ["N_RECHAZOS_24H","N_CVV_FAIL_24H","HUBO_CVV_FAIL_PREVIO",
           "HUBO_FRAUDE_PREVIO_24H","PREV_FUE_FRAUDE","MIN_DESDE_ULTIMO_FRAUDE"]

if SOLO_APROBADAS:
    print("\n[J] Rechazos CVV — OMITIDO (SOLO_APROBADAS=True)")
    for c_ in _cols_j:
        df[c_] = 0 if c_ != "MIN_DESDE_ULTIMO_FRAUDE" else np.nan
else:
    print("\n[J] Cascada y rechazos CVV...")

    df_ap  = df[df["ESTADO"] == "APROBADA"].copy().sort_values([col_cli, col_fh]).reset_index(drop=True)
    df_den = df[df["ESTADO"] == "DENEGADA"].copy()

    df_ap["_ts2"] = df_ap[col_fh].astype(np.int64) // 10**9
    fraude_acum = np.zeros(len(df_ap))
    for cli, g in df_ap.groupby(col_cli, sort=False):
        ts  = g["_ts2"].values
        esf = g["ES_FRAUDE_APROBADO"].values
        n   = len(ts)
        for i in range(n):
            j = np.searchsorted(ts, ts[i] - 24*3600, side="left")
            fraude_acum[g.index.values[i]] = esf[j:i].sum()

    df_ap["HUBO_FRAUDE_PREVIO_24H"] = (fraude_acum > 0).astype(int)
    df_ap["PREV_FUE_FRAUDE"] = (
        df_ap.groupby(col_cli)["ES_FRAUDE_APROBADO"].shift(1).fillna(0).astype(int)
    )
    df_ap["MIN_DESDE_ULTIMO_FRAUDE"] = np.nan

    for cli, g in df_ap.groupby(col_cli, sort=False):
        g_f = g[g["ES_FRAUDE_APROBADO"] == 1]
        if len(g_f) == 0: continue
        for ix in g.index:
            t_act = df_ap.loc[ix, col_fh]
            previos = g_f[g_f[col_fh] < t_act]
            if len(previos) > 0:
                df_ap.loc[ix, "MIN_DESDE_ULTIMO_FRAUDE"] = (
                    t_act - previos[col_fh].max()
                ).total_seconds() / 60

    if len(df_den) > 0 and "MOTIVO_RECHAZO" in df_den.columns:
        df_den_s = df_den.sort_values([col_cli, col_fh]).copy()
        df_den_s["_ts3"] = df_den_s[col_fh].astype(np.int64) // 10**9
        den_by_cli = {k: g for k, g in df_den_s.groupby(col_cli, sort=False)}
        rej_24h = np.zeros(len(df_ap))
        cvv_24h = np.zeros(len(df_ap))
        ap_ts   = df_ap[col_fh].astype(np.int64) // 10**9
        for i, (ix, row) in enumerate(df_ap.iterrows()):
            cli = row[col_cli]
            t   = int(ap_ts.iloc[i])
            if cli not in den_by_cli: continue
            gd   = den_by_cli[cli]
            mask = (gd["_ts3"].values >= t - 24*3600) & (gd["_ts3"].values < t)
            sub  = gd[mask]
            rej_24h[i] = len(sub)
            cvv_24h[i] = (sub["MOTIVO_RECHAZO"] == "CVV_FAIL").sum()
        df_ap["N_RECHAZOS_24H"]       = rej_24h.astype(int)
        df_ap["N_CVV_FAIL_24H"]       = cvv_24h.astype(int)
        df_ap["HUBO_CVV_FAIL_PREVIO"] = (cvv_24h > 0).astype(int)
    else:
        df_ap[["N_RECHAZOS_24H","N_CVV_FAIL_24H","HUBO_CVV_FAIL_PREVIO"]] = 0

    df_ap.drop(columns=["_ts2"], inplace=True)
    df = df.merge(
        df_ap[[col_cli, col_fh] + _cols_j].drop_duplicates([col_cli, col_fh]),
        on=[col_cli, col_fh], how="left"
    )
    for c_ in _cols_j:
        if c_ != "MIN_DESDE_ULTIMO_FRAUDE":
            df[c_] = df[c_].fillna(0).astype(int)

    print(f"  HUBO_FRAUDE_PREVIO_24H: {df['HUBO_FRAUDE_PREVIO_24H'].sum():,}")
    print(f"  N_CVV_FAIL_24H total  : {df['N_CVV_FAIL_24H'].sum():,}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE Q — VELOCIDAD POR BIN
#  Para cada txn: cuántas txn, cuánto monto y cuántos clientes distintos
#  tuvo ese BIN en las últimas 1h y 24h ANTERIORES a esa transacción.
#
#  Detecta ataques concentrados en un BIN:
#    - Muchas txn del mismo BIN en poco tiempo → TRX_BIN_1H alto
#    - Monto acumulado del BIN explotado en el día → MNT_BIN_24H alto
#    - Muchos clientes distintos usando el mismo BIN → CLIENTES_BIN_DIA alto
#
#  Umbrales configurables en config.py → UMBRALES_REGLA["bin_*"]
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[Q] Velocidad por BIN...")

if col_bin and col_bin in df.columns:
    df = df.sort_values([col_bin, col_fh]).reset_index(drop=True)
    df["_ts_q"] = df[col_fh].astype(np.int64) // 10**9

    VENTANAS_BIN = {
        "TRX_BIN_1H" : (3600,  "count"),
        "TRX_BIN_24H": (86400, "count"),
        "MNT_BIN_1H" : (3600,  "sum"),
        "MNT_BIN_24H": (86400, "sum"),
    }

    res_bin = {col: np.zeros(len(df)) for col in VENTANAS_BIN}
    for _bin_val, _grupo in df.groupby(col_bin, sort=False):
        _idx = _grupo.index.values
        _ts  = _grupo["_ts_q"].values
        _amt = _grupo[col_monto].fillna(0).values
        _n   = len(_ts)
        for col, (segs, modo) in VENTANAS_BIN.items():
            vals = np.zeros(_n)
            for i in range(_n):
                j = np.searchsorted(_ts, _ts[i] - segs, side="left")
                vals[i] = (i - j) if modo == "count" else _amt[j:i].sum()
            res_bin[col][_idx] = vals

    for col, vals in res_bin.items():
        df[col] = vals
        df[col] = df[col].round(2) if col.startswith("MNT_") else df[col].astype(int)

    # Clientes únicos del BIN por día (agrupado diario — eficiente y suficiente)
    _cli_bin_dia = (
        df.groupby([col_bin, "FECHA_DIA"])[col_cli]
        .nunique().reset_index()
        .rename(columns={col_cli: "CLIENTES_BIN_DIA"})
    )
    df = df.merge(_cli_bin_dia, on=[col_bin, "FECHA_DIA"], how="left")
    df["CLIENTES_BIN_DIA"] = df["CLIENTES_BIN_DIA"].fillna(0).astype(int)

    df.drop(columns=["_ts_q"], inplace=True)

    # Flags de alerta — umbrales desde config.py
    _umb_trx = UMBRALES_REGLA.get("bin_trx_1h",    10)
    _umb_mnt = UMBRALES_REGLA.get("bin_monto_24h", 5000)
    _umb_cli = UMBRALES_REGLA.get("bin_clientes_dia", 5)

    df["FLAG_RAFAGA_BIN_1H"]      = (df["TRX_BIN_1H"]      >= _umb_trx).astype(int)
    df["FLAG_MONTO_BIN_ALTO_24H"] = (df["MNT_BIN_24H"]      >= _umb_mnt).astype(int)
    df["FLAG_CLIENTES_BIN_ALTO"]  = (df["CLIENTES_BIN_DIA"] >= _umb_cli).astype(int)

    print(f"  TRX_BIN_1H    máx : {int(df['TRX_BIN_1H'].max())}")
    print(f"  MNT_BIN_24H   máx : {df['MNT_BIN_24H'].max():,.2f}")
    print(f"  CLIENTES_BIN_DIA  máx : {int(df['CLIENTES_BIN_DIA'].max())}")
    print(f"  FLAG_RAFAGA_BIN_1H     : {df['FLAG_RAFAGA_BIN_1H'].sum():,} txn")
    print(f"  FLAG_MONTO_BIN_ALTO_24H: {df['FLAG_MONTO_BIN_ALTO_24H'].sum():,} txn")
    print(f"  FLAG_CLIENTES_BIN_ALTO : {df['FLAG_CLIENTES_BIN_ALTO'].sum():,} txn")
else:
    df["TRX_BIN_1H"]              = 0
    df["TRX_BIN_24H"]             = 0
    df["MNT_BIN_1H"]              = 0.0
    df["MNT_BIN_24H"]             = 0.0
    df["CLIENTES_BIN_DIA"]        = 0
    df["FLAG_RAFAGA_BIN_1H"]      = 0
    df["FLAG_MONTO_BIN_ALTO_24H"] = 0
    df["FLAG_CLIENTES_BIN_ALTO"]  = 0
    print(f"  '{col_bin or 'bin'}' no disponible — Bloque Q omitido")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE R — SEÑALES DE GENERACIÓN ROBÓTICA
#  Detecta ataques donde múltiples tarjetas del mismo BIN cobran el mismo
#  monto exacto en el mismo día. NO requiere etiqueta de fraude (funciona
#  sobre las N también). Complementa al ML no supervisado.
#
#  Patrón típico: BIN 415100 → 47 tarjetas distintas → todas cobran S/98.00
#  → CV_MONTO_BIN_DIA ≈ 0 → FLAG_MONTO_ROBOTICO_BIN = 1
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[R] Señales de generación robótica...")

if col_bin and col_bin in df.columns and "TARJETA" in df.columns:
    # Coeficiente de variación del monto por BIN×día (0 = todos los montos iguales)
    _cv_bin = (
        df.groupby([col_bin, "FECHA_DIA"])[col_monto]
        .agg(_mean="mean", _std="std", N_MONTOS_DIST_BIN_DIA="nunique")
        .reset_index()
    )
    _cv_bin["CV_MONTO_BIN_DIA"] = (
        _cv_bin["_std"] / _cv_bin["_mean"].replace(0, np.nan)
    ).round(4).fillna(0)
    _cv_bin.drop(columns=["_mean", "_std"], inplace=True)
    df = df.merge(_cv_bin, on=[col_bin, "FECHA_DIA"], how="left")

    # Cuántas tarjetas distintas comparten exactamente el mismo monto en ese BIN×día
    _monto_bin = (
        df.groupby([col_bin, "FECHA_DIA", col_monto])["TARJETA"]
        .nunique().reset_index()
        .rename(columns={"TARJETA": "N_TARJETAS_MISMO_MONTO_BIN"})
    )
    df = df.merge(_monto_bin, on=[col_bin, "FECHA_DIA", col_monto], how="left")
    df["N_TARJETAS_MISMO_MONTO_BIN"] = df["N_TARJETAS_MISMO_MONTO_BIN"].fillna(1).astype(int)

    # Flag: monto idéntico en ≥3 tarjetas del mismo BIN Y variación casi nula
    df["FLAG_MONTO_ROBOTICO_BIN"] = (
        (df["N_TARJETAS_MISMO_MONTO_BIN"] >= 3) &
        (df["CV_MONTO_BIN_DIA"] < 0.05)
    ).astype(int)

    n_rob = df["FLAG_MONTO_ROBOTICO_BIN"].sum()
    print(f"  CV_MONTO_BIN_DIA  mín : {df['CV_MONTO_BIN_DIA'].min():.4f}")
    print(f"  N_TARJETAS_MISMO_MONTO_BIN máx : {df['N_TARJETAS_MISMO_MONTO_BIN'].max()}")
    print(f"  FLAG_MONTO_ROBOTICO_BIN : {n_rob:,} txn")
    if n_rob > 0:
        tasa_f_rob = df.loc[df["FLAG_MONTO_ROBOTICO_BIN"]==1, "ES_FRAUDE"].mean()
        print(f"  Tasa fraude en robóticas: {tasa_f_rob*100:.1f}%  ← si > tasa global = señal válida")
else:
    df["CV_MONTO_BIN_DIA"]            = np.nan
    df["N_MONTOS_DIST_BIN_DIA"]       = 0
    df["N_TARJETAS_MISMO_MONTO_BIN"]  = 0
    df["FLAG_MONTO_ROBOTICO_BIN"]     = 0
    print("  BIN o TARJETA no disponibles — Bloque R omitido")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE S — MONEDA / DIVISA
#  Detecta transacciones en moneda distinta a la habitual del cliente.
#
#  Lógica del monto_original:
#    monto_original ≈ monto_dolar  → txn realizada en USD
#    monto_original ≈ monto local  → txn realizada en soles (normal en Perú)
#    ninguno de los dos            → txn en otra moneda (EUR, GBP, etc.) → muy sospechoso
#
#  Lógica del campo moneda_trx (si disponible):
#    604 = PEN (soles) | 840 = USD | 978 = EUR | otros = inusual
#    Un cliente que siempre compra en soles y de golpe compra en USD
#    puede ser: viaje legítimo O tarjeta usada en comercio extranjero fraudulento.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[S] Moneda / divisa...")

col_mon_orig = C.get("monto_original", "")
col_moneda   = C.get("moneda_trx", "")

# ── Moneda de transacción ─────────────────────────────────────────────────────
MONEDA_LABEL = {"604": "PEN", "840": "USD", "978": "EUR", "826": "GBP"}
MONEDAS_NORMALES = {"604", "840"}   # soles y dólares son normales en Perú

if col_moneda and col_moneda in df.columns:
    df["MONEDA_TRX_COD"]   = df[col_moneda].astype(str).str.strip().str.zfill(3)
    df["MONEDA_TRX_TEXTO"] = df["MONEDA_TRX_COD"].map(MONEDA_LABEL).fillna("OTRA")
    df["FLAG_MONEDA_INUSUAL"] = (~df["MONEDA_TRX_COD"].isin(MONEDAS_NORMALES)).astype(int)
    print(f"  MONEDA_TRX_TEXTO:\n{df['MONEDA_TRX_TEXTO'].value_counts().to_string()}")
    print(f"  FLAG_MONEDA_INUSUAL: {df['FLAG_MONEDA_INUSUAL'].sum():,} txn")
else:
    df["MONEDA_TRX_COD"]    = "SIN_DATO"
    df["MONEDA_TRX_TEXTO"]  = "SIN_DATO"
    df["FLAG_MONEDA_INUSUAL"] = 0
    print(f"  '{col_moneda or 'moneda_trx'}' no disponible — Bloque S parcial")

# ── monto_original → inferir divisa si la columna está disponible ─────────────
col_md = C.get("monto_dolar", "")
_tiene_orig  = col_mon_orig and col_mon_orig in df.columns
_tiene_dolar = col_md and col_md in df.columns

if _tiene_orig:
    df[col_mon_orig] = pd.to_numeric(df[col_mon_orig], errors="coerce")

    if _tiene_dolar:
        _ratio_usd = (df[col_mon_orig] / df[col_md].replace(0, np.nan)).round(3)
        df["FLAG_TRX_EN_DOLAR"] = _ratio_usd.between(0.98, 1.02).astype(int)
    else:
        df["FLAG_TRX_EN_DOLAR"] = 0

    _ratio_pen = (df[col_mon_orig] / df[col_monto].replace(0, np.nan)).round(3)
    _es_pen    = _ratio_pen.between(0.98, 1.02)
    _es_usd    = df["FLAG_TRX_EN_DOLAR"].astype(bool)
    df["FLAG_MONEDA_OTRA"] = (~_es_pen & ~_es_usd).fillna(0).astype(int)

    print(f"  FLAG_TRX_EN_DOLAR : {df['FLAG_TRX_EN_DOLAR'].sum():,} txn")
    print(f"  FLAG_MONEDA_OTRA  : {df['FLAG_MONEDA_OTRA'].sum():,} txn  ← ni soles ni dólares")
else:
    df["FLAG_TRX_EN_DOLAR"] = 0
    df["FLAG_MONEDA_OTRA"]  = 0
    print(f"  '{col_mon_orig or 'monto_original'}' no disponible — flags de divisa en 0")

# ── Cambio de moneda del cliente ──────────────────────────────────────────────
# Si el cliente normalmente compra en soles y de golpe aparece en dólares (o viceversa),
# puede ser señal de tarjeta usada en comercio extranjero fraudulento.
if df["FLAG_TRX_EN_DOLAR"].sum() > 0:
    _moneda_habitual = (
        df.groupby(col_cli)["FLAG_TRX_EN_DOLAR"]
        .transform(lambda x: x.mode()[0] if len(x) > 0 else 0)
    )
    df["FLAG_CAMBIO_MONEDA_CLI"] = (
        df["FLAG_TRX_EN_DOLAR"] != _moneda_habitual
    ).astype(int)
    print(f"  FLAG_CAMBIO_MONEDA_CLI: {df['FLAG_CAMBIO_MONEDA_CLI'].sum():,} txn")
else:
    df["FLAG_CAMBIO_MONEDA_CLI"] = 0

# ── Saldo en moneda extranjera + monto alto ────────────────────────────────────
# Si la txn es en moneda extranjera y el saldo restante es bajo → agotamiento
col_saldo_s = C.get("saldo", "")
if col_saldo_s and col_saldo_s in df.columns and df["FLAG_MONEDA_INUSUAL"].sum() > 0:
    df["FLAG_AGOTAMIENTO_MONEDA_EXT"] = (
        (df["FLAG_MONEDA_INUSUAL"] == 1) &
        (df[col_saldo_s].fillna(9999) < df[col_monto] * 0.1)
    ).astype(int)
    print(f"  FLAG_AGOTAMIENTO_MONEDA_EXT: {df['FLAG_AGOTAMIENTO_MONEDA_EXT'].sum():,} txn")
else:
    df["FLAG_AGOTAMIENTO_MONEDA_EXT"] = 0


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE K — FLAGS DE REGLAS CONFIGURABLES
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[K] Flags de reglas configurables...")

for umbral in UMBRALES_REGLA.get("monto_acum_24h", []):
    df[f"FLAG_MNT_ACUM_{umbral}_24H"] = (df["MNT_CLIENTE_24H"] >= umbral).astype(int)

for umbral in UMBRALES_REGLA.get("trx_en_5min", []):
    df[f"FLAG_TRX_{umbral}_EN_5MIN"] = (df["TRX_CLIENTE_5MIN"] >= umbral).astype(int)

for umbral in UMBRALES_REGLA.get("trx_en_10min", []):
    df[f"FLAG_TRX_{umbral}_EN_10MIN"] = (df["TRX_CLIENTE_10MIN"] >= umbral).astype(int)

for umbral in UMBRALES_REGLA.get("trx_en_1h", []):
    df[f"FLAG_TRX_{umbral}_EN_1H"] = (df["TRX_CLIENTE_1H"] >= umbral).astype(int)

for mnt in UMBRALES_REGLA.get("monto_acum_24h", []):
    for trx in UMBRALES_REGLA.get("trx_en_5min", []):
        df[f"FLAG_COMBO_MNT{mnt}_TRX{trx}"] = (
            (df["MNT_CLIENTE_24H"] >= mnt) & (df["TRX_CLIENTE_5MIN"] >= trx)
        ).astype(int)

df["FLAG_ESCALADA_MONTO"] = (
    df["MONTO_PROM_5MIN"] >= df["MONTO_PROM_24H"].replace(0, np.nan) * 2
).fillna(0).astype(int)

print(f"  FLAGS de reglas configurables generados ✅")
for col in [c for c in df.columns if c.startswith("FLAG_MNT_ACUM_") or c.startswith("FLAG_TRX_")]:
    print(f"    {col}: {df[col].sum():,}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE L — SCORE DE RIESGO COMPUESTO (0 a 11)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[L] Score de riesgo compuesto...")

componentes = [
    "FLAG_RAFAGA_5MIN",                  # ráfaga de txn en 5 min
    "FLAG_VEL_ALTA_1H",                  # velocidad alta en 1h
    "HUBO_FRAUDE_PREVIO_24H",            # hubo fraude previo en 24h
    "HUBO_CVV_FAIL_PREVIO",              # hubo fallo CVV antes (cascada)
    "FLAG_MONTO_REDONDO",                # monto exacto múltiplo de 50
    "ES_MADRUGADA",                      # entre 0 y 6am
    "FLAG_REINCIDENTE",                  # cliente con múltiples txn en el dataset
    "FLAG_PAIS_INUSUAL",                 # país distinto al habitual del comercio
    "FLAG_BIN12_REPETIDO_DIA",           # mismo BIN12 en múltiples tarjetas ese día
    "TIENE_FRAUDE_PREVIO_PERIODO",       # cliente tuvo fraude en el período analizado
    "FLAG_HORA_FUERA_PERFIL_COMERCIO",   # txn fuera del horario habitual del comercio
]

df["SCORE_RIESGO"] = sum(
    df[c].fillna(0).astype(int) for c in componentes if c in df.columns
)
df["PERFIL_RIESGO"] = pd.cut(
    df["SCORE_RIESGO"],
    bins=[-1, 0, 2, 5, 99],
    labels=["BAJO","MEDIO","ALTO","MUY_ALTO"]
)
df["FLAG_HORARIO_RIESGO"] = (
    (df["ES_MADRUGADA"] == 1) | (df["ES_FIN_SEMANA"] == 1)
).astype(int)

print(f"  PERFIL_RIESGO:\n{df['PERFIL_RIESGO'].value_counts().sort_index().to_string()}")
print(f"  Score promedio: {df['SCORE_RIESGO'].mean():.2f}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE T — RECURRENCIA Y SUSCRIPCIONES
#  Detecta fraude en comercios de membresía mensual (Smart Fit, Apple Bill,
#  Netflix, Spotify, etc.) donde el patrón normal es UN cobro cada ~30 días.
#  El fraude aquí NO es por velocidad alta (TRX_5MIN≈0) sino por GAP anómalo:
#    - GAP muy corto  → tarjeta probada / doble cobro
#    - GAP muy largo  → reactivación de tarjeta robada / primera suscripción
#    - Primer cobro en comercio recurrente → alto riesgo (cuenta nueva)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[T] Recurrencia y suscripciones...")

# GAP en días (más legible que minutos para ciclos mensuales)
df["GAP_DIAS"] = (df["GAP_MINUTOS"] / 1440).round(2)

# ── Detección de ciclo mensual anómalo ───────────────────────────────────────
# Solo aplica si ES_RECURRENTE=1 (cobro automático de membresía)
_es_rec = df.get("ES_RECURRENTE", pd.Series(0, index=df.index)).fillna(0).astype(int)
_gap_min = df["GAP_MINUTOS"].fillna(99999)
_gap_dias = df["GAP_DIAS"].fillna(999)

# Cobro demasiado pronto (< 20 días): suscripción mensual que ya se cobró
# → puede ser doble cobro o tarjeta robada probada antes de que la cierren
df["FLAG_COBRO_ADELANTADO"] = (
    (_es_rec == 1) & (_gap_dias < 20) & (_gap_dias > 0)
).astype(int)

# Cobro demasiado tarde (> 45 días): skip de un mes, luego reaparece
# → tarjeta recuperada por fraudster, o reactivación de cuenta dormida
df["FLAG_COBRO_ATRASADO"] = (
    (_es_rec == 1) & (_gap_dias > 45)
).astype(int)

# Gap muy corto en recurrente (< 2 horas): el patrón de fraude Smart Fit
# Un cobro mensual que vuelve en minutos es imposible en lo legítimo
df["FLAG_GAP_CORTO_RECURRENTE"] = (
    (_es_rec == 1) & (_gap_min < 120)
).astype(int)

# Gap en la zona de mayor fraude según análisis (15-120 min): aplica a cualquier txn
# No solo recurrente — cover también intentos manuales repetidos
df["FLAG_GAP_ZONA_FRAUDE"] = (
    _gap_min.between(15, 120)
).astype(int)

n_adelantado = int(df["FLAG_COBRO_ADELANTADO"].sum())
n_atrasado   = int(df["FLAG_COBRO_ATRASADO"].sum())
n_gap_corto  = int(df["FLAG_GAP_CORTO_RECURRENTE"].sum())
n_zona       = int(df["FLAG_GAP_ZONA_FRAUDE"].sum())
print(f"  FLAG_COBRO_ADELANTADO    : {n_adelantado:,}  (recurrente < 20 días)")
print(f"  FLAG_COBRO_ATRASADO      : {n_atrasado:,}  (recurrente > 45 días)")
print(f"  FLAG_GAP_CORTO_RECURRENTE: {n_gap_corto:,}  (recurrente < 2 horas)")
print(f"  FLAG_GAP_ZONA_FRAUDE     : {n_zona:,}  (gap 15-120 min, zona de fraude)")

# ── Primera transacción en este comercio ─────────────────────────────────────
# ES_CLIENTE_NUEVO_COMERCIO ya existe (Bloque N).
# Aquí agregamos la combinación específica de riesgo:
# Primera txn + ES_RECURRENTE = nueva suscripción (riesgo alto en membresías)
if "ES_CLIENTE_NUEVO_COMERCIO" in df.columns:
    df["FLAG_NUEVA_SUSCRIPCION"] = (
        (df["ES_CLIENTE_NUEVO_COMERCIO"] == 1) & (_es_rec == 1)
    ).astype(int)
else:
    df["FLAG_NUEVA_SUSCRIPCION"] = 0

# Primera txn + monto alto (> P90 del comercio) = riesgo de account takeover
# Aplica a Apple.com, tiendas online de alto valor
_monto_p90_com = df[col_monto].quantile(0.90)
if "ES_CLIENTE_NUEVO_COMERCIO" in df.columns:
    df["FLAG_PRIMERA_TRX_MONTO_ALTO"] = (
        (df["ES_CLIENTE_NUEVO_COMERCIO"] == 1) &
        (df[col_monto] >= _monto_p90_com)
    ).astype(int)
else:
    df["FLAG_PRIMERA_TRX_MONTO_ALTO"] = 0

print(f"  FLAG_NUEVA_SUSCRIPCION       : {df['FLAG_NUEVA_SUSCRIPCION'].sum():,}  (1ra txn + recurrente)")
print(f"  FLAG_PRIMERA_TRX_MONTO_ALTO  : {df['FLAG_PRIMERA_TRX_MONTO_ALTO'].sum():,}  (1ra txn + monto ≥ P90 S/{_monto_p90_com:.2f})")

# ── Doble cobro en el mismo comercio ─────────────────────────────────────────
# Mismo cliente, mismo monto, mismo comercio en < 7 días → doble billing
# Aplica tanto a suscripciones como a hardware (Apple.com cobrado dos veces)
col_com = C.get("comercio", "")
if col_com and col_com in df.columns:
    _key_doble = df[col_cli].astype(str) + "|" + df[col_com].astype(str)
    _monto_str = df[col_monto].round(2).astype(str)
    _mask_gap_7d = _gap_dias < 7

    # Agrupar: cliente+comercio con gap < 7 días y mismo monto
    df["_KEY_DOBLE"] = _key_doble + "|" + _monto_str
    _doble_counts = (
        df[_mask_gap_7d]
        .groupby("_KEY_DOBLE")["_KEY_DOBLE"]
        .transform("count")
        .reindex(df.index, fill_value=0)
    )
    df["FLAG_DOBLE_COBRO_COMERCIO"] = (
        (_mask_gap_7d) & (_doble_counts >= 2)
    ).astype(int)
    df.drop(columns=["_KEY_DOBLE"], inplace=True)
else:
    df["FLAG_DOBLE_COBRO_COMERCIO"] = 0

print(f"  FLAG_DOBLE_COBRO_COMERCIO    : {df['FLAG_DOBLE_COBRO_COMERCIO'].sum():,}  (mismo monto, mismo com, < 7 días)")

# ── Frecuencia del cliente en este comercio ───────────────────────────────────
# Cuántas veces aparece el cliente en este comercio en el período analizado
# Para suscripciones: debería ser 1 por mes. Más de 3 en el período = anómalo.
if col_com and col_com in df.columns:
    _freq_cli_com = df.groupby([col_cli, col_com])[col_monto].transform("count")
    df["FREQ_CLIENTE_COMERCIO"] = _freq_cli_com.fillna(1).astype(int)
    df["FLAG_FREQ_INUSUAL_COM"] = (
        (_es_rec == 1) & (df["FREQ_CLIENTE_COMERCIO"] > 3)
    ).astype(int)
    print(f"  FLAG_FREQ_INUSUAL_COM        : {df['FLAG_FREQ_INUSUAL_COM'].sum():,}  (recurrente con >3 cobros en el período)")
else:
    df["FREQ_CLIENTE_COMERCIO"] = 1
    df["FLAG_FREQ_INUSUAL_COM"] = 0

# ── Cambio de monto en suscripción ───────────────────────────────────────────
# Si el cliente pagaba X/mes y de repente paga 3X → posible cambio de plan forzado
# (account takeover que upgradea la suscripción)
if col_com and col_com in df.columns and "MONTO_PROM_24H" in df.columns:
    _monto_hist_cli_com = (
        df.groupby([col_cli, col_com])[col_monto]
        .transform(lambda x: x.expanding().mean().shift(1))
    )
    _ratio_vs_hist = (df[col_monto] / _monto_hist_cli_com.replace(0, np.nan))
    df["FLAG_CAMBIO_MONTO_SUSCRIPCION"] = (
        (_es_rec == 1) &
        (_ratio_vs_hist > 2.0) &
        (_monto_hist_cli_com.notna())
    ).fillna(0).astype(int)
    print(f"  FLAG_CAMBIO_MONTO_SUSCRIPCION: {df['FLAG_CAMBIO_MONTO_SUSCRIPCION'].sum():,}  (monto 2x+ vs histórico del cliente en el comercio)")
else:
    df["FLAG_CAMBIO_MONTO_SUSCRIPCION"] = 0

# ── Catálogo de precios del comercio (automático, sin hardcodear) ─────────────
# Extrae los montos más frecuentes del dataset → son los precios reales del comercio.
# Para Smart Fit detecta: 9.90, 19.90, 29.90, 39.90, 99.90, 109.90, 119.90
# Para Apple Bill detecta: 9.90, 14.90, 19.90, etc.
# Para cualquier comercio de suscripción funciona sin configuración manual.
print("\n[T.2] Catálogo de precios del comercio...")

_montos_redond = df[col_monto].round(2)
_top_precios   = _montos_redond.value_counts().head(8).index.tolist()  # top 8 más frecuentes
_precio_base   = _top_precios[0] if _top_precios else df[col_monto].median()
_precio_2do    = _top_precios[1] if len(_top_precios) > 1 else None

print(f"  Precio base (más frecuente) : S/{_precio_base:.2f}")
print(f"  Precio 2do más frecuente    : S/{_precio_2do:.2f}" if _precio_2do else "  (solo 1 precio frecuente)")
print(f"  Catálogo completo           : {[round(p,2) for p in _top_precios]}")

# FLAG_MONTO_PRECIO_CONOCIDO: monto está dentro del catálogo (±1%)
def _en_catalogo(monto, catalogo, tol=0.01):
    return any(abs(monto - p) / (p + 0.01) <= tol for p in catalogo)

df["FLAG_MONTO_PRECIO_CONOCIDO"] = _montos_redond.apply(
    lambda m: int(_en_catalogo(m, _top_precios))
)

# FLAG_MONTO_MULTIPLO_BASE: monto ≈ N × precio_base (N = 2..12)
# Detecta pagos multi-mes: 3×119.90=359.70, 6×99.90=599.40, etc.
_mejor_n   = pd.Series(0, index=df.index, dtype=int)
_es_multip = pd.Series(False, index=df.index)
for _n in range(2, 13):
    _esperado = _precio_base * _n
    _match    = ((_montos_redond - _esperado).abs() / _esperado) <= 0.015
    _es_multip = _es_multip | _match
    _mejor_n[_match] = _n

df["FLAG_MONTO_MULTIPLO_BASE"] = _es_multip.astype(int)
df["N_MESES_EQUIV"]            = _mejor_n.where(_es_multip, other=1)
# Ajustar N_MESES_EQUIV para los precios del catálogo (1 mes)
df.loc[df["FLAG_MONTO_PRECIO_CONOCIDO"] == 1, "N_MESES_EQUIV"] = 1

# FLAG_POSIBLE_ADDON: monto entre precio_base y precio_base×1.5
# → probablemente plan base + adicional (coach, balance, etc.)
# No es el precio exacto, pero tampoco es un múltiplo — zona de add-ons
df["FLAG_POSIBLE_ADDON"] = (
    (_montos_redond > _precio_base * 1.02) &
    (_montos_redond < _precio_base * 1.50) &
    (df["FLAG_MONTO_PRECIO_CONOCIDO"] == 0) &
    (df["FLAG_MONTO_MULTIPLO_BASE"] == 0)
).astype(int)

# FLAG_POSIBLE_MANTENIMIENTO: monto coincide con el 2do precio más frecuente
# Para Smart Fit = S/99.90 (mantenimiento anual que clientes olvidan)
if _precio_2do:
    df["FLAG_POSIBLE_MANTENIMIENTO"] = (
        ((_montos_redond - _precio_2do).abs() / (_precio_2do + 0.01)) <= 0.015
    ).astype(int)
else:
    df["FLAG_POSIBLE_MANTENIMIENTO"] = 0

# FLAG_MONTO_NO_EXPLICADO: recurrente Y monto no encaja en ningún patrón conocido
# Estos son los candidatos reales a fraude (no card testing del precio conocido)
df["FLAG_MONTO_NO_EXPLICADO"] = (
    (_es_rec == 1) &
    (df["FLAG_MONTO_PRECIO_CONOCIDO"] == 0) &
    (df["FLAG_MONTO_MULTIPLO_BASE"]   == 0) &
    (df["FLAG_POSIBLE_ADDON"]         == 0) &
    (df["FLAG_POSIBLE_MANTENIMIENTO"] == 0)
).astype(int)

# ── Tipología de transacción de suscripción ──────────────────────────────────
# Resume en una sola columna de texto qué tipo de cobro es (para Excel/análisis)
_tipo = pd.Series("OTRO", index=df.index)
_tipo[df["FLAG_POSIBLE_MANTENIMIENTO"] == 1] = "MANTENIMIENTO_ANUAL"
_tipo[df["FLAG_POSIBLE_ADDON"] == 1]         = "PLAN+ADICIONAL"
_mask_multi = df["FLAG_MONTO_MULTIPLO_BASE"] == 1
_tipo[_mask_multi] = ("MULTI_MES_" + df.loc[_mask_multi, "N_MESES_EQUIV"].astype(str) + "M")
_tipo[df["FLAG_MONTO_PRECIO_CONOCIDO"] == 1] = "PRECIO_BASE"
_tipo[df["FLAG_MONTO_NO_EXPLICADO"] == 1]    = "MONTO_ANOMALO"
df["TIPO_COBRO_SUSCRIPCION"] = _tipo

n_conocido   = int(df["FLAG_MONTO_PRECIO_CONOCIDO"].sum())
n_multiplo   = int(df["FLAG_MONTO_MULTIPLO_BASE"].sum())
n_addon      = int(df["FLAG_POSIBLE_ADDON"].sum())
n_mant       = int(df["FLAG_POSIBLE_MANTENIMIENTO"].sum())
n_no_expl    = int(df["FLAG_MONTO_NO_EXPLICADO"].sum())
print(f"  FLAG_MONTO_PRECIO_CONOCIDO : {n_conocido:,}  → precio del catálogo (1 mes)")
print(f"  FLAG_MONTO_MULTIPLO_BASE   : {n_multiplo:,}  → pago multi-mes (2-12 meses)")
print(f"  FLAG_POSIBLE_ADDON         : {n_addon:,}  → plan base + adicional")
print(f"  FLAG_POSIBLE_MANTENIMIENTO : {n_mant:,}  → mantenimiento anual (disputa por confusión)")
print(f"  FLAG_MONTO_NO_EXPLICADO    : {n_no_expl:,}  → no encaja en ningún patrón ← sospechoso")
print(f"  TIPO_COBRO_SUSCRIPCION:\n{df['TIPO_COBRO_SUSCRIPCION'].value_counts().to_string()}")


# ═══════════════════════════════════════════════════════════════════════════════
#  RESUMEN DE VARIABLES GENERADAS
# ═══════════════════════════════════════════════════════════════════════════════
VARS_GENERADAS = [
    "HORA_DIA","DIA_SEMANA_NOM","ES_FIN_SEMANA","FRANJA_HORARIA","ES_MADRUGADA",
    "ES_HORARIO_LAB","QUINCENA","SEMANA_ISO","ES_FERIADO","ES_FECHA_ESPECIAL",
    "NOMBRE_FECHA_ESP","ES_DIA_PAGO",
    "ESTADO","ES_FRAUDE","ES_FRAUDE_APROBADO","INDICADOR_TEXTO","SEGURO",
    "MARCA_TARJETA","TIPO_PRODUCTO_TEXTO","ES_TOKENIZADA","BILLETERA_NOMBRE",
    "TIPO_ENTRADA","ES_TARJETA_PRESENTE","ES_MOTO",
    "SEG_NOMBRE","SEG_GRUPO","ORG_NOMBRE","TIPO_CVV","MOTIVO_RECHAZO","ES_CODIGO_CRITICO",
    "TRX_CLIENTE_2MIN","TRX_CLIENTE_5MIN","TRX_CLIENTE_10MIN","TRX_CLIENTE_1H","TRX_CLIENTE_24H",
    "MNT_CLIENTE_2MIN","MNT_CLIENTE_5MIN","MNT_CLIENTE_10MIN","MNT_CLIENTE_1H","MNT_CLIENTE_24H",
    "GAP_MINUTOS","FLAG_RAFAGA_5MIN","FLAG_RAFAGA_10MIN","FLAG_VEL_ALTA_1H","FLAG_ACUM_ALTO_1H",
    "MONTO_PROM_5MIN","MONTO_PROM_10MIN","MONTO_PROM_1H","MONTO_PROM_24H",
    "ACELERACION_MONTO","CONCENTRACION_5MIN_1H","ZSCORE_MONTO_CLIENTE","RATIO_MONTO_VS_HIST_CLIENTE",
    "TOTAL_TRX_CLIENTE","MONTO_TOTAL_CLIENTE","COMERCIOS_DISTINTOS","DIAS_ACTIVO",
    "TRX_CLIENTE_DIA","MONTO_CLIENTE_DIA","COMERCIOS_DIA",
    "FLAG_REINCIDENTE","FLAG_MULTI_COMERCIO_DIA","FLAG_RAFAGA_DIA",
    "FREC_DIARIA_CLIENTE","ES_CLIENTE_NUEVO_COMERCIO","DIAS_DESDE_ULT_TRX_COMERCIO",
    "RATIO_MONTO_VS_SALDO","FLAG_SALDO_AGOTADO",
    "CATEGORIA_COMERCIO","ES_COMERCIO_NUEVO",
    "TOTAL_TRX_COMERCIO","MONTO_TOTAL_COMERCIO","MONTO_PROM_COMERCIO",
    "CLIENTES_DIST_COMERCIO","DIAS_CON_TRX","TASA_FRAUDE_COMERCIO",
    "TRX_COMERCIO_DIA","RANKING_COMERCIO",
    "DESVIO_MONTO_VS_COMERCIO","RATIO_MONTO_VS_COMERCIO",
    "PAIS_PREDOMINANTE_COMERCIO","FLAG_PAIS_INUSUAL",
    "TOTAL_TRX_MCC","RANKING_MCC",
    "FLAG_MONTO_REDONDO","FLAG_MONTO_BAJO","ZSCORE_MONTO_COMERCIO",
    "RANGO_MONTO","RANGO_MONTO_PERCENTIL","RANGO_MONTO_ARBOL","DECIL_MONTO",
    "BIN_10","BIN_11",
    "TARJETAS_MISMO_BIN10_DIA","FLAG_BIN10_REPETIDO_DIA",
    "TARJETAS_MISMO_BIN11_DIA","FLAG_BIN11_REPETIDO_DIA",
    "TARJETAS_MISMO_BIN12_DIA","FLAG_BIN12_REPETIDO_DIA",
    "FECHAS_VEN_DIST_BIN_DIA","TARJETAS_MISMO_VEN_BIN","FLAG_VEN_CONCENTRADA_BIN",
    "N_RECHAZOS_24H","N_CVV_FAIL_24H","HUBO_CVV_FAIL_PREVIO",
    "HUBO_FRAUDE_PREVIO_24H","PREV_FUE_FRAUDE","MIN_DESDE_ULTIMO_FRAUDE",
    "SCORE_RIESGO","PERFIL_RIESGO","FLAG_HORARIO_RIESGO",
    # ── M: Score por marca ──────────────────────────────────────────────────
    "SCORE_MON_NORM","FLAG_SCORE_RIESGO_MON_ALTO","CATEGORIA_SCORE_MON",
    # ── N: Vínculos de cliente ───────────────────────────────────────────────
    "N_FRAUDES_CLIENTE_PERIODO","TIENE_FRAUDE_PREVIO_PERIODO","ES_RESIDENTE",
    "ZSCORE_MONTO_CLI_COMERCIO","TRX_DIA_PROM_CLIENTE_COMERCIO",
    "FLAG_TRX_EXCEDE_PATRON_CLI_COM","FLAG_PRIMERA_TRX_Y_DENEGADA",
    # ── O: Perfil horario del comercio ───────────────────────────────────────
    "HORA_PROM_COMERCIO","HORA_STD_COMERCIO","FLAG_HORA_FUERA_PERFIL_COMERCIO",
    "TRX_PROM_CLIENTE_DIA_COMERCIO","FLAG_CLIENTE_SUPERA_PERFIL_COMERCIO",
    # ── Q: Velocidad por BIN ─────────────────────────────────────────────────
    "TRX_BIN_1H","TRX_BIN_24H","MNT_BIN_1H","MNT_BIN_24H","CLIENTES_BIN_DIA",
    "FLAG_RAFAGA_BIN_1H","FLAG_MONTO_BIN_ALTO_24H","FLAG_CLIENTES_BIN_ALTO",
    # ── R: Generación robótica ────────────────────────────────────────────────
    "CV_MONTO_BIN_DIA","N_MONTOS_DIST_BIN_DIA","N_TARJETAS_MISMO_MONTO_BIN",
    "FLAG_MONTO_ROBOTICO_BIN",
    # ── G ampliado: MCC fraud rate ────────────────────────────────────────────
    "TASA_FRAUDE_MCC",
    # ── S: Moneda / divisa ────────────────────────────────────────────────────
    "ES_RECURRENTE",
    "MONEDA_TRX_COD", "MONEDA_TRX_TEXTO", "FLAG_MONEDA_INUSUAL",
    "FLAG_TRX_EN_DOLAR", "FLAG_MONEDA_OTRA",
    "FLAG_CAMBIO_MONEDA_CLI", "FLAG_AGOTAMIENTO_MONEDA_EXT",
    # ── T: Recurrencia y suscripciones ───────────────────────────────────────
    "GAP_DIAS",
    "FLAG_COBRO_ADELANTADO",        # recurrente < 20 días → doble cobro / intento temprano
    "FLAG_COBRO_ATRASADO",          # recurrente > 45 días → reactivación / cuenta dormida
    "FLAG_GAP_CORTO_RECURRENTE",    # recurrente < 2 horas → imposible en legítimo
    "FLAG_GAP_ZONA_FRAUDE",         # gap 15-120 min → zona de mayor concentración de fraude
    "FLAG_NUEVA_SUSCRIPCION",       # primera txn + ES_RECURRENTE → riesgo de suscripción falsa
    "FLAG_PRIMERA_TRX_MONTO_ALTO",  # primera txn + monto ≥ P90 → account takeover
    "FLAG_DOBLE_COBRO_COMERCIO",    # mismo monto, mismo comercio, < 7 días
    "FREQ_CLIENTE_COMERCIO",        # veces del cliente en este comercio en el período
    "FLAG_FREQ_INUSUAL_COM",        # recurrente con > 3 cobros (deberían ser 1/mes)
    "FLAG_CAMBIO_MONTO_SUSCRIPCION",# monto 2x+ vs histórico del cliente en el comercio
    # ── T.2: Catálogo de precios ─────────────────────────────────────────────
    "FLAG_MONTO_PRECIO_CONOCIDO",   # monto = precio del catálogo (1 mes normal)
    "FLAG_MONTO_MULTIPLO_BASE",     # monto = N × precio base (pago multi-mes)
    "N_MESES_EQUIV",                # cuántos meses equivale el monto
    "FLAG_POSIBLE_ADDON",           # monto = plan base + adicional (coach, balance...)
    "FLAG_POSIBLE_MANTENIMIENTO",   # monto = 2do precio más frecuente (mantenimiento anual)
    "FLAG_MONTO_NO_EXPLICADO",      # recurrente y monto no encaja en ningún patrón ← fraude
    "TIPO_COBRO_SUSCRIPCION",       # texto: PRECIO_BASE / MULTI_MES_3M / MONTO_ANOMALO / etc.
]

print("\n" + "─" * 65)
print("VARIABLES GENERADAS:")
for v in VARS_GENERADAS:
    print(f"  {'✅' if v in df.columns else '——'}  {v}")
print(f"\nTotal columnas: {df.shape[1]}")

# ═══════════════════════════════════════════════════════════════════════════════
#  GUARDAR
# ═══════════════════════════════════════════════════════════════════════════════
PARQUET_FEATURES.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(PARQUET_FEATURES, index=False)
print(f"\n✅ Features guardadas: {PARQUET_FEATURES}")
print(f"   {len(df):,} filas × {df.shape[1]} columnas")
print("─" * 65)
