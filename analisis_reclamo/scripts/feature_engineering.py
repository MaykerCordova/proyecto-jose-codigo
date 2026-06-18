"""
feature_engineering.py — Ingeniería de Variables para Análisis de Reclamos
Base 8850 / Master File — Scotiabank Peru — Prevención de Fraude

Lee data/reclamos_raw.parquet y genera ~60 variables nuevas.
IMPORTANTE: toda la data es fraude confirmado (no hay variable objetivo binaria).
El análisis es de perfilamiento y clustering, no de clasificación.

Bloques:
  A  Carga y validación
  B  Variables temporales          → cuándo ocurrió la txn y cuándo se reclamó
  C  Clasificación de la txn       → producto, canal, billetera, seguridad
  D  Variables de reclamo          → DIAS_HASTA_RECLAMO, BUCKET_RECLAMO, flags tardío/rápido
  E  BIN extendido                 → BIN10/11/12 desde columnas TARJETA + concentración BIN
  F  Señales de monto              → redondo, decil, rango, ratio vs patrón cliente
  G  Velocidad y concentración     → N_RECLAMOS_CLIENTE, rafagas por BIN, GAP_MINUTOS
  H  Perfil del cliente            → multi-reclamo, patrón histórico, saldo
  I  MCC y tipo de comercio        → categoría MCC, comercio Google, canal físico/digital
  J  Señales de autofraud          → composite de reclamo tardío + comercio + monto
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
    COLS, PARQUET_RAW, PARQUET_FEATURES, SEGMENTO_FOCO,
    PERIODO_INICIO, PERIODO_FIN, FECHA_DAYFIRST,
    MARCAR_PERIODO_GOOGLE, GOOGLE_INICIO, GOOGLE_FIN,
    UMBRAL_RECLAMO_TARDIO_DIAS, UMBRAL_RECLAMO_RAPIDO_DIAS,
    UMBRAL_MICROPAGO_MONTO, PAISES_PERU,
    ENTRY_MODE_LABEL, ENTRY_MODE_PRESENTE,
    MARCA_LABEL, TIPO_PROD_LABEL, FILTRO_MARCA,
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


ruta_entrada = Path(sys.argv[1]) if len(sys.argv) > 1 else PARQUET_RAW

print("═" * 65)
print(f"FEATURE ENGINEERING — ANÁLISIS DE RECLAMOS")
print(f"  Segmento foco : {SEGMENTO_FOCO}")
print(f"  Período       : {PERIODO_INICIO} → {PERIODO_FIN}")
print("═" * 65)

df = leer_parquet(str(ruta_entrada))

# Reportar columnas faltantes
cols_reales = set(df.columns)
faltantes   = {k: v for k, v in C.items() if v and v not in cols_reales}
if faltantes:
    print("\n⚠️  COLUMNAS NO ENCONTRADAS (variables dependientes se omiten):")
    for k, v in faltantes.items():
        print(f"   COLS['{k}'] = '{v}'  ← no existe en parquet")

# Castear montos
for col_key in ["monto", "monto_dolar", "monto_original"]:
    col_val = C.get(col_key, "")
    if col_val and col_val in df.columns:
        df[col_val] = (
            df[col_val].astype(str).str.strip()
            .str.replace(",", ".", regex=False)
            .str.replace(" ", "", regex=False)
        )
        df[col_val] = pd.to_numeric(df[col_val], errors="coerce")

# Referencias a columnas críticas
col_fh       = C["fecha_hora"]
col_monto    = C["monto"]
col_cli      = C["id_cliente"]
col_com      = C["comercio_nom"]
col_bin      = C.get("bin", "")
col_fec_txn  = C.get("fecha_txn", "")
col_hora_txn = C.get("hora_txn", "")
col_fec_rec  = C.get("fecha_reclamo", "")

# Construir FECHA_HORA si no existe en el parquet
# hora_txn llega como "01/01/1900 12:51:45" — extraer solo HH:MM:SS
if col_fh not in df.columns:
    if col_fec_txn in df.columns and col_hora_txn in df.columns:
        hora_str = (
            df[col_hora_txn].astype(str).str.strip()
            .str.extract(r'(\d{1,2}:\d{2}:\d{2})')[0]
            .fillna("00:00:00")
        )
        df[col_fh] = pd.to_datetime(
            df[col_fec_txn].astype(str).str.strip() + " " + hora_str,
            dayfirst=FECHA_DAYFIRST,
            errors="coerce"
        )
        print(f"  ✅ {col_fh} construida desde {col_fec_txn} + {col_hora_txn}")
    else:
        print(f"⚠️  '{col_fh}' no encontrada — continuando sin fechas completas")
        df[col_fh] = pd.NaT
else:
    df[col_fh] = pd.to_datetime(df[col_fh], errors="coerce")

# Parsear fecha_reclamo (también en formato dd/mm/yyyy)
if col_fec_rec and col_fec_rec in df.columns:
    df[col_fec_rec] = pd.to_datetime(df[col_fec_rec], dayfirst=FECHA_DAYFIRST, errors="coerce")

# Ordenar cronológicamente para ventanas deslizantes
if df[col_fh].notna().any():
    df = df.sort_values(col_fh).reset_index(drop=True)

# Fallbacks para columnas críticas
for col_key, col_val, default in [
    (col_cli,   col_cli,   None),
    (col_com,   col_com,   "SIN_COMERCIO"),
    (col_monto, col_monto, 0.0),
]:
    if col_val not in df.columns:
        if default is None:
            df[col_val] = df.index.astype(str)
            print(f"⚠️  '{col_val}' no encontrado — usando índice como id_cliente")
        else:
            df[col_val] = default
            print(f"⚠️  '{col_val}' no encontrado — usando '{default}'")

print(f"\n  Filas            : {len(df):,}")
print(f"  Clientes únicos  : {df[col_cli].nunique():,}")
print(f"  Comercios únicos : {df[col_com].nunique():,}")
print(f"  Monto total (S/) : {df[col_monto].sum():,.2f}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE B — VARIABLES TEMPORALES
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[B] Variables temporales...")

df["HORA_DIA"]       = df[col_fh].dt.hour
df["DIA_SEMANA"]     = df[col_fh].dt.dayofweek
df["DIA_SEMANA_NOM"] = df[col_fh].dt.strftime("%a").str.upper()
df["MES_TXN"]        = df[col_fh].dt.month
df["MES_NOM"]        = df[col_fh].dt.strftime("%b").str.upper()
df["ANIO"]           = df[col_fh].dt.year
df["MES_ANIO"]       = df[col_fh].dt.to_period("M").astype(str)
df["TRIMESTRE"]      = "Q" + df[col_fh].dt.quarter.astype(str)
df["FECHA_DIA"]      = df[col_fh].dt.normalize()
df["ES_FIN_SEMANA"]  = (df["DIA_SEMANA"] >= 5).astype(int)

_FRANJAS = [(0,6,"MADRUGADA"),(6,12,"MANANA"),(12,19,"TARDE"),(19,24,"NOCHE")]
def franja(h):
    for ini, fin, nom in _FRANJAS:
        if ini <= h < fin:
            return nom
    return "NOCHE"

df["FRANJA_HORARIA"] = df["HORA_DIA"].map(franja)
df["ES_MADRUGADA"]   = (df["FRANJA_HORARIA"] == "MADRUGADA").astype(int)
df["ES_HORARIO_LAB"] = ((df["DIA_SEMANA"] < 5) & df["HORA_DIA"].between(8, 17)).astype(int)

# Período de ataque Google (ene-feb 2026)
if MARCAR_PERIODO_GOOGLE:
    df["ES_PERIODO_GOOGLE"] = (
        df["FECHA_DIA"].between(pd.Timestamp(GOOGLE_INICIO), pd.Timestamp(GOOGLE_FIN))
    ).astype(int)
    print(f"  ES_PERIODO_GOOGLE (ene-feb 2026): {df['ES_PERIODO_GOOGLE'].sum():,} txn")
else:
    df["ES_PERIODO_GOOGLE"] = 0

print(f"  FRANJA_HORARIA:\n{df['FRANJA_HORARIA'].value_counts().to_string()}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE C — CLASIFICACIÓN DE LA TRANSACCIÓN
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[C] Clasificación de la transacción...")

col_eci       = C.get("eci", "")
col_marca     = C.get("marca", "")
col_em        = C.get("entry_mode", "")
col_moto      = C.get("ind_recurrente", "")
col_seg       = C.get("segmento", "")
col_tp        = C.get("tipo_producto", "")
col_cvvr      = C.get("cod_red_comercio", "")
col_canal     = C.get("canal", "")
col_adq       = C.get("tipo_adquiriente", "")
col_micropago = C.get("tipo_micropago", "")

# Marca de la tarjeta
if col_marca and col_marca in df.columns:
    df["MARCA_TARJETA"] = df[col_marca].astype(str).str.strip().str[:1].map(MARCA_LABEL).fillna("OTRA")
else:
    df["MARCA_TARJETA"] = "DESCONOCIDA"
    print("  ⚠️  marca no encontrada — MARCA_TARJETA = DESCONOCIDA")

# Tipo de producto (TC/TD)
if col_tp and col_tp in df.columns:
    df["TIPO_PRODUCTO_TEXTO"] = df[col_tp].astype(str).str.strip().map(TIPO_PROD_LABEL).fillna(df[col_tp])
else:
    df["TIPO_PRODUCTO_TEXTO"] = "Sin dato"

# Seguridad 3DS
CODIGOS_SEGURO = {"2", "02", "5", "05"}
if col_eci and col_eci in df.columns:
    df["ES_SEGURO_3DS"] = df[col_eci].astype(str).str.strip().isin(CODIGOS_SEGURO).astype(int)
else:
    df["ES_SEGURO_3DS"] = 0

# Entry mode (modo de ingreso de tarjeta)
if col_em and col_em in df.columns:
    df["TIPO_ENTRADA"]        = df[col_em].astype(str).str.strip().map(ENTRY_MODE_LABEL).fillna(df[col_em])
    df["ES_TARJETA_PRESENTE"] = df[col_em].astype(str).str.strip().isin(ENTRY_MODE_PRESENTE).astype(int)
else:
    df["TIPO_ENTRADA"]        = "Sin dato"
    df["ES_TARJETA_PRESENTE"] = 0

# Recurrente / MOTO
if col_moto and col_moto in df.columns:
    _ind = df[col_moto].astype(str).str.strip().str.upper()
    df["ES_RECURRENTE"] = (_ind == "R").astype(int)
    df["ES_MOTO"]       = _ind.isin({"M", "O", "T"}).astype(int)
else:
    df["ES_RECURRENTE"] = 0
    df["ES_MOTO"]       = 0

# Tipo CVV
COD_RED_LABEL = {"S": "CVV Estático", "D": "CVV Dinámico", "E": "Sin CVV (ecomm)", "N": "Sin CVV (presencial)"}
if col_cvvr and col_cvvr in df.columns:
    df["TIPO_CVV"] = df[col_cvvr].astype(str).str.strip().map(COD_RED_LABEL).fillna("Otro")
else:
    df["TIPO_CVV"] = "Sin dato"

# Segmento — viene como texto directamente, sin mapeo de diccionario
if col_seg and col_seg in df.columns:
    df["SEG_NOMBRE"] = df[col_seg].astype(str).str.strip().replace("nan", "Sin dato")
else:
    df["SEG_NOMBRE"] = "Sin dato"

# Canal
CANAL_LABEL = {
    "POS": "POS Fisico", "ATM": "Cajero ATM", "CNP": "Card Not Present",
    "ECO": "Ecommerce", "MOB": "Mobile", "CTL": "Contactless",
}
if col_canal and col_canal in df.columns:
    df["CANAL_TEXTO"]      = df[col_canal].astype(str).str.strip().map(CANAL_LABEL).fillna(df[col_canal])
    df["ES_ATM"]           = df[col_canal].astype(str).str.strip().str.upper().isin({"ATM"}).astype(int)
    df["ES_CANAL_FISICO"]  = df[col_canal].astype(str).str.strip().str.upper().isin({"POS", "ATM", "CTL"}).astype(int)
    df["ES_CANAL_DIGITAL"] = df[col_canal].astype(str).str.strip().str.upper().isin({"CNP", "ECO", "MOB"}).astype(int)
else:
    df["CANAL_TEXTO"]      = "Sin dato"
    df["ES_ATM"]           = 0
    df["ES_CANAL_FISICO"]  = df["ES_TARJETA_PRESENTE"]
    df["ES_CANAL_DIGITAL"] = (1 - df["ES_TARJETA_PRESENTE"])

# País — viene como nombre completo (ej: "PERU", "ESTADOS UNIDOS")
col_pais = C.get("pais", "")
if col_pais and col_pais in df.columns:
    df["ES_INTERNACIONAL"] = (
        ~df[col_pais].astype(str).str.strip().str.upper().isin(PAISES_PERU)
    ).astype(int)
else:
    df["ES_INTERNACIONAL"] = 0

# Tipo adquiriente (Niubiz, Izipay, Culqi, etc.)
if col_adq and col_adq in df.columns:
    df["ADQUIRIENTE"] = df[col_adq].astype(str).str.strip().str.upper()
    print(f"  ADQUIRIENTE: {df['ADQUIRIENTE'].value_counts().head(6).to_dict()}")
else:
    df["ADQUIRIENTE"] = "Sin dato"

# Micropago — viene como texto: "MICROPAGO" | "NO MICROPAGO"
if col_micropago and col_micropago in df.columns:
    df["ES_MICROPAGO"] = (
        df[col_micropago].astype(str).str.strip().str.upper() == "MICROPAGO"
    ).astype(int)
    print(f"  ES_MICROPAGO: {df['ES_MICROPAGO'].sum():,} txn ({df['ES_MICROPAGO'].mean()*100:.1f}%)")
else:
    # Derivar desde monto si no existe la columna
    df["ES_MICROPAGO"] = (df[col_monto] <= UMBRAL_MICROPAGO_MONTO).astype(int)
    print(f"  ES_MICROPAGO (derivado ≤S/{UMBRAL_MICROPAGO_MONTO}): {df['ES_MICROPAGO'].sum():,} txn")

print(f"  MARCA_TARJETA      : {df['MARCA_TARJETA'].value_counts().to_dict()}")
print(f"  ES_TARJETA_PRESENTE: {df['ES_TARJETA_PRESENTE'].sum():,}")
print(f"  ES_INTERNACIONAL   : {df['ES_INTERNACIONAL'].sum():,}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE D — VARIABLES DE RECLAMO
#  Las más importantes de esta base: CUÁNDO reclamó el cliente y QUÉ implica.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[D] Variables de reclamo...")

if col_fec_rec and col_fec_rec in df.columns and df[col_fec_rec].notna().any():
    # Días entre la txn y el reclamo
    df["DIAS_HASTA_RECLAMO"] = (df[col_fec_rec] - df[col_fh]).dt.days

    # Filtrar valores negativos o extremos (error de datos)
    df.loc[df["DIAS_HASTA_RECLAMO"] < 0, "DIAS_HASTA_RECLAMO"] = np.nan
    df.loc[df["DIAS_HASTA_RECLAMO"] > 730, "DIAS_HASTA_RECLAMO"] = np.nan  # >2 años = error

    df["SEMANAS_HASTA_RECLAMO"] = (df["DIAS_HASTA_RECLAMO"] / 7).round(1)
    df["MES_RECLAMO"]           = df[col_fec_rec].dt.month
    df["MES_ANIO_RECLAMO"]      = df[col_fec_rec].dt.to_period("M").astype(str)

    # FLAG_SIN_FECHA_RECLAMO: filas donde fecha_reclamo estaba vacía
    # (~1475 casos) — se mantienen en el dataset, solo se marcan
    df["FLAG_SIN_FECHA_RECLAMO"] = df[col_fec_rec].isna().astype(int)

    # BUCKET_RECLAMO: categoría del tiempo de demora
    def bucket_reclamo(dias):
        if pd.isna(dias):       return "SIN_DATO"
        if dias <= 3:           return "INMEDIATO"
        if dias <= 7:           return "RAPIDO"
        if dias <= 60:          return "NORMAL"
        if dias <= 90:          return "TARDIO"
        return "MUY_TARDIO"

    df["BUCKET_RECLAMO"]      = df["DIAS_HASTA_RECLAMO"].map(bucket_reclamo)
    df["FLAG_RECLAMO_RAPIDO"] = (df["DIAS_HASTA_RECLAMO"] <= UMBRAL_RECLAMO_RAPIDO_DIAS).astype(int)
    df["FLAG_RECLAMO_TARDIO"] = (df["DIAS_HASTA_RECLAMO"] >  UMBRAL_RECLAMO_TARDIO_DIAS).astype(int)

    dias_validos = df["DIAS_HASTA_RECLAMO"].dropna()
    print(f"  FLAG_SIN_FECHA_RECLAMO  : {df['FLAG_SIN_FECHA_RECLAMO'].sum():,} txn sin fecha de reclamo")
    print(f"  DIAS_HASTA_RECLAMO — mediana: {dias_validos.median():.0f}d  "
          f"P90: {dias_validos.quantile(0.9):.0f}d  max: {dias_validos.max():.0f}d")
    print(f"  FLAG_RECLAMO_RAPIDO (≤{UMBRAL_RECLAMO_RAPIDO_DIAS}d): {df['FLAG_RECLAMO_RAPIDO'].sum():,}")
    print(f"  FLAG_RECLAMO_TARDIO (>{UMBRAL_RECLAMO_TARDIO_DIAS}d): {df['FLAG_RECLAMO_TARDIO'].sum():,}  ← candidatos autofraud")
    print(f"  BUCKET_RECLAMO:\n{df['BUCKET_RECLAMO'].value_counts().to_string()}")
else:
    print("  ⚠️  fecha_reclamo no encontrada — variables de reclamo omitidas")
    for col in ["DIAS_HASTA_RECLAMO", "SEMANAS_HASTA_RECLAMO"]:
        df[col] = np.nan
    for col in ["MES_RECLAMO", "MES_ANIO_RECLAMO", "BUCKET_RECLAMO"]:
        df[col] = "SIN_DATO"
    df["FLAG_SIN_FECHA_RECLAMO"] = 1
    df["FLAG_RECLAMO_RAPIDO"]    = 0
    df["FLAG_RECLAMO_TARDIO"]    = 0


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE E — BIN EXTENDIDO (BIN10 / BIN11 / BIN12)
#  Se extrae directamente desde la columna `tarjeta` (PAN desencriptado).
#  BIN10 = primeros 10 dígitos, BIN11 = 11, BIN12 = 12.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[E] BIN extendido (BIN10/11/12)...")

col_tarjeta = C.get("tarjeta", "")

if col_tarjeta and col_tarjeta in df.columns:
    _pan = df[col_tarjeta].astype(str).str.strip().str.replace(" ", "", regex=False)

    df["BIN_10"] = _pan.str[:10]
    df["BIN_11"] = _pan.str[:11]
    df["BIN_12"] = _pan.str[:12]

    # Fecha de vencimiento como texto normalizado (MMYY → "0130")
    col_ven = C.get("fecha_vencimiento", "")
    if col_ven and col_ven in df.columns:
        df["VENCIMIENTO_STR"] = df[col_ven].astype(str).str.strip().str.zfill(4)
    else:
        df["VENCIMIENTO_STR"] = "0000"

    # BIN12 repetido el mismo día: ≥2 tarjetas distintas con mismo BIN12 ese día
    bin12_dia = df.groupby(["BIN_12", "FECHA_DIA"])[col_tarjeta].transform("nunique")
    df["N_TARJETAS_MISMO_BIN12_DIA"] = bin12_dia
    df["FLAG_BIN12_REPETIDO_DIA"]    = (bin12_dia >= 2).astype(int)

    bin10_dia = df.groupby(["BIN_10", "FECHA_DIA"])[col_tarjeta].transform("nunique")
    df["N_TARJETAS_MISMO_BIN10_DIA"] = bin10_dia
    df["FLAG_BIN10_REPETIDO_DIA"]    = (bin10_dia >= 3).astype(int)

    # Vencimiento concentrado en BIN: ≥3 tarjetas del mismo BIN con mismo vencimiento
    if col_bin and col_bin in df.columns:
        ven_bin = df.groupby([col_bin, "VENCIMIENTO_STR"])[col_tarjeta].transform("nunique")
    else:
        ven_bin = pd.Series(0, index=df.index)
    df["N_TARJETAS_MISMO_VEN_BIN"] = ven_bin
    df["FLAG_VEN_CONCENTRADA_BIN"] = (ven_bin >= 3).astype(int)

    print(f"  FLAG_BIN12_REPETIDO_DIA (≥2 tarjetas): {df['FLAG_BIN12_REPETIDO_DIA'].sum():,} txn")
    print(f"  FLAG_BIN10_REPETIDO_DIA (≥3 tarjetas): {df['FLAG_BIN10_REPETIDO_DIA'].sum():,} txn")
    print(f"  FLAG_VEN_CONCENTRADA_BIN (≥3 misma ven): {df['FLAG_VEN_CONCENTRADA_BIN'].sum():,} txn")
else:
    print("  ⚠️  columna 'tarjeta' no encontrada — BIN extendido omitido")
    for col in ["BIN_10","BIN_11","BIN_12","VENCIMIENTO_STR",
                "N_TARJETAS_MISMO_BIN12_DIA","FLAG_BIN12_REPETIDO_DIA",
                "N_TARJETAS_MISMO_BIN10_DIA","FLAG_BIN10_REPETIDO_DIA",
                "N_TARJETAS_MISMO_VEN_BIN","FLAG_VEN_CONCENTRADA_BIN"]:
        df[col] = 0 if col.startswith("FLAG") or col.startswith("N_") else ""


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE F — SEÑALES DE MONTO
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[F] Señales de monto...")

monto_p10 = df[col_monto].quantile(0.10)
monto_p90 = df[col_monto].quantile(0.90)
monto_p25 = df[col_monto].quantile(0.25)
monto_p75 = df[col_monto].quantile(0.75)

df["FLAG_MONTO_REDONDO"]  = (df[col_monto] % 50 == 0).astype(int)
df["FLAG_MONTO_BAJO"]     = (df[col_monto] < monto_p10).astype(int)
df["FLAG_MONTO_ALTO"]     = (df[col_monto] > monto_p90).astype(int)
df["DECIL_MONTO"]         = pd.qcut(df[col_monto], q=10, labels=False, duplicates="drop") + 1

df["RANGO_MONTO_CAT"] = pd.cut(
    df[col_monto],
    bins=[-np.inf, monto_p25, monto_p75, monto_p90, np.inf],
    labels=["BAJO", "MEDIO", "ALTO", "MUY_ALTO"]
)

# Z-score global del monto (para IF/LOF como feature numérico)
_mean = df[col_monto].mean()
_std  = df[col_monto].std()
if _std > 0:
    df["ZSCORE_MONTO"] = ((df[col_monto] - _mean) / _std).round(3)
else:
    df["ZSCORE_MONTO"] = 0.0

# Z-score del monto por cliente (patrón habitual del cliente)
df["_mean_cli"] = df.groupby(col_cli)[col_monto].transform("mean")
df["_std_cli"]  = df.groupby(col_cli)[col_monto].transform("std").fillna(1).replace(0, 1)
df["ZSCORE_MONTO_CLIENTE"] = ((df[col_monto] - df["_mean_cli"]) / df["_std_cli"]).round(3)
df["FLAG_MONTO_FUERA_PATRON"] = (df["ZSCORE_MONTO_CLIENTE"].abs() > 2).astype(int)
df.drop(columns=["_mean_cli", "_std_cli"], inplace=True)

# Moneda extranjera
col_mon = C.get("moneda_trx", "")
if col_mon and col_mon in df.columns:
    df["FLAG_TRX_EN_DOLAR"] = (df[col_mon].astype(str).str.strip() == "840").astype(int)
    df["FLAG_MONEDA_OTRA"]  = (~df[col_mon].astype(str).str.strip().isin({"604","840",""})).astype(int)
else:
    df["FLAG_TRX_EN_DOLAR"] = 0
    df["FLAG_MONEDA_OTRA"]  = 0

print(f"  Monto P10/P90    : S/{monto_p10:.2f} / S/{monto_p90:.2f}")
print(f"  FLAG_MONTO_REDONDO : {df['FLAG_MONTO_REDONDO'].sum():,}")
print(f"  FLAG_MONTO_BAJO    : {df['FLAG_MONTO_BAJO'].sum():,}")
print(f"  FLAG_MONTO_FUERA_PATRON: {df['FLAG_MONTO_FUERA_PATRON'].sum():,}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE G — VELOCIDAD Y CONCENTRACIÓN POR BIN Y CLIENTE
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[G] Velocidad y concentración...")

# --- Concentración de reclamos por BIN en el día de la txn ---
if col_bin and col_bin in df.columns:
    bin_dia_cnt = df.groupby([col_bin, "FECHA_DIA"])[col_monto].transform("count")
    df["N_RECLAMOS_BIN_DIA"] = bin_dia_cnt
    df["FLAG_RAFAGA_RECLAMOS_BIN"] = (bin_dia_cnt >= 5).astype(int)

    bin_total_cnt = df.groupby(col_bin)[col_monto].transform("count")
    df["N_RECLAMOS_BIN_PERIODO"] = bin_total_cnt

    print(f"  FLAG_RAFAGA_RECLAMOS_BIN (≥5 reclamos BIN/día): {df['FLAG_RAFAGA_RECLAMOS_BIN'].sum():,} txn")
else:
    df["N_RECLAMOS_BIN_DIA"]       = 0
    df["FLAG_RAFAGA_RECLAMOS_BIN"] = 0
    df["N_RECLAMOS_BIN_PERIODO"]   = 0

# --- GAP_MINUTOS: minutos entre esta txn y la anterior del mismo cliente ---
if df[col_fh].notna().any():
    df_sorted_gap = df.sort_values([col_cli, col_fh])
    df["GAP_MINUTOS"] = (
        df_sorted_gap.groupby(col_cli)[col_fh]
        .diff()
        .dt.total_seconds() / 60
    ).round(1)
    df["GAP_DIAS"] = (df["GAP_MINUTOS"] / 1440).round(1)
else:
    df["GAP_MINUTOS"] = np.nan
    df["GAP_DIAS"]    = np.nan

# GAP_ZONA_FRAUDE: 15-120 minutos (patrón de card testing)
df["FLAG_GAP_ZONA_FRAUDE"] = (
    df["GAP_MINUTOS"].between(15, 120, inclusive="both")
).astype(int)


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE H — PERFIL DEL CLIENTE DENTRO DE RECLAMOS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[H] Perfil del cliente...")

# Total de reclamos por cliente en el período
reclamos_cli = (
    df.groupby(col_cli).agg(
        N_RECLAMOS_CLIENTE     = (col_monto, "count"),
        MONTO_TOTAL_RECLAMOS   = (col_monto, "sum"),
        N_COMERCIOS_RECLAMO    = (col_com,   "nunique"),
        N_DIAS_CON_RECLAMO     = ("FECHA_DIA","nunique"),
    ).reset_index()
)
df = df.merge(reclamos_cli, on=col_cli, how="left")

df["FLAG_CLIENTE_MULTI_RECLAMO"] = (df["N_RECLAMOS_CLIENTE"] > 1).astype(int)
df["FLAG_MULTI_COMERCIO_RECLAMO"] = (df["N_COMERCIOS_RECLAMO"] > 1).astype(int)

# Z-score del monto del cliente dentro de sus propios reclamos
df["_mean_cli2"] = df.groupby(col_cli)[col_monto].transform("mean")
df["_std_cli2"]  = df.groupby(col_cli)[col_monto].transform("std").fillna(1).replace(0, 1)
df["RATIO_MONTO_VS_PATRON_CLI"] = (df[col_monto] / df["_mean_cli2"].replace(0, np.nan)).round(2)
df.drop(columns=["_mean_cli2", "_std_cli2"], inplace=True)

# Saldo disponible
df["RATIO_MONTO_VS_SALDO"] = np.nan   # saldo no disponible en esta base
df["FLAG_SALDO_AGOTADO"]   = 0

print(f"  Clientes con 1 reclamo  : {(df['N_RECLAMOS_CLIENTE']==1).sum():,} txn")
print(f"  Clientes con >1 reclamo : {df['FLAG_CLIENTE_MULTI_RECLAMO'].sum():,} txn")
print(f"  Reclamos en >1 comercio : {df['FLAG_MULTI_COMERCIO_RECLAMO'].sum():,} txn")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE I — MCC Y TIPO DE COMERCIO
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[I] MCC y tipo de comercio...")

col_mcc      = C.get("mcc", "")
col_mcc_desc = C.get("mcc_descripcion", "")

if col_mcc and col_mcc in df.columns:
    mcc_str = df[col_mcc].astype(str).str.strip()

    # Usar la descripción real de la base — sin diccionario inventado
    if col_mcc_desc and col_mcc_desc in df.columns:
        df["MCC_CATEGORIA"] = (
            df[col_mcc_desc].astype(str).str.strip()
            .replace({"nan": "Sin descripción", "": "Sin descripción"})
        )
    else:
        df["MCC_CATEGORIA"] = mcc_str  # fallback: usar el código numérico

    # Google / Play Store / YouTube (ataque ene-feb 2026)
    MCC_GOOGLE = {"5816", "5818", "7372", "4816"}
    df["ES_COMERCIO_GOOGLE"] = mcc_str.isin(MCC_GOOGLE).astype(int)

    # Cajero ATM por MCC
    df["ES_MCC_ATM"] = mcc_str.isin({"6011"}).astype(int)

    print(f"  Top MCC_CATEGORIA:\n{df['MCC_CATEGORIA'].value_counts().head(8).to_string()}")
    print(f"  ES_COMERCIO_GOOGLE: {df['ES_COMERCIO_GOOGLE'].sum():,} txn")
else:
    df["MCC_CATEGORIA"]      = "Sin dato"
    df["ES_COMERCIO_GOOGLE"] = 0
    df["ES_MCC_ATM"]         = 0

# Nombre del comercio: flag Google por nombre (complemento al MCC)
_nom_com = df[col_com].astype(str).str.upper()
df["FLAG_COMERCIO_GOOGLE_NOM"] = (
    _nom_com.str.contains("GOOGLE|PLAY STORE|YOUTUBE|GMAIL|ANDROID", regex=True, na=False)
).astype(int)

df["FLAG_COMERCIO_GOOGLE_COMB"] = (
    (df.get("ES_COMERCIO_GOOGLE", 0) == 1) | (df["FLAG_COMERCIO_GOOGLE_NOM"] == 1)
).astype(int)

print(f"  FLAG_COMERCIO_GOOGLE_NOM: {df['FLAG_COMERCIO_GOOGLE_NOM'].sum():,} txn")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE J — SEÑALES DE AUTOFRAUD (composite)
#  Un reclamo es candidato a autofraud cuando varios factores apuntan a que
#  el cliente SÍ realizó la txn pero la reclamó para recuperar el dinero.
#  Se construye un score simple 0-5 sumando señales individuales.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[J] Score de autofraud (composite)...")

# Señal 1: reclamo tardío (cliente legítimo típicamente reclama en <30 días)
s1 = df.get("FLAG_RECLAMO_TARDIO", pd.Series(0, index=df.index)).fillna(0).astype(int)

# Señal 2: monto dentro del patrón habitual del cliente (no es un monto inusual)
s2 = (df.get("FLAG_MONTO_FUERA_PATRON", pd.Series(0, index=df.index)) == 0).astype(int)

# Señal 3: tarjeta presente (transacción física — el cliente tenía la tarjeta)
s3 = df.get("ES_TARJETA_PRESENTE", pd.Series(0, index=df.index)).fillna(0).astype(int)

# Señal 4: sin ataque BIN (la tarjeta no está en un BIN comprometido ese día)
s4 = (df.get("FLAG_BIN12_REPETIDO_DIA", pd.Series(1, index=df.index)) == 0).astype(int)

# Señal 5: monto NO es bajo (el autofraud suele ser compras reales, no card testing)
s5 = (df.get("FLAG_MONTO_BAJO", pd.Series(0, index=df.index)) == 0).astype(int)

df["SCORE_AUTOFRAUD"] = s1 + s2 + s3 + s4 + s5
df["FLAG_CANDIDATO_AUTOFRAUD"] = (df["SCORE_AUTOFRAUD"] >= 4).astype(int)

print(f"  SCORE_AUTOFRAUD distribución:\n{df['SCORE_AUTOFRAUD'].value_counts().sort_index().to_string()}")
print(f"  FLAG_CANDIDATO_AUTOFRAUD (≥4): {df['FLAG_CANDIDATO_AUTOFRAUD'].sum():,} txn")


# ═══════════════════════════════════════════════════════════════════════════════
#  GUARDAR PARQUET
# ═══════════════════════════════════════════════════════════════════════════════

vars_nuevas = [c for c in df.columns if c not in cols_reales]
print(f"\n  Variables nuevas creadas : {len(vars_nuevas)}")

ruta_salida = PARQUET_FEATURES
os.makedirs(ruta_salida.parent, exist_ok=True)
df.to_parquet(str(ruta_salida), index=False)

print(f"\n  ✅ Guardado: {ruta_salida}")
print(f"     Shape final: {df.shape}")
print("═" * 65)
print("FEATURE ENGINEERING COMPLETO ✅")
print("═" * 65)
