"""
consolidar.py — Carga y limpieza de la base de reclamos
Base 8850 / Master File — Scotiabank Peru — Prevención de Fraude

Lee el archivo Excel/CSV de reclamos, aplica el filtro de segmento
definido en config.py y guarda reclamos_raw.parquet listo para
feature_engineering.py.

Uso:
    python scripts/consolidar.py
    python scripts/consolidar.py ruta/al/archivo.xlsx
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
    COLS, PARQUET_RAW, FOLDER_DATA, SEGMENTO_FOCO,
    PERIODO_INICIO, PERIODO_FIN, SKIPROWS,
    FILTRO_MARCA,
)

C = COLS

print("═" * 65)
print("CONSOLIDAR — BASE DE RECLAMOS")
print(f"  Segmento foco : {SEGMENTO_FOCO}")
print(f"  Período       : {PERIODO_INICIO} → {PERIODO_FIN}")
print("═" * 65)


# ─── LOCALIZAR EL ARCHIVO ────────────────────────────────────────────────────

if len(sys.argv) > 1:
    ruta_archivo = Path(sys.argv[1])
else:
    # Buscar automáticamente en data/ con extensiones conocidas
    extensiones = ["*.xlsx", "*.xls", "*.csv", "*.txt"]
    candidatos  = []
    for ext in extensiones:
        candidatos.extend(FOLDER_DATA.glob(ext))
    candidatos = [c for c in candidatos if "reclamos" in c.name.lower() or "master" in c.name.lower()]

    if not candidatos:
        print("\n❌  No se encontró archivo de reclamos en data/")
        print("    Opciones:")
        print("    1. Copia el archivo Excel a data/ con 'reclamos' en el nombre")
        print("    2. Pasa la ruta como argumento: python scripts/consolidar.py ruta/archivo.xlsx")
        sys.exit(1)

    ruta_archivo = candidatos[0]
    print(f"  Archivo encontrado: {ruta_archivo.name}")

if not ruta_archivo.exists():
    print(f"\n❌  Archivo no encontrado: {ruta_archivo}")
    sys.exit(1)


# ─── CARGAR EL ARCHIVO ───────────────────────────────────────────────────────

ext = ruta_archivo.suffix.lower()
print(f"\nCargando {ruta_archivo.name} ...")

if ext in [".xlsx", ".xls"]:
    df = pd.read_excel(ruta_archivo, skiprows=SKIPROWS, dtype=str)
elif ext in [".csv", ".txt"]:
    # Intentar separadores comunes
    for sep in [",", ";", "\t", "|"]:
        try:
            df = pd.read_csv(ruta_archivo, skiprows=SKIPROWS, dtype=str, sep=sep, encoding="latin-1")
            if df.shape[1] > 5:
                break
        except Exception:
            continue
else:
    print(f"❌  Extensión no soportada: {ext}")
    sys.exit(1)

df.columns = df.columns.str.strip()
print(f"  Filas brutas  : {len(df):,}")
print(f"  Columnas      : {df.shape[1]}")


# ─── DIAGNÓSTICO DE COLUMNAS ─────────────────────────────────────────────────

cols_reales   = set(df.columns)
cols_config   = {k: v for k, v in C.items() if v}
cols_faltantes = {k: v for k, v in cols_config.items() if v not in cols_reales}

if cols_faltantes:
    print(f"\n⚠️  Columnas en config.py que NO existen en el archivo ({len(cols_faltantes)}):")
    for k, v in cols_faltantes.items():
        print(f"   COLS['{k}'] = '{v}'")
    print("\n  TIP: Abre el archivo y copia el nombre EXACTO de la columna en config.py")
else:
    print("\n  ✅ Todas las columnas del config.py encontradas en el archivo")


# ─── CONSTRUIR FECHA_HORA ─────────────────────────────────────────────────────

col_fec = C.get("fecha_txn", "")
col_hor = C.get("hora_txn", "")
col_fh  = C.get("fecha_hora", "FECHA_HORA")

if col_fec in df.columns and col_hor in df.columns:
    df[col_fh] = pd.to_datetime(
        df[col_fec].astype(str).str.strip() + " " + df[col_hor].astype(str).str.strip(),
        errors="coerce"
    )
    nulos_fh = df[col_fh].isna().sum()
    print(f"\n  FECHA_HORA construida — {nulos_fh:,} nulos ({nulos_fh/len(df)*100:.1f}%)")
elif col_fec in df.columns:
    df[col_fh] = pd.to_datetime(df[col_fec], errors="coerce")
    print(f"\n  FECHA_HORA desde {col_fec} (sin hora exacta)")
else:
    print(f"\n⚠️  No se pudo construir FECHA_HORA — revisar config.py")
    df[col_fh] = pd.NaT


# ─── FILTRAR POR PERÍODO ──────────────────────────────────────────────────────

n_antes = len(df)
if df[col_fh].notna().any():
    df = df[
        df[col_fh].between(pd.Timestamp(PERIODO_INICIO), pd.Timestamp(PERIODO_FIN))
    ]
    print(f"  Filtro período : {n_antes:,} → {len(df):,} filas")


# ─── FILTRAR POR SEGMENTO ─────────────────────────────────────────────────────

filtro = FILTRO_MARCA.get(SEGMENTO_FOCO, {})
col_tp    = C.get("tipo_producto", "")
col_marca = C.get("marca", "")

n_antes = len(df)
if filtro and "tipo" in filtro and col_tp in df.columns:
    _tipo_vals = [v.upper() for v in filtro["tipo"]]
    mask_tipo  = df[col_tp].astype(str).str.strip().str.upper().isin(_tipo_vals)
    df = df[mask_tipo]

if filtro and "marca" in filtro and filtro["marca"] and col_marca in df.columns:
    _marca_vals = [v.upper() for v in filtro["marca"]]
    # Filtrar por primer dígito O por texto de marca
    _marca_col  = df[col_marca].astype(str).str.strip().str.upper()
    mask_marca  = _marca_col.isin(_marca_vals) | _marca_col.str[:1].isin(_marca_vals)
    df = df[mask_marca]

if filtro:
    print(f"  Filtro {SEGMENTO_FOCO} : {n_antes:,} → {len(df):,} filas")
else:
    print(f"  Filtro TODOS    : sin filtro de segmento")


# ─── ELIMINAR DUPLICADOS ──────────────────────────────────────────────────────

col_hash = C.get("cod_hash", "")
n_antes  = len(df)
if col_hash and col_hash in df.columns:
    df = df.drop_duplicates(subset=[col_hash])
    print(f"  Deduplicación  : {n_antes:,} → {len(df):,} filas (por hash)")
else:
    # Fallback: deduplicar por fecha + monto + cliente
    _dedup_cols = [c for c in [col_fh, C.get("id_cliente",""), C.get("monto","")]
                   if c and c in df.columns]
    if _dedup_cols:
        df = df.drop_duplicates(subset=_dedup_cols)
        print(f"  Deduplicación  : {n_antes:,} → {len(df):,} filas (por fecha+monto+cliente)")

df = df.reset_index(drop=True)


# ─── RESUMEN FINAL ────────────────────────────────────────────────────────────

col_monto = C.get("monto", "")
if col_monto in df.columns:
    df[col_monto] = pd.to_numeric(
        df[col_monto].astype(str).str.strip().str.replace(",", ".", regex=False),
        errors="coerce"
    )
    print(f"\n  Monto total (S/): {df[col_monto].sum():,.2f}")
    print(f"  Monto promedio  : S/{df[col_monto].mean():,.2f}")
    print(f"  Monto mediana   : S/{df[col_monto].median():,.2f}")

col_cli = C.get("id_cliente", "")
if col_cli in df.columns:
    print(f"  Clientes únicos : {df[col_cli].nunique():,}")

col_fec_rec = C.get("fecha_reclamo", "")
if col_fec_rec and col_fec_rec in df.columns:
    df[col_fec_rec] = pd.to_datetime(df[col_fec_rec], errors="coerce")
    n_sin_reclamo = df[col_fec_rec].isna().sum()
    print(f"  Con fecha_reclamo : {df[col_fec_rec].notna().sum():,}")
    if n_sin_reclamo > 0:
        print(f"  ⚠️  Sin fecha_reclamo: {n_sin_reclamo:,} — revisar")


# ─── GUARDAR ─────────────────────────────────────────────────────────────────

os.makedirs(FOLDER_DATA, exist_ok=True)
df.to_parquet(str(PARQUET_RAW), index=False)

print(f"\n  ✅ Guardado: {PARQUET_RAW}")
print(f"     Shape: {df.shape}")
print("═" * 65)
print("CONSOLIDAR COMPLETO ✅")
print("═" * 65)
print("\nSiguiente paso: python scripts/feature_engineering.py")
