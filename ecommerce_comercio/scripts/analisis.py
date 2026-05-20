"""
analisis.py
───────────
Lee data/consolidado_features.parquet y genera el Excel de análisis.

Hojas:
  1_Resumen         KPIs totales y por quincena (indicador F/B/D/P/N)
  2_Por_Producto    Pivot: indicador × tipo producto
  3_Por_Segmento    Pivot: indicador × segmento (con nombres legibles)
  4_Por_ECI         Pivot: indicador × seguridad ECI (Seguro / No Seguro)
  5_Motivos_Rechazo Distribución motivos de rechazo en denegadas
  6_Velocidad       GAP_MINUTOS: intervalos × indicador
  7_CVV             Pivot: indicador × ACF-COD RED COMERCIO
  8_Variables       Medias/medianas de features numéricas por indicador
  9_Perfil_Riesgo   Pivot: PERFIL_RIESGO × indicador
  10_Muestra        500 filas de fraudes (indicador=F) con todas las features
"""

import sys
import warnings
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    PARQUET_FEATURES, EXCEL_OUTPUT, COMERCIO_NOMBRE,
    SEG_NOMBRE, COD_RED_LABEL,
)

# ─────────────────────────────────────────────────────────────────────────────
# CARGA
# ─────────────────────────────────────────────────────────────────────────────
ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else PARQUET_FEATURES

if not ruta.exists():
    print(f"\n❌  No se encontró: {ruta}")
    print("    Ejecuta primero: python scripts/feature_engineering.py")
    sys.exit(1)

print("═" * 65)
print(f"ANÁLISIS ECOMMERCE — {COMERCIO_NOMBRE}")
print("═" * 65)

df = pd.read_parquet(ruta)

# Columnas clave (claves cortas, ya renombradas por feature_engineering.py)
COL_IND   = "indicador"
COL_MONTO = "monto"
COL_FH    = "fecha_hora"
COL_SEG   = "segmento"
COL_TIPO  = "tipo_producto"
COL_ECI   = "SEGURO"
COL_CVV   = "COD_RED_LABEL"
COL_MOTIVO= "MOTIVO_RECH"
COL_RIESGO= "PERFIL_RIESGO"
COL_QUI   = "QUINCENA"
COL_MES   = "mes"

INDICADORES = ["F","B","G","D","P","N"]

print(f"  Filas: {len(df):,} | Columnas: {df.shape[1]}")
if COL_IND in df.columns:
    print(f"  Distribución indicador:\n{df[COL_IND].value_counts().to_string()}")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DE FORMATO EXCEL
# ─────────────────────────────────────────────────────────────────────────────
FH = PatternFill("solid", fgColor="1F3864")   # azul oscuro — título principal
FS = PatternFill("solid", fgColor="2E75B6")   # azul medio — subtítulo / encabezado
FA = PatternFill("solid", fgColor="DEEAF1")   # azul claro — filas pares
FY = PatternFill("solid", fgColor="FFF2CC")   # amarillo  — interpretaciones
FF = PatternFill("solid", fgColor="FCE4D6")   # naranja   — filas fraude
fH = Font(color="FFFFFF", bold=True, size=10)
fN = Font(size=10)
fI = Font(italic=True, size=9, color="1F3864")
BT = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin")
)
AC = Alignment(horizontal="center", vertical="center", wrap_text=True)
AL = Alignment(horizontal="left",   vertical="center", wrap_text=True)


def titulo(ws, fila, n_cols, texto, fill=None):
    fill = fill or FH
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=n_cols)
    c = ws.cell(row=fila, column=1, value=texto)
    c.fill = fill; c.font = fH; c.alignment = AC; c.border = BT


def encabezado(ws, fila):
    for r in ws.iter_rows(min_row=fila, max_row=fila):
        for c in r:
            c.fill = FS; c.font = fH; c.alignment = AC; c.border = BT


def estilizar(ws, fi, ff, kw_fraude=None):
    for i, row in enumerate(ws.iter_rows(min_row=fi, max_row=ff), start=1):
        fl = FA if i % 2 == 0 else PatternFill()
        if kw_fraude and row[0].value and any(k in str(row[0].value).upper() for k in kw_fraude):
            fl = FF
        for c in row:
            c.fill = fl; c.font = fN; c.alignment = AC; c.border = BT


