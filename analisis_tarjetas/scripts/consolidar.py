"""
consolidar.py
─────────────
Lee todos los *.xlsx de data/comprometidas/ y los une en un solo parquet.

Mismo flujo que ecommerce_comercio:
  · Header en fila 5 → skiprows=4
  · Todo como texto para preservar ceros iniciales
  · Construye TARJETA desde dos columnas: col1[:6] + col2 + col1[12:]
  · Construye FECHA_HORA desde ACF-FECHA TRX + ACF-HORA TRX
  · Genera BIN_10, BIN_11, BIN_12
  · Salida: data/consolidado.parquet
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    COLS, SKIPROWS, FOLDER_JOURNALS, PARQUET_CONSOLIDADO, ANALISIS_NOMBRE,
)

C = COLS


# ─────────────────────────────────────────────────────────────────────────────
# 1. LOCALIZAR ARCHIVOS
# ─────────────────────────────────────────────────────────────────────────────
archivos = sorted(FOLDER_JOURNALS.glob("*.xlsx"))
if not archivos:
    archivos = sorted(FOLDER_JOURNALS.glob("*.xls"))

if not archivos:
    print(f"\n❌  No se encontraron archivos Excel en: {FOLDER_JOURNALS}")
    print("    Pon los journals de Monitor en esa carpeta y vuelve a ejecutar.")
    sys.exit(1)

print("═" * 65)
print(f"CONSOLIDADOR — {ANALISIS_NOMBRE}")
print("═" * 65)
print(f"  Carpeta : {FOLDER_JOURNALS}")
print(f"  Archivos: {len(archivos)}\n")


# ─────────────────────────────────────────────────────────────────────────────
# 2. CARGA DE CADA JOURNAL
# ─────────────────────────────────────────────────────────────────────────────
def cargar_journal(ruta: Path) -> pd.DataFrame:
    etiqueta = ruta.stem
    df = pd.read_excel(ruta, skiprows=SKIPROWS, dtype=str, header=0)
    df.dropna(how="all", inplace=True)
    df.columns = df.columns.str.strip()

    for col_key in ["monto", "monto_dolar"]:
        col_val = C.get(col_key, "")
        if col_val and col_val in df.columns:
            df[col_val] = (
                df[col_val].str.strip()
                .str.replace(",", "", regex=False)
                .pipe(pd.to_numeric, errors="coerce")
            )

    q_col = C.get("q_transaccional", "")
    if q_col and q_col in df.columns:
        df[q_col] = pd.to_numeric(df[q_col], errors="coerce")

    df["ARCHIVO_ORIGEN"] = etiqueta
    print(f"  ✅ {etiqueta:35s} → {len(df):>6,} filas")
    return df


partes = []
for ruta in archivos:
    df_part = cargar_journal(ruta)
    if not df_part.empty:
        partes.append(df_part)

if not partes:
    print("❌  Ningún archivo pudo cargarse.")
    sys.exit(1)

df = pd.concat(partes, ignore_index=True)
print(f"\n  📦 Total bruto: {len(df):,} filas | {df.shape[1]} columnas")


# ─────────────────────────────────────────────────────────────────────────────
# 3. CONSTRUCCIÓN DE TARJETA DESENCRIPTADA
# ─────────────────────────────────────────────────────────────────────────────
col1 = C.get("tarjeta_col1", "")
col2 = C.get("tarjeta_col2", "")

if col1 in df.columns and col2 in df.columns:
    df["TARJETA"] = (
        df[col1].astype(str).str.strip().str[:6]
        + df[col2].astype(str).str.strip()
        + df[col1].astype(str).str.strip().str[12:]
    )
    df["TARJETA"] = df["TARJETA"].str.replace("nan", "", regex=False)
    print(f"  ✅ TARJETA construida — {df['TARJETA'].nunique():,} únicas")
elif col1 in df.columns:
    df["TARJETA"] = df[col1].astype(str).str.strip()
    print(f"  ⚠️  TARJETA desde col1 solamente (col2 no encontrada)")
else:
    df["TARJETA"] = ""
    print(f"  ⚠️  No se pudo construir TARJETA — revisa config.py")


# ─────────────────────────────────────────────────────────────────────────────
# 4. BIN EXTENDIDOS
# ─────────────────────────────────────────────────────────────────────────────
for n in [10, 11, 12]:
    df[f"BIN_{n}"] = df["TARJETA"].str[:n]
print(f"  ✅ BIN_10, BIN_11, BIN_12 generados")


# ─────────────────────────────────────────────────────────────────────────────
# 5. CONSTRUCCIÓN DE FECHA_HORA
# ─────────────────────────────────────────────────────────────────────────────
col_fecha = C["fecha_trx"]
col_hora  = C["hora_trx"]
col_fh    = C["fecha_hora"]

if col_fecha in df.columns:
    df["_fecha_dt"] = pd.to_datetime(
        df[col_fecha].str.strip(), format="%Y%m%d", errors="coerce"
    )
    if col_hora in df.columns:
        fh_str = df["_fecha_dt"].dt.strftime("%Y-%m-%d") + " " + df[col_hora].str.strip()
        df[col_fh] = pd.to_datetime(fh_str, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    else:
        df[col_fh] = df["_fecha_dt"]
    df.drop(columns=["_fecha_dt"], inplace=True)
    nulos = df[col_fh].isna().sum()
    print(f"  ✅ FECHA_HORA construida  |  nulos: {nulos:,}")
else:
    print(f"  ⚠️  Columna fecha '{col_fecha}' no encontrada")


# ─────────────────────────────────────────────────────────────────────────────
# 6. NORMALIZAR TEXTO
# ─────────────────────────────────────────────────────────────────────────────
cols_texto = [
    "id_cliente", "bin", "comercio_nom", "canal", "tipo_producto",
    "segmento", "indicador", "cod_respuesta", "razon_respuesta",
    "eci", "cod_red_comercio", "pais", "entry_mode", "billetera",
    "ind_recurrente", "mcc", "marca",
]
for col_key in cols_texto:
    col_val = C.get(col_key, "")
    if col_val and col_val in df.columns:
        df[col_val] = df[col_val].astype(str).str.strip().str.upper()

col_bin = C.get("bin", "")
if col_bin in df.columns:
    df[col_bin] = df[col_bin].str.split(".").str[0]

col_org = C.get("organizacion", "")
if col_org in df.columns:
    df[col_org] = df[col_org].astype(str).str.split(".").str[0].str.strip()


# ─────────────────────────────────────────────────────────────────────────────
# 7. RESUMEN
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 65)
print("RESUMEN DEL CONSOLIDADO")
print("═" * 65)
print(f"  Filas totales    : {len(df):,}")
print(f"  Columnas         : {df.shape[1]}")

if col_fh in df.columns:
    print(f"  Rango de fechas  : {df[col_fh].min()}  →  {df[col_fh].max()}")
if "TARJETA" in df.columns:
    print(f"  Tarjetas únicas  : {df['TARJETA'].nunique():,}")

col_cli = C.get("id_cliente", "")
if col_cli in df.columns:
    print(f"  Clientes únicos  : {df[col_cli].nunique():,}")

print(f"\n  Archivos cargados:")
print(df["ARCHIVO_ORIGEN"].value_counts().sort_index().to_string(header=False))

col_ind = C.get("indicador", "")
if col_ind and col_ind in df.columns:
    print(f"\n  Indicador de fraude (F/N/G/P/D):")
    print(df[col_ind].value_counts().to_string(header=False))

col_monto = C.get("monto", "")
if col_monto and col_monto in df.columns:
    v = df[col_monto].dropna()
    print(f"\n  Monto S/ — min:{v.min():,.2f}  mediana:{v.median():,.2f}  max:{v.max():,.2f}")


# ─────────────────────────────────────────────────────────────────────────────
# 8. GUARDAR
# ─────────────────────────────────────────────────────────────────────────────
PARQUET_CONSOLIDADO.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(PARQUET_CONSOLIDADO, index=False)
print(f"\n✅ Guardado: {PARQUET_CONSOLIDADO}")
print(f"   {len(df):,} filas × {df.shape[1]} columnas")
print("═" * 65)
