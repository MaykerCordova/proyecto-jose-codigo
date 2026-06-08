"""
ml_scoring.py — Modelo de Scoring Supervisado: P(fraude) por transacción
Tarjetas Comprometidas N7 Débito — Scotiabank Peru

Ejecutar DESPUÉS de feature_engineering.py:
    python scripts/ml_scoring.py

Flujo:
  1. Regresión Logística (class_weight='balanced') — modelo base
  2. Evaluación Train vs Test: AUC, Gini, KS, LogLoss, F1
  3. Matrices de confusión (Train y Test)
  4. Análisis por deciles (Train y Test)
  5. Tabla de umbrales operativos
  6. PSI por feature (estabilidad)
  7. Si AUC < 0.75 → XGBoost con importancia de variables
  8. P_FRAUDE guardado en data/consolidado_scored.parquet

Output:
    output/ml_scoring_NOMBRE.xlsx
    data/consolidado_scored.parquet

Errores corregidos vs versión anterior:
  - Eliminadas features leaky: N_FRAUDES_PREVIOS_CLI,
    FLAG_CLIENTE_YA_FRAUDULENTO, HUBO_FRAUDE_PREVIO_24H
  - Eliminadas features muertas: N_RECHAZOS_24H, N_CVV_FAIL_24H,
    HUBO_CVV_FAIL_PREVIO, RATIO_MONTO_VS_SALDO (cero varianza / NaN masivo)
  - Agrega evaluación en Train + Test separados
  - Agrega matrices de confusión
  - Agrega análisis por deciles
  - Agrega cálculo de PSI
  - Corrige parámetro deprecado use_label_encoder en XGBoost
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
# FUNCIONES AUXILIARES
# ─────────────────────────────────────────────────────────────────────────────

def calcular_metricas(y_true, y_prob, nombre=""):
    """AUC, Gini, KS, LogLoss, F1 a umbral 0.50."""
    from sklearn.metrics import roc_auc_score, log_loss, f1_score
    from scipy.stats import ks_2samp

    auc     = roc_auc_score(y_true, y_prob)
    gini    = 2 * auc - 1
    ks, _   = ks_2samp(y_prob[y_true == 1], y_prob[y_true == 0])
    ll      = log_loss(y_true, y_prob)
    y_pred  = (y_prob >= 0.5).astype(int)
    f1      = f1_score(y_true, y_pred)
    return {
        "Muestra"  : nombre,
        "AUC"      : round(auc,  4),
        "Gini"     : round(gini, 4),
        "KS"       : round(ks,   4),
        "LogLoss"  : round(ll,   4),
        "F1-Score" : round(f1,   4),
    }


def matriz_confusion(y_true, y_prob, umbral=0.5):
    """DataFrame con matriz de confusión (Real × Pred)."""
    from sklearn.metrics import confusion_matrix
    y_pred = (y_prob >= umbral).astype(int)
    cm = confusion_matrix(y_true, y_pred)
    df_cm = pd.DataFrame(
        cm,
        index  =["Real_N", "Real_F"],
        columns=["Pred_N", "Pred_F"],
    )
    return df_cm


def analisis_deciles(y_true, y_prob, n=10):
    """Tabla de deciles: min/max score, N, fraudes, tasa, captura acumulada."""
    df_d = pd.DataFrame({"y": np.array(y_true), "p": np.array(y_prob)})
    df_d["decil"] = pd.qcut(df_d["p"].rank(method="first"), n, labels=False, duplicates="drop")
    df_d["decil"] = n - 1 - df_d["decil"]   # 0 = mayor score

    total_f = df_d["y"].sum()
    rows = []
    for d in range(n):
        sub = df_d[df_d["decil"] == d]
        if len(sub) == 0:
            continue
        nf = int(sub["y"].sum())
        rows.append({
            "Decil"           : d + 1,
            "Min_Score"       : round(sub["p"].min(), 4),
            "Max_Score"       : round(sub["p"].max(), 4),
            "N_Total"         : len(sub),
            "N_Fraudes"       : nf,
            "Tasa_Fraude%"    : round(nf / len(sub) * 100, 2),
            "Captura_Fraude%" : round(nf / max(total_f, 1) * 100, 2),
        })
    return pd.DataFrame(rows)


def calcular_psi(expected, actual, bins=10):
    """Population Stability Index entre train y test para una feature."""
    breakpoints = np.percentile(expected, np.linspace(0, 100, bins + 1))
    breakpoints = np.unique(breakpoints)
    if len(breakpoints) < 2:
        return np.nan
    e_cnt = np.histogram(expected, bins=breakpoints)[0]
    a_cnt = np.histogram(actual,   bins=breakpoints)[0]
    e_pct = np.where(e_cnt == 0, 1e-4, e_cnt / len(expected))
    a_pct = np.where(a_cnt == 0, 1e-4, a_cnt / len(actual))
    psi   = float(np.sum((a_pct - e_pct) * np.log(a_pct / e_pct)))
    estab = "Estable" if psi < 0.10 else ("Alerta" if psi < 0.25 else "Inestable")
    return round(psi, 4), estab


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

mask_modelado = df[col_ind].isin({"F", "G", "N"})
df_model      = df[mask_modelado].copy()
excluidos     = len(df) - len(df_model)
if excluidos > 0:
    print(f"  Filas excluidas (P/D)  : {excluidos:,}")
print(f"  Filas para modelado    : {len(df_model):,}")

y    = df_model["ES_FRAUDE"].astype(int)
n_f  = int(y.sum())
n_nf = int((y == 0).sum())
tasa = n_f / len(y) * 100
print(f"  Fraude (1)             : {n_f:,}  ({tasa:.2f}%)")
print(f"  No fraude (0)          : {n_nf:,}  ({100-tasa:.2f}%)")

# ── Features limpias (sin leakage, sin muertas, sin multicolinealidad) ────
# EXCLUIDAS con justificación:
#   N_FRAUDES_PREVIOS_CLI       → leaky: usa todo el período histórico
#   FLAG_CLIENTE_YA_FRAUDULENTO → leaky: usa todo el período histórico
#   HUBO_FRAUDE_PREVIO_24H      → leaky: label asignado retroactivamente
#   N_RECHAZOS_24H              → muerta: cero varianza en este dataset
#   N_CVV_FAIL_24H              → muerta: cero varianza en este dataset
#   HUBO_CVV_FAIL_PREVIO        → muerta: todo NaN
#   RATIO_MONTO_VS_SALDO        → muerta: saldo vacío para débito (~97% NaN)
#   TRX_CLIENTE_24H             → multicolineal: corr=0.9998 con TRX_TARJETA_24H
#   MNT_TARJETA_24H             → multicolineal: corr=0.9985 con MNT_CLIENTE_24H
#   TRX_CLIENTE_5MIN            → multicolineal: duplica TRX_TARJETA_5MIN
#   HORA_DIA                    → IV=0.0125, WOE plano en todas las franjas
#   ES_TRX_EXTRANJERO           → IV<0.01, sin poder predictivo
#   FLAG_PAIS_DISTINTO_CLIENTE  → IV=0.0041, sin poder predictivo

FEATURES = [f for f in [
    # Monto y moneda
    col_mto,
    "FLAG_MONTO_REDONDO",
    "FLAG_MONTO_BAJO",
    "FLAG_TRX_EN_USD",   # transacción en dólares vs soles
    # Velocidad tarjeta (se prefiere tarjeta sobre cliente — misma info, menos redundancia)
    "TRX_TARJETA_5MIN",
    "TRX_TARJETA_24H",
    # Velocidad cliente (franjas distintas a las de tarjeta)
    "TRX_CLIENTE_1H",
    "MNT_CLIENTE_1H",
    "MNT_CLIENTE_24H",
    "GAP_MINUTOS",
    # Z-scores e interacciones
    "ZSCORE_MONTO_CLIENTE",
    "ZSCORE_MONTO_CLI_COMERCIO",
    "ACELERACION_MONTO",
    "CONCENTRACION_5MIN_1H",
    # Temporal (solo madrugada y fin de semana — HORA_DIA sin poder)
    "ES_MADRUGADA",
    "ES_FIN_SEMANA",
    # Geografía (solo multi-país — los otros sin poder predictivo)
    "FLAG_MULTI_PAIS_24H",
    # MCC y canal
    "FLAG_MCC_ALTO_RIESGO",
    "FLAG_ECOMMERCE",
    # Flags de velocidad
    "FLAG_RAFAGA_5MIN",
    "FLAG_VEL_ALTA_1H",
    # Tipo de transacción
    "ES_TOKENIZADA",        # billetera digital (Google/Apple Pay)
    "ES_TARJETA_PRESENTE",  # transacción presencial (chip/NFC/banda)
    "ES_MOTO",              # mail/telephone order
    "ES_SEGURO",            # autenticada con 3DS (ECI 5 o 2)
    "FLAG_COD_TRX_10",      # código transacción 10
    "FLAG_COD_TRX_92",      # código transacción 92 (reversión/especial)
    # Perfil cliente vs comercio
    "RATIO_TRX_DIA_VS_HIST",
    "FLAG_MONTO_ALTO_CLI_COMERCIO",
    "FLAG_CLI_OUTLIER_TICKET_COMERCIO",
    "FLAG_HORA_FUERA_PERFIL_COMERCIO",
    # SCORE_RIESGO excluido: es suma de flags individuales que YA están en el modelo
    # → genera multicolinealidad severa (OR=44.74 inflado) y distorsiona coeficientes
    # → se mantiene como variable de negocio en reglas_monitor.py (útil ahí)
] if f in df_model.columns]

print(f"\n  Features limpias       : {len(FEATURES)}")
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
    from sklearn.metrics import roc_auc_score, roc_curve, classification_report
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

scaler     = StandardScaler()
X_train_sc = scaler.fit_transform(X_train)
X_test_sc  = scaler.transform(X_test)

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

y_prob_train = lr.predict_proba(X_train_sc)[:, 1]
y_prob_test  = lr.predict_proba(X_test_sc)[:, 1]

# Métricas Train vs Test
met_train = calcular_metricas(y_train, y_prob_train, "Train")
met_test  = calcular_metricas(y_test,  y_prob_test,  "Test")
df_metricas = pd.DataFrame([met_train, met_test])

auc_lr = met_test["AUC"]
ks_lr  = met_test["KS"]

print(f"\n  {'':10} {'AUC':>8} {'Gini':>8} {'KS':>8} {'LogLoss':>9} {'F1':>8}")
print("  " + "─" * 50)
for _, r in df_metricas.iterrows():
    flag = "✅" if r["AUC"] >= AUC_UMBRAL_LOGISTICA else "⚠️ "
    print(f"  {r['Muestra']:<10} {r['AUC']:>8.4f} {r['Gini']:>8.4f} "
          f"{r['KS']:>8.4f} {r['LogLoss']:>9.4f} {r['F1-Score']:>8.4f}  {flag}")

print(f"\n  Reporte a umbral 0.50 (Test):")
print(classification_report(y_test, (y_prob_test >= 0.5).astype(int),
                             target_names=["No Fraude", "Fraude"]))

# Odds ratios
coef_df = pd.DataFrame({
    "Variable"   : FEATURES,
    "Coeficiente": lr.coef_[0],
    "Odds_Ratio" : np.exp(lr.coef_[0]),
}).sort_values("Coeficiente", key=abs, ascending=False)
print(f"  Coeficientes (Odds Ratios) — top 20:")
print(coef_df.head(20).to_string(index=False))

# ─────────────────────────────────────────────────────────────────────────────
# 5. MATRICES DE CONFUSIÓN
# ─────────────────────────────────────────────────────────────────────────────
print("\n[4] Matrices de confusión (umbral 0.50)...")

cm_train = matriz_confusion(y_train, y_prob_train)
cm_test  = matriz_confusion(y_test,  y_prob_test)
print(f"\n  Train:\n{cm_train.to_string()}")
print(f"\n  Test:\n{cm_test.to_string()}")

# ─────────────────────────────────────────────────────────────────────────────
# 6. ANÁLISIS POR DECILES
# ─────────────────────────────────────────────────────────────────────────────
print("\n[5] Análisis por deciles...")

dec_train = analisis_deciles(y_train, y_prob_train)
dec_test  = analisis_deciles(y_test,  y_prob_test)

print(f"\n  Deciles TEST:")
print(dec_test[["Decil","Min_Score","Max_Score","N_Total","N_Fraudes",
                "Tasa_Fraude%","Captura_Fraude%"]].to_string(index=False))

# ─────────────────────────────────────────────────────────────────────────────
# 7. TABLA DE UMBRALES OPERATIVOS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[6] Tabla de umbrales operativos...")

umbrales = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
rows_umb = []
print(f"\n  {'Corte':>6} | {'Precision':>9} | {'Recall':>7} | {'F1':>6} | "
      f"{'Especificidad':>14} | {'FPR':>6} | {'Declina%':>9}")
print("  " + "─" * 78)

for u in umbrales:
    pred = (y_prob_test >= u).astype(int)
    tp   = int(((pred == 1) & (y_test == 1)).sum())
    fp   = int(((pred == 1) & (y_test == 0)).sum())
    fn   = int(((pred == 0) & (y_test == 1)).sum())
    tn   = int(((pred == 0) & (y_test == 0)).sum())
    prec = tp / (tp + fp + 1e-9)
    rec  = tp / (tp + fn + 1e-9)
    f1   = 2 * prec * rec / (prec + rec + 1e-9)
    spec = tn / (tn + fp + 1e-9)
    fpr  = fp / (fp + tn + 1e-9)
    pctd = pred.mean() * 100
    print(f"  {u:>6.2f} | {prec:>9.3f} | {rec:>7.3f} | {f1:>6.3f} | "
          f"{spec:>14.4f} | {fpr:>6.4f} | {pctd:>8.2f}%")
    rows_umb.append({
        "Corte"         : u,
        "Precision"     : round(prec, 4),
        "Recall"        : round(rec,  4),
        "F1-Score"      : round(f1,   4),
        "Especificidad" : round(spec, 4),
        "FPR"           : round(fpr,  4),
        "Pct_Declina%"  : round(pctd, 2),
        "TP": tp, "FP": fp, "FN": fn, "TN": tn,
    })

df_umbrales = pd.DataFrame(rows_umb)

print(f"""
  Umbrales operativos sugeridos:
    Declinar auto      : P >= 0.70  (Precision alta, menor fricción cliente)
    Revisión manual    : P >= 0.45
    Aprobar            : P <  0.45
