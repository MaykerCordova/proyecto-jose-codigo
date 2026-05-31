"""
transformaciones.py — Funciones puras de limpieza y parseo.

Son funciones, no clases, porque no guardan estado: reciben datos,
devuelven datos transformados y no dependen de nada externo.
"""
import re
import unicodedata

import pandas as pd
import polars as pl
import pyodbc


# ---------------------------------------------------------------------------
# Normalización de nombres de columna
# ---------------------------------------------------------------------------

def normalizar_nombre_columna(col: str) -> str:
    """
    Convierte un nombre de columna a formato estándar:
    minúsculas, sin tildes, sin espacios dobles, sin espacios al inicio/fin.

    Ejemplo: "ACF-Fecha TRX" → "acf-fecha trx"
    """
    col = str(col).strip().lower()
    col = unicodedata.normalize("NFKD", col)
    col = "".join(c for c in col if not unicodedata.combining(c))
    col = re.sub(r"\s+", " ", col)
    return col


def normalizar_columnas_pd(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica normalizar_nombre_columna a todas las columnas de un DataFrame pandas."""
    df = df.copy()
    df.columns = [normalizar_nombre_columna(c) for c in df.columns]
    return df


def normalizar_columnas_pl(df: pl.LazyFrame) -> pl.LazyFrame:
    """Aplica normalizar_nombre_columna a todas las columnas de un LazyFrame polars."""
    schema = df.collect_schema()
    return df.rename({c: normalizar_nombre_columna(c) for c in schema})


# ---------------------------------------------------------------------------
# Parseo de fechas
# ---------------------------------------------------------------------------

def parsear_fecha_pd(df: pd.DataFrame, columna: str = "fecha") -> pd.DataFrame:
    """
    Convierte la columna de fecha a datetime en pandas.
    Usa dayfirst=True porque las fechas del banco vienen en formato DD/MM/YYYY.
    Trunca a milisegundos para consistencia con polars.
    """
    if columna in df.columns:
        df[columna] = (
            pd.to_datetime(df[columna], errors="coerce", dayfirst=True)
            .dt.floor("ms")
        )
    return df


def parsear_fecha_pl(df: pl.LazyFrame, columna: str = "fecha") -> pl.LazyFrame:
    """
    Convierte la columna de fecha a Datetime("ms") en polars.

    Detecta el formato automáticamente:
    - Si contiene "/" → asume DD/MM/YYYY (formato texto de algunas fuentes)
    - Si no contiene "/" → asume que ya es un tipo Date o numérico casteable
    """
    schema = df.collect_schema()
    if columna not in schema:
        return df
    return df.with_columns(
        pl.when(pl.col(columna).cast(pl.Utf8).str.contains("/"))
        .then(
            pl.col(columna)
            .cast(pl.Utf8)
            .str.strptime(pl.Date, format="%d/%m/%Y", strict=False)
            .cast(pl.Datetime("ms"))
        )
        .otherwise(
            pl.col(columna).cast(pl.Date).cast(pl.Datetime("ms"))
        )
        .alias(columna)
    )


def pandas_a_polars_con_fecha(df: pd.DataFrame) -> pl.LazyFrame:
    """
    Convierte un DataFrame pandas a polars LazyFrame asegurando que
    la columna 'fecha' quede como Datetime("ms") (tipo requerido por el concat final).
    """
    lf = pl.from_pandas(df).lazy()
    if "fecha" in lf.collect_schema():
        lf = lf.with_columns(pl.col("fecha").cast(pl.Datetime("ms")))
    return lf


# ---------------------------------------------------------------------------
# Lectura de fuentes externas
# ---------------------------------------------------------------------------

def leer_access(ruta_accdb: str, sql: str) -> pd.DataFrame:
    """
    Lee una tabla o consulta desde una base de datos Access (.accdb).
    Usa pyodbc porque polars no tiene soporte nativo para Access.
    """
    cadena_conexion = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={ruta_accdb};"
    )
    with pyodbc.connect(cadena_conexion) as conn:
        return pd.read_sql(sql, conn)
