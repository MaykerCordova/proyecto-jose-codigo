"""
agregacion.py  (Paso 1 del pipeline — Preparación con Polars)
─────────────────────────────────────────────────────────────
Convierte el consolidado transaccional en series diarias por rango de BIN.

Unidad de análisis (llave principal):   BIN_10 × COMERCIO × FECHA
Vistas de roll-up:                      BIN_10 × MCC × FECHA   y   BIN_6 × FECHA

Métricas por fila (punto 3 de la especificación):
  · N_TRX               n° de transacciones
  · N_TARJETAS          n° de tarjetas únicas
  · RATIO_TRX_TARJETA   trx / tarjeta  (>3-5 = firma de testing)
  · TASA_DECLINACION    % denegadas según cod_respuesta
  · TICKET_PROM         monto promedio de las aprobadas
  · N_MCC               n° de MCC distintos (solo tiene sentido en roll-ups)
  · PCT_NOCTURNAS       % de trx en horas nocturnas (00-05h)

Además densifica el calendario: los días sin actividad de una serie
(desde su primera aparición) entran como 0 trx — sin esto el baseline
de la mediana queda sesgado hacia arriba.

Salidas:
  data/detalle_trx.parquet           (detalle reducido, lo usa atribucion.py)
  data/serie_bin10_comercio.parquet
  data/serie_bin10_mcc.parquet
  data/serie_bin6.parquet
"""

import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    COLS, HORAS_NOCTURNAS,
    PARQUET_CONSOLIDADO, PARQUET_DETALLE,
    PARQUET_SERIE_BIN10_COMERCIO, PARQUET_SERIE_BIN10_MCC, PARQUET_SERIE_BIN6,
)

C = COLS

print("═" * 65)
print("AGREGACIÓN — series diarias por rango de BIN (Polars)")
print("═" * 65)

if not PARQUET_CONSOLIDADO.exists():
    print(f"❌  No existe {PARQUET_CONSOLIDADO} — ejecuta primero consolidar.py")
    sys.exit(1)

df = pl.read_parquet(PARQUET_CONSOLIDADO)
print(f"  Consolidado: {df.height:,} filas")


# ─────────────────────────────────────────────────────────────────────────────
# 1. DETALLE REDUCIDO — solo las columnas que necesita el análisis
# ─────────────────────────────────────────────────────────────────────────────
def col(nombre_interno: str) -> str:
    """Nombre real en Monitor de una columna interna."""
    return C[nombre_interno]


requeridas = {
    "FECHA_HORA": col("fecha_hora"),
    "COMERCIO"  : col("comercio_nom"),
    "MCC"       : col("mcc"),
    "MONTO"     : col("monto"),
    "COD_RPTA"  : col("cod_respuesta"),
}
faltantes = [v for v in requeridas.values() if v not in df.columns]
if faltantes:
    print(f"❌  Faltan columnas en el consolidado: {faltantes}")
    print("    Revisa el diccionario COLS en config.py")
    sys.exit(1)

detalle = (
    df.select(
        pl.col(requeridas["FECHA_HORA"]).dt.date().alias("FECHA"),
        pl.col(requeridas["FECHA_HORA"]).dt.hour().alias("HORA"),
        pl.col("BIN_6"),
        pl.col("BIN_10"),
        pl.col("TARJETA"),
        pl.col(requeridas["COMERCIO"]).alias("COMERCIO"),
        pl.col(requeridas["MCC"]).alias("MCC"),
        pl.col(requeridas["MONTO"]).alias("MONTO"),
        pl.col(requeridas["COD_RPTA"]).alias("COD_RPTA"),
    )
    .drop_nulls(subset=["FECHA"])
    .with_columns(
        pl.col("COD_RPTA").str.strip_chars().is_in(["0", "00", "000"]).alias("APROBADA"),
        pl.col("HORA").is_in(sorted(HORAS_NOCTURNAS)).alias("NOCTURNA"),
    )
)

PARQUET_DETALLE.parent.mkdir(parents=True, exist_ok=True)
detalle.write_parquet(PARQUET_DETALLE)
print(f"  ✅ Detalle reducido: {detalle.height:,} filas → {PARQUET_DETALLE.name}")
print(f"     Rango: {detalle['FECHA'].min()} → {detalle['FECHA'].max()}")
print(f"     Tasa declinación global: {1 - detalle['APROBADA'].mean():.1%}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. AGREGACIÓN DIARIA POR NIVEL
# ─────────────────────────────────────────────────────────────────────────────
def agregar(claves: list[str]) -> pl.DataFrame:
    """Serie diaria con las métricas del punto 3 para la llave dada."""
    return (
        detalle.group_by(claves + ["FECHA"])
        .agg(
            pl.len().alias("N_TRX"),
            pl.col("TARJETA").n_unique().alias("N_TARJETAS"),
            (pl.len() / pl.col("TARJETA").n_unique()).alias("RATIO_TRX_TARJETA"),
            (1 - pl.col("APROBADA").mean()).alias("TASA_DECLINACION"),
            pl.col("MONTO").filter(pl.col("APROBADA")).mean().alias("TICKET_PROM"),
            pl.col("MONTO").filter(pl.col("APROBADA")).sum().alias("MONTO_APROBADO"),
            pl.col("MCC").n_unique().alias("N_MCC"),
            pl.col("COMERCIO").n_unique().alias("N_COMERCIOS"),
            pl.col("NOCTURNA").mean().alias("PCT_NOCTURNAS"),
        )
        .sort(claves + ["FECHA"])
    )


def densificar(serie: pl.DataFrame, claves: list[str]) -> pl.DataFrame:
    """
    Rellena con 0 los días sin actividad de cada serie, desde la primera
    fecha en que la serie aparece hasta el final del periodo observado.
    """
    fecha_min, fecha_max = detalle["FECHA"].min(), detalle["FECHA"].max()
    calendario = pl.DataFrame(
        {"FECHA": pl.date_range(fecha_min, fecha_max, "1d", eager=True)}
    )
    primera = serie.group_by(claves).agg(pl.col("FECHA").min().alias("PRIMERA_FECHA"))

    grid = (
        serie.select(claves).unique()
        .join(calendario, how="cross")
        .join(primera, on=claves)
        .filter(pl.col("FECHA") >= pl.col("PRIMERA_FECHA"))
        .drop("PRIMERA_FECHA")
    )
    return (
        grid.join(serie, on=claves + ["FECHA"], how="left")
        .with_columns(
            pl.col("N_TRX", "N_TARJETAS", "MONTO_APROBADO", "N_MCC", "N_COMERCIOS")
              .fill_null(0),
            pl.col("RATIO_TRX_TARJETA", "TASA_DECLINACION", "PCT_NOCTURNAS")
              .fill_null(0.0),
        )
        .sort(claves + ["FECHA"])
    )


NIVELES = {
    "BIN10_COMERCIO": (["BIN_10", "COMERCIO"], PARQUET_SERIE_BIN10_COMERCIO),
    "BIN10_MCC"     : (["BIN_10", "MCC"],      PARQUET_SERIE_BIN10_MCC),
    "BIN6"          : (["BIN_6"],              PARQUET_SERIE_BIN6),
}

print()
for nivel, (claves, ruta) in NIVELES.items():
    serie = densificar(agregar(claves), claves)
    serie.write_parquet(ruta)
    n_series = serie.select(claves).unique().height
    print(f"  ✅ {nivel:15s} → {n_series:>6,} series | {serie.height:>8,} filas-día | {ruta.name}")

print("\n✅ Agregación completa. Siguiente paso: python scripts/deteccion.py")
print("═" * 65)
