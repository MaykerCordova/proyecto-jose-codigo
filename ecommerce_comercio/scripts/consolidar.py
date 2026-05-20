"""
consolidar.py
─────────────
Lee todos los *.xlsx de data/journals/ y los une en un solo parquet.

Reglas de carga:
  · Header en fila 4 → skiprows=3
  · Todo como texto (dtype=str) excepto ACF-MONTO EN MONEDA LOCAL y ACF-MONTO DOLLAR
  · Construye FECHA_HORA desde ACF-FECHA TRX (AAAAMMDD) + ACF-HORA TRX (HH:MM:SS)
  · Agrega flags temporales: HORA, DIA_SEMANA, MES_NUM, ES_FINDE, ES_MADRUGADA
  · Salida: data/consolidado.parquet
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    COLS, SKIPROWS, FOLDER_JOURNALS, PARQUET_CONSOLIDADO,
    COMERCIO_NOMBRE,
)

C = COLS   # alias

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

print("═" * 60)
print(f"CONSOLIDADOR — {COMERCIO_NOMBRE}")
print("═" * 60)
print(f"  Carpeta: {FOLDER_JOURNALS}")
print(f"  Archivos encontrados: {len(archivos)}\n")


# ─────────────────────────────────────────────────────────────────────────────
# 2. CARGA DE CADA JOURNAL
# ─────────────────────────────────────────────────────────────────────────────
def cargar_journal(ruta: Path) -> pd.DataFrame:
    etiqueta = ruta.stem   # nombre del archivo sin extensión → QUINCENA

    df = pd.read_excel(
        ruta,
        skiprows=SKIPROWS,
        dtype=str,
        header=0,
    )

    # Eliminar filas completamente vacías
    df.dropna(how="all", inplace=True)

    # Limpiar espacios en nombres de columnas
    df.columns = df.columns.str.strip()

    # Castear montos a float
    for col_key in ["monto", "monto_dolar"]:
        col_val = C.get(col_key, "")
        if col_val and col_val in df.columns:
            df[col_val] = (
                df[col_val]
                .str.strip()
                .str.replace(",", "", regex=False)
                .pipe(pd.to_numeric, errors="coerce")
            )

    df["QUINCENA"] = etiqueta
    print(f"  ✅ {etiqueta:30s} → {len(df):>6,} filas | {df.shape[1]} cols")
    return df


partes = []
for ruta in archivos:
    df_part = cargar_journal(ruta)
    if not df_part.empty:
        partes.append(df_part)

if not partes:
    print("❌  Ningún archivo pudo cargarse. Revisa los Excel.")
    sys.exit(1)

df = pd.concat(partes, ignore_index=True)
print(f"\n  📦 Total consolidado: {len(df):,} filas | {df.shape[1]} columnas")


# ─────────────────────────────────────────────────────────────────────────────
# 3. CONSTRUCCIÓN DE FECHA_HORA
# ─────────────────────────────────────────────────────────────────────────────
col_fecha = C["fecha_trx"]
col_hora  = C["hora_trx"]
col_fh    = C["fecha_hora"]

tiene_fecha = col_fecha in df.columns
tiene_hora  = col_hora  in df.columns

if not tiene_fecha:
    print(f"\n⚠️  Columna '{col_fecha}' no encontrada — FECHA_HORA no se construye")
else:
    df["_fecha_dt"] = pd.to_datetime(
        df[col_fecha].str.strip(), format="%Y%m%d", errors="coerce"
    )

    if tiene_hora:
        fh_str = (
            df["_fecha_dt"].dt.strftime("%Y-%m-%d") + " " + df[col_hora].str.strip()
        )
        df[col_fh] = pd.to_datetime(fh_str, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    else:
        print(f"  ⚠️  Columna '{col_hora}' no encontrada — FECHA_HORA solo tendrá fecha")
        df[col_fh] = df["_fecha_dt"]

    df.drop(columns=["_fecha_dt"], inplace=True)

    # Flags temporales
    df["HORA"]         = df[col_fh].dt.hour
    df["DIA_SEMANA"]   = df[col_fh].dt.day_name()
    df["MES_NUM"]      = df[col_fh].dt.month
    df["ES_FINDE"]     = df[col_fh].dt.dayofweek.isin([5, 6]).astype(int)
    df["ES_MADRUGADA"] = df["HORA"].between(0, 5).astype(int)

    nulos_fh = df[col_fh].isna().sum()
    if nulos_fh:
        print(f"  ⚠️  {nulos_fh:,} filas con FECHA_HORA nula — revisa formato en Monitor")
    else:
        print(f"  ✅ FECHA_HORA construida sin nulos")


# ─────────────────────────────────────────────────────────────────────────────
# 4. RESUMEN
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 60)
print("RESUMEN DEL CONSOLIDADO")
print("═" * 60)
print(f"  Filas totales   : {len(df):,}")
print(f"  Columnas        : {df.shape[1]}")

if col_fh in df.columns:
    print(f"  Rango de fechas : {df[col_fh].min()}  →  {df[col_fh].max()}")

print(f"\n  Distribución por archivo (QUINCENA):")
print(df["QUINCENA"].value_counts().sort_index().to_string(header=False))

col_ind = C.get("indicador", "")
if col_ind and col_ind in df.columns:
    print(f"\n  Distribución por Indicador ({col_ind}):")
    print(df[col_ind].value_counts().to_string(header=False))

col_monto = C.get("monto", "")
if col_monto and col_monto in df.columns:
    print(f"\n  Monto (S/):")
    print(f"    Mín     : {df[col_monto].min():>12,.2f}")
    print(f"    Mediana : {df[col_monto].median():>12,.2f}")
    print(f"    Media   : {df[col_monto].mean():>12,.2f}")
    print(f"    Máx     : {df[col_monto].max():>12,.2f}")
    print(f"    Nulos   : {df[col_monto].isna().sum():>12,}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. GUARDAR PARQUET
# ─────────────────────────────────────────────────────────────────────────────
PARQUET_CONSOLIDADO.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(PARQUET_CONSOLIDADO, index=False)

print(f"\n✅ Consolidado guardado en: {PARQUET_CONSOLIDADO}")
print(f"   {len(df):,} filas × {df.shape[1]} columnas")
