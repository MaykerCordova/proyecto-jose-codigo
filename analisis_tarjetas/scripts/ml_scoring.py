"""
ml_scoring.py — Modelo de Scoring Supervisado: P(fraude) por transacción
Tarjetas Comprometidas N7 Débito — Scotiabank Peru

Ejecutar DESPUÉS de feature_engineering.py:
    python scripts/ml_scoring.py

Flujo:
  1. Regresión Logística (class_weight='balanced') — modelo base
  2. Evaluación: AUC-ROC, KS Statistic, curva Precision-Recall
  3. Tabla de umbrales operativos (Precision / Recall / FP% / % declina)
  4. Si AUC < 0.75 → XGBoost con SHAP values
  5. Score P_FRAUDE guardado en data/consolidado_scored.parquet

Output:
    output/ml_scoring_NOMBRE.xlsx  — métricas, coeficientes, umbrales
    data/consolidado_scored.parquet — parquet con columna P_FRAUDE añadida
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

OUTPUT_ML      = BASE_DIR / "output" / f"ml_scoring_{ANALISIS_NOMBRE}.xlsx"
PARQUET_SCORED = BASE_DIR / "data" / "consolidado_scored.parquet"

AUC_UMBRAL_LOGISTICA = 0.75   # Si AUC >= esto, la Logística es suficiente

print("═" * 65)
print(f"ML SCORING — {ANALISIS_NOMBRE}")
print("═" * 65)

# ─────────────────────────────────────────────────────────────────────────────
# 1. CARGA
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
    print("❌  Columna ES_FRAUDE no encontrada.")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# 2. PREPARAR TARGET Y FEATURES
# ─────────────────────────────────────────────────────────────────────────────
print("\n[1] Preparando dataset de modelado...")

# Target: F=1, G/N=0. Excluimos P (pendiente) y D (descarte) por ambigüedad.
# Descomenta la siguiente línea para incluirlos como 0:
mask_modelado = df[col_ind].isin({"F", "G", "N"})
df_model      = df[mask_modelado].copy()
excluidos     = len(df) - len(df_model)
if excluidos > 0:
    print(f"  Filas excluidas (P/D)  : {excluidos:,}")
print(f"  Filas para modelado    : {len(df_model):,}")

y = df_model["ES_FRAUDE"].astype(int)
n_f  = int(y.sum())
n_nf = int((y == 0).sum())
tasa = n_f / len(y) * 100
print(f"  Fraude (1)             : {n_f:,}  ({tasa:.2f}%)")
print(f"  No fraude (0)          : {n_nf:,}  ({100-tasa:.2f}%)")

FEATURES = [f for f in [
    # Monto y saldo
    col_mto,
    "RATIO_MONTO_VS_SALDO",
    "FLAG_MONTO_REDONDO",
    "FLAG_MONTO_BAJO",
    # Velocidad cliente
    "TRX_CLIENTE_5MIN",
    "TRX_CLIENTE_1H",
    "TRX_CLIENTE_24H",
    "MNT_CLIENTE_1H",
    "MNT_CLIENTE_24H",
    "GAP_MINUTOS",
    # Velocidad tarjeta
    "TRX_TARJETA_5MIN",
    "TRX_TARJETA_24H",
    "MNT_TARJETA_24H",
    # Z-scores y ratios
    "ZSCORE_MONTO_CLIENTE",
    "ZSCORE_MONTO_CLI_COMERCIO",
    "ACELERACION_MONTO",
    "CONCENTRACION_5MIN_1H",
    # Temporal
    "HORA_DIA",
    "ES_MADRUGADA",
    "ES_FIN_SEMANA",
    # Geografía
    "ES_TRX_EXTRANJERO",
    "FLAG_PAIS_DISTINTO_CLIENTE",
    "FLAG_MULTI_PAIS_24H",
    # MCC y canal
    "FLAG_MCC_ALTO_RIESGO",
    "FLAG_ECOMMERCE",
    # Historial de fraude
    "N_FRAUDES_PREVIOS_CLI",
    "FLAG_CLIENTE_YA_FRAUDULENTO",
    "HUBO_FRAUDE_PREVIO_24H",
    # Rechazos CVV
    "N_RECHAZOS_24H",
    "N_CVV_FAIL_24H",
    "HUBO_CVV_FAIL_PREVIO",
    # Perfil cliente vs comercio
    "RATIO_TRX_DIA_VS_HIST",
    "FLAG_MONTO_ALTO_CLI_COMERCIO",
    "FLAG_CLI_OUTLIER_TICKET_COMERCIO",
    "FLAG_HORA_FUERA_PERFIL_COMERCIO",
    # Score compuesto
    "SCORE_RIESGO",
] if f in df_model.columns]

print(f"\n  Features disponibles   : {len(FEATURES)}")
print(f"  Features: {FEATURES}")

X = df_model[FEATURES].copy().fillna(0)

# ─────────────────────────────────────────────────────────────────────────────
# 3. TRAIN / TEST SPLIT ESTRATIFICADO
# ─────────────────────────────────────────────────────────────────────────────
print("\n[2] Split train/test estratificado (80/20)...")

try:
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (
        roc_auc_score, classification_report,
        roc_curve, precision_recall_curve,
    )
    from scipy.stats import ks_2samp
except ImportError as e:
    print(f"❌  Dependencia faltante: {e}")
    print("    pip install scikit-learn scipy")
    sys.exit(1)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"  Train : {len(X_train):,} filas  (F={y_train.sum():,})")
print(f"  Test  : {len(X_test):,} filas  (F={y_test.sum():,})")

scaler      = StandardScaler()
X_train_sc  = scaler.fit_transform(X_train)
X_test_sc   = scaler.transform(X_test)

# ─────────────────────────────────────────────────────────────────────────────
# 4. REGRESIÓN LOGÍSTICA
# ─────────────────────────────────────────────────────────────────────────────
print("\n[3] Regresión Logística (class_weight='balanced')...")

lr = LogisticRegression(
    class_weight="balanced",
    max_iter=1000,
    solver="lbfgs",
    random_state=42,
)
lr.fit(X_train_sc, y_train)

y_prob_lr  = lr.predict_proba(X_test_sc)[:, 1]
y_pred_lr  = (y_prob_lr >= 0.5).astype(int)

auc_lr = roc_auc_score(y_test, y_prob_lr)

# KS Statistic
ks_stat, ks_pval = ks_2samp(
    y_prob_lr[y_test == 1],
    y_prob_lr[y_test == 0],
)

print(f"\n  ━━━ REGRESIÓN LOGÍSTICA ━━━")
print(f"  AUC-ROC    : {auc_lr:.4f}  {'✅ Aceptable' if auc_lr >= AUC_UMBRAL_LOGISTICA else '⚠️  Por debajo del umbral'}")
print(f"  KS Statistic: {ks_stat:.4f}  {'✅' if ks_stat >= 0.30 else '⚠️'} (ref: >0.30 aceptable, >0.50 excelente)")
print(f"\n  Reporte a umbral 0.50:")
print(classification_report(y_test, y_pred_lr, target_names=["No Fraude","Fraude"]))

# Odds ratios
print(f"\n  Coeficientes (Odds Ratios) — ordenados por |coef|:")
coef_df = pd.DataFrame({
    "Variable"    : FEATURES,
    "Coeficiente" : lr.coef_[0],
    "Odds_Ratio"  : np.exp(lr.coef_[0]),
}).sort_values("Coeficiente", key=abs, ascending=False)
print(coef_df.head(20).to_string(index=False))

# ─────────────────────────────────────────────────────────────────────────────
# 5. TABLA DE UMBRALES OPERATIVOS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[4] Tabla de umbrales operativos...")

umbrales = [0.20, 0.30, 0.40, 0.45, 0.50, 0.60, 0.70, 0.80]
rows_umb = []
print(f"\n  {'Umbral':>7} | {'Declina%':>9} | {'Precision':>9} | {'Recall':>7} | {'F1':>6} | {'FP%':>6} | {'TP%':>6}")
print("  " + "─" * 70)

for u in umbrales:
    pred  = (y_prob_lr >= u).astype(int)
    tp    = int(((pred == 1) & (y_test == 1)).sum())
    fp    = int(((pred == 1) & (y_test == 0)).sum())
    fn    = int(((pred == 0) & (y_test == 1)).sum())
    tn    = int(((pred == 0) & (y_test == 0)).sum())
    prec  = tp / (tp + fp + 1e-9)
    rec   = tp / (tp + fn + 1e-9)
    f1    = 2 * prec * rec / (prec + rec + 1e-9)
    pct_d = pred.mean() * 100
    fp_p  = fp / (y_test == 0).sum() * 100
    tp_p  = rec * 100
    print(f"  {u:>7.2f} | {pct_d:>8.1f}% | {prec:>9.3f} | {rec:>7.3f} | {f1:>6.3f} | {fp_p:>5.1f}% | {tp_p:>5.1f}%")
    rows_umb.append({
        "Umbral"        : u,
        "Pct_Declina%"  : round(pct_d, 2),
        "Precision"     : round(prec, 4),
        "Recall"        : round(rec, 4),
        "F1"            : round(f1, 4),
        "TP"            : tp,
        "FP"            : fp,
        "FN"            : fn,
        "TN"            : tn,
        "FP_pct%"       : round(fp_p, 2),
        "TP_pct%"       : round(tp_p, 2),
    })

df_umbrales = pd.DataFrame(rows_umb)

print(f"""
  Interpretación operativa:
    P >= 0.70 → Declinar automáticamente
    P >= 0.45 → Revisar manualmente / alerta
    P <  0.45 → Aprobar
