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
  L  Score de riesgo compuesto     → SCORE_RIESGO 0-9, PERFIL_RIESGO
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

df[col_fh] = pd.to_datetime(df[col_fh], errors="coerce")
df = df.sort_values(col_fh).reset_index(drop=True)

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
    df["ES_MOTO"] = df[col_moto].astype(str).str.strip().str.upper().isin(
        {"S", "SI", "1", "TRUE", "Y", "YES", "M"}
    ).astype(int)
else:
    df["ES_MOTO"] = 0

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
print(f"  Marca: {df['MARCA_TARJETA'].value_counts().to_dict()}")


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
            TOTAL_TRX_MCC  = (col_monto,"count"),
            MONTO_TOTAL_MCC = (col_monto,"sum"),
            COM_EN_MCC      = (col_com,  "nunique"),
        ).reset_index()
    )
    df = df.merge(totales_mcc, on=col_mcc, how="left")
    rank_mcc = totales_mcc[[col_mcc,"TOTAL_TRX_MCC"]].sort_values(
        "TOTAL_TRX_MCC", ascending=False
    ).reset_index(drop=True)
    rank_mcc["RANKING_MCC"] = rank_mcc.index + 1
    df = df.merge(rank_mcc[[col_mcc,"RANKING_MCC"]], on=col_mcc, how="left")

print(f"  Top 3 comercios:\n{rank_com.head(3).to_string(index=False)}")
print(f"  FLAG_PAIS_INUSUAL: {df['FLAG_PAIS_INUSUAL'].sum():,}")


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
#  BIN_12 repetido en el mismo día con distintas tarjetas → tarjetas generadas
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[I] Card testing (BIN extendido)...")

if "BIN_12" in df.columns and "TARJETA" in df.columns:
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
#  BLOQUE L — SCORE DE RIESGO COMPUESTO (0 a 9)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[L] Score de riesgo compuesto...")

componentes = [
    "FLAG_RAFAGA_5MIN",        # ráfaga de txn en 5 min
    "FLAG_VEL_ALTA_1H",        # velocidad alta en 1h
    "HUBO_FRAUDE_PREVIO_24H",  # hubo fraude previo en 24h
    "HUBO_CVV_FAIL_PREVIO",    # hubo fallo CVV antes (cascada)
    "FLAG_MONTO_REDONDO",      # monto exacto múltiplo de 50
    "ES_MADRUGADA",            # entre 0 y 6am
    "FLAG_REINCIDENTE",        # cliente con múltiples txn en el dataset
    "FLAG_PAIS_INUSUAL",       # país distinto al habitual del comercio
    "FLAG_BIN12_REPETIDO_DIA", # mismo BIN12 en múltiples tarjetas ese día
]

df["SCORE_RIESGO"] = sum(
    df[c].fillna(0).astype(int) for c in componentes if c in df.columns
)
df["PERFIL_RIESGO"] = pd.cut(
    df["SCORE_RIESGO"],
    bins=[-1, 0, 1, 3, 99],
    labels=["BAJO","MEDIO","ALTO","MUY_ALTO"]
)
df["FLAG_HORARIO_RIESGO"] = (
    (df["ES_MADRUGADA"] == 1) | (df["ES_FIN_SEMANA"] == 1)
).astype(int)

print(f"  PERFIL_RIESGO:\n{df['PERFIL_RIESGO'].value_counts().sort_index().to_string()}")
print(f"  Score promedio: {df['SCORE_RIESGO'].mean():.2f}")


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
    "TARJETAS_MISMO_BIN12_DIA","FLAG_BIN12_REPETIDO_DIA",
    "N_RECHAZOS_24H","N_CVV_FAIL_24H","HUBO_CVV_FAIL_PREVIO",
    "HUBO_FRAUDE_PREVIO_24H","PREV_FUE_FRAUDE","MIN_DESDE_ULTIMO_FRAUDE",
    "SCORE_RIESGO","PERFIL_RIESGO","FLAG_HORARIO_RIESGO",
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
