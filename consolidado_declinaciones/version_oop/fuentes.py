"""
fuentes.py — Clases que representan cada fuente de datos.

¿Por qué una jerarquía de clases aquí?
    Las 5 fuentes (VCAS, VRM, RT_DEBITO, RT_CREDITO, FRM) siguen el mismo
    pipeline: leer → normalizar → sinónimos → fecha → herramienta → master.
    Sin clases, ese pipeline se repite 5 veces (código espagueti).
    Con FuenteBase capturamos el patrón una sola vez.

    FRM es especial: usa Access (requiere pandas) y tiene un filtro de
    negocio propio. FuenteAccess hereda el contrato pero reemplaza la
    implementación donde lo necesita.

Jerarquía:
    FuenteBase (abstract)
    ├── FuenteParquet   → VCAS, VRM, RT_DEBITO, RT_CREDITO
    └── FuenteAccess    → FRM
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd
import polars as pl

from esquema import EsquemaMaster
from transformaciones import (
    leer_access,
    normalizar_columnas_pd,
    normalizar_columnas_pl,
    pandas_a_polars_con_fecha,
    parsear_fecha_pd,
    parsear_fecha_pl,
)


class FuenteBase(ABC):
    """
    Contrato base para todas las fuentes del consolidado.

    Cada fuente concreta solo necesita implementar `_cargar_crudo()`.
    El método `procesar()` aplica el pipeline estándar sobre lo que devuelva
    `_cargar_crudo()`, así no se repite código en cada fuente.
    """

    def __init__(self, nombre: str, esquema: EsquemaMaster) -> None:
        self.nombre = nombre
        self.esquema = esquema

    @abstractmethod
    def _cargar_crudo(self) -> pl.LazyFrame:
        """Devuelve los datos crudos de la fuente como LazyFrame polars."""
        ...

    def procesar(self) -> pl.LazyFrame:
        """
        Pipeline estándar (polars):
        1. Cargar datos crudos
        2. Normalizar nombres de columna (minúsculas, sin tildes)
        3. Renombrar al esquema master (sinónimos)
        4. Parsear columna fecha
        5. Agregar columna 'herramienta' con el nombre de la fuente
        6. Seleccionar solo las columnas master en orden
        """
        return (
            self._cargar_crudo()
            .pipe(normalizar_columnas_pl)
            .pipe(self.esquema.aplicar_sinonimos_pl)
            .pipe(parsear_fecha_pl)
            .with_columns(pl.lit(self.nombre).alias("herramienta"))
            .pipe(self.esquema.estandarizar_pl)
        )


class FuenteParquet(FuenteBase):
    """
    Fuente que lee desde un archivo Parquet con polars lazy (scan_parquet).

    scan_parquet es lazy: polars solo lee lo que necesita del archivo,
    lo que lo hace eficiente con datasets grandes (9M+ registros).
    """

    def __init__(self, nombre: str, ruta: Path, esquema: EsquemaMaster) -> None:
        super().__init__(nombre, esquema)
        self.ruta = ruta

    def validar(self) -> None:
        """Lanza error si el archivo no existe antes de intentar leerlo."""
        if not self.ruta.exists():
            raise FileNotFoundError(f"No existe el parquet para '{self.nombre}': {self.ruta}")

    def _cargar_crudo(self) -> pl.LazyFrame:
        return pl.scan_parquet(self.ruta)


class FuenteAccess(FuenteBase):
    """
    Fuente especial para la base de datos Access del sistema FRM.

    ¿Por qué distinta?
    - Access no tiene driver nativo en polars, necesita pyodbc (pandas).
    - Tiene un filtro de negocio propio: solo declinaciones reales
      (de39 == "63", sin condiciones de prueba NM/RD).

    El pipeline usa pandas hasta convertir a polars al final,
    para mantener consistencia con el resto del consolidado.
    """

    def __init__(
        self,
        nombre: str,
        ruta_accdb: str,
        tabla_sql: str,
        esquema: EsquemaMaster,
    ) -> None:
        super().__init__(nombre, esquema)
        self.ruta_accdb = ruta_accdb
        self.tabla_sql = tabla_sql

    def _cargar_crudo(self) -> pl.LazyFrame:
        # FRM usa pandas internamente; este método devuelve LazyFrame
        # para cumplir el contrato de FuenteBase, pero la lógica es pandas.
        df = leer_access(self.ruta_accdb, self.tabla_sql)
        df = normalizar_columnas_pd(df)
        df = self.esquema.aplicar_sinonimos_pd(df)
        df = parsear_fecha_pd(df)
        df = self._filtrar_declinaciones_validas(df)
        return pandas_a_polars_con_fecha(df)

    def procesar(self) -> pl.LazyFrame:
        """
        Pipeline para FRM: la carga y transformación pandas ocurre en
        `_cargar_crudo()`. Aquí solo agrega herramienta y estandariza.
        """
        return (
            self._cargar_crudo()
            .with_columns(pl.lit(self.nombre).alias("herramienta"))
            .pipe(self.esquema.estandarizar_pl)
        )

    def _filtrar_declinaciones_validas(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filtra solo registros que corresponden a declinaciones reales:
        - de39 (código de respuesta ISO) == "63"  → declinación por VCAS
        - condicion no es "NM" (no match) ni "RD" (reverso/duplicado)
        """
        condicion = df["condicion"].astype("string").str.strip()
        de39      = df["de39 resp de autorizacion"].astype("string").str.strip()
        mascara   = (
            (condicion.isna() | (condicion == "") | (~condicion.isin(["NM", "RD"])))
            & (de39 == "63")
        )
        return df[mascara]
