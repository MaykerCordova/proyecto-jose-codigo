"""
eda_fraude.py — Análisis Exploratorio: Fraude vs No Fraude
Tarjetas Comprometidas N7 Débito — Scotiabank Peru

Ejecutar DESPUÉS de feature_engineering.py:
    python scripts/eda_fraude.py

Output:
    output/eda_TARJETAS_COMPROMETIDAS_N7.xlsx  (estadísticas comparativas F vs N)
"""

import sys
import warnings
import pandas as pd
import numpy as np
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import COLS, PARQUET_FEATURES, ANALISIS_NOMBRE, BASE_DIR

C       = COLS
col_ind = C["indicador"]
col_mto = C["monto"]
col_mcc = C["mcc"]
col_pais= C["pais"]
col_em  = C["entry_mode"]

OUTPUT_EDA = BASE_DIR / "output" / f"eda_{ANALISIS_NOMBRE}.xlsx"

print("═" * 65)
print(f"EDA FRAUDE — {ANALISIS_NOMBRE}")
print("═" * 65)

# ─────────────────────────────────────────────────────────────────────────────
# CARGA
# ─────────────────────────────────────────────────────────────────────────────
ruta = PARQUET_FEATURES
if not ruta.exists():
    print(f"\n❌  No se encontró: {ruta}")
    print("    Ejecuta primero: python scripts/feature_engineering.py")
    sys.exit(1)

df = pd.read_parquet(ruta)
df[col_mto] = pd.to_numeric(df[col_mto], errors="coerce")
print(f"\n  Filas totales : {len(df):,}")
print(f"  Columnas      : {df.shape[1]}")

if "ES_FRAUDE" not in df.columns:
    print("❌  Columna ES_FRAUDE no encontrada. Verifica feature_engineering.py")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# 1. BALANCE DE CLASES
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("[1] BALANCE DE CLASES")
print("─" * 65)

dist_ind = df[col_ind].value_counts()
print(f"\n  Distribución indicador:")
for v, n in dist_ind.items():
    print(f"    {v:3s}  {n:8,}  ({n/len(df)*100:.1f}%)")

n_fraude    = int(df["ES_FRAUDE"].sum())
n_no_fraude = len(df) - n_fraude
tasa_fraude = n_fraude / len(df) * 100

print(f"\n  ES_FRAUDE = 1 (F)     : {n_fraude:,}  ({tasa_fraude:.2f}%)")
print(f"  ES_FRAUDE = 0 (resto) : {n_no_fraude:,}  ({100-tasa_fraude:.2f}%)")
print(f"\n  Ratio desbalance      : 1 : {n_no_fraude // max(n_fraude,1)}")

if tasa_fraude < 5:
    print("  ⚠️  Clase muy desbalanceada — usar class_weight='balanced' en el modelo")
elif tasa_fraude > 40:
    print("  ✅  Balance aceptable para modelado directo")

df_f = df[df["ES_FRAUDE"] == 1]
df_n = df[df["ES_FRAUDE"] == 0]

# ─────────────────────────────────────────────────────────────────────────────
# 2. VARIABLES NUMÉRICAS — COMPARACIÓN F vs N
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("[2] VARIABLES NUMÉRICAS — Fraude vs No Fraude")
print("─" * 65)

NUMERICAS = [f for f in [
    col_mto,
    "TRX_CLIENTE_5MIN", "TRX_CLIENTE_1H", "TRX_CLIENTE_24H",
    "MNT_CLIENTE_1H", "MNT_CLIENTE_24H", "GAP_MINUTOS",
    "TRX_TARJETA_5MIN", "TRX_TARJETA_24H", "MNT_TARJETA_24H",
    "ZSCORE_MONTO_CLIENTE", "ZSCORE_MONTO_CLI_COMERCIO",
    "ACELERACION_MONTO", "CONCENTRACION_5MIN_1H",
    "HORA_DIA", "RATIO_MONTO_VS_SALDO",
    "N_RECHAZOS_24H", "N_CVV_FAIL_24H",
    "TOTAL_TRX_CLIENTE", "TOTAL_TRX_TARJETA",
    "SCORE_RIESGO",
] if f in df.columns]

rows_num = []
for col in NUMERICAS:
    vals_f = df_f[col].dropna()
    vals_n = df_n[col].dropna()
    if len(vals_f) == 0 or len(vals_n) == 0:
        continue

    # Mann-Whitney U — no paramétrico, no asume normalidad
    try:
        from scipy.stats import mannwhitneyu
        stat, pval = mannwhitneyu(vals_f, vals_n, alternative="two-sided")
        significativo = "***" if pval < 0.001 else ("**" if pval < 0.01 else ("*" if pval < 0.05 else ""))
    except Exception:
        pval, significativo = np.nan, ""

    rows_num.append({
        "Variable"          : col,
        "Media_F"           : round(vals_f.mean(), 4),
        "Media_N"           : round(vals_n.mean(), 4),
        "Mediana_F"         : round(vals_f.median(), 4),
        "Mediana_N"         : round(vals_n.median(), 4),
        "Std_F"             : round(vals_f.std(), 4),
        "Std_N"             : round(vals_n.std(), 4),
        "p_valor"           : round(pval, 6) if not np.isnan(pval) else None,
        "Significativo"     : significativo,
        "N_F"               : len(vals_f),
        "N_N"               : len(vals_n),
    })