def autofit(ws):
    for col in ws.columns:
        ml = max((len(str(c.value)) for c in col if c.value is not None), default=10)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(ml + 4, 40)


def escribir_tabla(ws, df_t, fila_inicio):
    df_r = df_t.reset_index()
    n = len(df_r.columns)
    for j, col in enumerate(df_r.columns, start=1):
        c = ws.cell(row=fila_inicio, column=j, value=str(col))
        c.fill = FS; c.font = fH; c.alignment = AC; c.border = BT
    fila_inicio += 1
    for i, row in df_r.iterrows():
        fl = FA if i % 2 == 0 else PatternFill()
        for j, val in enumerate(row, start=1):
            v = round(val, 4) if isinstance(val, float) else val
            c = ws.cell(row=fila_inicio, column=j, value=v)
            c.fill = fl; c.font = fN; c.alignment = AC; c.border = BT
        fila_inicio += 1
    return fila_inicio


# ─────────────────────────────────────────────────────────────────────────────
# DATOS DERIVADOS
# ─────────────────────────────────────────────────────────────────────────────
df[COL_MONTO] = pd.to_numeric(df[COL_MONTO], errors="coerce")
df[COL_FH]    = pd.to_datetime(df[COL_FH],    errors="coerce")

if COL_SEG in df.columns:
    df["SEG_NOMBRE"] = df[COL_SEG].astype(str).map(SEG_NOMBRE).fillna("Otro/Sin seg")

df_f = df[df[COL_IND] == "F"].copy() if COL_IND in df.columns else pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# 1. RESUMEN
# ─────────────────────────────────────────────────────────────────────────────
print("\n[1] Resumen...")

quincenas = sorted(df[COL_QUI].unique()) if COL_QUI in df.columns else ["Total"]
indicadores_presentes = [i for i in INDICADORES if i in df[COL_IND].unique()] if COL_IND in df.columns else []

filas_res = []
for qui in quincenas:
    sub = df[df[COL_QUI] == qui] if COL_QUI in df.columns else df
    fila = {"Quincena": qui, "Total trx": len(sub),
            "Monto total (S/)": round(sub[COL_MONTO].sum(), 2),
            "Ticket prom (S/)": round(sub[COL_MONTO].mean(), 2)}
    for ind in indicadores_presentes:
        si = sub[sub[COL_IND] == ind] if COL_IND in sub.columns else pd.DataFrame()
        fila[f"N_{ind}"]      = len(si)
        fila[f"Monto_{ind}"]  = round(si[COL_MONTO].sum(), 2)
        fila[f"Ticket_{ind}"] = round(si[COL_MONTO].mean(), 2) if len(si) > 0 else 0
    n_tot = len(sub)
    n_f   = len(sub[sub[COL_IND] == "F"]) if COL_IND in sub.columns else 0
    fila["Tasa_F%"] = round(n_f / n_tot * 100, 4) if n_tot > 0 else 0
    filas_res.append(fila)

df_resumen = pd.DataFrame(filas_res)


# ─────────────────────────────────────────────────────────────────────────────
# 2–4. PIVOTS POR DIMENSIÓN
# ─────────────────────────────────────────────────────────────────────────────
def pivot_dim(col_dim, label="SEG_NOMBRE"):
    if col_dim not in df.columns or COL_IND not in df.columns:
        return pd.DataFrame()
    col_use = label if label in df.columns else col_dim
    t = df.groupby([col_use, COL_IND]).agg(
        N_trx=(COL_MONTO, "count"),
        Monto=(COL_MONTO, "sum"),
    ).reset_index()
    piv = t.pivot_table(index=col_use, columns=COL_IND, values="N_trx", fill_value=0)
    piv["TOTAL"] = piv.sum(axis=1)
    piv = piv.sort_values("TOTAL", ascending=False)
    return piv


print("[2] Pivot por producto...")
df_prod = pivot_dim(COL_TIPO, COL_TIPO)

print("[3] Pivot por segmento...")
df_seg = pivot_dim(COL_SEG, "SEG_NOMBRE")

