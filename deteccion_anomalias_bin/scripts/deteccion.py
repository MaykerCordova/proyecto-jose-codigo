"""
deteccion.py  (Pasos 2-3 del pipeline — Baseline y Detección)
─────────────────────────────────────────────────────────────
Para cada serie diaria calcula un baseline robusto con ventana móvil
(solo días ANTERIORES, para no contaminar el baseline con el propio pico):

    mediana_t = mediana(N_TRX de los últimos `ventana_dias` días previos a t)
    MAD_t     = mediana(|N_TRX - mediana|) en la misma ventana
    z_t       = 0.6745 * (N_TRX_t - mediana_t) / max(MAD_t, mad_min)

Se usa mediana/MAD en lugar de media/desviación para que picos pasados
no inflen el baseline (un spike de la semana pasada no debe "normalizar"
el spike de hoy).

Alerta = z > z_umbral  Y  N_TRX >= min_trx_dia  Y  exceso positivo.

Corre en los 3 niveles: BIN10×COMERCIO (principal), BIN10×MCC y BIN6.
Salida: data/alertas.parquet  (todas las filas-día con su z, flag ALERTA)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    DETECCION,
    PARQUET_SERIE_BIN10_COMERCIO, PARQUET_SERIE_BIN10_MCC, PARQUET_SERIE_BIN6,
    PARQUET_ALERTAS,
)

VENTANA  = DETECCION["ventana_dias"]
MIN_HIST = DETECCION["min_dias_historia"]
Z_UMBRAL = DETECCION["z_umbral"]
MAD_MIN  = DETECCION["mad_min"]
MIN_TRX  = DETECCION["min_trx_dia"]

NIVELES = {
    "BIN10_COMERCIO": (PARQUET_SERIE_BIN10_COMERCIO, ["BIN_10", "COMERCIO"]),
    "BIN10_MCC"     : (PARQUET_SERIE_BIN10_MCC,      ["BIN_10", "MCC"]),
    "BIN6"          : (PARQUET_SERIE_BIN6,           ["BIN_6"]),
}

print("═" * 65)
print("DETECCIÓN — z-score robusto (mediana + MAD, ventana móvil)")
print("═" * 65)
print(f"  ventana={VENTANA}d | min_historia={MIN_HIST}d | z>{Z_UMBRAL} | min_trx={MIN_TRX}")


def mad(ventana: np.ndarray) -> float:
    return float(np.median(np.abs(ventana - np.median(ventana))))


def detectar(df: pd.DataFrame, claves: list[str]) -> pd.DataFrame:
    df = df.sort_values(claves + ["FECHA"]).reset_index(drop=True)
    g = df.groupby(claves, sort=False)["N_TRX"]

    # shift(1): la ventana usa solo días anteriores al día evaluado
    df["BASELINE_MEDIANA"] = g.transform(
        lambda s: s.shift(1).rolling(VENTANA, min_periods=MIN_HIST).median()
    )
    df["BASELINE_MAD"] = g.transform(
        lambda s: s.shift(1).rolling(VENTANA, min_periods=MIN_HIST).apply(mad, raw=True)
    )

    df["EXCESO"] = df["N_TRX"] - df["BASELINE_MEDIANA"]
    df["Z_ROBUSTO"] = (
        0.6745 * df["EXCESO"] / df["BASELINE_MAD"].clip(lower=MAD_MIN)
    )
    df["ALERTA"] = (
        (df["Z_ROBUSTO"] > Z_UMBRAL)
        & (df["N_TRX"] >= MIN_TRX)
        & (df["EXCESO"] > 0)
    )
    return df


partes = []
for nivel, (ruta, claves) in NIVELES.items():
    if not ruta.exists():
        print(f"  ⚠️  {nivel}: no existe {ruta.name} — ejecuta agregacion.py")
        continue

    df = detectar(pd.read_parquet(ruta), claves)

    # Llave legible única para todos los niveles (para consolidar en una tabla)
    df["NIVEL"] = nivel
    df["CLAVE"] = df[claves].astype(str).agg(" | ".join, axis=1)

    n_alertas = int(df["ALERTA"].sum())
    n_series  = df.groupby(claves).ngroups
    print(f"  ✅ {nivel:15s} → {n_series:>6,} series | {n_alertas:>4,} alertas")
    partes.append(df)

if not partes:
    print("❌  No se procesó ningún nivel.")
    sys.exit(1)

resultado = pd.concat(partes, ignore_index=True)

cols_comunes = [
    "NIVEL", "CLAVE", "BIN_6", "BIN_10", "COMERCIO", "MCC", "FECHA",
    "N_TRX", "N_TARJETAS", "RATIO_TRX_TARJETA", "TASA_DECLINACION",
    "TICKET_PROM", "MONTO_APROBADO", "N_MCC", "N_COMERCIOS", "PCT_NOCTURNAS",
    "BASELINE_MEDIANA", "BASELINE_MAD", "EXCESO", "Z_ROBUSTO", "ALERTA",
]
resultado = resultado.reindex(columns=cols_comunes)
resultado.to_parquet(PARQUET_ALERTAS, index=False)

alertas = resultado[resultado["ALERTA"]]
print(f"\n  📦 Total: {len(resultado):,} filas-día | {len(alertas):,} alertas")
if not alertas.empty:
    print("\n  Top 10 alertas por z-score:")
    top = alertas.nlargest(10, "Z_ROBUSTO")[
        ["NIVEL", "CLAVE", "FECHA", "N_TRX", "BASELINE_MEDIANA", "Z_ROBUSTO"]
    ]
    print(top.to_string(index=False))

print(f"\n✅ Guardado: {PARQUET_ALERTAS}")
print("   Siguiente paso: python scripts/atribucion.py")
print("═" * 65)
