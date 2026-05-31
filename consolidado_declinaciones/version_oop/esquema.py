"""
esquema.py — Define el esquema estándar del consolidado.

¿Por qué una clase?
    EsquemaMaster agrupa dos cosas que siempre van juntas:
    1. QUÉ columnas tiene el master (COLUMNAS_MASTER)
    2. CÓMO se llaman esas columnas en cada fuente (SINONIMOS)
    Además expone métodos para aplicar esa lógica a pandas y a polars.
    Sin esta clase, esas tres responsabilidades estarían dispersas en
    variables globales y funciones sueltas, difíciles de mantener juntas.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import polars as pl

from transformaciones import normalizar_nombre_columna


# ---------------------------------------------------------------------------
# Definición de columnas y sinónimos (datos de configuración)
# ---------------------------------------------------------------------------

COLUMNAS_MASTER: list[str] = [
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

# Cada clave es el nombre estándar en el master.
# Cada valor es la lista de nombres posibles en las fuentes (en orden de prioridad).
SINONIMOS_BRUTOS: dict[str, list[str]] = {
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


# ---------------------------------------------------------------------------
# Clase principal
# ---------------------------------------------------------------------------

@dataclass
class EsquemaMaster:
    """
    Encapsula el esquema estándar del consolidado y la lógica para:
    - Mapear columnas de cualquier fuente al nombre estándar (sinónimos)
    - Estandarizar un DataFrame al esquema final (solo columnas master)

    Admite tanto pandas (para FRM/Access) como polars (para el resto).
    """

    columnas: list[str] = field(default_factory=lambda: list(COLUMNAS_MASTER))
    sinonimos_brutos: dict[str, list[str]] = field(
        default_factory=lambda: dict(SINONIMOS_BRUTOS)
    )

    def __post_init__(self) -> None:
        # Pre-normaliza los sinónimos una sola vez al construir el esquema
        self.sinonimos_norm: dict[str, list[str]] = {
            col_master: [normalizar_nombre_columna(s) for s in lista]
            for col_master, lista in self.sinonimos_brutos.items()
        }

    # ------------------------------------------------------------------
    # Aplicar sinónimos: renombra columnas al nombre master
    # ------------------------------------------------------------------

    def aplicar_sinonimos_pd(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Para cada columna master, busca cuál candidato existe en el DataFrame
        pandas y lo renombra. Si no encuentra ninguno, no hace nada.
        """
        df = df.copy()
        for col_master, candidatos in self.sinonimos_norm.items():
            for candidato in candidatos:
                if candidato in df.columns:
                    df[col_master] = df[candidato]
                    break
        return df

    def aplicar_sinonimos_pl(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """
        Para cada columna master, busca cuál candidato existe en el schema polars
        y lo alias al nombre estándar. Si no encuentra ninguno, agrega None.
        """
        schema = df.collect_schema()
        expresiones = []
        for col_master, candidatos in self.sinonimos_norm.items():
            for candidato in candidatos:
                if candidato in schema:
                    expresiones.append(pl.col(candidato).alias(col_master))
                    break
            else:
                expresiones.append(pl.lit(None).alias(col_master))
        return df.with_columns(expresiones)

    # ------------------------------------------------------------------
    # Estandarizar: queda solo con las columnas master en el orden correcto
    # ------------------------------------------------------------------

    def estandarizar_pd(self, df: pd.DataFrame) -> pd.DataFrame:
        """Agrega columnas master faltantes con pd.NA y selecciona solo COLUMNAS_MASTER."""
        for col in self.columnas:
            if col not in df.columns:
                df[col] = pd.NA
        return df[self.columnas]

    def estandarizar_pl(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """Selecciona solo COLUMNAS_MASTER; rellena con None las que no existan."""
        schema = df.collect_schema()
        return df.select([
            pl.col(col) if col in schema else pl.lit(None).alias(col)
            for col in self.columnas
        ])