print("[4] Pivot por ECI...")
df_eci = pivot_dim(COL_ECI, COL_ECI)


# ─────────────────────────────────────────────────────────────────────────────
# 5. MOTIVOS DE RECHAZO
# ─────────────────────────────────────────────────────────────────────────────
print("[5] Motivos de rechazo...")
df_den_local = df[df.get("ESTADO", pd.Series("", index=df.index)) == "DENEGADA"] if "ESTADO" in df.columns else df[df[COL_IND] != "F"]

if COL_MOTIVO in df_den_local.columns and len(df_den_local) > 0:
    df_motivos = (
        df_den_local.groupby(COL_MOTIVO)
        .agg(N_Rechazos=(COL_MOTIVO,"count"), Monto_Rech=(COL_MONTO,"sum"))
        .sort_values("N_Rechazos", ascending=False)
    )
    df_motivos["% del total"] = (df_motivos["N_Rechazos"] / len(df_den_local) * 100).round(2)
else:
    df_motivos = pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# 6. VELOCIDAD (GAP_MINUTOS × INDICADOR)
# ─────────────────────────────────────────────────────────────────────────────
print("[6] Velocidad...")
if "GAP_MINUTOS" in df.columns and COL_IND in df.columns:
    df["BUCKET_GAP"] = pd.cut(
        df["GAP_MINUTOS"].clip(0, 1440),
        bins=[-0.001, 1, 2, 5, 15, 60, 1440],
        labels=["≤1min","1-2min","2-5min","5-15min","15-60min",">60min"],
        include_lowest=True,
    )
    df_vel = (
        df.groupby(["BUCKET_GAP", COL_IND], observed=True)
        .agg(N_trx=(COL_MONTO,"count"))
        .reset_index()
        .pivot_table(index="BUCKET_GAP", columns=COL_IND, values="N_trx", fill_value=0, observed=True)
    )
    df_vel["TOTAL"] = df_vel.sum(axis=1)
else:
    df_vel = pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# 7. CVV / COD RED COMERCIO
# ─────────────────────────────────────────────────────────────────────────────
print("[7] CVV...")
if COL_CVV in df.columns and COL_IND in df.columns:
    df_cvv = (
        df.groupby([COL_CVV, COL_IND])
        .agg(N_trx=(COL_MONTO,"count"), Monto=(COL_MONTO,"sum"))
        .reset_index()
        .pivot_table(index=COL_CVV, columns=COL_IND, values="N_trx", fill_value=0)
    )
    df_cvv["TOTAL"] = df_cvv.sum(axis=1)
else:
    df_cvv = pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# 8. VARIABLES NUMÉRICAS — MEDIA Y MEDIANA POR INDICADOR
# ─────────────────────────────────────────────────────────────────────────────
print("[8] Variables numéricas...")
VARS_NUM = [
    COL_MONTO, "N_TRX_5MIN", "N_TRX_1H", "N_TRX_24H", "GAP_MINUTOS",
    "MONTO_ACUM_2H", "MONTO_ACUM_24H", "ZSCORE_MONTO_CLI",
    "RATIO_MONTO_AVG_CLI", "RATIO_MONTO_SALDO",
    "N_RECHAZOS_24H", "N_CVV_FAIL_24H", "SCORE_RIESGO",
    "DIAS_DESDE_PRIMERA_COMPRA",
]
VARS_NUM = [v for v in VARS_NUM if v in df.columns]

if COL_IND in df.columns and VARS_NUM:
    rows_v = []
    for var in VARS_NUM:
        fila = {"Variable": var}
        for ind in indicadores_presentes:
            s = df.loc[df[COL_IND] == ind, var].dropna()
            fila[f"{ind}_media"]   = round(s.mean(), 4)  if len(s) > 0 else None
            fila[f"{ind}_mediana"] = round(s.median(), 4) if len(s) > 0 else None
        rows_v.append(fila)
    df_vars = pd.DataFrame(rows_v).set_index("Variable")
else:
    df_vars = pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# 9. PERFIL DE RIESGO × INDICADOR
