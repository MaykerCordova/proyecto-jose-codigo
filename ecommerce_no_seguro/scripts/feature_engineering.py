"""
Feature Engineering — Comercios No Seguros (sin 3DS/TDS)
Dataset: fraudes confirmados ya filtrados (todo el parquet es fraude F).

Bloques:
  A  Parseo de fechas       → DATETIME_TRX, DATETIME_CIERRE
  B  Variables temporales   → hora, día, franja, quincena
  C  Días de investigación  → DIAS_PARA_CIERRE
  D  Velocidad por tarjeta  → conteo/monto de fraudes de esa tarjeta
  D2 Ventanas temporales    → txn y monto acumulado en 2/5/10 min, 1h, 24h
  E  Perfil del comercio    → concentración de fraude por comercio/MCC
  F  Señales de monto       → monto redondo, ratio vs saldo, rango
  G  Flags compuestos       → score de riesgo, perfil para Power BI
  H  Guardar parquet enriquecido
"""

import pandas as pd
import numpy as np
import sys
import os
import warnings

warnings.filterwarnings("ignore")

from config import COLS, PARQUET_INPUT, PARQUET_OUTPUT

C = COLS   # alias corto


def leer_archivo(ruta):
    """Lee parquet, CSV o Excel según la extensión real del archivo."""
    if not os.path.exists(ruta):
        print(f"\n❌ ERROR: No se encontró el archivo: {ruta}")
        print("   Verifica que PARQUET_INPUT en config.py sea la ruta correcta.")
        print("   También puedes pasar la ruta como argumento:")
        print("   python feature_engineering.py C:\\ruta\\a\\tu_archivo.csv\n")
        sys.exit(1)

    ext = os.path.splitext(ruta)[1].lower()

    # Intentar parquet primero (independiente de extensión)
    if ext in (".parquet", ".pq", "") :
        try:
            df = pd.read_parquet(ruta)
            print(f"  Formato detectado  : Parquet ✅")
            return df
        except Exception:
            pass  # no era parquet real, seguir intentando

    if ext in (".csv", ".txt"):
        df = pd.read_csv(ruta, encoding="utf-8", low_memory=False,
                         on_bad_lines="warn")
        print(f"  Formato detectado  : CSV ✅")
        return df

    if ext in (".xlsx", ".xls", ".xlsm"):
        df = pd.read_excel(ruta)
        print(f"  Formato detectado  : Excel ✅")
        return df

    # Último recurso: intentar CSV aunque la extensión diga parquet
    try:
        df = pd.read_csv(ruta, encoding="utf-8", low_memory=False,
                         on_bad_lines="warn")
        print(f"  Formato detectado  : CSV (extensión era {ext}) ✅")
        return df
    except Exception:
        pass

    print(f"\n❌ ERROR: No se pudo leer '{ruta}'.")
    print("   Formatos soportados: .parquet, .csv, .txt, .xlsx")
    print("   Si el archivo viene de una extracción de base de datos,")
    print("   expórtalo como CSV y actualiza PARQUET_INPUT en config.py.\n")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
#  CARGA
# ═══════════════════════════════════════════════════════════════════════════════
# Acepta ruta como argumento: python feature_engineering.py mi_archivo.csv
ruta_entrada = sys.argv[1] if len(sys.argv) > 1 else PARQUET_INPUT

print("─" * 65)
print(f"Cargando: {ruta_entrada}")
df = leer_archivo(ruta_entrada)

# ── Validación de columnas configuradas ──────────────────────────────────────
cols_reales = set(df.columns)
cols_config = {k: v for k, v in C.items() if v}  # solo los que tienen valor
faltantes = {k: v for k, v in cols_config.items() if v not in cols_reales}

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
# Montos → numérico (pueden venir como string con comas o espacios)
for col_key in ["monto", "monto_dolar", "saldo_disponible"]:
    col_val = C.get(col_key)
    if col_val and col_val in df.columns:
        df[col_val] = (
            df[col_val].astype(str)
            .str.strip()
            .str.replace(",", ".", regex=False)   # coma decimal → punto
            .str.replace(" ", "", regex=False)    # quitar espacios
        )
        df[col_val] = pd.to_numeric(df[col_val], errors="coerce")

# Texto → limpiar y normalizar
COLS_TEXTO = [
    C["tarjeta"], C["comercio_id"], C["canal"], C["tipo_tarjeta"],
    C["segmento"], C["organizacion"], C["modalidad_fraude"],
    C["nivel_tarjeta"], C["mcc"],
]
for col in COLS_TEXTO:
    if col in df.columns:
        df[col] = df[col].astype(str).str.strip().str.upper()

