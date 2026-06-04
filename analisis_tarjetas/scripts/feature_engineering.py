"""
feature_engineering.py — Ingeniería de Variables
Tarjetas Comprometidas N7 Débito — Scotiabank Peru

Lee data/consolidado.parquet y genera ~85 variables nuevas.

Bloques heredados de ecommerce_comercio:
  A  Carga y validación
  B  Variables temporales
  C  Clasificación de la txn
  D  Ventanas deslizantes por cliente
  E  Interacciones velocidad×monto
  F  Perfil del cliente
  G  Perfil del comercio y MCC
  H  Señales de monto
  I  Card testing (BIN extendido)
  J  Rechazos y cascada CVV
  K  Flags de reglas configurables
  L  Score de riesgo compuesto

Bloques nuevos para tarjetas comprometidas:
  M  Ventanas deslizantes por TARJETA (adicional a cliente)
  N  Flags de país y geografía
  O  MCC de alto riesgo y entry mode
  P  Score de riesgo ajustado para débito comprometido
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
    ANALISIS_NOMBRE, UMBRALES_REGLA,
    SEG_NOMBRE, SEG_GRUPO, COD_RED_LABEL, BILLETERA_LABEL, BILLETERA_DEFAULT,
    ENTRY_MODE_LABEL, ENTRY_MODE_PRESENTE, ENTRY_MODE_NP,
    MARCA_LABEL, TIPO_PROD_LABEL, CODIGOS_CRITICOS,
    ORG_NOMBRE, FERIADOS_PERU, FECHAS_ESPECIALES, DIAS_PAGO,
    MCC_ALTO_RIESGO,
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
print(f"FEATURE ENGINEERING — {ANALISIS_NOMBRE}")
print(f"  Modo: {'SOLO APROBADAS' if SOLO_APROBADAS else 'APROBADAS + DENEGADAS'}")
print("═" * 65)

df = leer_parquet(str(ruta_entrada))

cols_reales = set(df.columns)
faltantes   = {k: v for k, v in C.items() if v and v not in cols_reales}
if faltantes:
    print("\n⚠️  COLUMNAS NO ENCONTRADAS (features dependientes se omiten):")
    for k, v in faltantes.items():
        print(f"   COLS['{k}'] = '{v}'  ← no existe")

for col_key in ["monto", "monto_dolar", "monto_original", "saldo"]:
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

if col_fh not in df.columns:
    print(f"\n⚠️  '{col_fh}' no encontrada. Continuando sin fechas...")
    df[col_fh] = pd.NaT
else:
    df[col_fh] = pd.to_datetime(df[col_fh], errors="coerce")

if df[col_fh].notna().any():
    df = df.sort_values(col_fh).reset_index(drop=True)

if col_cli not in df.columns:
    df[col_cli] = df.index.astype(str)
if col_com not in df.columns:
    df[col_com] = "SIN_COMERCIO"
if col_monto not in df.columns:
    df[col_monto] = 0.0

print(f"\n  Filas            : {len(df):,}")
print(f"  Clientes únicos  : {df[col_cli].nunique():,}")
if "TARJETA" in df.columns:
    print(f"  Tarjetas únicas  : {df['TARJETA'].nunique():,}")
print(f"  Monto total (S/) : {df[col_monto].sum():,.2f}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE A2 — MONEDA DE LA TRANSACCIÓN (USD vs PEN)
#  Lógica: si monto_original ≈ monto_dolar  → transacción en USD
#          si monto_original ≈ monto_local   → transacción en PEN
#  Tolerancia de 0.01 para comparación de flotantes
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[A2] Moneda de la transacción (USD vs PEN)...")

col_monto_orig = C.get("monto_original", "")
col_monto_usd  = C.get("monto_dolar", "")
col_monto_loc  = C["monto"]

if col_monto_orig and col_monto_orig in df.columns:
    df[col_monto_orig] = pd.to_numeric(df[col_monto_orig], errors="coerce")
    df[col_monto_usd]  = pd.to_numeric(df[col_monto_usd],  errors="coerce")

    # FLAG_TRX_EN_USD: monto_original coincide con monto_dolar
    df["FLAG_TRX_EN_USD"] = (
        (df[col_monto_orig] - df[col_monto_usd]).abs() <= 0.01
    ).astype(int)

    # FLAG_TRX_EN_PEN: monto_original coincide con monto_local
    df["FLAG_TRX_EN_PEN"] = (
        (df[col_monto_orig] - df[col_monto_loc]).abs() <= 0.01
    ).astype(int)

    n_usd = int(df["FLAG_TRX_EN_USD"].sum())
    n_pen = int(df["FLAG_TRX_EN_PEN"].sum())
    n_amb = int(((df["FLAG_TRX_EN_USD"] == 0) & (df["FLAG_TRX_EN_PEN"] == 0)).sum())
    print(f"  Transacciones en USD : {n_usd:,}  ({n_usd/len(df)*100:.1f}%)")
    print(f"  Transacciones en PEN : {n_pen:,}  ({n_pen/len(df)*100:.1f}%)")
    print(f"  Moneda no identificada: {n_amb:,}  ({n_amb/len(df)*100:.1f}%)")
else:
    df["FLAG_TRX_EN_USD"] = 0
    df["FLAG_TRX_EN_PEN"] = 0
    print(f"  ⚠️  '{col_monto_orig}' no encontrada — FLAG_TRX_EN_USD/PEN = 0")

print("  Bloque A2 OK ✅")


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

df["FRANJA_HORARIA"]  = df["HORA_DIA"].map(franja)
df["ES_MADRUGADA"]    = (df["FRANJA_HORARIA"] == "MADRUGADA").astype(int)
df["ES_HORARIO_LAB"]  = ((df["DIA_SEMANA"] < 5) & df["HORA_DIA"].between(8, 17)).astype(int)

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
    df["ES_TARJETA_NO_PRESENTE"] = df[col_em].isin(ENTRY_MODE_NP).astype(int)
else:
    df["TIPO_ENTRADA"]           = "Sin dato"
    df["ES_TARJETA_PRESENTE"]    = 0
    df["ES_TARJETA_NO_PRESENTE"] = 0

if col_moto and col_moto in df.columns:
    df["ES_MOTO"] = df[col_moto].astype(str).str.strip().str.upper().isin(
        {"S", "SI", "1", "TRUE", "Y", "YES", "M"}
    ).astype(int)
else:
    df["ES_MOTO"] = 0

# ES_SEGURO: transacción autenticada con 3DS (ECI 5=Visa seguro, 2=MC seguro)
if col_eci and col_eci in df.columns:
    _eci = df[col_eci].astype(str).str.strip().str.lstrip("0")
    df["ES_SEGURO"] = _eci.isin({"2", "5"}).astype(int)
else:
    df["ES_SEGURO"] = 0

# FLAG_COD_TRX: flags por código de transacción
# 00=compra estándar (mayoría), 10=telefónica/MOTO, 92=reversión/especial
col_cod_trx = C.get("cod_trx", "")
if col_cod_trx and col_cod_trx in df.columns:
    _ct = df[col_cod_trx].astype(str).str.strip().str.zfill(2)
    df["FLAG_COD_TRX_10"] = (_ct == "10").astype(int)
    df["FLAG_COD_TRX_92"] = (_ct == "92").astype(int)
    print(f"  FLAG_COD_TRX_10 : {df['FLAG_COD_TRX_10'].sum():,}")
    print(f"  FLAG_COD_TRX_92 : {df['FLAG_COD_TRX_92'].sum():,}")
else:
    df["FLAG_COD_TRX_10"] = 0
    df["FLAG_COD_TRX_92"] = 0

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

print(f"  ES_FRAUDE: {df['ES_FRAUDE'].sum():,}")
print(f"  Indicador:\n{df[col_ind].value_counts().to_string() if col_ind in df.columns else 'sin col'}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE D — VENTANAS DESLIZANTES POR CLIENTE
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

print(f"  TRX_CLIENTE_5MIN media : {df['TRX_CLIENTE_5MIN'].mean():.2f}")
print(f"  MNT_CLIENTE_24H media  : {df['MNT_CLIENTE_24H'].mean():,.2f}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE E — INTERACCIONES VELOCIDAD × MONTO
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[E] Interacciones velocidad × monto...")

for w in ["5MIN", "10MIN", "1H", "24H"]:
    df[f"MONTO_PROM_{w}"] = (
        df[f"MNT_CLIENTE_{w}"] / df[f"TRX_CLIENTE_{w}"].replace(0, np.nan)
    ).round(2)

df["ACELERACION_MONTO"]    = (df["MONTO_PROM_5MIN"] / df["MONTO_PROM_1H"].replace(0, np.nan)).round(2)
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
        TOTAL_TRX_CLIENTE   = (col_monto, "count"),
        MONTO_TOTAL_CLIENTE = (col_monto, "sum"),
        COMERCIOS_DISTINTOS = (col_com,   "nunique"),
        DIAS_ACTIVO         = ("FECHA_DIA","nunique"),
    ).reset_index()
)
df = df.merge(totales_cli, on=col_cli, how="left")

cli_dia = (
    df.groupby([col_cli, "FECHA_DIA"]).agg(
        TRX_CLIENTE_DIA   = (col_monto, "count"),
        MONTO_CLIENTE_DIA = (col_monto, "sum"),
        COMERCIOS_DIA     = (col_com,   "nunique"),
    ).reset_index()
)
df = df.merge(cli_dia, on=[col_cli, "FECHA_DIA"], how="left")

df["FLAG_REINCIDENTE"]        = (df["TOTAL_TRX_CLIENTE"] > 1).astype(int)
df["FLAG_MULTI_COMERCIO_DIA"] = (df["COMERCIOS_DIA"] > 1).astype(int)
df["FLAG_RAFAGA_DIA"]         = (df["TRX_CLIENTE_DIA"] >= 3).astype(int)
df["FREC_DIARIA_CLIENTE"]     = (df["TOTAL_TRX_CLIENTE"] / df["DIAS_ACTIVO"].replace(0, 1)).round(2)

df_s = df.sort_values([col_cli, col_com, col_fh])
df["_rango_cc"] = df_s.groupby([col_cli, col_com]).cumcount()
df["ES_CLIENTE_NUEVO_COMERCIO"] = (df["_rango_cc"] == 0).astype(int)
df.drop(columns=["_rango_cc"], inplace=True)

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

print(f"  Clientes reincidentes: {df.loc[df['FLAG_REINCIDENTE']==1, col_cli].nunique():,}")


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
        MONTO_TOTAL_COMERCIO  = (col_monto, "sum"),
        MONTO_PROM_COMERCIO   = (col_monto, "mean"),
        CLIENTES_DIST_COMERCIO= (col_cli,   "nunique"),
        DIAS_CON_TRX          = ("FECHA_DIA","nunique"),
        FRAUDES_COMERCIO      = ("ES_FRAUDE","sum"),
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

print(f"  FLAG_PAIS_INUSUAL: {df['FLAG_PAIS_INUSUAL'].sum():,}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE H — SEÑALES DE MONTO
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[H] Señales de monto...")

df["FLAG_MONTO_REDONDO"] = ((df[col_monto] % 50 == 0) & (df[col_monto] >= 50)).astype(int)
df["FLAG_MONTO_BAJO"]    = (df[col_monto] < 20).astype(int)
df["FLAG_MONTO_TEST"]    = (df[col_monto] <= 5).astype(int)   # montos ínfimos típicos de card testing

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

df["RANGO_MONTO"]           = df[col_monto].map(rango_std)
df["RANGO_MONTO_PERCENTIL"] = df[col_monto].map(rango_perc)
df["DECIL_MONTO"] = pd.qcut(df[col_monto], q=10, labels=False, duplicates="drop").astype("Int64") + 1

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

col_musd = C.get("monto_dolar", "")
if col_musd and col_musd in df.columns:
    df["TIPO_CAMBIO"] = (df[col_monto] / df[col_musd].replace(0, np.nan)).round(4)

print(f"  Q25={q25:.2f} | Q50={q50:.2f} | Q75={q75:.2f} | P90={p90:.2f}")
print(f"  FLAG_MONTO_BAJO : {df['FLAG_MONTO_BAJO'].sum():,} | FLAG_MONTO_TEST: {df['FLAG_MONTO_TEST'].sum():,}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE I — CARD TESTING (BIN extendido)
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


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE J — RECHAZOS Y CASCADA CVV
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

print("  FLAGS de reglas configurables generados ✅")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE M — VENTANAS DESLIZANTES POR TARJETA (nuevo)
#  Complementa el bloque D (que es por cliente).
#  En tarjetas comprometidas interesa saber cuántas veces se usa esa tarjeta
#  específica, independientemente del cliente.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[M] Ventanas deslizantes por TARJETA...")

if "TARJETA" in df.columns and df[col_fh].notna().any():
    df = df.sort_values(["TARJETA", col_fh]).reset_index(drop=True)
    df["_ts_t"] = df[col_fh].astype(np.int64) // 10**9

    VENTANAS_TAR = {
        "TRX_TARJETA_5MIN" :  (  5 * 60, "count"),
        "TRX_TARJETA_1H"   :  ( 60 * 60, "count"),
        "TRX_TARJETA_24H"  :  (24 * 3600, "count"),
        "MNT_TARJETA_1H"   :  ( 60 * 60, "sum"),
        "MNT_TARJETA_24H"  :  (24 * 3600, "sum"),
    }

    res_tar = {col: np.zeros(len(df)) for col in VENTANAS_TAR}
    for tarjeta, grupo in df.groupby("TARJETA", sort=False):
        idx = grupo.index.values
        for col, (segs, modo) in VENTANAS_TAR.items():
            vals = calcular_ventana(grupo.rename(columns={"_ts_t": "_ts"}), segs, modo, col_monto)
            res_tar[col][idx] = vals

    for col, vals in res_tar.items():
        df[col] = vals
        df[col] = df[col].round(2) if col.startswith("MNT_") else df[col].astype(int)

    df["GAP_MINUTOS_TARJETA"] = (
        df.groupby("TARJETA")[col_fh].diff().dt.total_seconds() / 60
    ).round(1)

    df["FLAG_TARJETA_RAFAGA_5MIN"] = (df["TRX_TARJETA_5MIN"]  >= 2).astype(int)
    df["FLAG_TARJETA_VEL_ALTA_1H"] = (df["TRX_TARJETA_1H"]   >= 3).astype(int)

    df.drop(columns=["_ts_t"], inplace=True)

    # Total de usos de cada tarjeta en todo el dataset
    uso_tarjeta = df.groupby("TARJETA").agg(
        TOTAL_TRX_TARJETA    = (col_monto, "count"),
        MONTO_TOTAL_TARJETA  = (col_monto, "sum"),
        PAISES_TARJETA       = (col_pais,  "nunique") if col_pais and col_pais in df.columns else (col_monto, "count"),
        DIAS_CON_TRX_TARJETA = ("FECHA_DIA", "nunique"),
    ).reset_index()
    df = df.merge(uso_tarjeta, on="TARJETA", how="left")

    print(f"  TRX_TARJETA_24H media          : {df['TRX_TARJETA_24H'].mean():.2f}")
    print(f"  FLAG_TARJETA_RAFAGA_5MIN       : {df['FLAG_TARJETA_RAFAGA_5MIN'].sum():,}")
else:
    for col in ["TRX_TARJETA_5MIN","TRX_TARJETA_1H","TRX_TARJETA_24H",
                "MNT_TARJETA_1H","MNT_TARJETA_24H","GAP_MINUTOS_TARJETA",
                "FLAG_TARJETA_RAFAGA_5MIN","FLAG_TARJETA_VEL_ALTA_1H",
                "TOTAL_TRX_TARJETA","MONTO_TOTAL_TARJETA","DIAS_CON_TRX_TARJETA"]:
        df[col] = 0
    df["PAISES_TARJETA"] = 0
    print("  TARJETA no disponible — omitiendo bloque M")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE N — FLAGS DE PAÍS Y GEOGRAFÍA (nuevo)
#  Especialmente relevante para tarjetas débito comprometidas:
#  fraude suele ocurrir desde países distintos al habitual del cliente.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[N] Flags de país y geografía...")

if col_pais and col_pais in df.columns:
    # País predominante del CLIENTE (no del comercio)
    pais_cli = (
        df.groupby(col_cli)[col_pais]
        .agg(lambda x: x.mode()[0] if len(x) > 0 else "SIN_DATO")
        .reset_index()
        .rename(columns={col_pais: "PAIS_HABITUAL_CLIENTE"})
    )
    df = df.merge(pais_cli, on=col_cli, how="left")
    df["FLAG_PAIS_DISTINTO_CLIENTE"] = (
        df[col_pais] != df["PAIS_HABITUAL_CLIENTE"]
    ).astype(int)

    # Transacciones en Perú vs extranjero
    df["ES_TRX_PERU"] = df[col_pais].isin({"PE", "PER", "604"}).astype(int)
    df["ES_TRX_EXTRANJERO"] = (df["ES_TRX_PERU"] == 0).astype(int)

    # Diversidad de países en 24h por tarjeta
    if "TARJETA" in df.columns and df[col_fh].notna().any():
        df_tar_pais_24 = df.sort_values(["TARJETA", col_fh]).copy()
        df_tar_pais_24["_ts_np"] = df_tar_pais_24[col_fh].astype(np.int64) // 10**9
        n_paises_24 = np.zeros(len(df_tar_pais_24))
        for tar, g in df_tar_pais_24.groupby("TARJETA", sort=False):
            ts    = g["_ts_np"].values
            pais  = g[col_pais].values
            n     = len(ts)
            for i in range(n):
                j = np.searchsorted(ts, ts[i] - 24*3600, side="left")
                n_paises_24[g.index.values[i]] = len(set(pais[j:i]))
        df_tar_pais_24["N_PAISES_24H_TARJETA"] = n_paises_24.astype(int)
        df_tar_pais_24.drop(columns=["_ts_np"], inplace=True)
        df = df.merge(
            df_tar_pais_24[["TARJETA", col_fh, "N_PAISES_24H_TARJETA"]].drop_duplicates(["TARJETA", col_fh]),
            on=["TARJETA", col_fh], how="left"
        )
        df["N_PAISES_24H_TARJETA"] = df["N_PAISES_24H_TARJETA"].fillna(0).astype(int)
        df["FLAG_MULTI_PAIS_24H"] = (df["N_PAISES_24H_TARJETA"] > 1).astype(int)
    else:
        df["N_PAISES_24H_TARJETA"] = 0
        df["FLAG_MULTI_PAIS_24H"]  = 0

    print(f"  ES_TRX_EXTRANJERO      : {df['ES_TRX_EXTRANJERO'].sum():,}")
    print(f"  FLAG_PAIS_DISTINTO_CLI : {df['FLAG_PAIS_DISTINTO_CLIENTE'].sum():,}")
    print(f"  FLAG_MULTI_PAIS_24H    : {df['FLAG_MULTI_PAIS_24H'].sum():,}")
else:
    for col in ["PAIS_HABITUAL_CLIENTE","FLAG_PAIS_DISTINTO_CLIENTE",
                "ES_TRX_PERU","ES_TRX_EXTRANJERO",
                "N_PAISES_24H_TARJETA","FLAG_MULTI_PAIS_24H"]:
        df[col] = 0
    print("  Columna país no disponible — omitiendo bloque N")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE O — MCC DE ALTO RIESGO Y ENTRY MODE (nuevo)
#  MCC específicos son señal fuerte de fraude en débito comprometido.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[O] MCC de alto riesgo y entry mode...")

if col_mcc and col_mcc in df.columns:
    # Limpiar MCC: quitar el "+" si lo trae
    df["_mcc_clean"] = df[col_mcc].astype(str).str.strip().str.replace("+", "", regex=False)
    df["FLAG_MCC_ALTO_RIESGO"] = df["_mcc_clean"].isin(MCC_ALTO_RIESGO).astype(int)
    # MCC de ATM / adelanto de efectivo
    df["FLAG_MCC_ATM_CASH"] = df["_mcc_clean"].isin({"6011","6012"}).astype(int)
    df.drop(columns=["_mcc_clean"], inplace=True)
    print(f"  FLAG_MCC_ALTO_RIESGO : {df['FLAG_MCC_ALTO_RIESGO'].sum():,}")
    print(f"  FLAG_MCC_ATM_CASH    : {df['FLAG_MCC_ATM_CASH'].sum():,}")
else:
    df["FLAG_MCC_ALTO_RIESGO"] = 0
    df["FLAG_MCC_ATM_CASH"]    = 0

# Flag ecommerce (tarjeta no presente) — crítico para débito comprometido
if col_em and col_em in df.columns:
    df["FLAG_ECOMMERCE"] = df[col_em].isin(ENTRY_MODE_NP).astype(int)
    # Combinación de alto riesgo: ecommerce + madrugada
    df["FLAG_ECOM_MADRUGADA"] = (
        (df["FLAG_ECOMMERCE"] == 1) & (df["ES_MADRUGADA"] == 1)
    ).astype(int)
    # ecommerce + país extranjero
    df["FLAG_ECOM_EXTRANJERO"] = (
        (df["FLAG_ECOMMERCE"] == 1) & (df.get("ES_TRX_EXTRANJERO", pd.Series(0, index=df.index)) == 1)
    ).astype(int)
else:
    df["FLAG_ECOMMERCE"]       = 0
    df["FLAG_ECOM_MADRUGADA"]  = 0
    df["FLAG_ECOM_EXTRANJERO"] = 0

print(f"  FLAG_ECOMMERCE        : {df['FLAG_ECOMMERCE'].sum():,}")
print(f"  FLAG_ECOM_MADRUGADA   : {df['FLAG_ECOM_MADRUGADA'].sum():,}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE P — VÍNCULOS DEL CLIENTE (nuevo)
#  Historial de fraude del cliente, primera transacción, desviación en comercio.
#  Esto es lo que el especialista llama "vínculos" — el comportamiento del cliente
#  a lo largo del tiempo, no solo en la transacción actual.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[P] Vínculos del cliente (multifraude, primera txn, patrón en comercio)...")

if col_ind and col_ind in df.columns:
    # ── Historial de fraudes del cliente en TODO el dataset ───────────────────
    fraude_cli = (
        df.groupby(col_cli)["ES_FRAUDE"]
        .agg(N_FRAUDES_PREVIOS_CLI_TOTAL="sum")
        .reset_index()
    )
    df = df.merge(fraude_cli, on=col_cli, how="left")
    df["N_FRAUDES_PREVIOS_CLI_TOTAL"] = df["N_FRAUDES_PREVIOS_CLI_TOTAL"].fillna(0).astype(int)

    # N_FRAUDES_PREVIOS excluyendo la txn actual (fraudes ANTES de esta)
    df_sorted_cli = df.sort_values([col_cli, col_fh]).copy()
    df["N_FRAUDES_PREVIOS_CLI"] = (
        df_sorted_cli.groupby(col_cli)["ES_FRAUDE"].cumsum() - df_sorted_cli["ES_FRAUDE"]
    ).astype(int)

    df["FLAG_CLIENTE_MULTIFRAUDE"] = (df["N_FRAUDES_PREVIOS_CLI"] >= 2).astype(int)
    df["FLAG_CLIENTE_YA_FRAUDULENTO"] = (df["N_FRAUDES_PREVIOS_CLI"] >= 1).astype(int)

    # Días desde el último fraude del mismo cliente (hacia atrás)
    df_f_cli = df[df["ES_FRAUDE"] == 1][[col_cli, col_fh]].rename(columns={col_fh: "_t_fraude"})
    df = df.merge(df_f_cli, on=col_cli, how="left")
    df["_delta_fraude"] = (df[col_fh] - df["_t_fraude"]).dt.days
    df = df[df["_delta_fraude"].isna() | (df["_delta_fraude"] > 0)]  # solo fraudes anteriores
    df["DIAS_DESDE_ULT_FRAUDE_CLI"] = (
        df.groupby([col_cli, col_fh])["_delta_fraude"].transform("min")
    )
    df.drop(columns=["_t_fraude", "_delta_fraude"], inplace=True)
    df = df.drop_duplicates(subset=[col_cli, col_fh] if col_fh in df.columns else [col_cli]).reset_index(drop=True)

    print(f"  Clientes con fraude previo : {df['FLAG_CLIENTE_YA_FRAUDULENTO'].sum():,}")
    print(f"  FLAG_CLIENTE_MULTIFRAUDE   : {df['FLAG_CLIENTE_MULTIFRAUDE'].sum():,}")
else:
    df["N_FRAUDES_PREVIOS_CLI"]       = 0
    df["N_FRAUDES_PREVIOS_CLI_TOTAL"] = 0
    df["FLAG_CLIENTE_MULTIFRAUDE"]    = 0
    df["FLAG_CLIENTE_YA_FRAUDULENTO"] = 0
    df["DIAS_DESDE_ULT_FRAUDE_CLI"]   = np.nan

# ── Primera transacción del cliente en TODO el dataset ────────────────────────
df_sorted_p = df.sort_values([col_cli, col_fh])
df["FLAG_PRIMERA_TRX_CLI_TOTAL"] = (
    df_sorted_p.groupby(col_cli).cumcount() == 0
).astype(int)

# ── Ratio txn del día vs promedio histórico diario del cliente ────────────────
# FREC_DIARIA_CLIENTE ya existe (total txn / días activos)
# TRX_CLIENTE_DIA ya existe (txn hoy)
if "TRX_CLIENTE_DIA" in df.columns and "FREC_DIARIA_CLIENTE" in df.columns:
    df["RATIO_TRX_DIA_VS_HIST"] = (
        df["TRX_CLIENTE_DIA"] / df["FREC_DIARIA_CLIENTE"].replace(0, np.nan)
    ).round(2)
    df["FLAG_TRX_DIA_ANOMALA"] = (df["RATIO_TRX_DIA_VS_HIST"] >= 2).astype(int)
    print(f"  FLAG_TRX_DIA_ANOMALA       : {df['FLAG_TRX_DIA_ANOMALA'].sum():,} txn")
else:
    df["RATIO_TRX_DIA_VS_HIST"] = np.nan
    df["FLAG_TRX_DIA_ANOMALA"]  = 0

# ── Z-score del monto del cliente en ESE comercio específico ─────────────────
# (diferente al ZSCORE_MONTO_CLIENTE que es vs todo el historial)
df["_mean_cc"] = df.groupby([col_cli, col_com])[col_monto].transform("mean")
df["_std_cc"]  = df.groupby([col_cli, col_com])[col_monto].transform("std").fillna(1).replace(0, 1)
df["ZSCORE_MONTO_CLI_COMERCIO"]    = ((df[col_monto] - df["_mean_cc"]) / df["_std_cc"]).round(3)
df["FLAG_MONTO_ALTO_CLI_COMERCIO"] = (df["ZSCORE_MONTO_CLI_COMERCIO"] >= 2).astype(int)
df.drop(columns=["_mean_cc", "_std_cc"], inplace=True)

# ── Ticket promedio del cliente en ese comercio ───────────────────────────────
monto_prom_cc = (
    df.groupby([col_cli, col_com])[col_monto]
    .mean().reset_index()
    .rename(columns={col_monto: "MONTO_PROM_CLI_COMERCIO"})
)
df = df.merge(monto_prom_cc, on=[col_cli, col_com], how="left")
df["RATIO_MONTO_VS_CLI_COMERCIO"] = (
    df[col_monto] / df["MONTO_PROM_CLI_COMERCIO"].replace(0, np.nan)
).round(2)

print(f"  FLAG_MONTO_ALTO_CLI_COMERCIO: {df['FLAG_MONTO_ALTO_CLI_COMERCIO'].sum():,}")
print("  Bloque P OK ✅")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE Q — SCORE DE MARCA (TC — Visa 0-99 / Mastercard 0-999)  (nuevo)
#  El score de marca solo llega para tarjeta de crédito.
#  Visa: 0-99 | Mastercard: 0-999 → normalizar a 0-1 para comparar.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[Q] Score de marca (TC — Visa 0-99 / MC 0-999)...")

col_score_mon = C.get("score_riesgo_mon", "")
col_tp        = C.get("tipo_producto", "")

if col_score_mon and col_score_mon in df.columns:
    df[col_score_mon] = pd.to_numeric(df[col_score_mon], errors="coerce")

    # Solo aplica a TC (crédito)
    es_tc = (df[col_tp].str.upper() == "TC") if col_tp and col_tp in df.columns else pd.Series(False, index=df.index)

    # Normalizar por marca: Visa 0-99 → /99; Mastercard 0-999 → /999
    df["SCORE_NORMALIZADO"] = np.nan
    mask_visa = es_tc & (df["MARCA_TARJETA"] == "VISA")
    mask_mc   = es_tc & (df["MARCA_TARJETA"] == "MASTERCARD")
    df.loc[mask_visa, "SCORE_NORMALIZADO"] = (df.loc[mask_visa, col_score_mon] / 99).clip(0, 1).round(4)
    df.loc[mask_mc,   "SCORE_NORMALIZADO"] = (df.loc[mask_mc,   col_score_mon] / 999).clip(0, 1).round(4)

    # Score alto = riesgo alto (marca considera esta txn sospechosa)
    df["FLAG_SCORE_ALTO_TC"] = (
        es_tc & (df["SCORE_NORMALIZADO"] >= 0.70)
    ).astype(int)

    # Para TD: usamos SCORE_RIESGO propio — se calculará en Bloque L
    df["ES_TC"] = es_tc.astype(int)
    df["ES_TD"] = (~es_tc).astype(int)

    n_con_score = df.loc[es_tc, "SCORE_NORMALIZADO"].notna().sum()
    print(f"  TC con score de marca      : {n_con_score:,}")
    print(f"  FLAG_SCORE_ALTO_TC         : {df['FLAG_SCORE_ALTO_TC'].sum():,}")
    print(f"  Score norm Visa — media    : {df.loc[mask_visa,'SCORE_NORMALIZADO'].mean():.3f}")
    print(f"  Score norm MC   — media    : {df.loc[mask_mc,  'SCORE_NORMALIZADO'].mean():.3f}")
else:
    df["SCORE_NORMALIZADO"] = np.nan
    df["FLAG_SCORE_ALTO_TC"] = 0
    df["ES_TC"] = 0
    df["ES_TD"] = 0
    print(f"  Columna score '{col_score_mon}' no encontrada — omitiendo bloque Q")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE R — COMPORTAMIENTO DEL CLIENTE EN EL COMERCIO  (nuevo)
#  Un cliente que se desvía del patrón habitual de ESE comercio es sospechoso.
#  Ej: el comercio tiene ticket promedio S/50 y este cliente paga S/500.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[R] Comportamiento del cliente vs perfil del comercio...")

# ── ¿Es outlier este cliente en este comercio? ────────────────────────────────
# Compara las txn del cliente en ese comercio vs el promedio de TODOS los clientes
# en ese comercio (ya calculado en MONTO_PROM_COMERCIO y CLIENTES_DIST_COMERCIO)

if "MONTO_PROM_COMERCIO" in df.columns:
    df["RATIO_TICKET_CLI_VS_COMERCIO"] = (
        df["MONTO_PROM_CLI_COMERCIO"] / df["MONTO_PROM_COMERCIO"].replace(0, np.nan)
    ).round(2)
    df["FLAG_CLI_OUTLIER_TICKET_COMERCIO"] = (df["RATIO_TICKET_CLI_VS_COMERCIO"] >= 3).astype(int)
else:
    df["RATIO_TICKET_CLI_VS_COMERCIO"]     = np.nan
    df["FLAG_CLI_OUTLIER_TICKET_COMERCIO"] = 0

# ── ¿Este cliente hace más txn que el promedio del comercio? ─────────────────
# FREC_DIARIA_CLIENTE = txn del cliente por día (su propio promedio)
# TRX_COMERCIO_DIA    = txn totales en ese comercio ese día
# promedio_cli_en_comercio = TRX_COMERCIO_DIA / CLIENTES_DIST_COMERCIO

if "TRX_COMERCIO_DIA" in df.columns and "CLIENTES_DIST_COMERCIO" in df.columns:
    df["PROM_TRX_CLI_DIA_COMERCIO"] = (
        df["TRX_COMERCIO_DIA"] / df["CLIENTES_DIST_COMERCIO"].replace(0, np.nan)
    ).round(2)
    df["RATIO_TRX_CLI_VS_PROM_COMERCIO"] = (
        df["TRX_CLIENTE_DIA"] / df["PROM_TRX_CLI_DIA_COMERCIO"].replace(0, np.nan)
    ).round(2)
    df["FLAG_CLI_OUTLIER_VELOCIDAD_COMERCIO"] = (
        df["RATIO_TRX_CLI_VS_PROM_COMERCIO"] >= 3
    ).astype(int)
else:
    df["PROM_TRX_CLI_DIA_COMERCIO"]           = np.nan
    df["RATIO_TRX_CLI_VS_PROM_COMERCIO"]      = np.nan
    df["FLAG_CLI_OUTLIER_VELOCIDAD_COMERCIO"] = 0

print(f"  FLAG_CLI_OUTLIER_TICKET_COMERCIO   : {df['FLAG_CLI_OUTLIER_TICKET_COMERCIO'].sum():,}")
print(f"  FLAG_CLI_OUTLIER_VELOCIDAD_COMERCIO: {df['FLAG_CLI_OUTLIER_VELOCIDAD_COMERCIO'].sum():,}")
print("  Bloque R OK ✅")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE L (reordenado) — SCORE DE RIESGO COMPUESTO
#  Se calcula al final para incluir todos los flags nuevos
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[L] Score de riesgo compuesto...")

componentes_base = [
    "FLAG_RAFAGA_5MIN",
    "FLAG_VEL_ALTA_1H",
    "HUBO_FRAUDE_PREVIO_24H",
    "HUBO_CVV_FAIL_PREVIO",
    "FLAG_MONTO_REDONDO",
    "ES_MADRUGADA",
    "FLAG_REINCIDENTE",
    "FLAG_PAIS_INUSUAL",
    "FLAG_BIN12_REPETIDO_DIA",
]

componentes_nuevos = [
    # Bloque M — velocidad por tarjeta
    "FLAG_TARJETA_RAFAGA_5MIN",
    "FLAG_TARJETA_VEL_ALTA_1H",
    # Bloque N — país
    "FLAG_PAIS_DISTINTO_CLIENTE",
    "FLAG_MULTI_PAIS_24H",
    # Bloque O — MCC / entry mode
    "FLAG_MCC_ALTO_RIESGO",
    "FLAG_ECOM_MADRUGADA",
    "FLAG_ECOM_EXTRANJERO",
    "FLAG_MONTO_TEST",
    # Bloque P — vínculos del cliente
    "FLAG_CLIENTE_YA_FRAUDULENTO",
    "FLAG_CLIENTE_MULTIFRAUDE",
    "FLAG_PRIMERA_TRX_CLI_TOTAL",
    "FLAG_TRX_DIA_ANOMALA",
    "FLAG_MONTO_ALTO_CLI_COMERCIO",
    # Bloque Q — score marca TC
    "FLAG_SCORE_ALTO_TC",
    # Bloque R — outlier en comercio
    "FLAG_CLI_OUTLIER_TICKET_COMERCIO",
    "FLAG_CLI_OUTLIER_VELOCIDAD_COMERCIO",
]

todos_componentes = componentes_base + componentes_nuevos
componentes_validos = [c for c in todos_componentes if c in df.columns]

df["SCORE_RIESGO"] = sum(
    df[c].fillna(0).astype(int) for c in componentes_validos
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
print(f"  Componentes del score ({len(componentes_validos)}): {componentes_validos}")


# ═══════════════════════════════════════════════════════════════════════════════
#  RESUMEN DE VARIABLES GENERADAS
# ═══════════════════════════════════════════════════════════════════════════════
VARS_GENERADAS = [
    # Temporales
    "HORA_DIA","DIA_SEMANA_NOM","ES_FIN_SEMANA","FRANJA_HORARIA","ES_MADRUGADA",
    "ES_HORARIO_LAB","QUINCENA","SEMANA_ISO","ES_FERIADO","ES_FECHA_ESPECIAL",
    "NOMBRE_FECHA_ESP","ES_DIA_PAGO",
    # Clasificación
    "ESTADO","ES_FRAUDE","ES_FRAUDE_APROBADO","INDICADOR_TEXTO","SEGURO",
    "MARCA_TARJETA","TIPO_PRODUCTO_TEXTO","ES_TOKENIZADA","BILLETERA_NOMBRE",
    "TIPO_ENTRADA","ES_TARJETA_PRESENTE","ES_TARJETA_NO_PRESENTE","ES_MOTO",
    "SEG_NOMBRE","SEG_GRUPO","ORG_NOMBRE","TIPO_CVV","MOTIVO_RECHAZO","ES_CODIGO_CRITICO",
    # Ventanas por cliente (D)
    "TRX_CLIENTE_2MIN","TRX_CLIENTE_5MIN","TRX_CLIENTE_10MIN","TRX_CLIENTE_1H","TRX_CLIENTE_24H",
    "MNT_CLIENTE_2MIN","MNT_CLIENTE_5MIN","MNT_CLIENTE_10MIN","MNT_CLIENTE_1H","MNT_CLIENTE_24H",
    "GAP_MINUTOS","FLAG_RAFAGA_5MIN","FLAG_RAFAGA_10MIN","FLAG_VEL_ALTA_1H","FLAG_ACUM_ALTO_1H",
    # Interacciones (E)
    "MONTO_PROM_5MIN","MONTO_PROM_10MIN","MONTO_PROM_1H","MONTO_PROM_24H",
    "ACELERACION_MONTO","CONCENTRACION_5MIN_1H","ZSCORE_MONTO_CLIENTE","RATIO_MONTO_VS_HIST_CLIENTE",
    # Perfil cliente (F)
    "TOTAL_TRX_CLIENTE","MONTO_TOTAL_CLIENTE","COMERCIOS_DISTINTOS","DIAS_ACTIVO",
    "TRX_CLIENTE_DIA","MONTO_CLIENTE_DIA","COMERCIOS_DIA",
    "FLAG_REINCIDENTE","FLAG_MULTI_COMERCIO_DIA","FLAG_RAFAGA_DIA",
    "FREC_DIARIA_CLIENTE","ES_CLIENTE_NUEVO_COMERCIO","DIAS_DESDE_ULT_TRX_COMERCIO",
    "RATIO_MONTO_VS_SALDO","FLAG_SALDO_AGOTADO",
    # Perfil comercio (G)
    "CATEGORIA_COMERCIO","ES_COMERCIO_NUEVO",
    "TOTAL_TRX_COMERCIO","MONTO_TOTAL_COMERCIO","MONTO_PROM_COMERCIO",
    "CLIENTES_DIST_COMERCIO","DIAS_CON_TRX","TASA_FRAUDE_COMERCIO",
    "TRX_COMERCIO_DIA","RANKING_COMERCIO",
    "DESVIO_MONTO_VS_COMERCIO","RATIO_MONTO_VS_COMERCIO",
    "PAIS_PREDOMINANTE_COMERCIO","FLAG_PAIS_INUSUAL",
    "TOTAL_TRX_MCC","RANKING_MCC",
    # Señales monto (H)
    "FLAG_MONTO_REDONDO","FLAG_MONTO_BAJO","FLAG_MONTO_TEST","ZSCORE_MONTO_COMERCIO",
    "RANGO_MONTO","RANGO_MONTO_PERCENTIL","RANGO_MONTO_ARBOL","DECIL_MONTO",
    # Card testing (I)
    "TARJETAS_MISMO_BIN12_DIA","FLAG_BIN12_REPETIDO_DIA",
    # Rechazos (J)
    "N_RECHAZOS_24H","N_CVV_FAIL_24H","HUBO_CVV_FAIL_PREVIO",
    "HUBO_FRAUDE_PREVIO_24H","PREV_FUE_FRAUDE","MIN_DESDE_ULTIMO_FRAUDE",
    # Ventanas por tarjeta (M) — NUEVO
    "TRX_TARJETA_5MIN","TRX_TARJETA_1H","TRX_TARJETA_24H",
    "MNT_TARJETA_1H","MNT_TARJETA_24H","GAP_MINUTOS_TARJETA",
    "FLAG_TARJETA_RAFAGA_5MIN","FLAG_TARJETA_VEL_ALTA_1H",
    "TOTAL_TRX_TARJETA","MONTO_TOTAL_TARJETA","PAISES_TARJETA","DIAS_CON_TRX_TARJETA",
    # País y geografía (N) — NUEVO
    "PAIS_HABITUAL_CLIENTE","FLAG_PAIS_DISTINTO_CLIENTE",
    "ES_TRX_PERU","ES_TRX_EXTRANJERO",
    "N_PAISES_24H_TARJETA","FLAG_MULTI_PAIS_24H",
    # MCC y entry mode (O) — NUEVO
    "FLAG_MCC_ALTO_RIESGO","FLAG_MCC_ATM_CASH",
    "FLAG_ECOMMERCE","FLAG_ECOM_MADRUGADA","FLAG_ECOM_EXTRANJERO",
    # Vínculos del cliente (P) — NUEVO
    "N_FRAUDES_PREVIOS_CLI","N_FRAUDES_PREVIOS_CLI_TOTAL",
    "FLAG_CLIENTE_YA_FRAUDULENTO","FLAG_CLIENTE_MULTIFRAUDE",
    "DIAS_DESDE_ULT_FRAUDE_CLI",
    "FLAG_PRIMERA_TRX_CLI_TOTAL",
    "RATIO_TRX_DIA_VS_HIST","FLAG_TRX_DIA_ANOMALA",
    "ZSCORE_MONTO_CLI_COMERCIO","FLAG_MONTO_ALTO_CLI_COMERCIO",
    "MONTO_PROM_CLI_COMERCIO","RATIO_MONTO_VS_CLI_COMERCIO",
    # Score de marca TC (Q) — NUEVO
    "SCORE_NORMALIZADO","FLAG_SCORE_ALTO_TC","ES_TC","ES_TD",
    # Outlier en comercio (R) — NUEVO
    "RATIO_TICKET_CLI_VS_COMERCIO","FLAG_CLI_OUTLIER_TICKET_COMERCIO",
    "PROM_TRX_CLI_DIA_COMERCIO","RATIO_TRX_CLI_VS_PROM_COMERCIO","FLAG_CLI_OUTLIER_VELOCIDAD_COMERCIO",
    # Score (L)
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