# ─────────────────────────────────────────────────────────────────────────────
print("[9] Perfil de riesgo...")
if COL_RIESGO in df.columns and COL_IND in df.columns:
    df_riesgo = (
        df.groupby([str(COL_RIESGO), COL_IND], observed=True)
        .size().reset_index(name="N_trx")
        .pivot_table(index=str(COL_RIESGO), columns=COL_IND, values="N_trx", fill_value=0, observed=True)
    )
    df_riesgo["TOTAL"] = df_riesgo.sum(axis=1)
    df_riesgo["% F"] = (df_riesgo.get("F", 0) / df_riesgo["TOTAL"] * 100).round(2)
else:
    df_riesgo = pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# 10. MUESTRA DE FRAUDES
# ─────────────────────────────────────────────────────────────────────────────
print("[10] Muestra de fraudes...")
cols_muestra = [c for c in [
    "id_cliente","fecha_hora","comercio_nom",COL_MONTO,"ESTADO",COL_IND,
    "N_TRX_5MIN","N_TRX_1H","N_TRX_24H","GAP_MINUTOS","ES_RAFAGA",
    "MONTO_ACUM_24H","ZSCORE_MONTO_CLI","ES_PRIMERA_VEZ_COMERCIO",
    "HUBO_FRAUDE_PREVIO_24H","N_RECHAZOS_24H","N_CVV_FAIL_24H",
    "HUBO_CVV_FAIL_PREVIO","SCORE_RIESGO","PERFIL_RIESGO",
] if c in df.columns]

if len(df_f) > 0:
    df_muestra = df_f[cols_muestra].sample(min(500, len(df_f)), random_state=42)
else:
    df_muestra = df[cols_muestra].sample(min(500, len(df)), random_state=42)


# ─────────────────────────────────────────────────────────────────────────────
# EXPORTAR EXCEL
# ─────────────────────────────────────────────────────────────────────────────
EXCEL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
hoy = datetime.today().strftime("%d/%m/%Y")
print(f"\nExportando a Excel: {EXCEL_OUTPUT}")

