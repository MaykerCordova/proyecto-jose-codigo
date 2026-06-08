"""
Feature Engineering — Canal Digital (Banca Digital)
Dataset: fraudes confirmados ya filtrados (SUB_GRUPO='Digital', ESTADO='APROBADA', ORG='SBP').
Todo el parquet es fraude.

Bloques:
  A   Construcción de DATETIME_TRX — fecha y hora vienen separadas (diferencia vs ecommerce_no_seguro)
  B   Variables temporales   → hora, día, franja, quincena
  C   Días de investigación  → DIAS_PARA_CIERRE
  D   Velocidad por tarjeta  → reincidencia, ráfaga, beneficiarios distintos
  D2  Ventanas temporales    → txn/monto en 2/5/10 min, 1h, 24h
  E   Perfil del beneficiario → ranking bancos destino, FLAG_CUENTA_MULA, FLAG_MISMO_TITULAR
  F   Señales de operación y monto → TIPO_OPERACION_GRUPO, monto redondo, rango
  G   Autenticación y dispositivo  → FLAG_SIN_AUTENTICADOR, TIPO_DISPOSITIVO, FLAG_IP_REAL
  H   Score de riesgo digital compuesto → SCORE_RIESGO_DIG, PERFIL_RIESGO_DIG
  I   Guardar parquet enriquecido
"""

import pandas as pd
import numpy as np
import sys
import os
import warnings

warnings.filterwarnings("ignore")

from config import COLS, PARQUET_INPUT, PARQUET_OUTPUT, UMBRAL_CUENTA_MULA

C = COLS   # alias corto


def leer_archivo(ruta):
    """Lee parquet, CSV o Excel según la extensión real del archivo."""
    if not os.path.exists(ruta):
        print(f"\n❌ ERROR: No se encontró el archivo: {ruta}")
        print("   Verifica que PARQUET_INPUT en config.py sea la ruta correcta.")
        print("   También puedes pasar la ruta como argumento:")
        print("   python feature_engineering.py C:\\ruta\\a\\tu_archivo.parquet\n")
        sys.exit(1)

    ext = os.path.splitext(ruta)[1].lower()

    if ext in (".parquet", ".pq", ""):
        try:
            df = pd.read_parquet(ruta)
            print(f"  Formato detectado  : Parquet ✅")
            return df
        except Exception:
            pass

    if ext in (".csv", ".txt"):
        df = pd.read_csv(ruta, encoding="utf-8", low_memory=False, on_bad_lines="warn")
        print(f"  Formato detectado  : CSV ✅")
        return df

    if ext in (".xlsx", ".xls", ".xlsm"):
        df = pd.read_excel(ruta)
        print(f"  Formato detectado  : Excel ✅")
        return df

    try:
        df = pd.read_csv(ruta, encoding="utf-8", low_memory=False, on_bad_lines="warn")
        print(f"  Formato detectado  : CSV (extensión era {ext}) ✅")
        return df
    except Exception:
        pass

    print(f"\n❌ ERROR: No se pudo leer '{ruta}'.")
    print("   Formatos soportados: .parquet, .csv, .txt, .xlsx")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
#  CARGA
# ═══════════════════════════════════════════════════════════════════════════════
ruta_entrada = sys.argv[1] if len(sys.argv) > 1 else PARQUET_INPUT

print("─" * 65)
print(f"Cargando: {ruta_entrada}")
df = leer_archivo(ruta_entrada)

# ── Validación de columnas configuradas ──────────────────────────────────────
cols_reales = set(df.columns)
cols_config = {k: v for k, v in C.items() if v}
faltantes   = {k: v for k, v in cols_config.items() if v not in cols_reales}

if faltantes:
    print("\n⚠️  COLUMNAS NO ENCONTRADAS EN EL ARCHIVO:")
    print("   (actualiza config.py con el nombre exacto de tu parquet)\n")
    for clave, nombre_config in faltantes.items():
        print(f"   config['{clave}'] = '{nombre_config}'  ← NO existe")
    print("\n   Columnas disponibles en tu archivo:")
    for c in sorted(df.columns):
        print(f"     {c}")
    print()