print(f"  Filas              : {len(df):,}")
print(f"  Tarjetas únicas    : {df[C['tarjeta']].nunique():,}")
print(f"  Comercios únicos   : {df[C['comercio_id']].nunique():,}")
print(f"  Monto total (local): {df[C['monto']].sum():,.2f}")
if C.get("monto_dolar") and C["monto_dolar"] in df.columns:
    print(f"  Monto total (USD)  : {df[C['monto_dolar']].sum():,.2f}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE A — Parseo de fechas
#   DATETIME_TRX  ← columna combinada  "YYYY-MM-DD HH:MM:SS"
#   DATETIME_CIERRE ← columna solo fecha "YYYY-MM-DD"
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[A] Construcción de DATETIMEs...")

def parsear_dt(serie, nombre):
    dt = pd.to_datetime(serie.astype(str).str.strip(), errors="coerce")
    nulos = dt.isna().sum()
    if nulos > 0:
        print(f"  ⚠️  {nulos:,} filas con {nombre} no parseado — revisa el formato")
    else:
        print(f"  {nombre} OK ✅")
    return dt

df["DATETIME_TRX"]    = parsear_dt(df[C["fecha_hora_trx"]], "DATETIME_TRX")
df["DATETIME_CIERRE"] = parsear_dt(df[C["fecha_cierre"]],   "DATETIME_CIERRE")

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

# Franja horaria
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
print(f"  Días promedio para cierre   : {df.loc[validos,'DIAS_PARA_CIERRE'].mean():.1f}")
print(f"  Días máx para cierre        : {df.loc[validos,'DIAS_PARA_CIERRE'].max():.0f}")

# Rango de tiempo de investigación
def rango_cierre(d):
    if   pd.isna(d) or d < 0: return "SIN_CIERRE"
    elif d <= 1:               return "1_DIA"
    elif d <= 7:               return "1_SEMANA"
    elif d <= 30:              return "1_MES"
    else:                      return "MAS_1_MES"

df["RANGO_DIAS_CIERRE"] = df["DIAS_PARA_CIERRE"].map(rango_cierre)


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE D — Velocidad / comportamiento de la TARJETA
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[D] Comportamiento por tarjeta...")

# Totales por tarjeta en todo el dataset
totales_trj = (
    df.groupby(C["tarjeta"])
    .agg(
        TOTAL_FRAUDES_TARJETA   = (C["monto"], "count"),
        MONTO_TOTAL_FRAUDE_TRJ  = (C["monto"], "sum"),
        MONTO_USD_FRAUDE_TRJ    = (C["monto_dolar"], "sum") if C["monto_dolar"] in df.columns else (C["monto"], "count"),
        COMERCIOS_DISTINTOS_TRJ = (C["comercio_id"], "nunique"),
        MCC_DISTINTOS_TRJ       = (C["mcc"], "nunique"),
        CANALES_DISTINTOS_TRJ   = (C["canal"], "nunique"),
        DIAS_ACTIVA_TRJ         = ("FECHA_DIA", "nunique"),
    )
    .reset_index()
)
# Si no tiene monto_dolar, renombrar columna duplicada
if C["monto_dolar"] not in df.columns:
    totales_trj = totales_trj.rename(columns={"MONTO_USD_FRAUDE_TRJ": "_DROP"}).drop(columns=["_DROP"])

df = df.merge(totales_trj, on=C["tarjeta"], how="left")

# Fraudes de la tarjeta en el MISMO DÍA
fraudes_dia_trj = (
    df.groupby([C["tarjeta"], "FECHA_DIA"])
    .agg(
        FRAUDES_TRJ_DIA          = (C["monto"], "count"),
        MONTO_FRAUDE_TRJ_DIA     = (C["monto"], "sum"),
        COMERCIOS_DISTINTOS_DIA  = (C["comercio_id"], "nunique"),
    )
    .reset_index()
)
df = df.merge(fraudes_dia_trj, on=[C["tarjeta"], "FECHA_DIA"], how="left")

# Flags de velocidad
df["FLAG_TARJETA_REINCIDENTE"] = (df["TOTAL_FRAUDES_TARJETA"] > 1).astype(int)
df["FLAG_MULTI_COMERCIO_DIA"]  = (df["COMERCIOS_DISTINTOS_DIA"] > 1).astype(int)
df["FLAG_RAFAGA_DIA"]          = (df["FRAUDES_TRJ_DIA"] >= 3).astype(int)

# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE D2 — Ventanas temporales deslizantes por tarjeta
#  Para cada transacción calcula cuántas txn y cuánto monto acumuló
#  esa tarjeta en los N minutos/horas ANTERIORES a ese momento.
#  Nota: se trabaja sobre el dataset de fraudes — mide velocidad
#        con la que esa tarjeta acumuló fraudes confirmados.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[D2] Ventanas temporales deslizantes...")

# Ordenar por tarjeta y tiempo (indispensable para las ventanas)
df = df.sort_values([C["tarjeta"], "DATETIME_TRX"]).reset_index(drop=True)

# Timestamp en segundos para aritmética rápida
df["_ts"] = df["DATETIME_TRX"].astype(np.int64) // 10**9

VENTANAS = {
    "TXN_CARD_2M" :  (  2 * 60,  "count"),   # txn en últimos  2 minutos
    "TXN_CARD_5M" :  (  5 * 60,  "count"),   # txn en últimos  5 minutos
    "TXN_CARD_10M":  ( 10 * 60,  "count"),   # txn en últimos 10 minutos
    "TXN_CARD_1H" :  ( 60 * 60,  "count"),   # txn en última   1 hora
    "TXN_CARD_24H":  ( 24*3600,  "count"),   # txn en últimas 24 horas
    "AMT_CARD_1H" :  ( 60 * 60,  "sum"),     # monto acumulado última 1 hora
    "AMT_CARD_24H":  ( 24*3600,  "sum"),     # monto acumulado últimas 24 horas
}

def calcular_ventana(grupo, segundos, modo, col_monto):
    """Para cada fila del grupo cuenta txn o suma monto en [t-segundos, t)."""
    ts  = grupo["_ts"].values
    amt = grupo[col_monto].values if modo == "sum" else None
    n   = len(ts)
    res = np.zeros(n)
    for i in range(n):
        t_inicio = ts[i] - segundos
        j = np.searchsorted(ts, t_inicio, side="left")
        if modo == "count":
            res[i] = i - j          # filas anteriores dentro de la ventana
        else:
            res[i] = amt[j:i].sum() # monto acumulado dentro de la ventana
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
    if col.startswith("AMT_"):
        df[col] = df[col].round(2)
    else:
        df[col] = df[col].astype(int)

df.drop(columns=["_ts"], inplace=True)

# Flags de ventana
df["FLAG_VEL_ALTA_1H"]  = (df["TXN_CARD_1H"]  >= 2).astype(int)  # 2+ fraudes en 1h
df["FLAG_VEL_ALTA_10M"] = (df["TXN_CARD_10M"] >= 2).astype(int)  # 2+ fraudes en 10min
df["FLAG_ACUM_ALTO_1H"] = (df["AMT_CARD_1H"]  >= df[C["monto"]] * 2).astype(int)

print(f"  TXN_CARD_2M  media : {df['TXN_CARD_2M'].mean():.2f} txn previas en 2 min")
print(f"  TXN_CARD_1H  media : {df['TXN_CARD_1H'].mean():.2f} txn previas en 1 hora")
print(f"  AMT_CARD_24H media : {df['AMT_CARD_24H'].mean():,.2f}")
print(f"  FLAG_VEL_ALTA_1H   : {df['FLAG_VEL_ALTA_1H'].sum():,} txn con 2+ fraudes previos en 1h")
print("  Ventanas temporales OK ✅")

# Ratio monto del fraude vs saldo disponible
if C["saldo_disponible"] in df.columns:
    df["RATIO_MONTO_VS_SALDO"] = (
        df[C["monto"]] / df[C["saldo_disponible"]].replace(0, np.nan)
    ).round(4)
    df["FLAG_SALDO_AGOTADO"] = (df["RATIO_MONTO_VS_SALDO"] >= 0.9).astype(int)
    print(f"  RATIO_MONTO_VS_SALDO OK ✅  |  Fraudes que agotan saldo (≥90%): {df['FLAG_SALDO_AGOTADO'].sum():,}")

print(f"  Tarjetas reincidentes     : {df.loc[df['FLAG_TARJETA_REINCIDENTE']==1, C['tarjeta']].nunique():,}")
print(f"  Ráfagas (≥3 fraudes/día)  : {df['FLAG_RAFAGA_DIA'].sum():,} transacciones")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE E — Perfil del COMERCIO y del MCC
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[E] Perfil de comercio y MCC...")

# Por comercio
totales_com = (
    df.groupby(C["comercio_id"])
    .agg(
        TOTAL_FRAUDES_COMERCIO  = (C["monto"], "count"),
        MONTO_TOTAL_FRAUDE_COM  = (C["monto"], "sum"),
        MONTO_PROM_FRAUDE_COM   = (C["monto"], "mean"),
        TARJETAS_DISTINTAS_COM  = (C["tarjeta"], "nunique"),
        CANALES_DISTINTOS_COM   = (C["canal"], "nunique"),
        DIAS_CON_FRAUDE_COM     = ("FECHA_DIA", "nunique"),
    )
    .reset_index()
)
df = df.merge(totales_com, on=C["comercio_id"], how="left")

# Fraudes por comercio por día
fraudes_com_dia = (
    df.groupby([C["comercio_id"], "FECHA_DIA"])
    .agg(FRAUDES_COM_DIA = (C["monto"], "count"))
    .reset_index()
)
df = df.merge(fraudes_com_dia, on=[C["comercio_id"], "FECHA_DIA"], how="left")

# Ranking de comercios más golpeados
rank_com = (
    totales_com[[C["comercio_id"], "TOTAL_FRAUDES_COMERCIO"]]
    .sort_values("TOTAL_FRAUDES_COMERCIO", ascending=False)
    .reset_index(drop=True)
)
rank_com["RANKING_COMERCIO"] = rank_com.index + 1
df = df.merge(rank_com[[C["comercio_id"], "RANKING_COMERCIO"]], on=C["comercio_id"], how="left")

# Por MCC
totales_mcc = (
    df.groupby(C["mcc"])
    .agg(
        TOTAL_FRAUDES_MCC  = (C["monto"], "count"),
        MONTO_TOTAL_MCC    = (C["monto"], "sum"),
        COMERCIOS_EN_MCC   = (C["comercio_id"], "nunique"),
        TARJETAS_EN_MCC    = (C["tarjeta"], "nunique"),
    )
    .reset_index()
)
df = df.merge(totales_mcc, on=C["mcc"], how="left")

rank_mcc = (
    totales_mcc[[C["mcc"], "TOTAL_FRAUDES_MCC"]]
    .sort_values("TOTAL_FRAUDES_MCC", ascending=False)
    .reset_index(drop=True)
)
rank_mcc["RANKING_MCC"] = rank_mcc.index + 1
df = df.merge(rank_mcc[[C["mcc"], "RANKING_MCC"]], on=C["mcc"], how="left")

print("  Perfil comercio y MCC OK ✅")
print(f"  Top 5 comercios:\n{rank_com.head(5).to_string(index=False)}")
print(f"  Top 5 MCC:\n{rank_mcc.head(5).to_string(index=False)}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE E2 — Antigüedad y novedad del COMERCIO
#  Detecta comercios que aparecen de la nada (solo 1 mes en la base)
#  y ya generan alto impacto — patrón típico de comercio fantasma.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[E2] Antigüedad y novedad de comercio...")

# Fecha del primer y último fraude por comercio
fechas_com = (
    df.groupby(C["comercio_id"])
    .agg(
        PRIMER_FECHA_COMERCIO = ("DATETIME_TRX", "min"),
        ULTIMO_FECHA_COMERCIO = ("DATETIME_TRX", "max"),
    )
    .reset_index()
)

# Meses calendarios distintos en los que aparece el comercio (YYYY-MM)
meses_com = (
    df.assign(_MES_CAL=df["DATETIME_TRX"].dt.to_period("M").astype(str))
    .groupby(C["comercio_id"])["_MES_CAL"]
    .nunique()
    .reset_index()
    .rename(columns={"_MES_CAL": "MESES_DISTINTOS_COMERCIO"})
)

novedad_com = fechas_com.merge(meses_com, on=C["comercio_id"], how="left")

# Antigüedad en días dentro del dataset (último - primer fraude)
novedad_com["ANTIGÜEDAD_COMERCIO_DIAS"] = (
    novedad_com["ULTIMO_FECHA_COMERCIO"] - novedad_com["PRIMER_FECHA_COMERCIO"]
).dt.days

# Umbral top 20% por monto para FLAG_COMERCIO_ALTO_IMPACTO_RAPIDO
umbral_monto_top20 = totales_com["MONTO_TOTAL_FRAUDE_COM"].quantile(0.80)

novedad_com = novedad_com.merge(
    totales_com[[C["comercio_id"], "MONTO_TOTAL_FRAUDE_COM"]],
    on=C["comercio_id"], how="left"
)

novedad_com["FLAG_COMERCIO_NUEVO"] = (
    novedad_com["MESES_DISTINTOS_COMERCIO"] == 1
).astype(int)

novedad_com["FLAG_COMERCIO_ALTO_IMPACTO_RAPIDO"] = (
    (novedad_com["FLAG_COMERCIO_NUEVO"] == 1) &
    (novedad_com["MONTO_TOTAL_FRAUDE_COM"] >= umbral_monto_top20)
).astype(int)

df = df.merge(
    novedad_com[[
        C["comercio_id"],
        "PRIMER_FECHA_COMERCIO", "ULTIMO_FECHA_COMERCIO",
        "MESES_DISTINTOS_COMERCIO", "ANTIGÜEDAD_COMERCIO_DIAS",
        "FLAG_COMERCIO_NUEVO", "FLAG_COMERCIO_ALTO_IMPACTO_RAPIDO",
    ]],
    on=C["comercio_id"], how="left"
)

nuevos = df[df["FLAG_COMERCIO_NUEVO"] == 1][C["comercio_id"]].nunique()
alto_impacto = df[df["FLAG_COMERCIO_ALTO_IMPACTO_RAPIDO"] == 1][C["comercio_id"]].nunique()
print(f"  Comercios nuevos (1 mes en base)         : {nuevos:,}")
print(f"  Comercios nuevos + alto impacto (top 20%): {alto_impacto:,}")
print(f"  Umbral monto top 20%                     : {umbral_monto_top20:,.2f}")
if alto_impacto > 0:
    cols_show = [C["comercio_id"], "MESES_DISTINTOS_COMERCIO",
                 "ANTIGÜEDAD_COMERCIO_DIAS", "MONTO_TOTAL_FRAUDE_COM"]
    top_nuevos = (
        df[df["FLAG_COMERCIO_ALTO_IMPACTO_RAPIDO"] == 1]
        [[*cols_show]]
        .drop_duplicates()
        .sort_values("MONTO_TOTAL_FRAUDE_COM", ascending=False)
        .head(5)
    )
    print(f"  Top comercios fantasma:\n{top_nuevos.to_string(index=False)}")
print("  Antigüedad comercio OK ✅")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE F — Señales de MONTO
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[F] Señales de monto...")

# Monto redondo
df["FLAG_MONTO_REDONDO"] = (df[C["monto"]] % 1 == 0).astype(int)

# Desviación vs promedio del comercio
df["DESVIO_MONTO_VS_COM"] = df[C["monto"]] - df["MONTO_PROM_FRAUDE_COM"]
df["RATIO_MONTO_VS_COM"]  = (df[C["monto"]] / df["MONTO_PROM_FRAUDE_COM"].replace(0, np.nan)).round(2)

# Rango de monto
q25, q50, q75 = df[C["monto"]].quantile([0.25, 0.50, 0.75])
def rango_monto(m):
    if   m <= q25: return "BAJO"
    elif m <= q50: return "MEDIO_BAJO"
    elif m <= q75: return "MEDIO_ALTO"
    else:          return "ALTO"
df["RANGO_MONTO"] = df[C["monto"]].map(rango_monto)

# Tipo de cambio implícito (si hay monto local y dólar)
if C["monto_dolar"] in df.columns:
    df["TIPO_CAMBIO_IMPLICITO"] = (
        df[C["monto"]] / df[C["monto_dolar"]].replace(0, np.nan)
    ).round(4)

print(f"  Cuartiles monto: Q25={q25:.2f} | Q50={q50:.2f} | Q75={q75:.2f}")
print(f"  Montos redondos : {df['FLAG_MONTO_REDONDO'].sum():,} ({df['FLAG_MONTO_REDONDO'].mean()*100:.1f}%)")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE G — Flags compuestos de RIESGO (slicers Power BI)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[G] Flags compuestos de riesgo...")

# CVV estático
if C["cvv_dinamico"] and C["cvv_dinamico"] in df.columns:
    df["FLAG_CVV_ESTATICO"] = (
        df[C["cvv_dinamico"]].astype(str).str.upper().isin(["N", "NO", "0", "FALSE"])
    ).astype(int)
    cvv_flag = df["FLAG_CVV_ESTATICO"]
else:
    cvv_flag = pd.Series(0, index=df.index)

# Score de riesgo compuesto
df["SCORE_RIESGO_TRJ"] = (
    df["FLAG_TARJETA_REINCIDENTE"] +
    df["FLAG_MULTI_COMERCIO_DIA"]  +
    df["FLAG_RAFAGA_DIA"]          +
    df["FLAG_MONTO_REDONDO"]       +
    df["ES_MADRUGADA"]             +
    cvv_flag
)

df["PERFIL_RIESGO"] = pd.cut(
    df["SCORE_RIESGO_TRJ"],
    bins=[-1, 0, 1, 2, 99],
    labels=["BAJO", "MEDIO", "ALTO", "MUY_ALTO"]
)

df["FLAG_HORARIO_RIESGO"] = (
    (df["ES_MADRUGADA"] == 1) | (df["ES_FIN_SEMANA"] == 1)
).astype(int)

print(f"  PERFIL_RIESGO:\n{df['PERFIL_RIESGO'].value_counts().to_string()}")


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
    "TOTAL_FRAUDES_TARJETA", "MONTO_TOTAL_FRAUDE_TRJ", "COMERCIOS_DISTINTOS_TRJ",
    "MCC_DISTINTOS_TRJ", "CANALES_DISTINTOS_TRJ", "DIAS_ACTIVA_TRJ",
    "FRAUDES_TRJ_DIA", "MONTO_FRAUDE_TRJ_DIA", "COMERCIOS_DISTINTOS_DIA",
    "FLAG_TARJETA_REINCIDENTE", "FLAG_MULTI_COMERCIO_DIA", "FLAG_RAFAGA_DIA",
    "RATIO_MONTO_VS_SALDO", "FLAG_SALDO_AGOTADO",
    # D2 — ventanas temporales
    "TXN_CARD_2M", "TXN_CARD_5M", "TXN_CARD_10M", "TXN_CARD_1H", "TXN_CARD_24H",
    "AMT_CARD_1H", "AMT_CARD_24H",
    "FLAG_VEL_ALTA_1H", "FLAG_VEL_ALTA_10M", "FLAG_ACUM_ALTO_1H",
    # E — comercio / MCC
    "TOTAL_FRAUDES_COMERCIO", "MONTO_TOTAL_FRAUDE_COM", "MONTO_PROM_FRAUDE_COM",
    "TARJETAS_DISTINTAS_COM", "CANALES_DISTINTOS_COM", "DIAS_CON_FRAUDE_COM",
    "FRAUDES_COM_DIA", "RANKING_COMERCIO",
    "TOTAL_FRAUDES_MCC", "MONTO_TOTAL_MCC", "COMERCIOS_EN_MCC",
    "TARJETAS_EN_MCC", "RANKING_MCC",
    # E2 — antigüedad y novedad del comercio
    "PRIMER_FECHA_COMERCIO", "ULTIMO_FECHA_COMERCIO",
    "MESES_DISTINTOS_COMERCIO", "ANTIGÜEDAD_COMERCIO_DIAS",
    "FLAG_COMERCIO_NUEVO", "FLAG_COMERCIO_ALTO_IMPACTO_RAPIDO",
    # F — monto
    "FLAG_MONTO_REDONDO", "DESVIO_MONTO_VS_COM", "RATIO_MONTO_VS_COM",
    "RANGO_MONTO", "TIPO_CAMBIO_IMPLICITO",
    # G — riesgo compuesto
    "FLAG_CVV_ESTATICO", "SCORE_RIESGO_TRJ", "PERFIL_RIESGO", "FLAG_HORARIO_RIESGO",
]

print("\n" + "─" * 65)
print("VARIABLES NUEVAS AGREGADAS:")
for v in VARS_NUEVAS:
    existe = "✅" if v in df.columns else "—— (columna origen no disponible)"
    print(f"  {existe}  {v}")

print(f"\nColumnas totales en el dataset enriquecido: {df.shape[1]}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BLOQUE H — Guardar parquet enriquecido
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n[H] Guardando en: {PARQUET_OUTPUT}")
df.to_parquet(PARQUET_OUTPUT, index=False)
print(f"  ✅ Listo — {len(df):,} filas × {df.shape[1]} columnas")
print(f"  Archivo: {PARQUET_OUTPUT}")
print("─" * 65)