with pd.ExcelWriter(EXCEL_OUTPUT, engine="openpyxl") as writer:

    # ── Hoja 1: Resumen ────────────────────────────────────────────────────────
    s1 = "1_Resumen"
    df_resumen.to_excel(writer, sheet_name=s1, index=False, startrow=3)
    ws = writer.sheets[s1]; nc = len(df_resumen.columns)
    titulo(ws, 1, nc, f"ANÁLISIS ECOMMERCE — {COMERCIO_NOMBRE} | {hoy}")
    titulo(ws, 2, nc, "RESUMEN KPIs POR QUINCENA", fill=FS)
    encabezado(ws, 4)
    estilizar(ws, 5, ws.max_row, kw_fraude=["FRAUDE","_F"])
    autofit(ws)

    # ── Hoja 2: Por Producto ───────────────────────────────────────────────────
    if not df_prod.empty:
        s2 = "2_Por_Producto"
        df_prod.to_excel(writer, sheet_name=s2, startrow=3)
        ws = writer.sheets[s2]; nc = len(df_prod.columns) + 1
        titulo(ws, 1, nc, "DISTRIBUCIÓN POR TIPO PRODUCTO")
        titulo(ws, 2, nc, "Filas = tipo producto | Columnas = indicador fraude", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row); autofit(ws)

    # ── Hoja 3: Por Segmento ───────────────────────────────────────────────────
    if not df_seg.empty:
        s3 = "3_Por_Segmento"
        df_seg.to_excel(writer, sheet_name=s3, startrow=3)
        ws = writer.sheets[s3]; nc = len(df_seg.columns) + 1
        titulo(ws, 1, nc, "DISTRIBUCIÓN POR SEGMENTO CLIENTE")
        titulo(ws, 2, nc, "Segmento según VAA-EVENTO DE COMPROMISO OTRA FUENTE", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row); autofit(ws)

    # ── Hoja 4: Por ECI ────────────────────────────────────────────────────────
    if not df_eci.empty:
        s4 = "4_Por_ECI"
        df_eci.to_excel(writer, sheet_name=s4, startrow=3)
        ws = writer.sheets[s4]; nc = len(df_eci.columns) + 1
        titulo(ws, 1, nc, "DISTRIBUCIÓN POR SEGURIDAD ECI")
        titulo(ws, 2, nc, "Seguro (ECI 2/5) vs No Seguro | Columnas = indicador", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row); autofit(ws)

    # ── Hoja 5: Motivos de Rechazo ────────────────────────────────────────────
    if not df_motivos.empty:
        s5 = "5_Motivos_Rechazo"
        df_motivos.to_excel(writer, sheet_name=s5, startrow=3)
        ws = writer.sheets[s5]; nc = len(df_motivos.columns) + 1
        titulo(ws, 1, nc, "MOTIVOS DE RECHAZO — TRANSACCIONES DENEGADAS")
        titulo(ws, 2, nc, "Solo denegadas | CVV_FAIL = riesgo alto de fraude", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row); autofit(ws)

    # ── Hoja 6: Velocidad ─────────────────────────────────────────────────────
    if not df_vel.empty:
        s6 = "6_Velocidad"
        df_vel.to_excel(writer, sheet_name=s6, startrow=3)
        ws = writer.sheets[s6]; nc = len(df_vel.columns) + 1
        titulo(ws, 1, nc, "VELOCIDAD — DISTRIBUCIÓN DE GAP ENTRE TRANSACCIONES")
        titulo(ws, 2, nc, "Filas = intervalo entre trx | Columnas = indicador fraude", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row); autofit(ws)

    # ── Hoja 7: CVV ───────────────────────────────────────────────────────────
    if not df_cvv.empty:
        s7 = "7_CVV"
        df_cvv.to_excel(writer, sheet_name=s7, startrow=3)
        ws = writer.sheets[s7]; nc = len(df_cvv.columns) + 1
        titulo(ws, 1, nc, "CVV / ACF-COD RED COMERCIO POR INDICADOR")
        titulo(ws, 2, nc, "S=Estático TD | D=Dinámico TC/TD | E=Estático TC | N=Sin CVV", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row); autofit(ws)

    # ── Hoja 8: Variables ─────────────────────────────────────────────────────
    if not df_vars.empty:
        s8 = "8_Variables"
        df_vars.to_excel(writer, sheet_name=s8, startrow=3)
        ws = writer.sheets[s8]; nc = len(df_vars.columns) + 1
        titulo(ws, 1, nc, "VARIABLES NUMÉRICAS — MEDIA Y MEDIANA POR INDICADOR")
        titulo(ws, 2, nc, "F=Fraude B/G=Buena D=Descarte P=Pendiente N=Normal", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row, kw_fraude=["MONTO","SCORE","RIESGO"]); autofit(ws)

    # ── Hoja 9: Perfil de Riesgo ──────────────────────────────────────────────
    if not df_riesgo.empty:
        s9 = "9_Perfil_Riesgo"
        df_riesgo.to_excel(writer, sheet_name=s9, startrow=3)
        ws = writer.sheets[s9]; nc = len(df_riesgo.columns) + 1
        titulo(ws, 1, nc, "PERFIL DE RIESGO × INDICADOR DE FRAUDE")
        titulo(ws, 2, nc, "Score 0-6: BAJO ≤0 | MEDIO=1 | ALTO=2 | MUY_ALTO≥3", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row); autofit(ws)

    # ── Hoja 10: Muestra ──────────────────────────────────────────────────────
    s10 = "10_Muestra"
    df_muestra.to_excel(writer, sheet_name=s10, index=False, startrow=2)
    ws = writer.sheets[s10]; nc = len(df_muestra.columns)
    titulo(ws, 1, nc, f"MUESTRA DE FRAUDES (500 filas aleatorias) — {COMERCIO_NOMBRE}")
    encabezado(ws, 3); autofit(ws)


print(f"\n✅ Excel generado: {EXCEL_OUTPUT}")
print("   Hojas: 1_Resumen | 2_Por_Producto | 3_Por_Segmento | 4_Por_ECI")
print("          5_Motivos_Rechazo | 6_Velocidad | 7_CVV | 8_Variables")
print("          9_Perfil_Riesgo | 10_Muestra")