df_num = pd.DataFrame(rows_num)
df_num_show = df_num.sort_values("p_valor").head(20)
print(f"\n  Top variables con mayor diferencia estadística F vs N:")
print(df_num_show[["Variable","Media_F","Media_N","Mediana_F","Mediana_N","p_valor","Significativo"]].to_string(index=False))

# ─────────────────────────────────────────────────────────────────────────────
# 3. VARIABLES BINARIAS / FLAGS — COMPARACIÓN F vs N
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("[3] FLAGS BINARIOS — Tasa fraude con flag=1 vs flag=0")
print("─" * 65)

FLAGS = [f for f in [
    "ES_MADRUGADA", "ES_FIN_SEMANA", "FLAG_RAFAGA_5MIN",
    "FLAG_VEL_ALTA_1H", "FLAG_MONTO_REDONDO", "FLAG_MONTO_BAJO",
    "FLAG_MCC_ALTO_RIESGO", "FLAG_ECOMMERCE", "FLAG_PAIS_DISTINTO_CLIENTE",
    "FLAG_MULTI_PAIS_24H", "ES_TRX_EXTRANJERO",
    "HUBO_CVV_FAIL_PREVIO", "HUBO_FRAUDE_PREVIO_24H",
    "FLAG_BIN12_REPETIDO_DIA", "FLAG_CLIENTE_YA_FRAUDULENTO",
    "FLAG_MONTO_ALTO_CLI_COMERCIO", "FLAG_CLI_OUTLIER_TICKET_COMERCIO",
    "FLAG_HORA_FUERA_PERFIL_COMERCIO",
] if f in df.columns]

rows_flag = []
for col in FLAGS:
    g = df.groupby(col)["ES_FRAUDE"].agg(["sum", "count"]).reset_index()
    g.columns = [col, "n_fraude", "n_total"]
    g["tasa_fraude"] = g["n_fraude"] / g["n_total"]
    row = {"Flag": col}
    for _, r in g.iterrows():
        lbl = f"Flag={int(r[col])}"
        row[f"N_{lbl}"]         = int(r["n_total"])
        row[f"Tasa_F_{lbl}_%"] = round(r["tasa_fraude"] * 100, 2)
    rows_flag.append(row)

df_flags = pd.DataFrame(rows_flag)
print(f"\n{'Flag':<42} {'N_Flag=0':>10} {'Tasa%_0':>9} {'N_Flag=1':>10} {'Tasa%_1':>9}")
print("─" * 85)
for _, r in df_flags.iterrows():
    n0  = r.get("N_Flag=0",  0)
    t0  = r.get("Tasa_F_Flag=0_%", 0)
    n1  = r.get("N_Flag=1",  0)
    t1  = r.get("Tasa_F_Flag=1_%", 0)
    print(f"  {r['Flag']:<40} {n0:>10,} {t0:>8.2f}% {n1:>10,} {t1:>8.2f}%")

# ─────────────────────────────────────────────────────────────────────────────
# 4. TOP MCCs POR TASA DE FRAUDE
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("[4] TOP MCCs POR TASA DE FRAUDE")
print("─" * 65)

if col_mcc in df.columns:
    mcc_stats = (
        df.groupby(col_mcc)
        .agg(N=(col_mto, "count"), N_F=("ES_FRAUDE", "sum"), Monto_med=(col_mto, "median"))
        .reset_index()
    )
    mcc_stats["Tasa_F%"] = (mcc_stats["N_F"] / mcc_stats["N"] * 100).round(2)
    top_mcc = mcc_stats[mcc_stats["N"] >= 20].sort_values("Tasa_F%", ascending=False).head(20)
    print(f"\n  Top 20 MCCs (mín 20 txn) con mayor tasa de fraude:")
    print(top_mcc[["ACF-MCC +","N","N_F","Tasa_F%","Monto_med"]].rename(
        columns={col_mcc:"MCC"}
    ).to_string(index=False))

# ─────────────────────────────────────────────────────────────────────────────
# 5. FRANJA HORARIA
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("[5] FRANJA HORARIA — Tasa de fraude por hora del día")
print("─" * 65)

if "HORA_DIA" in df.columns:
    hora_stats = (
        df.groupby("HORA_DIA")
        .agg(N=(col_mto,"count"), N_F=("ES_FRAUDE","sum"))
        .reset_index()
    )
    hora_stats["Tasa_F%"] = (hora_stats["N_F"] / hora_stats["N"] * 100).round(2)
    print(f"\n  {'Hora':>5} {'N':>8} {'N_F':>8} {'Tasa_F%':>9}")
    for _, r in hora_stats.iterrows():
        bar = "█" * int(r["Tasa_F%"] / 2)
        print(f"  {int(r['HORA_DIA']):>5}  {int(r['N']):>8,}  {int(r['N_F']):>8,}  {r['Tasa_F%']:>8.2f}%  {bar}")