# ── Conversión de tipos ───────────────────────────────────────────────────────
for col_key in ["monto", "monto_dolar"]:
    col_val = C.get(col_key)
    if col_val and col_val in df.columns:
        df[col_val] = (
            df[col_val].astype(str)
            .str.strip()
            .str.replace(",", ".", regex=False)
            .str.replace(" ", "", regex=False)
        )
        df[col_val] = pd.to_numeric(df[col_val], errors="coerce")

COLS_TEXTO = [
    C["tarjeta"], C["canal_digital"], C["operacion"],
    C["tipo_tarjeta"], C["segmento"], C["autenticador"],
    C["banco_destino"], C["cuenta_destino"], C["tipo_id_destino"],
    C["canal_joy"], C["modalidad_fraude"],
]
for col in COLS_TEXTO:
    if col and col in df.columns:
        df[col] = df[col].astype(str).str.strip().str.upper()

print(f"  Filas              : {len(df):,}")
print(f"  Tarjetas únicas    : {df[C['tarjeta']].nunique():,}")
print(f"  Monto total (soles): {df[C['monto']].sum():,.2f}")
if C["monto_dolar"] in df.columns:
    print(f"  Monto total (USD)  : {df[C['monto_dolar']].sum():,.2f}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE A — Construcción de DATETIME_TRX
#  En digital, fecha y hora vienen en columnas SEPARADAS.
#  En ecommerce_no_seguro venían combinadas en una sola columna.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[A] Construcción de DATETIMEs...")

fecha_raw = df[C["fecha_trx"]].astype(str).str.strip()
hora_raw  = df[C["hora_trx"]].astype(str).str.strip()
hora_raw  = hora_raw.replace({"nan": "00:00:00", "": "00:00:00", "None": "00:00:00"})

df["DATETIME_TRX"] = pd.to_datetime(fecha_raw + " " + hora_raw, errors="coerce")
nulos = df["DATETIME_TRX"].isna().sum()
if nulos > 0:
    print(f"  ⚠️  {nulos:,} filas con DATETIME_TRX no parseado — revisa formato fecha/hora")
else:
    print(f"  DATETIME_TRX OK ✅")

df["DATETIME_CIERRE"] = pd.to_datetime(
    df[C["fecha_cierre"]].astype(str).str.strip(), errors="coerce"
)
nulos_c = df["DATETIME_CIERRE"].isna().sum()
if nulos_c > 0:
    print(f"  ⚠️  {nulos_c:,} filas con DATETIME_CIERRE no parseado")
else:
    print(f"  DATETIME_CIERRE OK ✅")

# Quitar timezone si alguna columna la trae (tz-aware vs tz-naive causa error en bloque C)
if df["DATETIME_TRX"].dt.tz is not None:
    df["DATETIME_TRX"] = df["DATETIME_TRX"].dt.tz_convert("UTC").dt.tz_localize(None)
if df["DATETIME_CIERRE"].dt.tz is not None:
    df["DATETIME_CIERRE"] = df["DATETIME_CIERRE"].dt.tz_convert("UTC").dt.tz_localize(None)

df = df.sort_values("DATETIME_TRX").reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE B — Variables temporales de la TRANSACCIÓN
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[B] Variables temporales...")

df["HORA_DIA"]       = df["DATETIME_TRX"].dt.hour
df["DIA_SEMANA"]     = df["DATETIME_TRX"].dt.dayofweek         # 0=Lun … 6=Dom
df["DIA_SEMANA_NOM"] = df["DATETIME_TRX"].dt.strftime("%a").str.upper()
df["MES"]            = df["DATETIME_TRX"].dt.month
df["MES_NOM"]        = df["DATETIME_TRX"].dt.strftime("%b").str.upper()
df["ANIO"]           = df["DATETIME_TRX"].dt.year
df["FECHA_DIA"]      = df["DATETIME_TRX"].dt.date
df["SEMANA_ISO"]     = df["DATETIME_TRX"].dt.isocalendar().week.astype(int)
df["ES_FIN_SEMANA"]  = (df["DIA_SEMANA"] >= 5).astype(int)
df["QUINCENA"]       = np.where(df["DATETIME_TRX"].dt.day <= 15, "Q1", "Q2")

_FRANJAS = [(0, 6, "MADRUGADA"), (6, 12, "MAÑANA"), (12, 19, "TARDE"), (19, 24, "NOCHE")]
def franja(h):
    for ini, fin, nom in _FRANJAS:
        if ini <= h < fin:
            return nom
    return "NOCHE"

df["FRANJA_HORARIA"] = df["HORA_DIA"].map(franja)
df["ES_MADRUGADA"]   = (df["FRANJA_HORARIA"] == "MADRUGADA").astype(int)
df["ES_HORARIO_LAB"] = ((df["DIA_SEMANA"] < 5) & df["HORA_DIA"].between(8, 17)).astype(int)

print("  Variables temporales OK ✅")
print(f"  Distribución FRANJA_HORARIA:\n{df['FRANJA_HORARIA'].value_counts().to_string()}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE C — Días de investigación  (DATETIME_CIERRE - DATETIME_TRX)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[C] Días de investigación...")

df["DIAS_PARA_CIERRE"] = (df["DATETIME_CIERRE"] - df["DATETIME_TRX"]).dt.days
validos = df["DIAS_PARA_CIERRE"].notna() & (df["DIAS_PARA_CIERRE"] >= 0)
print(f"  Registros con cierre válido : {validos.sum():,}")
if validos.sum() > 0:
    print(f"  Días promedio para cierre   : {df.loc[validos,'DIAS_PARA_CIERRE'].mean():.1f}")
    print(f"  Días máx para cierre        : {df.loc[validos,'DIAS_PARA_CIERRE'].max():.0f}")

def rango_cierre(d):
    if   pd.isna(d) or d < 0: return "SIN_CIERRE"
    elif d <= 1:               return "1_DIA"
    elif d <= 7:               return "1_SEMANA"
    elif d <= 30:              return "1_MES"
    else:                      return "MAS_1_MES"

df["RANGO_DIAS_CIERRE"] = df["DIAS_PARA_CIERRE"].map(rango_cierre)


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE D — Velocidad / comportamiento de la TARJETA
#  Diferencia vs ecommerce_no_seguro: usa BENEFICIARIO en lugar de COMERCIO/MCC
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[D] Comportamiento por tarjeta...")

# Identificador único del beneficiario: banco destino + cuenta destino
df["_BENEFICIARIO"] = (
    df[C["banco_destino"]].astype(str).str.strip() + "|" +
    df[C["cuenta_destino"]].astype(str).str.strip()
)

totales_trj = (
    df.groupby(C["tarjeta"])
    .agg(
        TOTAL_FRAUDES_TARJETA       = (C["monto"], "count"),
        MONTO_TOTAL_FRAUDE_TRJ      = (C["monto"], "sum"),
        BENEFICIARIOS_DISTINTOS_TRJ = ("_BENEFICIARIO", "nunique"),
        CANALES_DISTINTOS_TRJ       = (C["canal_digital"], "nunique"),
        DIAS_ACTIVA_TRJ             = ("FECHA_DIA", "nunique"),
    )
    .reset_index()
)
df = df.merge(totales_trj, on=C["tarjeta"], how="left")

fraudes_dia_trj = (
    df.groupby([C["tarjeta"], "FECHA_DIA"])
    .agg(
        FRAUDES_TRJ_DIA             = (C["monto"], "count"),
        MONTO_FRAUDE_TRJ_DIA        = (C["monto"], "sum"),
        BENEFICIARIOS_DISTINTOS_DIA = ("_BENEFICIARIO", "nunique"),
    )
    .reset_index()
)
df = df.merge(fraudes_dia_trj, on=[C["tarjeta"], "FECHA_DIA"], how="left")

df["FLAG_TARJETA_REINCIDENTE"]    = (df["TOTAL_FRAUDES_TARJETA"] > 1).astype(int)
df["FLAG_MULTI_BENEFICIARIO_DIA"] = (df["BENEFICIARIOS_DISTINTOS_DIA"] > 1).astype(int)
df["FLAG_RAFAGA_DIA"]             = (df["FRAUDES_TRJ_DIA"] >= 3).astype(int)

print(f"  Tarjetas reincidentes      : {df.loc[df['FLAG_TARJETA_REINCIDENTE']==1, C['tarjeta']].nunique():,}")
print(f"  Ráfagas (≥3 fraudes/día)   : {df['FLAG_RAFAGA_DIA'].sum():,} transacciones")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE D2 — Ventanas temporales deslizantes por tarjeta
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[D2] Ventanas temporales deslizantes...")

df = df.sort_values([C["tarjeta"], "DATETIME_TRX"]).reset_index(drop=True)
df["_ts"] = df["DATETIME_TRX"].astype(np.int64) // 10**9

VENTANAS = {
    "TXN_CARD_2M" : (  2 * 60, "count"),
    "TXN_CARD_5M" : (  5 * 60, "count"),
    "TXN_CARD_10M": ( 10 * 60, "count"),
    "TXN_CARD_1H" : ( 60 * 60, "count"),
    "TXN_CARD_24H": ( 24*3600, "count"),
    "AMT_CARD_1H" : ( 60 * 60, "sum"),
    "AMT_CARD_24H": ( 24*3600, "sum"),
}

def calcular_ventana(grupo, segundos, modo, col_monto):
    ts  = grupo["_ts"].values
    amt = grupo[col_monto].values if modo == "sum" else None
    n   = len(ts)
    res = np.zeros(n)
    for i in range(n):
        t_inicio = ts[i] - segundos
        j = np.searchsorted(ts, t_inicio, side="left")
        res[i] = (i - j) if modo == "count" else amt[j:i].sum()
    return res

resultados = {col: np.zeros(len(df)) for col in VENTANAS}
for tarjeta, grupo in df.groupby(C["tarjeta"], sort=False):
    idx = grupo.index
    for col, (segundos, modo) in VENTANAS.items():
        vals = calcular_ventana(grupo, segundos, modo, C["monto"])
        for i, ix in enumerate(idx):
            resultados[col][ix] = vals[i]

for col, vals in resultados.items():
    df[col] = vals
    df[col] = df[col].round(2) if col.startswith("AMT_") else df[col].astype(int)

df.drop(columns=["_ts"], inplace=True)

df["FLAG_VEL_ALTA_1H"]  = (df["TXN_CARD_1H"]  >= 2).astype(int)
df["FLAG_VEL_ALTA_10M"] = (df["TXN_CARD_10M"] >= 2).astype(int)
df["FLAG_ACUM_ALTO_1H"] = (df["AMT_CARD_1H"]  >= df[C["monto"]] * 2).astype(int)

print(f"  TXN_CARD_1H  media : {df['TXN_CARD_1H'].mean():.2f} fraudes previos en 1h")
print(f"  FLAG_VEL_ALTA_1H   : {df['FLAG_VEL_ALTA_1H'].sum():,} txn con 2+ fraudes previos en 1h")
print("  Ventanas temporales OK ✅")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE E — Perfil del BENEFICIARIO
#  Reemplaza el bloque E de comercio/MCC de ecommerce_no_seguro.
#  Detecta bancos destino más golpeados y cuentas mula.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[E] Perfil del beneficiario...")

# Por banco destino
totales_banco = (
    df.groupby(C["banco_destino"])
    .agg(
        TOTAL_FRAUDES_BANCO_DEST = (C["monto"], "count"),
        MONTO_TOTAL_FRAUDE_BANCO = (C["monto"], "sum"),
        TARJETAS_EN_BANCO_DEST   = (C["tarjeta"], "nunique"),
        DIAS_CON_FRAUDE_BANCO    = ("FECHA_DIA", "nunique"),
    )
    .reset_index()
)
df = df.merge(totales_banco, on=C["banco_destino"], how="left")

rank_banco = (
    totales_banco[[C["banco_destino"], "TOTAL_FRAUDES_BANCO_DEST"]]
    .sort_values("TOTAL_FRAUDES_BANCO_DEST", ascending=False)
    .reset_index(drop=True)
)
rank_banco["RANKING_BANCO_DEST"] = rank_banco.index + 1
df = df.merge(rank_banco[[C["banco_destino"], "RANKING_BANCO_DEST"]], on=C["banco_destino"], how="left")

# Por cuenta destino — detectar cuentas mula
totales_cuenta = (
    df.groupby(C["cuenta_destino"])
    .agg(
        TOTAL_FRAUDES_CUENTA_DEST = (C["monto"], "count"),
        MONTO_TOTAL_FRAUDE_CUENTA = (C["monto"], "sum"),
        TARJETAS_EN_CUENTA_DEST   = (C["tarjeta"], "nunique"),
    )
    .reset_index()
)
df = df.merge(totales_cuenta, on=C["cuenta_destino"], how="left")

# Cuenta mula: misma cuenta destino recibe fraude desde múltiples tarjetas distintas
df["FLAG_CUENTA_MULA"] = (df["TARJETAS_EN_CUENTA_DEST"] >= UMBRAL_CUENTA_MULA).astype(int)

# M = el titular se transfiere a su propia cuenta en otro banco
df["FLAG_MISMO_TITULAR"] = (
    df[C["tipo_id_destino"]].astype(str).str.upper().str.strip() == "M"
).astype(int)
df["FLAG_TERCERO"] = (1 - df["FLAG_MISMO_TITULAR"])

print("  Perfil beneficiario OK ✅")
print(f"  Top 5 bancos destino:\n{rank_banco.head(5).to_string(index=False)}")
print(f"  Cuentas mula (≥{UMBRAL_CUENTA_MULA} tarjetas distintas) : {df[df['FLAG_CUENTA_MULA']==1][C['cuenta_destino']].nunique():,}")
print(f"  FLAG_MISMO_TITULAR (transferencia a sí mismo)  : {df['FLAG_MISMO_TITULAR'].sum():,} ({df['FLAG_MISMO_TITULAR'].mean()*100:.1f}%)")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE F — Señales de OPERACIÓN y MONTO
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[F] Señales de operación y monto...")

# Categorizar por tipo de operación (NOM_OPERACION)
def categorizar_operacion(op):
    if pd.isna(op) or str(op).upper().strip() in ("NAN", "NONE", ""):
        return "OTRO"
    op = str(op).upper()
    if any(x in op for x in ["YAPE", "PLIN", "BIM", "INTEROP", "QR", "PRINYAPE"]):
        return "YAPE_PLIN_QR"
    if "PASARELA" in op:
        return "PASARELA"
    if any(x in op for x in ["TRANSFER", "TRF", "TIB", "TIP", " CC", "INMEDIATA", "TERCERO"]):
        return "TRANSFERENCIA"
    if any(x in op for x in ["PAGO", "ABONO", "PRESTAMO", "SERVICIO"]):
        return "PAGO"
    return "OTRO"

df["TIPO_OPERACION_GRUPO"] = df[C["operacion"]].map(categorizar_operacion)
df["FLAG_ES_YAPE_PLIN_QR"]  = (df["TIPO_OPERACION_GRUPO"] == "YAPE_PLIN_QR").astype(int)
df["FLAG_ES_PASARELA"]      = (df["TIPO_OPERACION_GRUPO"] == "PASARELA").astype(int)
df["FLAG_ES_TRANSFERENCIA"] = (df["TIPO_OPERACION_GRUPO"] == "TRANSFERENCIA").astype(int)
df["FLAG_ES_PAGO"]          = (df["TIPO_OPERACION_GRUPO"] == "PAGO").astype(int)

# Categorizar canal digital
def categorizar_canal(canal):
    if pd.isna(canal) or str(canal).upper().strip() in ("NAN", "NONE", ""):
        return "DESCONOCIDO"
    canal = str(canal).upper()
    if any(x in canal for x in ["YAPE", "PLIN", "BIM"]):
        return "YAPE_PLIN"
    if "PASARELA" in canal:
        return "PASARELA"
    if "INMEDIATA" in canal:
        return "TRANSF_INMEDIATA"   # a otro banco (externo)
    if "TERCERO" in canal:
        return "TRANSF_TERCEROS"    # dentro de Scotiabank
    return "OTRO"

df["CANAL_DIGITAL_GRUPO"] = df[C["canal_digital"]].map(categorizar_canal)
df["FLAG_CANAL_EXTERNO"]  = (df["CANAL_DIGITAL_GRUPO"] == "TRANSF_INMEDIATA").astype(int)

# ── Umbrales de rango de monto (ajusta aquí si cambian los criterios) ─────────
RANGO_UMBRALES = [
    (0,      100,    "1_MICRO",    "S/ 0 – S/ 100"),
    (100,    500,    "2_BAJO",     "S/ 101 – S/ 500"),
    (500,    2000,   "3_MEDIO",    "S/ 501 – S/ 2,000"),
    (2000,   10000,  "4_ALTO",     "S/ 2,001 – S/ 10,000"),
    (10000,  np.inf, "5_MUY_ALTO", "S/ 10,001 a más"),
]

def clasificar_monto(m):
    """Devuelve (etiqueta, texto_rango) para un monto dado."""
    if pd.isna(m) or m < 0:
        return ("SIN_DATO", "Sin dato")
    for desde, hasta, etiqueta, texto in RANGO_UMBRALES:
        if desde < hasta:           # rango normal
            if desde <= m < hasta:
                return (etiqueta, texto)
        else:                       # último rango (hasta = inf)
            if m >= desde:
                return (etiqueta, texto)
    return ("5_MUY_ALTO", "S/ 10,001 a más")

_rangos = df[C["monto"]].map(clasificar_monto)
df["RANGO_MONTO"]       = _rangos.map(lambda x: x[0])   # etiqueta ordenable: 1_MICRO, 2_BAJO…
df["RANGO_MONTO_TEXTO"] = _rangos.map(lambda x: x[1])   # texto legible: "S/ 0 – S/ 100"

# Señales de monto
df["FLAG_MONTO_REDONDO"] = (df[C["monto"]] % 1 == 0).astype(int)

if C["monto_dolar"] in df.columns:
    df["TIPO_CAMBIO_IMPLICITO"] = (
        df[C["monto"]] / df[C["monto_dolar"]].replace(0, np.nan)
    ).round(4)

print(f"  Montos redondos : {df['FLAG_MONTO_REDONDO'].sum():,} ({df['FLAG_MONTO_REDONDO'].mean()*100:.1f}%)")
print(f"  Distribución RANGO_MONTO:\n{df['RANGO_MONTO'].value_counts().sort_index().to_string()}")
print(f"  Distribución TIPO_OPERACION_GRUPO:\n{df['TIPO_OPERACION_GRUPO'].value_counts().to_string()}")
print(f"  Distribución CANAL_DIGITAL_GRUPO:\n{df['CANAL_DIGITAL_GRUPO'].value_counts().to_string()}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE G — Autenticación y DISPOSITIVO
#  Variables exclusivas del canal digital — no existen en ecommerce_no_seguro.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[G] Autenticación y dispositivo...")

_auth = df[C["autenticador"]].astype(str).str.upper().str.strip()
df["FLAG_SIN_AUTENTICADOR"] = _auth.isin(["NO APLICA", "NAN", "NONE", ""]).astype(int)
df["FLAG_OTP"]               = _auth.str.contains("OTP",   na=False).astype(int)
df["FLAG_BIOMETRICO"]        = _auth.str.contains("BIOM",  na=False).astype(int)
df["FLAG_CLAVE_DIGITAL"]     = _auth.str.contains("CLAVE", na=False).astype(int)

_joy = df[C["canal_joy"]].astype(str).str.upper().str.strip()
def tipo_dispositivo(joy):
    if "IOS" in joy or "APPLE" in joy: return "iOS"
    if "ANDROID" in joy:               return "Android"
    if "WEB" in joy or "INTERNET" in joy: return "Web"
    return "OTRO"
df["TIPO_DISPOSITIVO"] = _joy.map(tipo_dispositivo)
df["FLAG_WEB"]         = (df["TIPO_DISPOSITIVO"] == "Web").astype(int)

# IP real — viene del script de extracción como ES_IP_REAL
if C["es_ip_real"] in df.columns:
    df["FLAG_IP_REAL"] = df[C["es_ip_real"]].astype(int)
else:
    df["FLAG_IP_REAL"] = 0

print(f"  Distribución TIPO_DISPOSITIVO:\n{df['TIPO_DISPOSITIVO'].value_counts().to_string()}")
print(f"  FLAG_SIN_AUTENTICADOR  : {df['FLAG_SIN_AUTENTICADOR'].sum():,} ({df['FLAG_SIN_AUTENTICADOR'].mean()*100:.1f}%)")
print(f"  FLAG_OTP               : {df['FLAG_OTP'].sum():,}")
print(f"  FLAG_BIOMETRICO        : {df['FLAG_BIOMETRICO'].sum():,}")
print(f"  FLAG_CLAVE_DIGITAL     : {df['FLAG_CLAVE_DIGITAL'].sum():,}")
print("  Autenticación y dispositivo OK ✅")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE H — Score de riesgo DIGITAL compuesto
#  9 componentes, cada uno vale 1 punto.
#  PERFIL_RIESGO_DIG: BAJO=0 / MEDIO=1-2 / ALTO=3-5 / MUY_ALTO=6+
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[H] Score de riesgo digital...")

df["SCORE_RIESGO_DIG"] = (
    df["FLAG_TARJETA_REINCIDENTE"]  +   # tarjeta ya apareció antes en el dataset
    df["FLAG_RAFAGA_DIA"]           +   # ≥3 fraudes en el mismo día
    df["FLAG_VEL_ALTA_1H"]          +   # 2+ fraudes previos en la última hora
    df["FLAG_MONTO_REDONDO"]        +   # monto sin centavos (patrón común en fraude)
    df["ES_MADRUGADA"]              +   # entre 00:00 y 05:59
    df["FLAG_SIN_AUTENTICADOR"]     +   # no hubo OTP ni biometría ni clave digital
    df["FLAG_TERCERO"]              +   # transferencia a persona distinta al titular
    df["FLAG_CUENTA_MULA"]          +   # cuenta destino recibe fraude de muchas tarjetas
    df["FLAG_IP_REAL"]                  # transacción vino por navegador web con IP real
)

df["PERFIL_RIESGO_DIG"] = pd.cut(
    df["SCORE_RIESGO_DIG"],
    bins=[-1, 0, 2, 5, 99],
    labels=["BAJO", "MEDIO", "ALTO", "MUY_ALTO"]
)

df["FLAG_HORARIO_RIESGO"] = (
    (df["ES_MADRUGADA"] == 1) | (df["ES_FIN_SEMANA"] == 1)
).astype(int)

print(f"  PERFIL_RIESGO_DIG:\n{df['PERFIL_RIESGO_DIG'].value_counts().to_string()}")
print(f"  Score promedio: {df['SCORE_RIESGO_DIG'].mean():.2f}  |  Score máx: {df['SCORE_RIESGO_DIG'].max()}")


# ═══════════════════════════════════════════════════════════════════════════════
#  RESUMEN DE VARIABLES CONSTRUIDAS
# ═══════════════════════════════════════════════════════════════════════════════
VARS_NUEVAS = [
    # A/B — temporales
    "DATETIME_TRX", "DATETIME_CIERRE",
    "HORA_DIA", "DIA_SEMANA", "DIA_SEMANA_NOM", "MES", "MES_NOM", "ANIO",
    "FECHA_DIA", "SEMANA_ISO", "ES_FIN_SEMANA", "FRANJA_HORARIA",
    "ES_MADRUGADA", "ES_HORARIO_LAB", "QUINCENA",
    # C — investigación
    "DIAS_PARA_CIERRE", "RANGO_DIAS_CIERRE",
    # D — tarjeta
    "TOTAL_FRAUDES_TARJETA", "MONTO_TOTAL_FRAUDE_TRJ",
    "BENEFICIARIOS_DISTINTOS_TRJ", "CANALES_DISTINTOS_TRJ", "DIAS_ACTIVA_TRJ",
    "FRAUDES_TRJ_DIA", "MONTO_FRAUDE_TRJ_DIA", "BENEFICIARIOS_DISTINTOS_DIA",
    "FLAG_TARJETA_REINCIDENTE", "FLAG_MULTI_BENEFICIARIO_DIA", "FLAG_RAFAGA_DIA",
    # D2 — ventanas temporales
    "TXN_CARD_2M", "TXN_CARD_5M", "TXN_CARD_10M", "TXN_CARD_1H", "TXN_CARD_24H",
    "AMT_CARD_1H", "AMT_CARD_24H",
    "FLAG_VEL_ALTA_1H", "FLAG_VEL_ALTA_10M", "FLAG_ACUM_ALTO_1H",
    # E — beneficiario
    "TOTAL_FRAUDES_BANCO_DEST", "MONTO_TOTAL_FRAUDE_BANCO",
    "TARJETAS_EN_BANCO_DEST", "DIAS_CON_FRAUDE_BANCO", "RANKING_BANCO_DEST",
    "TOTAL_FRAUDES_CUENTA_DEST", "MONTO_TOTAL_FRAUDE_CUENTA",
    "TARJETAS_EN_CUENTA_DEST", "FLAG_CUENTA_MULA",
    "FLAG_MISMO_TITULAR", "FLAG_TERCERO",
    # F — operación / monto
    "TIPO_OPERACION_GRUPO", "CANAL_DIGITAL_GRUPO",
    "FLAG_ES_YAPE_PLIN_QR", "FLAG_ES_PASARELA", "FLAG_ES_TRANSFERENCIA", "FLAG_ES_PAGO",
    "FLAG_CANAL_EXTERNO",
    "FLAG_MONTO_REDONDO", "RANGO_MONTO", "RANGO_MONTO_TEXTO", "TIPO_CAMBIO_IMPLICITO",
    # G — autenticación / dispositivo
    "FLAG_SIN_AUTENTICADOR", "FLAG_OTP", "FLAG_BIOMETRICO", "FLAG_CLAVE_DIGITAL",
    "TIPO_DISPOSITIVO", "FLAG_WEB", "FLAG_IP_REAL",
    # H — riesgo compuesto
    "SCORE_RIESGO_DIG", "PERFIL_RIESGO_DIG", "FLAG_HORARIO_RIESGO",
]

print("\n" + "─" * 65)
print("VARIABLES NUEVAS AGREGADAS:")
for v in VARS_NUEVAS:
    existe = "✅" if v in df.columns else "——  (columna origen no disponible)"
    print(f"  {existe}  {v}")

print(f"\nColumnas totales en el dataset enriquecido: {df.shape[1]}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE I — Guardar parquet enriquecido
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n[I] Guardando en: {PARQUET_OUTPUT}")
df.to_parquet(PARQUET_OUTPUT, index=False)
print(f"  ✅ Listo — {len(df):,} filas × {df.shape[1]} columnas")
print(f"  Archivo: {PARQUET_OUTPUT}")
print("─" * 65)
