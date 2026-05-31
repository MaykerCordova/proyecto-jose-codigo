# =============================================================================
# CONSOLIDADO HERRAMIENTAS - VERSIÓN ORIGINAL (código estructurado/espagueti)
# Transcrito desde: codigo_test_consolidadoV2.ipynb
# =============================================================================

# IMPORTS
# ----------------------------------------------------------------------
import pandas as pd
import polars as pl
import pyodbc
from pathlib import Path
import unicodedata
import re
import time

DEBUG = False
pd.set_option("display.max_columns", 200)

# RUTAS
# ----------------------------------------------------------------------
DATA_DIR            = Path(r"C:\Users\s4930359\Data_Herramientas\data\silver")
VRM_PARQUET         = DATA_DIR / "vrm_gold.parquet"
RT_DEBITO_PARQUET   = DATA_DIR / "rt_debito_gold.parquet"
RT_CREDITO_PARQUET  = DATA_DIR / "rt_credito_consolidated.parquet"
VCAS_PARQUET        = DATA_DIR / "VCAS_unitario.parquet"
RUTA_BD_FRM         = r"C:\Users\s4930359\Data_Herramientas\BBDD_FRM\BBDD_FRM.accdb"

OUT_DIR             = Path(r"C:\Users\s4930359\OneDrive - The Bank of Nova Scotia\Seguimiento_Consolidado_Herramientas")
MASTER_OUT_PARQUET  = OUT_DIR / "MASTER_CONSOLIDADO.parquet"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# VALIDACIONES INICIALES
# ----------------------------------------------------------------------
for p in [VRM_PARQUET, RT_DEBITO_PARQUET, RT_CREDITO_PARQUET]:
    if not p.exists():
        raise FileNotFoundError(f"❌ No existe el parquet: {p}")

# HELPERS
# ----------------------------------------------------------------------
def normalize_colname(col: str) -> str:
    col = str(col).strip().lower()
    col = unicodedata.normalize("NFKD", col)
    col = "".join(c for c in col if not unicodedata.combining(c))
    col = re.sub(r"\s+", " ", col)
    return col

def normalize_columns_pd(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [normalize_colname(c) for c in df.columns]
    return df

def normalize_columns_pl(df: pl.LazyFrame) -> pl.LazyFrame:
    return df.rename({c: normalize_colname(c) for c in df.schema})

def read_access(path_accdb: str, sql: str) -> pd.DataFrame:
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={path_accdb};"
    )
    with pyodbc.connect(conn_str) as conn:
        return pd.read_sql(sql, conn)

# MASTER SCHEMA
# ----------------------------------------------------------------------
MASTER_COLS = [
    "fecha",
    "monto_usd",
    "tarjeta_final",
    "bin",
    "nombre_comercio",
    "entry_mode",
    "codigo_pais",
    "concresultado_vcas",
    "acf_tvr",
    "herramienta",
    "mcc",
    "STIP",
]

SYNONYMS = {
    "fecha": [
        "fecha", "acf-fecha", "RT-Fecha TRX", "ACF_Fecha_TRX"
    ],
    "monto_usd": [
        "monto usd", "monto", "acf-monto unico", "acf-monto dollar",
        "Monto USD", "RT-Monto TRX"
    ],
    "bin": [
        "bin", "acf-bin"
    ],
    "nombre_comercio": [
        "nombre de comercio", "comercio", "acf-nombre comercio",
        "acf-nombre/localizacion comercio", "Merchant Country", "RT-Nombre Comercio"
    ],
    "entry_mode": [
        "entry mode", "acf-entry mode"
    ],
    "codigo_pais": [
        "codigo pais", "merchant country",
        "acf-pais origen 87519",
        "de61.13 pais del pos", "Merchant Country"
    ],
    "concresultado_vcas": [
        "reglas concaresultado", "concaresultado vcas", "'Reglas CONCARESULTADO"
    ],
    "acf_tvr": [
        "ACF-TVR"
    ],
    "tarjeta_final": [
        "ACF-Tarjeta SHA256", "ACF-TARJETA REGISTRO 750",
        "NUMERO DE TARJETA", "TARJETA", "Tarjeta"
    ],
    "mcc": [
        "ACF-MCC +"
    ],
    "STIP": [
        "STIP Reason Code"
    ],
}

SYNONYMS_NORM = {
    k: [normalize_colname(v) for v in vals]
    for k, vals in SYNONYMS.items()
}