""")

# ─────────────────────────────────────────────────────────────────────────────
# 6. XGBOOST (si AUC de Logística < umbral)
# ─────────────────────────────────────────────────────────────────────────────
usar_xgb    = auc_lr < AUC_UMBRAL_LOGISTICA
modelo_final = "Logistica"
auc_final    = auc_lr
ks_final     = ks_stat
y_prob_final = y_prob_lr
df_shap      = pd.DataFrame()
coef_xgb_df  = pd.DataFrame()

if usar_xgb:
    print(f"\n[5] AUC Logística ({auc_lr:.4f}) < {AUC_UMBRAL_LOGISTICA} → Entrenando XGBoost...")
    try:
        from xgboost import XGBClassifier

        scale_pw = n_nf / max(n_f, 1)
        xgb = XGBClassifier(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            scale_pos_weight=scale_pw,
            use_label_encoder=False,
            eval_metric="auc",
            random_state=42,
            n_jobs=-1,
        )
        xgb.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        y_prob_xgb = xgb.predict_proba(X_test)[:, 1]
        auc_xgb    = roc_auc_score(y_test, y_prob_xgb)
        ks_xgb, _  = ks_2samp(y_prob_xgb[y_test==1], y_prob_xgb[y_test==0])

        print(f"\n  ━━━ XGBOOST ━━━")
        print(f"  AUC-ROC     : {auc_xgb:.4f}")
        print(f"  KS Statistic: {ks_xgb:.4f}")
        diff_auc = auc_xgb - auc_lr
        print(f"  Diferencia vs Logística: {diff_auc:+.4f}")
        if diff_auc < 0.03:
            print(f"  → Diferencia < 0.03: se mantiene Regresión Logística (parsimonia)")
        else:
            print(f"  → Diferencia >= 0.03: se adopta XGBoost")
            modelo_final  = "XGBoost"
            auc_final     = auc_xgb
            ks_final      = ks_xgb
            y_prob_final  = y_prob_xgb

        # Feature importance XGBoost
        coef_xgb_df = pd.DataFrame({
            "Variable"   : FEATURES,
            "Importancia": xgb.feature_importances_,
        }).sort_values("Importancia", ascending=False)
        print(f"\n  Top 15 features (XGBoost):")
        print(coef_xgb_df.head(15).to_string(index=False))

        # SHAP values
        try:
            import shap
            explainer  = shap.TreeExplainer(xgb)
            shap_vals  = explainer.shap_values(X_test)
            shap_mean  = np.abs(shap_vals).mean(axis=0)
            df_shap    = pd.DataFrame({"Variable": FEATURES, "SHAP_mean": shap_mean})
            df_shap    = df_shap.sort_values("SHAP_mean", ascending=False)
            print(f"\n  SHAP values (top 15):")
            print(df_shap.head(15).to_string(index=False))
        except ImportError:
            print("  ℹ️  SHAP no instalado (pip install shap) — omitiendo SHAP values")

    except ImportError:
        print("  ℹ️  XGBoost no instalado (pip install xgboost) — manteniendo Logística")
        usar_xgb = False

else:
    print(f"\n[5] AUC Logística ({auc_lr:.4f}) >= {AUC_UMBRAL_LOGISTICA} ✅ — No se requiere XGBoost")

# ─────────────────────────────────────────────────────────────────────────────
# 7. SCORE P_FRAUDE AL DATASET COMPLETO
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n[6] Asignando P_FRAUDE al dataset completo con modelo: {modelo_final}...")

X_full  = df[FEATURES].copy().fillna(0)

if modelo_final == "Logistica":
    X_full_sc          = scaler.transform(X_full)
    df["P_FRAUDE"]     = lr.predict_proba(X_full_sc)[:, 1].round(4)
else:
    df["P_FRAUDE"]     = xgb.predict_proba(X_full)[:, 1].round(4)

df["CATEGORIA_RIESGO_ML"] = pd.cut(
    df["P_FRAUDE"],
    bins  = [0, 0.30, 0.45, 0.70, 1.0],
    labels= ["BAJO", "MEDIO", "ALTO", "MUY_ALTO"],
    include_lowest=True,
)

print(f"  Distribución P_FRAUDE:")
print(df.groupby("CATEGORIA_RIESGO_ML", observed=True)["ES_FRAUDE"].agg(
    N="count", N_Fraude="sum"
).assign(Tasa_F=lambda x: (x["N_Fraude"]/x["N"]*100).round(2)).to_string())

# Guardar parquet scored
try:
    df.to_parquet(PARQUET_SCORED, index=False)
    print(f"\n  ✅  Parquet guardado: {PARQUET_SCORED}")
except Exception as e:
    print(f"  ⚠️  Error guardando parquet: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# 8. CURVA ROC — datos para graficar
# ─────────────────────────────────────────────────────────────────────────────
fpr, tpr, thresholds_roc = roc_curve(y_test, y_prob_final)
df_roc = pd.DataFrame({"FPR": fpr, "TPR": tpr, "Threshold": thresholds_roc})

# Punto de operación sugerido (maximiza TPR - FPR)
idx_opt = np.argmax(tpr - fpr)
print(f"\n  Punto óptimo en curva ROC:")
print(f"    Threshold : {thresholds_roc[idx_opt]:.4f}")
print(f"    TPR (Recall): {tpr[idx_opt]:.4f}")
print(f"    FPR         : {fpr[idx_opt]:.4f}")

# ─────────────────────────────────────────────────────────────────────────────
# 9. EXPORTAR EXCEL
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n[7] Exportando Excel: {OUTPUT_ML}...")

# Sheet: métricas resumen
df_metricas = pd.DataFrame([{
    "Modelo"         : modelo_final,
    "AUC_ROC"        : round(auc_final, 4),
    "KS_Statistic"   : round(ks_final, 4),
    "AUC_Logistica"  : round(auc_lr, 4),
    "KS_Logistica"   : round(ks_stat, 4),
    "N_Train"        : len(X_train),
    "N_Test"         : len(X_test),
    "N_Fraude_Train" : int(y_train.sum()),
    "N_Fraude_Test"  : int(y_test.sum()),
    "Tasa_Fraude%"   : round(tasa, 2),
    "Features_usadas": len(FEATURES),
}])

try:
    with pd.ExcelWriter(OUTPUT_ML, engine="openpyxl") as writer:
        df_metricas.to_excel(writer, sheet_name="Metricas_Resumen", index=False)
        coef_df.to_excel(writer, sheet_name="Coeficientes_LR", index=False)
        df_umbrales.to_excel(writer, sheet_name="Tabla_Umbrales", index=False)
        df_roc.to_excel(writer, sheet_name="Curva_ROC", index=False)
        if not coef_xgb_df.empty:
            coef_xgb_df.to_excel(writer, sheet_name="Importancia_XGB", index=False)
        if not df_shap.empty:
            df_shap.to_excel(writer, sheet_name="SHAP_Values", index=False)

        # Distribución del score final
        dist_score = df.groupby("CATEGORIA_RIESGO_ML", observed=True)["ES_FRAUDE"].agg(
            N="count", N_Fraude="sum"
        ).reset_index()
        dist_score.columns = ["Categoria", "N_Total", "N_Fraude"]
        dist_score["Tasa_F%"] = (dist_score["N_Fraude"] / dist_score["N_Total"] * 100).round(2)
        dist_score.to_excel(writer, sheet_name="Dist_Score", index=False)

    print(f"  ✅  Excel guardado: {OUTPUT_ML}")
except Exception as e:
    print(f"  ⚠️  Error guardando Excel: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# 10. RESUMEN FINAL
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 65)
print("ML SCORING COMPLETADO")
print("═" * 65)
print(f"""
  Modelo seleccionado  : {modelo_final}
  AUC-ROC              : {auc_final:.4f}  {'✅' if auc_final >= 0.75 else '⚠️'}
  KS Statistic         : {ks_final:.4f}  {'✅' if ks_final >= 0.30 else '⚠️'}

  Umbrales sugeridos:
    Declinar auto      : P >= 0.70
    Alerta / revisión  : P >= 0.45
    Aprobar            : P <  0.45

  Archivos generados:
    → {OUTPUT_ML}
    → {PARQUET_SCORED}
""")