""")

# ─────────────────────────────────────────────────────────────────────────────
# 8. PSI POR FEATURE (estabilidad Train vs Test)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[7] PSI por feature (estabilidad Train vs Test)...")

rows_psi = []
X_tr_arr = X_train.values
X_te_arr = X_test.values
for i, feat in enumerate(FEATURES):
    try:
        psi_val, estab = calcular_psi(X_tr_arr[:, i], X_te_arr[:, i])
        rows_psi.append({"Variable": feat, "PSI": psi_val, "Estabilidad": estab})
    except Exception:
        rows_psi.append({"Variable": feat, "PSI": np.nan, "Estabilidad": "Error"})

df_psi = pd.DataFrame(rows_psi).sort_values("PSI", ascending=False)
print(f"\n  {'Variable':<45} {'PSI':>8} {'Estabilidad':>12}")
print("  " + "─" * 68)
for _, r in df_psi.iterrows():
    flag = "⚠️ " if r["Estabilidad"] != "Estable" else "  "
    print(f"  {r['Variable']:<45} {r['PSI']:>8.4f} {r['Estabilidad']:>12}  {flag}")

# ─────────────────────────────────────────────────────────────────────────────
# 9. XGBOOST (si AUC de Logística < umbral)
# ─────────────────────────────────────────────────────────────────────────────
modelo_final = "Logistica"
auc_final    = auc_lr
y_prob_final_train = y_prob_train
y_prob_final_test  = y_prob_test
df_metricas_final  = df_metricas.copy()
coef_xgb_df        = pd.DataFrame()
df_shap            = pd.DataFrame()

if auc_lr < AUC_UMBRAL_LOGISTICA:
    print(f"\n[8] AUC Logística ({auc_lr:.4f}) < {AUC_UMBRAL_LOGISTICA} → Entrenando XGBoost...")
    try:
        from xgboost import XGBClassifier

        scale_pw = n_nf / max(n_f, 1)
        xgb = XGBClassifier(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            scale_pos_weight=scale_pw,
            eval_metric="auc",
            random_state=42,
            n_jobs=-1,
        )
        xgb.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        yp_xgb_train = xgb.predict_proba(X_train)[:, 1]
        yp_xgb_test  = xgb.predict_proba(X_test)[:, 1]
        auc_xgb      = roc_auc_score(y_test, yp_xgb_test)
        diff_auc     = auc_xgb - auc_lr

        met_xgb_tr = calcular_metricas(y_train, yp_xgb_train, "Train")
        met_xgb_te = calcular_metricas(y_test,  yp_xgb_test,  "Test")
        print(f"\n  ━━━ XGBOOST ━━━")
        print(f"  AUC Train : {met_xgb_tr['AUC']:.4f}  |  AUC Test: {met_xgb_te['AUC']:.4f}")
        print(f"  Diferencia vs Logística: {diff_auc:+.4f}")

        if diff_auc < 0.03:
            print("  → Diferencia < 0.03: se mantiene Regresión Logística (parsimonia)")
        else:
            print("  → Diferencia >= 0.03: se adopta XGBoost")
            modelo_final           = "XGBoost"
            auc_final              = auc_xgb
            y_prob_final_train     = yp_xgb_train
            y_prob_final_test      = yp_xgb_test
            df_metricas_final      = pd.DataFrame([met_xgb_tr, met_xgb_te])

        coef_xgb_df = pd.DataFrame({
            "Variable"   : FEATURES,
            "Importancia": xgb.feature_importances_,
            "Pct%"       : (xgb.feature_importances_ * 100).round(2),
        }).sort_values("Importancia", ascending=False)
        print(f"\n  Top 15 features (XGBoost):")
        print(coef_xgb_df.head(15).to_string(index=False))

        try:
            import shap
            explainer = shap.TreeExplainer(xgb)
            shap_vals = explainer.shap_values(X_test)
            df_shap   = pd.DataFrame({
                "Variable" : FEATURES,
                "SHAP_mean": np.abs(shap_vals).mean(axis=0),
            }).sort_values("SHAP_mean", ascending=False)
            print(f"\n  SHAP values (top 15):")
            print(df_shap.head(15).to_string(index=False))
        except ImportError:
            print("  ℹ️  SHAP no instalado — omitiendo")

    except ImportError:
        print("  ℹ️  XGBoost no instalado — manteniendo Logística")
else:
    print(f"\n[8] AUC Logística ({auc_lr:.4f}) >= {AUC_UMBRAL_LOGISTICA} ✅ — No se requiere XGBoost")

# ─────────────────────────────────────────────────────────────────────────────
# 10. SCORE P_FRAUDE AL DATASET COMPLETO
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n[9] Asignando P_FRAUDE con modelo: {modelo_final}...")

X_full = df[FEATURES].copy().fillna(0)

if modelo_final == "Logistica":
    df["P_FRAUDE"] = lr.predict_proba(scaler.transform(X_full))[:, 1].round(4)
else:
    df["P_FRAUDE"] = xgb.predict_proba(X_full)[:, 1].round(4)

df["CATEGORIA_RIESGO_ML"] = pd.cut(
    df["P_FRAUDE"],
    bins=[0, 0.30, 0.45, 0.70, 1.0],
    labels=["BAJO", "MEDIO", "ALTO", "MUY_ALTO"],
    include_lowest=True,
)

dist_score = (
    df.groupby("CATEGORIA_RIESGO_ML", observed=True)["ES_FRAUDE"]
    .agg(N="count", N_Fraude="sum")
    .reset_index()
)
dist_score.columns    = ["Categoria", "N_Total", "N_Fraude"]
dist_score["Tasa_F%"] = (dist_score["N_Fraude"] / dist_score["N_Total"] * 100).round(2)
print(f"\n  Distribución P_FRAUDE:")
print(dist_score.to_string(index=False))

try:
    df.to_parquet(PARQUET_SCORED, index=False)
    print(f"\n  ✅  Parquet guardado: {PARQUET_SCORED}")
except Exception as e:
    print(f"  ⚠️  Error guardando parquet: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# 11. CURVA ROC
# ─────────────────────────────────────────────────────────────────────────────
fpr_tr, tpr_tr, _ = roc_curve(y_train, y_prob_final_train)
fpr_te, tpr_te, _ = roc_curve(y_test,  y_prob_final_test)
n_pts = min(500, len(fpr_te))
idx   = np.linspace(0, len(fpr_te) - 1, n_pts, dtype=int)
df_roc = pd.DataFrame({
    "FPR_Train": np.interp(fpr_te[idx], fpr_tr, tpr_tr),   # TPR train interpolado
    "TPR_Train": np.interp(fpr_te[idx], fpr_tr, tpr_tr),
    "FPR_Test" : fpr_te[idx],
    "TPR_Test" : tpr_te[idx],
})
# Corregir columnas
df_roc = pd.DataFrame({
    "FPR_Train": fpr_tr[np.linspace(0, len(fpr_tr)-1, n_pts, dtype=int)],
    "TPR_Train": tpr_tr[np.linspace(0, len(tpr_tr)-1, n_pts, dtype=int)],
    "FPR_Test" : fpr_te[idx],
    "TPR_Test" : tpr_te[idx],
})

idx_opt = int(np.argmax(tpr_te - fpr_te))
print(f"\n  Punto óptimo ROC (Test): umbral en FPR={fpr_te[idx_opt]:.4f} | TPR={tpr_te[idx_opt]:.4f}")

# ─────────────────────────────────────────────────────────────────────────────
# 12. EXPORTAR EXCEL
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n[10] Exportando Excel: {OUTPUT_ML}...")

# Parámetros del modelo
params_lr = {
    "Parametro": ["modelo", "solver", "max_iter", "class_weight", "random_state",
                  "n_features", "AUC_Test", "KS_Test"],
    "Valor"    : ["LogisticRegression", "lbfgs", 1000, "balanced", 42,
                  len(FEATURES), round(auc_lr, 4), round(ks_lr, 4)],
}
df_params = pd.DataFrame(params_lr)

OUTPUT_ML.parent.mkdir(exist_ok=True)
try:
    with pd.ExcelWriter(OUTPUT_ML, engine="openpyxl") as writer:
        df_metricas_final.to_excel(writer, sheet_name="Metricas_Train_Test", index=False)
        cm_train.to_excel(writer,          sheet_name="CM_Train")
        cm_test.to_excel(writer,           sheet_name="CM_Test")
        dec_train.to_excel(writer,         sheet_name="Deciles_Train",  index=False)
        dec_test.to_excel(writer,          sheet_name="Deciles_Test",   index=False)
        df_umbrales.to_excel(writer,       sheet_name="Tabla_Umbrales", index=False)
        df_psi.to_excel(writer,            sheet_name="PSI_Features",   index=False)
        coef_df.to_excel(writer,           sheet_name="Coeficientes_LR",index=False)
        df_roc.to_excel(writer,            sheet_name="Curva_ROC",      index=False)
        dist_score.to_excel(writer,        sheet_name="Dist_Score",     index=False)
        df_params.to_excel(writer,         sheet_name="Parametros",     index=False)
        if not coef_xgb_df.empty:
            coef_xgb_df.to_excel(writer,   sheet_name="Importancia_XGB",index=False)
        if not df_shap.empty:
            df_shap.to_excel(writer,       sheet_name="SHAP_Values",    index=False)

    print(f"  ✅  Excel guardado: {OUTPUT_ML}")
except Exception as e:
    print(f"  ⚠️  Error guardando Excel: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# 13. RESUMEN FINAL
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 65)
print("ML SCORING COMPLETADO")
print("═" * 65)
print(f"""
  Modelo seleccionado  : {modelo_final}
  AUC-ROC  (Test)      : {auc_final:.4f}   {'✅' if auc_final >= 0.75 else '⚠️'}
  KS Stat  (Test)      : {ks_lr:.4f}   {'✅' if ks_lr >= 0.30 else '⚠️'}
  Features usadas      : {len(FEATURES)} (sin leakage)

  Umbrales operativos:
    Declinar auto      : P >= 0.70
    Revisión manual    : P >= 0.45
    Aprobar            : P <  0.45

  Archivos generados:
    → {OUTPUT_ML}
    → {PARQUET_SCORED}
""")
