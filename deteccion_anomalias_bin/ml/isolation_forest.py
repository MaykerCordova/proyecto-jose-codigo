"""
isolation_forest.py  (Paso 6 — Fase 2: capa multivariada)
──────────────────────────────────────────────────────────
Entrena un Isolation Forest sobre la tabla de features por
BIN_10 × COMERCIO × día y marca combinaciones anómalas que ningún
umbral univariado detecta.

Ejemplo de firma que el z-score de volumen NO ve:
  volumen normal + 12 trx/tarjeta + 45% de declinación → card testing.

Contraste con el baseline: la salida cruza los flags del IF contra las
alertas del z-robusto (deteccion.py) para ver dónde coinciden y dónde
el IF aporta casos nuevos.

Requiere haber corrido antes: agregacion.py y deteccion.py
Salidas: data/if_scores.parquet | output/isolation_forest_<NOMBRE>.xlsx
"""

import sys
from pathlib import Path

import pandas as pd
from sklearn.ensemble import IsolationForest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from config import (
    ISOLATION_FOREST, PARQUET_SERIE_BIN10_COMERCIO, PARQUET_ALERTAS,
    PARQUET_IF, EXCEL_IF,
)

CFG      = ISOLATION_FOREST
FEATURES = CFG["features"]

print("═" * 65)
print("ISOLATION FOREST — capa multivariada (fase 2)")
print("═" * 65)

if not PARQUET_SERIE_BIN10_COMERCIO.exists():
    print("❌  Falta la serie BIN10×COMERCIO — ejecuta agregacion.py")
    sys.exit(1)

df = pd.read_parquet(PARQUET_SERIE_BIN10_COMERCIO)

# Solo días con actividad: los días densificados a 0 no aportan al modelo
df = df[df["N_TRX"] > 0].copy()
print(f"  Filas BIN10×COMERCIO×día con actividad: {len(df):,}")

X = df[FEATURES].fillna(0.0)

modelo = IsolationForest(
    n_estimators=CFG["n_estimators"],
    contamination=CFG["contamination"],
    random_state=CFG["random_state"],
)
df["FLAG_IF"]  = modelo.fit_predict(X) == -1
df["SCORE_IF"] = modelo.score_samples(X)          # más negativo = más anómalo

n_flags = int(df["FLAG_IF"].sum())
print(f"  Flags IF: {n_flags:,} ({n_flags / len(df):.2%})")


# ─────────────────────────────────────────────────────────────────────────────
# CONTRASTE CON EL BASELINE (z-robusto)
# ─────────────────────────────────────────────────────────────────────────────
if PARQUET_ALERTAS.exists():
    alertas_z = pd.read_parquet(PARQUET_ALERTAS)
    alertas_z = alertas_z[alertas_z["NIVEL"] == "BIN10_COMERCIO"][
        ["BIN_10", "COMERCIO", "FECHA", "Z_ROBUSTO", "ALERTA"]
    ].rename(columns={"ALERTA": "ALERTA_Z"})
    df = df.merge(alertas_z, on=["BIN_10", "COMERCIO", "FECHA"], how="left")
    df["ALERTA_Z"] = df["ALERTA_Z"].fillna(False)

    cruce = pd.crosstab(df["FLAG_IF"], df["ALERTA_Z"],
                        rownames=["FLAG_IF"], colnames=["ALERTA_Z"])
    print("\n  Matriz IF vs baseline z-robusto:")
    print(cruce.to_string())
    solo_if = df[df["FLAG_IF"] & ~df["ALERTA_Z"]]
    print(f"\n  Casos que SOLO detecta el IF (aporte multivariado): {len(solo_if):,}")
else:
    print("  ⚠️  Sin alertas.parquet — corre deteccion.py para el contraste.")
    df["ALERTA_Z"] = False


# ─────────────────────────────────────────────────────────────────────────────
# GUARDAR
# ─────────────────────────────────────────────────────────────────────────────
df.to_parquet(PARQUET_IF, index=False)

flags = df[df["FLAG_IF"]].sort_values("SCORE_IF")
cols_out = (["BIN_10", "COMERCIO", "FECHA", "SCORE_IF", "ALERTA_Z"]
            + FEATURES)
EXCEL_IF.parent.mkdir(parents=True, exist_ok=True)
with pd.ExcelWriter(EXCEL_IF, engine="openpyxl") as xl:
    flags[cols_out].to_excel(xl, sheet_name="1_Flags_IF", index=False)
    if "ALERTA_Z" in df.columns:
        solo_if = df[df["FLAG_IF"] & ~df["ALERTA_Z"]].sort_values("SCORE_IF")
        solo_if[cols_out].to_excel(xl, sheet_name="2_Solo_IF", index=False)

print(f"\n✅ Guardado: {PARQUET_IF}")
print(f"✅ Guardado: {EXCEL_IF}")
print("═" * 65)