if "FRANJA_HORARIA" in df.columns:
    print(f"\n  Por franja horaria:")
    fh = df.groupby("FRANJA_HORARIA")["ES_FRAUDE"].agg(["mean","count","sum"]).reset_index()
    fh.columns = ["Franja","Tasa_F","N_Total","N_Fraude"]
    fh["Tasa_F%"] = (fh["Tasa_F"] * 100).round(2)
    print(fh[["Franja","N_Total","N_Fraude","Tasa_F%"]].to_string(index=False))

# ─────────────────────────────────────────────────────────────────────────────
# 6. PAÍS — DISTRIBUCIÓN
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("[6] PAÍS DE TRANSACCIÓN")
print("─" * 65)

if col_pais in df.columns:
    pais_stats = (
        df.groupby(col_pais)
        .agg(N=(col_mto,"count"), N_F=("ES_FRAUDE","sum"))
        .reset_index()
    )
    pais_stats["Tasa_F%"] = (pais_stats["N_F"] / pais_stats["N"] * 100).round(2)
    top_pais = pais_stats.sort_values("N_F", ascending=False).head(20)
    print(f"\n  {'País':<8} {'N':>10} {'N_Fraude':>10} {'Tasa_F%':>9}")
    for _, r in top_pais.iterrows():
        print(f"  {str(r[col_pais]):<8} {int(r['N']):>10,} {int(r['N_F']):>10,} {r['Tasa_F%']:>8.2f}%")

# ─────────────────────────────────────────────────────────────────────────────
# 7. CORRELACIÓN DE FEATURES CON ES_FRAUDE
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("[7] CORRELACIÓN CON ES_FRAUDE (Pearson)")
print("─" * 65)

TODAS_NUM = [f for f in NUMERICAS + FLAGS if f in df.columns]
corr_series = df[TODAS_NUM + ["ES_FRAUDE"]].corr()["ES_FRAUDE"].drop("ES_FRAUDE")
corr_sorted = corr_series.abs().sort_values(ascending=False)
print(f"\n  Top 20 features más correlacionadas con fraude:")
for feat, corr_abs in corr_sorted.head(20).items():
    corr_val = corr_series[feat]
    barra = "+" if corr_val > 0 else "-"
    print(f"  {feat:<45} {corr_val:+.4f}  {barra * int(abs(corr_val)*30)}")

# ─────────────────────────────────────────────────────────────────────────────
# 8. EXPORTAR EXCEL
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("[8] Exportando Excel...")
print("─" * 65)

OUTPUT_EDA.parent.mkdir(exist_ok=True)

# Sheet: balance
df_balance = pd.DataFrame({
    "Indicador"   : dist_ind.index.tolist(),
    "N"           : dist_ind.values.tolist(),
    "Pct%"        : (dist_ind.values / len(df) * 100).round(2).tolist(),
})

# Sheet: hora
df_hora = hora_stats if "HORA_DIA" in df.columns else pd.DataFrame()

# Sheet: país
df_pais_out = pais_stats.sort_values("N_F", ascending=False) if col_pais in df.columns else pd.DataFrame()

# Sheet: MCC
df_mcc_out = top_mcc.rename(columns={col_mcc: "MCC"}) if col_mcc in df.columns else pd.DataFrame()

# Sheet: correlaciones
df_corr_out = corr_series.reset_index()
df_corr_out.columns = ["Variable","Corr_con_ES_FRAUDE"]
df_corr_out["Abs_Corr"] = df_corr_out["Corr_con_ES_FRAUDE"].abs()
df_corr_out = df_corr_out.sort_values("Abs_Corr", ascending=False)

try:
    with pd.ExcelWriter(OUTPUT_EDA, engine="openpyxl") as writer:
        df_balance.to_excel(writer, sheet_name="Balance_Clases", index=False)
        df_num.sort_values("p_valor").to_excel(writer, sheet_name="Numericas_F_vs_N", index=False)
        df_flags.to_excel(writer, sheet_name="Flags_F_vs_N", index=False)
        df_hora.to_excel(writer, sheet_name="Hora_del_Dia", index=False)
        df_pais_out.to_excel(writer, sheet_name="Por_Pais", index=False)
        df_mcc_out.to_excel(writer, sheet_name="Top_MCC", index=False)
        df_corr_out.to_excel(writer, sheet_name="Correlaciones", index=False)

    print(f"\n  ✅  Excel guardado en: {OUTPUT_EDA}")
except Exception as e:
    print(f"\n  ⚠️  Error al guardar Excel: {e}")

print("\n" + "═" * 65)
print("EDA COMPLETADO")
print("═" * 65)
print(f"\n  Resumen clave:")
print(f"    Tasa de fraude        : {tasa_fraude:.2f}%")
print(f"    Variables numéricas   : {len(NUMERICAS)}")
print(f"    Flags binarios        : {len(FLAGS)}")
print(f"    Top feature (corr)    : {corr_sorted.index[0]}  ({corr_series[corr_sorted.index[0]]:+.4f})")
