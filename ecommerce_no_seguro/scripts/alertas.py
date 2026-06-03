"""
alertas.py — Detector de anomalías diario: Comercios No Seguros
================================================================
Lee el parquet enriquecido generado por feature_engineering.py y evalúa
tres detectores sobre los últimos 7 días vs los 60 días previos:

  ① Comercio fantasma   — aparece en período reciente y es FLAG_COMERCIO_NUEVO
  ② Spike de volumen    — fraudes recientes 3x por encima del promedio histórico
  ③ Spike de monto      — monto promedio reciente > media histórica + 2 desv. estándar

Salida: alertas_YYYYMMDD.xlsx con una hoja por detector + hoja resumen ejecutivo.
"""

import pandas as pd
import numpy as np
import sys
import os
from datetime import date, timedelta

from config import COLS, PARQUET_OUTPUT

# ── Parámetros de corte ────────────────────────────────────────────────────────
DIAS_RECIENTE  = 7    # período "hoy vs últimos N días"
DIAS_BASELINE  = 60   # días de historia previa para calcular promedios
SPIKE_VOL_X    = 3.0  # multiplicador para spike de volumen (3x el promedio diario)
SPIKE_MONTO_SD = 2.0  # desviaciones estándar para spike de monto

# ── Fecha de corte (puede sobreescribirse por argumento) ──────────────────────
if len(sys.argv) > 1:
    try:
        fecha_hoy = pd.to_datetime(sys.argv[1]).date()
    except Exception:
        print(f"⚠️  Fecha inválida '{sys.argv[1]}'. Usando fecha del sistema.")
        fecha_hoy = date.today()
else:
    fecha_hoy = date.today()

fecha_inicio_reciente  = fecha_hoy - timedelta(days=DIAS_RECIENTE)
fecha_inicio_baseline  = fecha_hoy - timedelta(days=DIAS_RECIENTE + DIAS_BASELINE)
fecha_fin_baseline     = fecha_inicio_reciente - timedelta(days=1)

C = COLS

print("─" * 65)
print(f"Detector de alertas — Comercios No Seguros")
print(f"Fecha de corte      : {fecha_hoy}")
print(f"Período reciente    : {fecha_inicio_reciente} → {fecha_hoy}  ({DIAS_RECIENTE} días)")
print(f"Baseline histórico  : {fecha_inicio_baseline} → {fecha_fin_baseline}  ({DIAS_BASELINE} días)")
print("─" * 65)


# ═══════════════════════════════════════════════════════════════════════════════
#  CARGA
# ═══════════════════════════════════════════════════════════════════════════════
if not os.path.exists(PARQUET_OUTPUT):
    print(f"\n❌ No se encontró el parquet enriquecido: {PARQUET_OUTPUT}")
    print("   Ejecuta primero feature_engineering.py\n")
    sys.exit(1)

df = pd.read_parquet(PARQUET_OUTPUT)
df["DATETIME_TRX"] = pd.to_datetime(df["DATETIME_TRX"])
df["FECHA_DIA"]    = pd.to_datetime(df["FECHA_DIA"]).dt.date

print(f"  Registros totales cargados: {len(df):,}")

# ── Separar períodos ──────────────────────────────────────────────────────────
df_rec  = df[df["FECHA_DIA"] >= fecha_inicio_reciente].copy()
df_base = df[(df["FECHA_DIA"] >= fecha_inicio_baseline) &
             (df["FECHA_DIA"] <= fecha_fin_baseline)].copy()

print(f"  Registros período reciente : {len(df_rec):,}")
print(f"  Registros baseline         : {len(df_base):,}")

if len(df_rec) == 0:
    print("\n⚠️  Sin datos en el período reciente. Verifica la fecha de corte o el parquet.")
    sys.exit(0)

if len(df_base) == 0:
    print("\n⚠️  Sin datos en el baseline histórico. Necesitas al menos 7 días de historia previa.")
    sys.exit(0)


# ═══════════════════════════════════════════════════════════════════════════════
#  DETECTOR ① — COMERCIO FANTASMA
#  Comercios que aparecen en el período reciente con FLAG_COMERCIO_NUEVO = 1
#  (solo 1 mes en toda la base) y ya generan alto impacto.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[①] Detector: comercio fantasma...")

cols_fantasma = [
    C["comercio_id"], C["comercio_nom"],
    "FLAG_COMERCIO_NUEVO", "FLAG_COMERCIO_ALTO_IMPACTO_RAPIDO",
    "MESES_DISTINTOS_COMERCIO", "ANTIGÜEDAD_COMERCIO_DIAS",
    "PRIMER_FECHA_COMERCIO",
]
cols_fantasma = [c for c in cols_fantasma if c in df_rec.columns]

fantasmas = (
    df_rec[df_rec["FLAG_COMERCIO_NUEVO"] == 1]
    [cols_fantasma]
    .drop_duplicates(subset=[C["comercio_id"]])
)

