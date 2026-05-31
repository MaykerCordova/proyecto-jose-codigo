"""
detector_anomalias.py — Detección de anomalías por Z-score.

Para cada dimensión (herramienta, comercio, BIN6) calcula:
    - Volumen diario de transacciones declinadas
    - Monto diario rechazado
    - Media y desviación estándar de los últimos VENTANA_DIAS días
    - Z-score del día T-1 (ayer)
    - Flag de alerta si Z-score > UMBRAL_ZSCORE

¿Por qué Z-score y no ML?
    Con datos diarios desde enero 2025 (~5 meses), el Z-score es
    estadísticamente robusto, interpretable para el negocio y no
    requiere entrenamiento. Si hay un pico de 100K vs una media de
    5K-7K, el Z-score lo detecta inmediatamente.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import polars as pl


@dataclass
class AlertaGrupo:
    """Resultado del análisis de anomalía para un grupo específico."""
    dimension:       str    # "herramienta", "comercio", "bin6"
    grupo:           str    # valor del grupo (ej: "VRM", "AMAZON.COM")
    herramienta:     str    # herramienta del grupo (para comercio/bin6)
    fecha:           date
    volumen_hoy:     int
    monto_hoy:       float
    media_volumen:   float
    std_volumen:     float
    zscore_volumen:  float
    media_monto:     float
    std_monto:       float
    zscore_monto:    float

    @property
    def es_alerta(self) -> bool:
        return abs(self.zscore_volumen) > 2.0 or abs(self.zscore_monto) > 2.0

    @property
    def tipo_alerta(self) -> str:
        partes = []
        if abs(self.zscore_volumen) > 2.0:
            partes.append(f"volumen Z={self.zscore_volumen:+.1f}")
        if abs(self.zscore_monto) > 2.0:
            partes.append(f"monto Z={self.zscore_monto:+.1f}")
        return " | ".join(partes) if partes else "Normal"


class DetectorAnomalias:
    """
    Analiza el parquet de Power BI y detecta picos anómalos en T-1.

    Flujo:
        1. Carga el parquet y agrega por (herramienta, dia)
        2. Calcula rolling mean/std de VENTANA_DIAS días (excluyendo T-1)
        3. Calcula Z-score para T-1 en cada grupo
        4. Repite por comercio y por BIN6 (top N más activos)
        5. Devuelve un dict con todos los resultados listos para el reporte
    """

    def __init__(
        self,
        ruta_parquet: Path,
        ventana_dias: int = 30,
        umbral_zscore: float = 2.0,
        top_n: int = 10,
    ) -> None:
        self.ruta_parquet  = ruta_parquet
        self.ventana_dias  = ventana_dias
        self.umbral_zscore = umbral_zscore
        self.top_n         = top_n

    def analizar(self) -> dict:
        """Punto de entrada. Devuelve dict con alertas y datos para gráficas."""
        print("  Detectando anomalías...")

        df = pl.read_parquet(self.ruta_parquet)
        df = df.with_columns(pl.col("fecha").cast(pl.Date).alias("dia"))

        fecha_t1 = df["dia"].max()
        print(f"  Fecha T-1: {fecha_t1}")

        alertas_herramienta = self._analizar_dimension(df, "herramienta", fecha_t1)
        alertas_comercio    = self._analizar_dimension(df, "nombre_comercio", fecha_t1)
        alertas_bin6        = self._analizar_dimension(df, "bin6", fecha_t1)

        total_alertas = sum(
            1 for a in alertas_herramienta + alertas_comercio + alertas_bin6
            if a.es_alerta
        )
        print(f"  Alertas detectadas: {total_alertas}")

        return {
            "fecha_t1":             fecha_t1,
            "total_alertas":        total_alertas,
            "alertas_herramienta":  alertas_herramienta,
            "alertas_comercio":     [a for a in alertas_comercio  if a.es_alerta][:self.top_n],
            "alertas_bin6":         [a for a in alertas_bin6       if a.es_alerta][:self.top_n],
            "df_evolutivo":         self._preparar_evolutivo(df, fecha_t1),
            "resumen_herramienta":  self._resumen_t1(df, fecha_t1),
        }

    # ------------------------------------------------------------------
    # Análisis por dimensión
    # ------------------------------------------------------------------

    def _analizar_dimension(
        self,
        df: pl.DataFrame,
        columna: str,
        fecha_t1: date,
    ) -> list[AlertaGrupo]:
        """
        Agrupa por (herramienta, columna, dia), calcula Z-score para T-1.
        Para comercio y bin6, filtra solo los grupos con actividad suficiente
        (mínimo 7 días con transacciones en la ventana).
        """
        if columna not in df.columns:
            return []

        # Agregado diario por herramienta + dimensión
        # dict.fromkeys elimina duplicados si columna == "herramienta"
        group_keys = list(dict.fromkeys(["herramienta", columna, "dia"]))
        diario = (
            df
            .group_by(group_keys)
            .agg([
                pl.len().alias("volumen"),
                pl.col("monto_usd").cast(pl.Float64).sum().alias("monto"),
            ])
            .sort(group_keys)
            .to_pandas()
        )

        if diario.empty:
            return []

        # Calcular rolling mean/std usando los N días ANTERIORES (shift=1)
        diario = diario.sort_values(["herramienta", columna, "dia"])

        diario["mean_vol"] = diario.groupby(["herramienta", columna])["volumen"].transform(
            lambda x: x.shift(1).rolling(self.ventana_dias, min_periods=7).mean()
        )
        diario["std_vol"] = diario.groupby(["herramienta", columna])["volumen"].transform(
            lambda x: x.shift(1).rolling(self.ventana_dias, min_periods=7).std()
        )
        diario["mean_mto"] = diario.groupby(["herramienta", columna])["monto"].transform(
            lambda x: x.shift(1).rolling(self.ventana_dias, min_periods=7).mean()
        )
        diario["std_mto"] = diario.groupby(["herramienta", columna])["monto"].transform(
            lambda x: x.shift(1).rolling(self.ventana_dias, min_periods=7).std()
        )

        # Solo T-1
        hoy = diario[diario["dia"] == fecha_t1].copy()
        if hoy.empty:
            return []

        # Z-score (si std == 0 o NaN → zscore = 0, no hay variación)
        hoy["zscore_vol"] = (hoy["volumen"] - hoy["mean_vol"]) / hoy["std_vol"].replace(0, float("nan"))
        hoy["zscore_mto"] = (hoy["monto"]   - hoy["mean_mto"]) / hoy["std_mto"].replace(0, float("nan"))
        hoy = hoy.fillna(0)

        # Construir lista de AlertaGrupo
        alertas = []
        for _, row in hoy.iterrows():
            alertas.append(AlertaGrupo(
                dimension      = columna,
                grupo          = str(row[columna]) if pd.notna(row[columna]) else "(vacío)",
                herramienta    = str(row["herramienta"]),
                fecha          = fecha_t1,
                volumen_hoy    = int(row["volumen"]),
                monto_hoy      = float(row["monto"]),
                media_volumen  = float(row["mean_vol"]),
                std_volumen    = float(row["std_vol"]),
                zscore_volumen = float(row["zscore_vol"]),
                media_monto    = float(row["mean_mto"]),
                std_monto      = float(row["std_mto"]),
                zscore_monto   = float(row["zscore_mto"]),
            ))

        # Ordenar por Z-score absoluto descendente
        alertas.sort(key=lambda a: max(abs(a.zscore_volumen), abs(a.zscore_monto)), reverse=True)
        return alertas

    # ------------------------------------------------------------------
    # Datos para gráficas
    # ------------------------------------------------------------------

    def _preparar_evolutivo(self, df: pl.DataFrame, fecha_t1: date) -> pd.DataFrame:
        """
        Devuelve el evolutivo diario por herramienta para los últimos
        VENTANA_DIAS días. Es la data que usa el gráfico de líneas del correo.
        """
        desde = pd.Timestamp(fecha_t1) - pd.Timedelta(days=self.ventana_dias)
        return (
            df
            .filter(pl.col("dia") >= pl.lit(desde.date()))
            .group_by(["herramienta", "dia"])
            .agg([
                pl.len().alias("volumen"),
                pl.col("monto_usd").cast(pl.Float64).sum().alias("monto"),
            ])
            .sort(["herramienta", "dia"])
            .to_pandas()
        )

    def _resumen_t1(self, df: pl.DataFrame, fecha_t1: date) -> pd.DataFrame:
        """Resumen de volumen y monto del día T-1 por herramienta."""
        return (
            df
            .filter(pl.col("dia") == pl.lit(fecha_t1))
            .group_by("herramienta")
            .agg([
                pl.len().alias("transacciones"),
                pl.col("monto_usd").cast(pl.Float64).sum().alias("monto_usd"),
            ])
            .sort("transacciones", descending=True)
            .to_pandas()
        )
