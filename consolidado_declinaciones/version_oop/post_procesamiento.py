"""
post_procesamiento.py — Transformaciones finales para Power BI.

Toma MASTER_CONSOLIDADO.parquet (data cruda) y genera MASTER_POWERBI.parquet
con filtros de negocio y columnas calculadas ya aplicadas.

¿Por qué aquí y no en Power BI?
    Power BI tarda 10+ minutos procesando 9M registros con filtros encima.
    Polars hace lo mismo en segundos. Power BI solo carga el resultado y visualiza.

Reglas de negocio configurables al inicio del archivo:
    Para agregar/quitar un filtro, solo edita las constantes de la sección
    CONSTANTES DE NEGOCIO. No hay que tocar la lógica de las clases.
"""
from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import polars as pl


# ---------------------------------------------------------------------------
# CONSTANTES DE NEGOCIO
#
# PRINCIPIO DE ARQUITECTURA:
#   Solo viven aquí los filtros que son decisiones de REPORTE,
#   no de validez de data. Los filtros de validez de cada fuente
#   están en el pipeline individual de cada herramienta:
#     - BIN/MCC excluidos RT_DEBITO → rt_debito_pipeline_medallion.py
#     - STIP excluidos VRM          → PIPELINE VRM - ARQUITECTURA MEDALLION
#     - Filtro Rejected VCAS        → vcas_unitario.ipynb
#     - Filtro de39/condicion FRM   → FuenteAccess._filtrar_declinaciones_validas()
# ---------------------------------------------------------------------------

# Fecha de corte global: aplica a TODAS las herramientas.
# None = sin corte, muestra toda la data.
FECHA_CORTE_GLOBAL: date | None = date(2025, 1, 1)

# RT_CREDITO: decisión de reporte — hubo migración en julio 2025.
# Datos anteriores distorsionan visualizaciones. SE QUEDA AQUÍ.
FECHA_CORTE_RT_CREDITO = date(2025, 7, 1)


# ---------------------------------------------------------------------------
# Clase principal
# ---------------------------------------------------------------------------

class PostProcesadorMaster:
    """
    Aplica filtros de negocio y columnas calculadas al master consolidado,
    y genera el parquet final que carga Power BI.

    ¿Por qué una clase?
        Agrupa las reglas de negocio con la lógica que las aplica.
        Cada método privado es un paso independiente y nombrado,
        fácil de activar, desactivar o modificar sin tocar el resto.
    """

    def __init__(self, ruta_entrada: Path, ruta_salida: Path) -> None:
        self.ruta_entrada = ruta_entrada
        self.ruta_salida  = ruta_salida

    def ejecutar(self) -> None:
        """Corre el pipeline completo de post-procesamiento."""
        t0 = time.time()
        print("  Post-procesamiento para Power BI...")

        lf = pl.scan_parquet(self.ruta_entrada)

        # Filtro global de fecha (aplica antes que cualquier otro)
        lf = self._filtrar_fecha_global(lf)

        # Columnas calculadas primero (BIN6 se necesita para el filtro RT_DEBITO)
        lf = self._agregar_bin_limpio_y_bin6(lf)
        lf = self._corregir_entry_mode(lf)
        lf = self._agregar_llave1(lf)

        # Filtro de reporte: RT_CREDITO solo desde la fecha de migración
        lf = self._filtrar_rt_credito(lf)

        df = lf.collect(streaming=True)
        self.ruta_salida.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(self.ruta_salida)

        print(f"  Filas Power BI : {df.height:,}")
        print(f"  Guardado en    : {self.ruta_salida.name}")
        print(f"  Tiempo         : {time.time() - t0:.2f}s")

    # ------------------------------------------------------------------
    # Filtro global
    # ------------------------------------------------------------------

    def _filtrar_fecha_global(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """
        Aplica un corte de fecha a TODAS las herramientas.
        Útil para mostrar solo los últimos N meses en Power BI.
        Si FECHA_CORTE_GLOBAL es None, no filtra nada.
        """
        if FECHA_CORTE_GLOBAL is None:
            return lf
        corte = pl.lit(FECHA_CORTE_GLOBAL).cast(pl.Datetime("ms"))
        return lf.filter(pl.col("fecha") >= corte)

    # ------------------------------------------------------------------
    # Columnas calculadas
    # ------------------------------------------------------------------

    def _agregar_bin_limpio_y_bin6(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """
        Problema: Excel lee BIN como float → "427158" se convierte en "427158.0"
        Solución: eliminar el ".0" del final antes de operar con el BIN.

        BIN_LIMPIO → BIN completo sin el ".0"   (para comparar con el BIN original)
        BIN6       → primeros 6 caracteres       (estandariza BINs de 6 y 8 dígitos)

        Se generan ambas columnas para poder validar que el fix es correcto.
        """
        bin_limpio = (
            pl.col("bin")
            .cast(pl.Utf8)
            .str.replace(r"\.0$", "")
        )
        return lf.with_columns([
            bin_limpio.alias("bin_limpio"),
            bin_limpio.str.slice(0, 6).alias("bin6"),
        ])

    def _corregir_entry_mode(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """
        VCAS no siempre incluye entry_mode.
        Cuando es null en VCAS se asume 81 (e-commerce).
        Se castea a texto para consistencia con el resto de fuentes.
        """
        return lf.with_columns(
            pl.when(
                (pl.col("herramienta") == "VCAS") & pl.col("entry_mode").is_null()
            )
            .then(pl.lit("81"))
            .otherwise(pl.col("entry_mode").cast(pl.Utf8))
            .alias("entry_mode")
        )

    def _agregar_llave1(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """
        Llave compuesta para identificar transacciones por monto único:
        tarjeta_final + fecha + nombre_comercio, separados por "_".
        """
        return lf.with_columns(
            pl.concat_str(
                [
                    pl.col("tarjeta_final").cast(pl.Utf8),
                    pl.col("fecha").cast(pl.Utf8),
                    pl.col("nombre_comercio").cast(pl.Utf8),
                ],
                separator="_",
            ).alias("llave1")
        )

    # ------------------------------------------------------------------
    # Filtros por herramienta
    # ------------------------------------------------------------------

    def _filtrar_rt_credito(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """
        RT_CREDITO: solo registros desde FECHA_CORTE_RT_CREDITO (2025-07-01).
        Antes de esa fecha hubo una migración que genera datos inconsistentes.
        """
        corte = pl.lit(FECHA_CORTE_RT_CREDITO).cast(pl.Datetime("ms"))
        return lf.filter(
            ~(
                (pl.col("herramienta") == "RT_CREDITO")
                & (pl.col("fecha") < corte)
            )
        )