# Agregar monto y conteo del período reciente
resumen_rec = (
    df_rec.groupby(C["comercio_id"])
    .agg(
        FRAUDES_RECIENTES   = (C["monto"], "count"),
        MONTO_RECIENTE      = (C["monto"],  "sum"),
        TARJETAS_RECIENTES  = (C["tarjeta"], "nunique"),
    )
    .reset_index()
)

fantasmas = fantasmas.merge(resumen_rec, on=C["comercio_id"], how="left")
fantasmas = fantasmas.sort_values("MONTO_RECIENTE", ascending=False)

print(f"  Comercios fantasma detectados : {len(fantasmas):,}")
if len(fantasmas) > 0:
    print(f"  Monto total en riesgo         : {fantasmas['MONTO_RECIENTE'].sum():,.2f}")


# ═══════════════════════════════════════════════════════════════════════════════
#  DETECTOR ② — SPIKE DE VOLUMEN
#  Comercio cuyo promedio diario de fraudes en período reciente
#  supera SPIKE_VOL_X veces su promedio diario en el baseline.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[②] Detector: spike de volumen...")

# Promedio diario en baseline por comercio
vol_base = (
    df_base.groupby(C["comercio_id"])
    .agg(FRAUDES_BASE_TOTAL = (C["monto"], "count"))
    .reset_index()
)
vol_base["FRAUDES_DIARIO_BASE"] = vol_base["FRAUDES_BASE_TOTAL"] / DIAS_BASELINE

# Promedio diario en período reciente
vol_rec = (
    df_rec.groupby(C["comercio_id"])
    .agg(
        FRAUDES_REC_TOTAL  = (C["monto"], "count"),
        MONTO_REC_TOTAL    = (C["monto"],  "sum"),
        TARJETAS_REC       = (C["tarjeta"], "nunique"),
    )
    .reset_index()
)
vol_rec["FRAUDES_DIARIO_REC"] = vol_rec["FRAUDES_REC_TOTAL"] / DIAS_RECIENTE

spike_vol = vol_rec.merge(vol_base, on=C["comercio_id"], how="left")
spike_vol["FRAUDES_DIARIO_BASE"] = spike_vol["FRAUDES_DIARIO_BASE"].fillna(0)

# Ratio: cuántas veces el reciente supera el baseline
spike_vol["RATIO_VOLUMEN"] = np.where(
    spike_vol["FRAUDES_DIARIO_BASE"] > 0,
    spike_vol["FRAUDES_DIARIO_REC"] / spike_vol["FRAUDES_DIARIO_BASE"],
    np.inf  # comercio sin historia = infinito (nuevo)
)

# Filtrar: ratio >= SPIKE_VOL_X y al menos 2 fraudes en período reciente
spike_vol = spike_vol[
    (spike_vol["RATIO_VOLUMEN"] >= SPIKE_VOL_X) &
    (spike_vol["FRAUDES_REC_TOTAL"] >= 2)
].sort_values("RATIO_VOLUMEN", ascending=False)

# Agregar nombre del comercio si está disponible
if C["comercio_nom"] in df.columns:
    nombres = df[[C["comercio_id"], C["comercio_nom"]]].drop_duplicates()
    spike_vol = spike_vol.merge(nombres, on=C["comercio_id"], how="left")

spike_vol["RATIO_VOLUMEN"] = spike_vol["RATIO_VOLUMEN"].replace(np.inf, 999).round(1)

print(f"  Comercios con spike de volumen (≥{SPIKE_VOL_X}x): {len(spike_vol):,}")


# ═══════════════════════════════════════════════════════════════════════════════
#  DETECTOR ③ — SPIKE DE MONTO
#  Monto promedio reciente del comercio > media histórica + 2 desv. estándar.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[③] Detector: spike de monto...")

# Estadísticas de monto en baseline por comercio
monto_base = (
    df_base.groupby(C["comercio_id"])[C["monto"]]
    .agg(
        MONTO_PROM_BASE = "mean",
        MONTO_STD_BASE  = "std",
        N_BASE          = "count",
    )
    .reset_index()
)
monto_base["MONTO_STD_BASE"] = monto_base["MONTO_STD_BASE"].fillna(0)
monto_base["UMBRAL_SPIKE_MONTO"] = (
    monto_base["MONTO_PROM_BASE"] + SPIKE_MONTO_SD * monto_base["MONTO_STD_BASE"]
)

# Monto promedio reciente por comercio
monto_rec = (
    df_rec.groupby(C["comercio_id"])
    .agg(
        MONTO_PROM_REC  = (C["monto"], "mean"),
        MONTO_TOTAL_REC = (C["monto"], "sum"),
        FRAUDES_REC     = (C["monto"], "count"),
        TARJETAS_REC    = (C["tarjeta"], "nunique"),
    )
    .reset_index()
)

