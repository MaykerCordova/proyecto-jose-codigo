"""
analisis.py
───────────
Lee data/consolidado_features.parquet y genera el Excel de análisis.

Hojas:
  1_Resumen          KPIs totales y por quincena (indicadores F/B/D/P/N)
  2_Por_Producto     Pivot: indicador × tipo producto
  3_Por_Segmento     Pivot: indicador × segmento cliente
  4_Por_ECI          Pivot: indicador × seguridad ECI
  5_Velocidad        Distribución GAP y ventanas TXN × indicador
  6_Monto_Acum       Ventanas de monto acumulado + interacciones (RATIO_AMT_TXN)
  7_Motivos_Rechazo  Solo denegadas: distribución de motivos (si SOLO_APROBADAS=False)
  8_CVV              Pivot: indicador × ACF-COD RED COMERCIO
  9_Variables        Medias/medianas de features numéricas por indicador
  10_Perfil_Riesgo   PERFIL_RIESGO × indicador
  11_Muestra         500 filas de fraudes con todas las features

Cada hoja incluye una fila de interpretación que explica qué significa
y qué patrones buscar.
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
    SEG_NOMBRE, COD_RED_LABEL, SOLO_APROBADAS,
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
print(f"ANÁLISIS EXCEL — {COMERCIO_NOMBRE}")
print(f"  Modo: {'SOLO APROBADAS' if SOLO_APROBADAS else 'APROBADAS + DENEGADAS'}")
print("═" * 65)
df = pd.read_parquet(ruta)

# Identificar columnas clave (claves internas, ya renombradas por FE)
COL_IND   = "indicador"
COL_MONTO = "monto"
COL_FH    = "fecha_hora"
COL_SEG   = "SEG_NOMBRE"
COL_TIPO  = "tipo_producto"
COL_ECI   = "SEGURO"
COL_CVV   = "COD_RED_LABEL"
COL_MOTIVO= "MOTIVO_RECH"
COL_RIESGO= "PERFIL_RIESGO"
COL_QUI   = "QUINCENA"
COL_ID    = "id_cliente"

INDICADORES = ["F","B","G","D","P","N"]
ind_presentes = [i for i in INDICADORES if COL_IND in df.columns and i in df[COL_IND].unique()]

df[COL_MONTO] = pd.to_numeric(df[COL_MONTO], errors="coerce")
df[COL_FH]    = pd.to_datetime(df[COL_FH],    errors="coerce")

print(f"  Filas: {len(df):,} | Columnas: {df.shape[1]}")
if COL_IND in df.columns:
    print(f"  Distribución indicador:\n{df[COL_IND].value_counts().to_string()}")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DE FORMATO EXCEL
# ─────────────────────────────────────────────────────────────────────────────
FH  = PatternFill("solid", fgColor="1F3864")   # azul oscuro — título principal
FS  = PatternFill("solid", fgColor="2E75B6")   # azul medio  — subtítulo / encabezado col
FA  = PatternFill("solid", fgColor="DEEAF1")   # azul claro  — filas pares
FY  = PatternFill("solid", fgColor="FFF2CC")   # amarillo    — interpretación
FF  = PatternFill("solid", fgColor="FCE4D6")   # naranja     — filas fraude destacadas
FG  = PatternFill("solid", fgColor="E2EFDA")   # verde claro — filas buenas destacadas
fH  = Font(color="FFFFFF", bold=True, size=10)
fN  = Font(size=10)
fI  = Font(italic=True, size=9, color="1F3864")
BT  = Border(left=Side(style="thin"), right=Side(style="thin"),
             top=Side(style="thin"), bottom=Side(style="thin"))
AC  = Alignment(horizontal="center", vertical="center", wrap_text=True)
AL  = Alignment(horizontal="left",   vertical="center", wrap_text=True)


def titulo(ws, fila, n_cols, texto, fill=None):
    fill = fill or FH
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=n_cols)
    c = ws.cell(row=fila, column=1, value=texto)
    c.fill = fill; c.font = fH; c.alignment = AC; c.border = BT


def encabezado(ws, fila):
    for r in ws.iter_rows(min_row=fila, max_row=fila):
        for c in r: c.fill = FS; c.font = fH; c.alignment = AC; c.border = BT


def estilizar(ws, fi, ff):
    for i, row in enumerate(ws.iter_rows(min_row=fi, max_row=ff), start=1):
        fl = FA if i % 2 == 0 else PatternFill()
        for c in row: c.fill = fl; c.font = fN; c.alignment = AC; c.border = BT


def interpretacion(ws, fila, n_cols, texto):
    """Fila amarilla con el texto de interpretación al pie de la tabla."""
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=n_cols)
    c = ws.cell(row=fila, column=1, value=f"  INTERPRETACION: {texto}")
    c.fill = FY; c.font = fI; c.alignment = AL; c.border = BT
    ws.row_dimensions[fila].height = 40


def autofit(ws):
    for col in ws.columns:
        ml = max((len(str(c.value)) for c in col if c.value is not None), default=10)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(ml + 4, 45)


def escribir_df(ws, df_t, fila_ini, resaltar_ind=None):
    """Escribe DataFrame desde fila_ini, devuelve la fila siguiente."""
    df_r = df_t.reset_index()
    n    = len(df_r.columns)
    # encabezado
    for j, col in enumerate(df_r.columns, start=1):
        c = ws.cell(row=fila_ini, column=j, value=str(col))
        c.fill = FS; c.font = fH; c.alignment = AC; c.border = BT
    fila_ini += 1
    # datos
    for i, row in df_r.iterrows():
        fl = FA if i % 2 == 0 else PatternFill()
        if resaltar_ind and len(row) > 0 and str(row.iloc[0]) == resaltar_ind:
            fl = FF
        for j, val in enumerate(row, start=1):
            v = round(val, 4) if isinstance(val, float) else val
            c = ws.cell(row=fila_ini, column=j, value=v)
            c.fill = fl; c.font = fN; c.alignment = AC; c.border = BT
        fila_ini += 1
    return fila_ini


def pivot_por_indicador(col_dim, label_col=None, top_n=20):
    col_use = label_col if label_col and label_col in df.columns else col_dim
    if not col_use or col_use not in df.columns or COL_IND not in df.columns:
        return pd.DataFrame()
    t = (df.groupby([col_use, COL_IND], observed=True)
         .agg(N_trx=(COL_MONTO,"count"), Monto=(COL_MONTO,"sum"))
         .reset_index())
    piv = t.pivot_table(index=col_use, columns=COL_IND, values="N_trx", fill_value=0, observed=True)
    piv["TOTAL"] = piv.sum(axis=1)
    if "F" in piv.columns:
        piv["TASA_F%"] = (piv["F"] / piv["TOTAL"] * 100).round(2)
    return piv.sort_values("TOTAL", ascending=False).head(top_n)


# ─────────────────────────────────────────────────────────────────────────────
# CONSTRUIR TABLAS
# ─────────────────────────────────────────────────────────────────────────────

# 1 — RESUMEN
print("[1] Resumen...")
quincenas = sorted(df[COL_QUI].unique()) if COL_QUI in df.columns else ["Total"]
filas_res = []
for q in quincenas:
    sub = df[df[COL_QUI] == q] if COL_QUI in df.columns else df
    fila = {"Quincena": q, "Total trx": len(sub),
            "Monto total (S/)": round(sub[COL_MONTO].sum(), 2),
            "Ticket prom (S/)": round(sub[COL_MONTO].mean(), 2)}
    for ind in ind_presentes:
        si = sub[sub[COL_IND] == ind]
        fila[f"N_{ind}"]     = len(si)
        fila[f"Monto_{ind}"] = round(si[COL_MONTO].sum(), 2)
        fila[f"Ticket_{ind}"]= round(si[COL_MONTO].mean(), 2) if len(si) > 0 else 0
    n_tot = len(sub); n_f = (sub[COL_IND] == "F").sum() if COL_IND in sub.columns else 0
    fila["Tasa_F%"] = round(n_f / n_tot * 100, 4) if n_tot > 0 else 0
    filas_res.append(fila)
df_resumen = pd.DataFrame(filas_res)

# 2 — Por Producto
print("[2] Por producto...")
df_prod = pivot_por_indicador(COL_TIPO, COL_TIPO)

# 3 — Por Segmento
print("[3] Por segmento...")
df_seg = pivot_por_indicador("segmento", COL_SEG)

# 4 — Por ECI
print("[4] Por ECI...")
df_eci = pivot_por_indicador(COL_ECI, COL_ECI)

# 5 — VELOCIDAD (GAP + ventanas TXN)
print("[5] Velocidad...")
VARS_VEL = [c for c in ["GAP_MINUTOS","TXN_CARD_2M","TXN_CARD_5M","TXN_CARD_10M",
                         "TXN_CARD_1H","TXN_CARD_24H"] if c in df.columns]
if VARS_VEL and COL_IND in df.columns:
    rows_vel = []
    for var in VARS_VEL:
        fila = {"Variable": var}
        for ind in ind_presentes:
            s = df.loc[df[COL_IND]==ind, var].dropna()
            fila[f"{ind}_media"]  = round(s.mean(), 3)  if len(s)>0 else None
            fila[f"{ind}_mediana"]= round(s.median(), 3) if len(s)>0 else None
            fila[f"{ind}_p90"]    = round(s.quantile(.90), 3) if len(s)>0 else None
        rows_vel.append(fila)
    df_vel = pd.DataFrame(rows_vel).set_index("Variable")
    # Tabla distribución GAP
    if "GAP_MINUTOS" in df.columns:
        df["BUCKET_GAP"] = pd.cut(
            df["GAP_MINUTOS"].clip(0,1440),
            bins=[-0.001,1,2,5,15,60,1440],
            labels=["≤1min","1-2min","2-5min","5-15min","15-60min",">60min"],
            include_lowest=True)
        df_gap = df.groupby(["BUCKET_GAP",COL_IND],observed=True).size().reset_index(name="N")
        df_gap = df_gap.pivot_table(index="BUCKET_GAP",columns=COL_IND,values="N",fill_value=0,observed=True)
        df_gap["TOTAL"] = df_gap.sum(axis=1)
    else:
        df_gap = pd.DataFrame()
else:
    df_vel = pd.DataFrame(); df_gap = pd.DataFrame()

# 6 — MONTO ACUMULADO + INTERACCIONES
print("[6] Monto acumulado e interacciones...")
VARS_AMT = [c for c in ["AMT_CARD_2M","AMT_CARD_5M","AMT_CARD_10M","AMT_CARD_1H","AMT_CARD_24H",
                         "RATIO_AMT_TXN_5M","RATIO_AMT_TXN_10M","RATIO_AMT_TXN_1H","RATIO_AMT_TXN_24H",
                         "ACELERACION_MONTO","CONCENT_MONTO_5M_1H",
                         "ZSCORE_MONTO_CLI","RATIO_MONTO_AVG","RATIO_MONTO_VS_SALDO"] if c in df.columns]
if VARS_AMT and COL_IND in df.columns:
    rows_amt = []
    for var in VARS_AMT:
        fila = {"Variable": var}
        for ind in ind_presentes:
            s = df.loc[df[COL_IND]==ind, var].dropna()
            fila[f"{ind}_media"]  = round(s.mean(), 4)   if len(s)>0 else None
            fila[f"{ind}_mediana"]= round(s.median(), 4) if len(s)>0 else None
            fila[f"{ind}_p90"]    = round(s.quantile(.90),4) if len(s)>0 else None
        rows_amt.append(fila)
    df_amt = pd.DataFrame(rows_amt).set_index("Variable")
else:
    df_amt = pd.DataFrame()

# 7 — MOTIVOS DE RECHAZO
print("[7] Motivos de rechazo...")
if not SOLO_APROBADAS and COL_MOTIVO in df.columns:
    df_den_local = df[df.get("ESTADO", pd.Series("",index=df.index)) == "DENEGADA"] if "ESTADO" in df.columns else pd.DataFrame()
    if len(df_den_local) > 0:
        df_motivos = (df_den_local.groupby(COL_MOTIVO)
                      .agg(N_Rechazos=(COL_MOTIVO,"count"), Monto_Rech=(COL_MONTO,"sum"))
                      .sort_values("N_Rechazos", ascending=False))
        df_motivos["% del total"] = (df_motivos["N_Rechazos"] / len(df_den_local) * 100).round(2)
    else:
        df_motivos = pd.DataFrame()
else:
    df_motivos = pd.DataFrame()

# 8 — CVV
print("[8] CVV...")
df_cvv = pivot_por_indicador(COL_CVV, COL_CVV)

# 9 — VARIABLES NUMÉRICAS GENERALES
print("[9] Variables numéricas...")
VARS_GEN = [c for c in [COL_MONTO,
            "N_RECHAZOS_24H","N_CVV_FAIL_24H","HUBO_FRAUDE_PREVIO_24H",
            "SCORE_RIESGO","DIAS_ACTIVA","RANKING_COM",
            "FLAG_MONTO_REDONDO","FLAG_MONTO_BAJO","ES_RAFAGA","FLAG_REINCIDENTE"] if c in df.columns]
if VARS_GEN and COL_IND in df.columns:
    rows_gv = []
    for var in VARS_GEN:
        fila = {"Variable": var}
        for ind in ind_presentes:
            s = df.loc[df[COL_IND]==ind, var].dropna()
            fila[f"{ind}_media"]  = round(s.mean(), 4)   if len(s)>0 else None
            fila[f"{ind}_mediana"]= round(s.median(), 4) if len(s)>0 else None
        rows_gv.append(fila)
    df_vars = pd.DataFrame(rows_gv).set_index("Variable")
else:
    df_vars = pd.DataFrame()

# 10 — PERFIL DE RIESGO
print("[10] Perfil riesgo...")
if COL_RIESGO in df.columns and COL_IND in df.columns:
    df_riesgo = (df.groupby([str(COL_RIESGO),COL_IND],observed=True)
                 .size().reset_index(name="N_trx")
                 .pivot_table(index=str(COL_RIESGO),columns=COL_IND,
                              values="N_trx",fill_value=0,observed=True))
    df_riesgo["TOTAL"] = df_riesgo.sum(axis=1)
    if "F" in df_riesgo.columns:
        df_riesgo["TASA_F%"] = (df_riesgo["F"] / df_riesgo["TOTAL"] * 100).round(2)
else:
    df_riesgo = pd.DataFrame()

# 11 — MUESTRA
print("[11] Muestra...")
df_f = df[df[COL_IND]=="F"] if COL_IND in df.columns else pd.DataFrame()
cols_m = [c for c in [COL_ID,"fecha_hora","comercio_nom",COL_MONTO,COL_IND,"ESTADO",
                       "N_TRX_5MIN","N_TRX_1H","N_TRX_24H","GAP_MINUTOS","ES_RAFAGA",
                       "AMT_CARD_1H","AMT_CARD_24H","RATIO_AMT_TXN_1H",
                       "ZSCORE_MONTO_CLI","ES_PRIMERA_VEZ_COMERCIO",
                       "HUBO_FRAUDE_PREVIO_24H","N_RECHAZOS_24H","N_CVV_FAIL_24H",
                       "SCORE_RIESGO","PERFIL_RIESGO"] if c in df.columns]
df_muestra = (df_f[cols_m].sample(min(500,len(df_f)),random_state=42)
              if len(df_f)>0 else df[cols_m].sample(min(500,len(df)),random_state=42))


# ─────────────────────────────────────────────────────────────────────────────
# EXPORTAR EXCEL
# ─────────────────────────────────────────────────────────────────────────────
EXCEL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
hoy  = datetime.today().strftime("%d/%m/%Y")
modo = "SOLO APROBADAS" if SOLO_APROBADAS else "APROBADAS + DENEGADAS"
print(f"\nExportando a: {EXCEL_OUTPUT}")

with pd.ExcelWriter(EXCEL_OUTPUT, engine="openpyxl") as writer:

    # ── Hoja 1: Resumen ────────────────────────────────────────────────────────
    sn = "1_Resumen"; nc = len(df_resumen.columns)
    df_resumen.to_excel(writer, sheet_name=sn, index=False, startrow=3)
    ws = writer.sheets[sn]
    titulo(ws, 1, nc, f"ANÁLISIS ECOMMERCE — {COMERCIO_NOMBRE}  |  {hoy}  |  {modo}")
    titulo(ws, 2, nc, "KPIs POR QUINCENA — N transacciones, montos y tasa de fraude por indicador", fill=FS)
    encabezado(ws, 4); estilizar(ws, 5, ws.max_row)
    interpretacion(ws, ws.max_row+1, nc,
        "Lee de izquierda a derecha por quincena. La columna Tasa_F% muestra el % de fraudes sobre el total. "
        "Si la tasa sube de quincena en quincena, hay deterioro. Compara N_F (fraudes) con N_B+N_G (buenas) "
        "para entender si el problema es de volumen o de tasa. Monto_F alto con N_F bajo = fraudes de ticket grande.")
    autofit(ws)

    # ── Hoja 2: Por Producto ───────────────────────────────────────────────────
    if not df_prod.empty:
        sn = "2_Por_Producto"; nc = len(df_prod.columns)+1
        df_prod.to_excel(writer, sheet_name=sn, startrow=3)
        ws = writer.sheets[sn]
        titulo(ws, 1, nc, "DISTRIBUCIÓN POR TIPO DE PRODUCTO")
        titulo(ws, 2, nc, "Filas = tipo producto | Columnas = indicador fraude | TASA_F% = fraude/total", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row)
        interpretacion(ws, ws.max_row+1, nc,
            "Compara la TASA_F% entre tipos de producto (TC vs TD). Si una categoría tiene tasa mayor, "
            "puede ser un vector preferido por el fraude. Si TC tiene más fraude que TD en valor absoluto "
            "pero menor tasa, puede ser solo por mayor volumen.")
        autofit(ws)

    # ── Hoja 3: Por Segmento ───────────────────────────────────────────────────
    if not df_seg.empty:
        sn = "3_Por_Segmento"; nc = len(df_seg.columns)+1
        df_seg.to_excel(writer, sheet_name=sn, startrow=3)
        ws = writer.sheets[sn]
        titulo(ws, 1, nc, "DISTRIBUCIÓN POR SEGMENTO DE CLIENTE")
        titulo(ws, 2, nc, "Segmento: VAA-EVENTO DE COMPROMISO OTRA FUENTE | TASA_F% por segmento", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row)
        interpretacion(ws, ws.max_row+1, nc,
            "Identifica qué segmento concentra más fraudes. Affluent/Premium con TASA_F alta puede indicar "
            "fraude de alto valor. Mass con muchos casos puede ser fraude masivo de bajo ticket. "
            "Compara TASA_F% del segmento vs la tasa global del resumen.")
        autofit(ws)

    # ── Hoja 4: Por ECI ────────────────────────────────────────────────────────
    if not df_eci.empty:
        sn = "4_Por_ECI"; nc = len(df_eci.columns)+1
        df_eci.to_excel(writer, sheet_name=sn, startrow=3)
        ws = writer.sheets[sn]
        titulo(ws, 1, nc, "DISTRIBUCIÓN POR SEGURIDAD ECI (3DS)")
        titulo(ws, 2, nc, "Seguro = ECI 2 o 5 (autenticado 3DS) | No Seguro = sin autenticación", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row)
        interpretacion(ws, ws.max_row+1, nc,
            "Si 'No Seguro' concentra la mayoría de los fraudes (indicador F), confirma que el comercio "
            "procesa transacciones sin 3DS y ese es el vector principal. Si 'Seguro' también tiene fraude, "
            "puede haber fraude posterior a la autenticación (tarjeta robada con OTP comprometida).")
        autofit(ws)

    # ── Hoja 5: Velocidad ─────────────────────────────────────────────────────
    sn = "5_Velocidad"
    ws = writer.book.create_sheet(sn); writer.sheets[sn] = ws
    fa = 1
    titulo(ws, fa, 12, "VELOCIDAD — GAP ENTRE TRANSACCIONES Y CONTEO POR VENTANA TEMPORAL"); fa += 1
    titulo(ws, fa, 12, "Media, mediana y percentil 90 por indicador | Compara F vs B para detectar diferencias", fill=FS); fa += 1

    if not df_gap.empty:
        titulo(ws, fa, len(df_gap.columns)+1, "DISTRIBUCIÓN DE GAP (intervalo entre transacciones)", fill=FS); fa += 1
        fa = escribir_df(ws, df_gap, fa)
        interpretacion(ws, fa, len(df_gap.columns)+1,
            "Filas = rango de tiempo entre la trx actual y la anterior del mismo cliente. "
            "Si fraudes (F) se concentran en '≤1min' o '1-2min', hay patrón de ráfaga. "
            "En buenas (B/G), el grueso suele estar en '>60min'. Diferencia clara = señal fuerte de regla."); fa += 2

    if not df_vel.empty:
        titulo(ws, fa, len(df_vel.columns)+1, "ESTADÍSTICAS TXN Y MONTO ACUMULADO POR VENTANA × INDICADOR", fill=FS); fa += 1
        fa = escribir_df(ws, df_vel, fa)
        interpretacion(ws, fa, len(df_vel.columns)+1,
            "Para cada variable (TXN_CARD_5M = transacciones previas del cliente en 5 min), compara la media F vs B. "
            "Si F tiene media muy superior, la variable es útil para una regla. P90 indica el umbral para capturar "
            "el 90% de los fraudes: un umbral ≥ ese valor bloquearía casi todos los fraudes de esa categoría."); fa += 2

    autofit(ws)

    # ── Hoja 6: Monto Acumulado + Interacciones ────────────────────────────────
    if not df_amt.empty:
        sn = "6_Monto_Acum"; nc = len(df_amt.columns)+1
        df_amt.to_excel(writer, sheet_name=sn, startrow=3)
        ws = writer.sheets[sn]
        titulo(ws, 1, nc, "MONTO ACUMULADO E INTERACCIONES VELOCIDAD × MONTO")
        titulo(ws, 2, nc,
               "AMT_CARD_Xm = monto acumulado previo en X min/h | RATIO_AMT_TXN_X = monto promedio por txn en esa ventana | "
               "ACELERACION_MONTO = ratio 5min / ratio 1h (>1 = escalada rápida)", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row)
        interpretacion(ws, ws.max_row+1, nc,
            "AMT_CARD_1H alto en F vs B indica que los fraudes acumulan más monto antes del fraude actual. "
            "RATIO_AMT_TXN_5M bajo en F puede indicar card testing (montos pequeños para probar la tarjeta). "
            "ACELERACION_MONTO > 1 significa que el cliente gasta más en el corto plazo que en el largo: señal de escalada. "
            "CONCENT_MONTO_5M_1H cerca de 1.0 = todo el gasto de la última hora fue en los últimos 5 minutos (ráfaga intensa).")
        autofit(ws)

    # ── Hoja 7: Motivos de Rechazo ────────────────────────────────────────────
    sn = "7_Motivos_Rechazo"
    if not df_motivos.empty:
        nc = len(df_motivos.columns)+1
        df_motivos.to_excel(writer, sheet_name=sn, startrow=3)
        ws = writer.sheets[sn]
        titulo(ws, 1, nc, "MOTIVOS DE RECHAZO — TRANSACCIONES DENEGADAS")
        titulo(ws, 2, nc, "Solo transacciones denegadas | Clasificación automática por ACF-RAZON RESPUESTA", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row)
        interpretacion(ws, ws.max_row+1, nc,
            "CVV_FAIL: el cliente intentó con CVV incorrecto antes del fraude — indica tarjeta robada sin CVV conocido. "
            "FONDOS_INSUF: intentos con fondos insuficientes antes del fraude — puede ser probando el saldo. "
            "AUTH_FAIL: falló 3DS antes del fraude — posible bypass de autenticación. "
            "Si muchos clientes con fraude aprobado tienen rechazos previos, agregar N_RECHAZOS_24H a regla de detección.")
    else:
        ws = writer.book.create_sheet(sn); writer.sheets[sn] = ws
        titulo(ws, 1, 2, "MOTIVOS DE RECHAZO — NO DISPONIBLE")
        ws.cell(row=2, column=1, value="Esta hoja requiere SOLO_APROBADAS = False en config.py" if SOLO_APROBADAS else "No hay transacciones denegadas en el dataset.")
    autofit(ws)

    # ── Hoja 8: CVV ───────────────────────────────────────────────────────────
    if not df_cvv.empty:
        sn = "8_CVV"; nc = len(df_cvv.columns)+1
        df_cvv.to_excel(writer, sheet_name=sn, startrow=3)
        ws = writer.sheets[sn]
        titulo(ws, 1, nc, "CVV DINÁMICO — ACF-COD RED COMERCIO × INDICADOR")
        titulo(ws, 2, nc, "S=Estático TD | D=Dinámico TC/TD | E=Estático TC | N=No Match/Sin CVV | TASA_F% por tipo", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row)
        interpretacion(ws, ws.max_row+1, nc,
            "N (No Match / Sin CVV) con TASA_F% alta es el principal indicador de riesgo: la tarjeta no tiene CVV dinámico "
            "o el CVV no coincidió con el registro. Si D (Dinámico) también tiene fraude, puede haber compromiso del token. "
            "Comparar la tasa de F entre S y D permite cuantificar el beneficio de activar CVV dinámico.")
        autofit(ws)

    # ── Hoja 9: Variables Generales ────────────────────────────────────────────
    if not df_vars.empty:
        sn = "9_Variables"; nc = len(df_vars.columns)+1
        df_vars.to_excel(writer, sheet_name=sn, startrow=3)
        ws = writer.sheets[sn]
        titulo(ws, 1, nc, "VARIABLES NUMÉRICAS — MEDIA Y MEDIANA POR INDICADOR")
        titulo(ws, 2, nc, "F=Fraude B/G=Buena D=Descarte P=Pendiente N=Normal | Media y mediana por indicador", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row)
        interpretacion(ws, ws.max_row+1, nc,
            "Compara la media de F vs B/G para cada variable. Una variable discrimina bien si la diferencia es grande "
            "en relación a la media de B. SCORE_RIESGO alto en F y bajo en B/G confirma que el score clasifica bien. "
            "FLAG_MONTO_REDONDO o FLAG_MONTO_BAJO con media cercana a 1 en F indica que casi todos los fraudes tienen ese patrón.")
        autofit(ws)

    # ── Hoja 10: Perfil de Riesgo ──────────────────────────────────────────────
    if not df_riesgo.empty:
        sn = "10_Perfil_Riesgo"; nc = len(df_riesgo.columns)+1
        df_riesgo.to_excel(writer, sheet_name=sn, startrow=3)
        ws = writer.sheets[sn]
        titulo(ws, 1, nc, "PERFIL DE RIESGO × INDICADOR DE FRAUDE")
        titulo(ws, 2, nc, "BAJO=0 flags | MEDIO=1 flag | ALTO=2-3 flags | MUY_ALTO=4+ flags | TASA_F% por perfil", fill=FS)
        encabezado(ws, 4); estilizar(ws, 5, ws.max_row)
        interpretacion(ws, ws.max_row+1, nc,
            "Un buen score de riesgo concentra los fraudes en MUY_ALTO y ALTO, con poca TASA_F% en BAJO y MEDIO. "
            "Si BAJO tiene una tasa de fraude similar a MUY_ALTO, el score no discrimina bien y hay que revisar los flags. "
            "El TOTAL de cada perfil muestra cuántas transacciones caerían en una regla de bloqueo por perfil.")
        autofit(ws)

    # ── Hoja 11: Muestra ──────────────────────────────────────────────────────
    sn = "11_Muestra"; nc = len(df_muestra.columns)
    df_muestra.to_excel(writer, sheet_name=sn, index=False, startrow=3)
    ws = writer.sheets[sn]
    titulo(ws, 1, nc, f"MUESTRA DE FRAUDES — 500 FILAS ALEATORIAS CON FEATURES — {COMERCIO_NOMBRE}")
    titulo(ws, 2, nc, "Útil para revisión manual y validación de features. Ordena por SCORE_RIESGO desc para ver los más riesgosos.", fill=FS)
    encabezado(ws, 4)
    interpretacion(ws, ws.max_row+1, nc,
        "Usa esta hoja para revisar casos individuales. Ordena la columna SCORE_RIESGO de mayor a menor para ver "
        "los fraudes con más señales de alerta. Revisa AMT_CARD_1H y N_TRX_5MIN de los casos F para calibrar umbrales. "
        "Si ves fraudes con SCORE=0, investiga: pueden ser fraudes sofisticados sin señales de velocidad.")
    autofit(ws)


print(f"\n✅ Excel generado: {EXCEL_OUTPUT}")
print("   Hojas: 1_Resumen | 2_Por_Producto | 3_Por_Segmento | 4_Por_ECI")
print("          5_Velocidad | 6_Monto_Acum | 7_Motivos_Rechazo | 8_CVV")
print("          9_Variables | 10_Perfil_Riesgo | 11_Muestra")