# SINÓNIMOS + PARSEO
# ----------------------------------------------------------------------
def apply_synonyms_pd(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for master_col, candidates in SYNONYMS_NORM.items():
        for c in candidates:
            if c in df.columns:
                df[master_col] = df[c]
                break
    return df

def apply_synonyms_pl(df: pl.LazyFrame) -> pl.LazyFrame:
    exprs = []
    schema = df.schema
    for master_col, candidates in SYNONYMS_NORM.items():
        for c in candidates:
            if c in schema:
                exprs.append(pl.col(c).alias(master_col))
                break
        else:
            exprs.append(pl.lit(None).alias(master_col))
    return df.with_columns(exprs)

def parse_fecha_pd(df: pd.DataFrame, col: str = "fecha") -> pd.DataFrame:
    if col in df.columns:
        df[col] = (
            pd.to_datetime(df[col], errors="coerce", dayfirst=True, infer_datetime_format=True)
            .dt.floor("ms")
        )
    return df

def parse_fecha_pl(df: pl.LazyFrame, col: str = "fecha") -> pl.LazyFrame:
    schema = df.collect_schema()
    if col in schema:
        return df.with_columns(
            pl.when(pl.col(col).cast(pl.Utf8).str.contains("/"))
            .then(
                pl.col(col)
                .cast(pl.Utf8)
                .str.strptime(pl.Date, format="%d/%m/%Y", strict=False)
                .cast(pl.Datetime("ms"))
            )
            .otherwise(
                pl.col(col).cast(pl.Date).cast(pl.Datetime("ms"))
            )
            .alias(col)
        )
    return df

def pandas_to_polars_with_fecha(df: pd.DataFrame) -> pl.LazyFrame:
    lf = pl.from_pandas(df).lazy()
    if "fecha" in lf.collect_schema():
        lf = lf.with_columns(pl.col("fecha").cast(pl.Datetime("ms")))
    return lf

# EXTRACCIÓN
# ----------------------------------------------------------------------
t0 = time.time()

# ----- VCAS
df_vcas = (
    pl.scan_parquet(VCAS_PARQUET)
    .pipe(normalize_columns_pl)
    .pipe(apply_synonyms_pl)
    .pipe(parse_fecha_pl)
    .with_columns(pl.lit("VCAS").alias("herramienta"))
)

# ----- FRM
df_frm = read_access(RUTA_BD_FRM, "SELECT * FROM BBDD_FRM")
df_frm = normalize_columns_pd(df_frm)
df_frm = apply_synonyms_pd(df_frm)
df_frm = parse_fecha_pd(df_frm)

cond  = df_frm["condicion"].astype("string").str.strip()
de39  = df_frm["de39 resp de autorizacion"].astype("string").str.strip()
df_frm = df_frm[
    (cond.isna() | (cond == "") | (~cond.isin(["NM", "RD"])))
    & (de39 == "63")
]
df_frm["herramienta"] = "FRM"

# ----- VRM
df_vrm = (
    pl.scan_parquet(VRM_PARQUET)
    .pipe(normalize_columns_pl)
    .pipe(apply_synonyms_pl)
    .pipe(parse_fecha_pl)
    .with_columns(pl.lit("VRM").alias("herramienta"))
)

# ----- RT DÉBITO
df_rt_d = (
    pl.scan_parquet(RT_DEBITO_PARQUET)
    .pipe(normalize_columns_pl)
    .pipe(apply_synonyms_pl)
    .pipe(parse_fecha_pl)
    .with_columns(pl.lit("RT_DEBITO").alias("herramienta"))
)

# ----- RT CRÉDITO
df_rt_c = (
    pl.scan_parquet(RT_CREDITO_PARQUET)
    .pipe(normalize_columns_pl)
    .pipe(apply_synonyms_pl)
    .pipe(parse_fecha_pl)
    .with_columns(pl.lit("RT_CREDITO").alias("herramienta"))
)

# ESTANDARIZACIÓN MASTER
# ----------------------------------------------------------------------
def to_master_pd(df: pd.DataFrame) -> pd.DataFrame:
    for c in MASTER_COLS:
        if c not in df.columns:
            df[c] = pd.NA
    return df[MASTER_COLS]

def to_master_pl(df: pl.LazyFrame) -> pl.LazyFrame:
    schema = df.collect_schema()
    return df.select([
        pl.col(c) if c in schema else pl.lit(None).alias(c)
        for c in MASTER_COLS
    ])

std_vcas  = to_master_pl(df_vcas)
std_frm   = to_master_pd(df_frm)
std_vrm   = to_master_pl(df_vrm)
std_rt_d  = to_master_pl(df_rt_d)
std_rt_c  = to_master_pl(df_rt_c)

# UNION FINAL
# ----------------------------------------------------------------------
master_lazy = pl.concat(
    [
        std_vcas,
        pandas_to_polars_with_fecha(std_frm),
        std_vrm,
        std_rt_d,
        std_rt_c,
    ],
    how="vertical_relaxed",
)

master = master_lazy.collect()

# OUTPUT
# ----------------------------------------------------------------------
master.write_parquet(MASTER_OUT_PARQUET)

# VALIDACIONES FINALES
# ----------------------------------------------------------------------
print("✅ MASTER CONSOLIDADO GENERADO")
print(f"Filas totales: {master.height:,}")
print("📅 FECHA:")
print("  Tipo:", master.schema["fecha"])
print("  Min:", master["fecha"].min())
print("  Max:", master["fecha"].max())
print("  % Nulos:", round(master["fecha"].null_count() / master.height * 100, 2), "%")
print(f"🕐 Tiempo total: {time.time() - t0:.2f} segundos")