spike_monto = monto_rec.merge(monto_base, on=C["comercio_id"], how="left")

# Solo comparar comercios que tienen baseline (mínimo 3 registros)
spike_monto = spike_monto[spike_monto["N_BASE"] >= 3].copy()
spike_monto = spike_monto[
    spike_monto["MONTO_PROM_REC"] > spike_monto["UMBRAL_SPIKE_MONTO"]
].sort_values("MONTO_PROM_REC", ascending=False)

spike_monto["DESVIOS_SOBRE_MEDIA"] = (
    (spike_monto["MONTO_PROM_REC"] - spike_monto["MONTO_PROM_BASE"]) /
    spike_monto["MONTO_STD_BASE"].replace(0, np.nan)
).round(1)

if C["comercio_nom"] in df.columns:
    spike_monto = spike_monto.merge(nombres, on=C["comercio_id"], how="left")

print(f"  Comercios con spike de monto (>{SPIKE_MONTO_SD}σ): {len(spike_monto):,}")


# ═══════════════════════════════════════════════════════════════════════════════
#  RESUMEN EJECUTIVO
# ═══════════════════════════════════════════════════════════════════════════════
total_alertas = len(fantasmas) + len(spike_vol) + len(spike_monto)

# Comercios únicos alertados (puede haber solapamiento entre detectores)
ids_alertados = set(fantasmas[C["comercio_id"]].tolist() if len(fantasmas) > 0 else [])
ids_alertados |= set(spike_vol[C["comercio_id"]].tolist() if len(spike_vol) > 0 else [])
ids_alertados |= set(spike_monto[C["comercio_id"]].tolist() if len(spike_monto) > 0 else [])

print("\n" + "═" * 65)
print(f"RESUMEN EJECUTIVO — {fecha_hoy}")
print("═" * 65)
print(f"  ① Comercios fantasma              : {len(fantasmas):>4}")
print(f"  ② Spikes de volumen (≥{SPIKE_VOL_X}x)       : {len(spike_vol):>4}")
print(f"  ③ Spikes de monto  (>{SPIKE_MONTO_SD}σ)       : {len(spike_monto):>4}")
print(f"  Comercios únicos con alguna alerta: {len(ids_alertados):>4}")
print("═" * 65)

resumen = pd.DataFrame({
    "Detector"           : ["① Comercio fantasma", f"② Spike volumen (≥{SPIKE_VOL_X}x)", f"③ Spike monto (>{SPIKE_MONTO_SD}σ)"],
    "Comercios alertados": [len(fantasmas), len(spike_vol), len(spike_monto)],
    "Descripción"        : [
        "Aparece solo en 1 mes de la base — bloqueo preventivo",
        f"Fraudes diarios {SPIKE_VOL_X}x sobre su promedio histórico",
        f"Monto promedio {SPIKE_MONTO_SD} desviaciones sobre su media histórica",
    ],
    "Período reciente"   : [f"{fecha_inicio_reciente} → {fecha_hoy}"] * 3,
    "Baseline"           : [f"{fecha_inicio_baseline} → {fecha_fin_baseline}"] * 3,
})


# ═══════════════════════════════════════════════════════════════════════════════
#  EXPORTAR EXCEL
# ═══════════════════════════════════════════════════════════════════════════════
nombre_archivo = f"alertas_{fecha_hoy.strftime('%Y%m%d')}.xlsx"

with pd.ExcelWriter(nombre_archivo, engine="openpyxl") as writer:

    # Hoja 0 — Resumen ejecutivo
    resumen.to_excel(writer, sheet_name="0_Resumen", index=False)

    # Hoja 1 — Comercios fantasma
    if len(fantasmas) > 0:
        fantasmas.to_excel(writer, sheet_name="1_Fantasma", index=False)
    else:
        pd.DataFrame({"Resultado": ["Sin alertas en este período"]}).to_excel(
            writer, sheet_name="1_Fantasma", index=False)

    # Hoja 2 — Spike volumen
    if len(spike_vol) > 0:
        spike_vol.to_excel(writer, sheet_name="2_Spike_Volumen", index=False)
    else:
        pd.DataFrame({"Resultado": ["Sin alertas en este período"]}).to_excel(
            writer, sheet_name="2_Spike_Volumen", index=False)

    # Hoja 3 — Spike monto
    if len(spike_monto) > 0:
        spike_monto.to_excel(writer, sheet_name="3_Spike_Monto", index=False)
    else:
        pd.DataFrame({"Resultado": ["Sin alertas en este período"]}).to_excel(
            writer, sheet_name="3_Spike_Monto", index=False)

print(f"\n✅ Archivo generado: {nombre_archivo}")
print(f"   Hojas: 0_Resumen | 1_Fantasma | 2_Spike_Volumen | 3_Spike_Monto")
print("─" * 65)
