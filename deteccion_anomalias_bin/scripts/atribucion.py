"""
atribucion.py  (Pasos 4-5 y 7 del pipeline — Atribución, filtro de campañas y salida)
─────────────────────────────────────────────────────────────────────────────────────
Para cada ALERTA de deteccion.py responde tres preguntas:

1. ¿DÓNDE está concentrado el incremento?  (share of excess)
   Descompone el exceso sobre baseline por COMERCIO, MCC y BIN_10:
   exceso_categoria = max(0, trx_dia_categoria − promedio_diario_baseline_categoria)
   share = exceso_categoria / exceso_total

2. ¿Cambió la MEZCLA o solo el volumen?  (chi-cuadrado)
   Compara la distribución del día anómalo vs el baseline en:
   COMERCIO, MCC y FRANJA HORARIA.
   p < alfa → mezcla distinta (nuevo MCC, giro nocturno) → sospechoso.
   Mezcla igual + más volumen → probable legítimo.

3. ¿Tiene explicación COMERCIAL?  (calendario de eventos)
   Cruza la fecha contra CALENDARIO_EVENTOS / EVENTOS_RANGO / DIAS_PAGO.

Prioridad resultante:
   ALTA   sin evento + mezcla distinta   (o tasa de declinación disparada)
   MEDIA  sin evento + mezcla estable, o evento + mezcla distinta
   BAJA   evento + mezcla estable

Salida: output/alertas_<NOMBRE>.xlsx con hojas:
   0_Resumen | 1_Alertas | 2_Contribucion | 3_Series_Alertadas
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    ANALISIS_NOMBRE, DETECCION, ATRIBUCION, FRANJAS_HORARIAS,
    CALENDARIO_EVENTOS, EVENTOS_RANGO, DIAS_PAGO, FERIADOS_PERU,
    PARQUET_DETALLE, PARQUET_ALERTAS, EXCEL_OUTPUT,
)

VENTANA   = DETECCION["ventana_dias"]
ALFA      = ATRIBUCION["alfa_chi2"]
MIN_FREQ  = ATRIBUCION["min_freq_chi2"]
TOP_N     = ATRIBUCION["top_n"]
DECL_RATIO = ATRIBUCION["decl_ratio"]
DECL_DELTA = ATRIBUCION["decl_delta"]

print("═" * 65)
print("ATRIBUCIÓN — contribución + chi-cuadrado + calendario")
print("═" * 65)

for ruta in (PARQUET_DETALLE, PARQUET_ALERTAS):
    if not ruta.exists():
        print(f"❌  No existe {ruta} — ejecuta los pasos anteriores.")
        sys.exit(1)

detalle  = pd.read_parquet(PARQUET_DETALLE)
detalle["FECHA"] = pd.to_datetime(detalle["FECHA"]).dt.date
series   = pd.read_parquet(PARQUET_ALERTAS)
series["FECHA"] = pd.to_datetime(series["FECHA"]).dt.date
alertas  = series[series["ALERTA"]].copy()

print(f"  Alertas a caracterizar: {len(alertas):,}")
if alertas.empty:
    print("  ✅ Sin alertas — no se genera Excel de atribución.")
    sys.exit(0)


# ─────────────────────────────────────────────────────────────────────────────
# CALENDARIO DE EVENTOS
# ─────────────────────────────────────────────────────────────────────────────
def evento_de(fecha: date) -> str:
    eventos = []
    mmdd = fecha.strftime("%m-%d")
    if mmdd in CALENDARIO_EVENTOS:
        eventos.append(CALENDARIO_EVENTOS[mmdd])
    for ini, fin, nombre in EVENTOS_RANGO:
        if date.fromisoformat(ini) <= fecha <= date.fromisoformat(fin):
            eventos.append(nombre)
    if fecha.day in DIAS_PAGO:
        eventos.append("Dia de pago")
    if fecha.isoformat() in FERIADOS_PERU:
        eventos.append("Feriado")
    return " + ".join(eventos)


# ─────────────────────────────────────────────────────────────────────────────
# FILTRO DE TRANSACCIONES DE UNA ALERTA
# ─────────────────────────────────────────────────────────────────────────────
def filtro_llave(fila: pd.Series) -> pd.Series:
    """Máscara del detalle transaccional que corresponde a la llave de la alerta."""
    if fila["NIVEL"] == "BIN6":
        return detalle["BIN_6"] == fila["BIN_6"]
    m = detalle["BIN_10"] == fila["BIN_10"]
    if fila["NIVEL"] == "BIN10_COMERCIO":
        return m & (detalle["COMERCIO"] == fila["COMERCIO"])
    return m & (detalle["MCC"] == fila["MCC"])          # BIN10_MCC


def franja(hora: int) -> str:
    for nombre, horas in FRANJAS_HORARIAS.items():
        if hora in horas:
            return nombre
    return "SIN HORA"


# ─────────────────────────────────────────────────────────────────────────────
# 1. SHARE OF EXCESS — descomposición del exceso por dimensión
# ─────────────────────────────────────────────────────────────────────────────
def share_of_excess(dia: pd.DataFrame, base: pd.DataFrame,
                    dim: str, n_dias_base: int) -> pd.DataFrame:
    cnt_dia  = dia[dim].value_counts()
    cnt_base = base[dim].value_counts() / max(n_dias_base, 1)   # promedio diario
    tabla = pd.DataFrame({"TRX_DIA": cnt_dia}).join(
        pd.DataFrame({"BASE_DIARIO": cnt_base}), how="left"
    ).fillna(0.0)
    tabla["EXCESO"] = (tabla["TRX_DIA"] - tabla["BASE_DIARIO"]).clip(lower=0)
    total = tabla["EXCESO"].sum()
    tabla["SHARE"] = tabla["EXCESO"] / total if total > 0 else 0.0
    return tabla.sort_values("EXCESO", ascending=False)


def resumen_top(tabla: pd.DataFrame) -> str:
    filas = tabla[tabla["SHARE"] > 0].head(TOP_N)
    return ", ".join(f"{idx} ({s:.0%})" for idx, s in filas["SHARE"].items())


# ─────────────────────────────────────────────────────────────────────────────
# 2. CHI-CUADRADO DE MEZCLA — día anómalo vs baseline
# ─────────────────────────────────────────────────────────────────────────────
def chi2_mezcla(dia: pd.DataFrame, base: pd.DataFrame, dim: str) -> float:
    """p-valor del chi2; np.nan si no hay suficientes datos/categorías."""
    cnt_dia, cnt_base = dia[dim].value_counts(), base[dim].value_counts()
    cats = (cnt_dia.add(cnt_base, fill_value=0))
    cats = cats[cats >= MIN_FREQ].index
    if len(cats) < 2:
        return np.nan
    tabla = np.array([
        cnt_dia.reindex(cats, fill_value=0).values,
        cnt_base.reindex(cats, fill_value=0).values,
    ])
    if tabla.sum(axis=1).min() == 0:
        return np.nan
    return float(chi2_contingency(tabla).pvalue)


# ─────────────────────────────────────────────────────────────────────────────
# 3. CARACTERIZAR CADA ALERTA
# ─────────────────────────────────────────────────────────────────────────────
DIMS_CONTRIB = {          # dimensiones a descomponer según el nivel de la alerta
    "BIN6"          : ["COMERCIO", "MCC", "BIN_10"],
    "BIN10_COMERCIO": ["MCC"],
    "BIN10_MCC"     : ["COMERCIO"],
}
DIMS_CHI2 = {
    "BIN6"          : ["COMERCIO", "MCC", "FRANJA"],
    "BIN10_COMERCIO": ["MCC", "FRANJA"],
    "BIN10_MCC"     : ["COMERCIO", "FRANJA"],
}

detalle["FRANJA"] = detalle["HORA"].map(franja)

filas_alerta, filas_contrib = [], []

for _, a in alertas.iterrows():
    mask   = filtro_llave(a)
    f_ini  = a["FECHA"] - timedelta(days=VENTANA)
    dia    = detalle[mask & (detalle["FECHA"] == a["FECHA"])]
    base   = detalle[mask & (detalle["FECHA"] >= f_ini) & (detalle["FECHA"] < a["FECHA"])]
    n_dias_base = max((a["FECHA"] - f_ini).days, 1)

    # Contribución (share of excess) por cada dimensión relevante
    tops = {}
    for dim in DIMS_CONTRIB[a["NIVEL"]]:
        tabla = share_of_excess(dia, base, dim, n_dias_base)
        tops[dim] = resumen_top(tabla)
        det = tabla[tabla["SHARE"] > 0].head(10).reset_index(names="CATEGORIA")
        det.insert(0, "DIMENSION", dim)
        det.insert(0, "FECHA", a["FECHA"])
        det.insert(0, "CLAVE", a["CLAVE"])
        det.insert(0, "NIVEL", a["NIVEL"])
        filas_contrib.append(det)

    # Chi-cuadrado de mezcla
    pvals = {dim: chi2_mezcla(dia, base, dim) for dim in DIMS_CHI2[a["NIVEL"]]}
    p_min = np.nanmin(list(pvals.values())) if any(
        not np.isnan(v) for v in pvals.values()
    ) else np.nan
    mezcla_distinta = bool(p_min < ALFA) if not np.isnan(p_min) else False

    # Tasa de declinación del día vs baseline
    decl_dia  = 1 - dia["APROBADA"].mean() if len(dia) else 0.0
    decl_base = 1 - base["APROBADA"].mean() if len(base) else 0.0
    decl_alta = decl_dia > max(DECL_RATIO * decl_base, decl_base + DECL_DELTA)

    # Calendario
    evento = evento_de(a["FECHA"])

    # Prioridad
    if decl_alta or (not evento and mezcla_distinta):
        prioridad = "ALTA"
    elif (not evento and not mezcla_distinta) or (evento and mezcla_distinta):
        prioridad = "MEDIA"
    else:
        prioridad = "BAJA"

    filas_alerta.append({
        "PRIORIDAD"        : prioridad,
        "NIVEL"            : a["NIVEL"],
        "CLAVE"            : a["CLAVE"],
        "FECHA"            : a["FECHA"],
        "N_TRX"            : a["N_TRX"],
        "BASELINE_MEDIANA" : a["BASELINE_MEDIANA"],
        "VECES_SOBRE_BASE" : round(a["N_TRX"] / max(a["BASELINE_MEDIANA"], 1), 1),
        "Z_ROBUSTO"        : round(a["Z_ROBUSTO"], 1),
        "N_TARJETAS"       : a["N_TARJETAS"],
        "RATIO_TRX_TARJETA": round(a["RATIO_TRX_TARJETA"], 2),
        "DECL_DIA"         : round(decl_dia, 3),
        "DECL_BASELINE"    : round(decl_base, 3),
        "FLAG_DECL_ALTA"   : decl_alta,
        "MEZCLA_DISTINTA"  : mezcla_distinta,
        "P_MIN_CHI2"       : round(p_min, 4) if not np.isnan(p_min) else None,
        "TOP_COMERCIO"     : tops.get("COMERCIO", ""),
        "TOP_MCC"          : tops.get("MCC", ""),
        "TOP_BIN10"        : tops.get("BIN_10", ""),
        "EVENTO"           : evento,
        "TICKET_PROM"      : a["TICKET_PROM"],
        "PCT_NOCTURNAS"    : round(a["PCT_NOCTURNAS"], 3),
    })

orden_prio = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
df_alertas = (
    pd.DataFrame(filas_alerta)
    .sort_values(["PRIORIDAD", "Z_ROBUSTO"],
                 key=lambda s: s.map(orden_prio) if s.name == "PRIORIDAD" else s,
                 ascending=[True, False])
)
df_contrib = pd.concat(filas_contrib, ignore_index=True) if filas_contrib else pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# 4. SERIES COMPLETAS DE LAS LLAVES ALERTADAS (para graficar en Excel/Power BI)
# ─────────────────────────────────────────────────────────────────────────────
llaves_alertadas = alertas[["NIVEL", "CLAVE"]].drop_duplicates()
df_series = series.merge(llaves_alertadas, on=["NIVEL", "CLAVE"])[
    ["NIVEL", "CLAVE", "FECHA", "N_TRX", "BASELINE_MEDIANA", "Z_ROBUSTO",
     "N_TARJETAS", "RATIO_TRX_TARJETA", "TASA_DECLINACION", "ALERTA"]
].sort_values(["NIVEL", "CLAVE", "FECHA"])


# ─────────────────────────────────────────────────────────────────────────────
# 5. RESUMEN Y EXCEL
# ─────────────────────────────────────────────────────────────────────────────
resumen = pd.DataFrame({
    "Indicador": [
        "Periodo analizado",
        "Alertas totales", "Prioridad ALTA", "Prioridad MEDIA", "Prioridad BAJA",
        "Alertas con evento comercial", "Alertas con mezcla distinta (chi2)",
        "Alertas con declinación disparada",
        "Parámetros", "",
    ],
    "Valor": [
        f"{detalle['FECHA'].min()} → {detalle['FECHA'].max()}",
        len(df_alertas),
        (df_alertas["PRIORIDAD"] == "ALTA").sum(),
        (df_alertas["PRIORIDAD"] == "MEDIA").sum(),
        (df_alertas["PRIORIDAD"] == "BAJA").sum(),
        (df_alertas["EVENTO"] != "").sum(),
        df_alertas["MEZCLA_DISTINTA"].sum(),
        df_alertas["FLAG_DECL_ALTA"].sum(),
        f"ventana={VENTANA}d, z>{DETECCION['z_umbral']}, alfa_chi2={ALFA}",
        "Prioridad: ALTA=sin evento+mezcla distinta o declinación disparada | "
        "BAJA=evento+mezcla estable",
    ],
})

EXCEL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
with pd.ExcelWriter(EXCEL_OUTPUT, engine="openpyxl") as xl:
    resumen.to_excel(xl,    sheet_name="0_Resumen",          index=False)
    df_alertas.to_excel(xl, sheet_name="1_Alertas",          index=False)
    df_contrib.to_excel(xl, sheet_name="2_Contribucion",     index=False)
    df_series.to_excel(xl,  sheet_name="3_Series_Alertadas", index=False)

print(f"\n  Prioridad ALTA : {(df_alertas['PRIORIDAD'] == 'ALTA').sum():>4}")
print(f"  Prioridad MEDIA: {(df_alertas['PRIORIDAD'] == 'MEDIA').sum():>4}")
print(f"  Prioridad BAJA : {(df_alertas['PRIORIDAD'] == 'BAJA').sum():>4}")

top_alta = df_alertas[df_alertas["PRIORIDAD"] == "ALTA"].head(5)
for _, r in top_alta.iterrows():
    driver = r["TOP_COMERCIO"] or r["TOP_MCC"] or r["TOP_BIN10"]
    print(f"\n  🔴 {r['CLAVE']} | {r['FECHA']}: {r['N_TRX']:.0f} trx "
          f"({r['VECES_SOBRE_BASE']}x su baseline), driver: {driver}, "
          f"decline {r['DECL_DIA']:.0%} (normal {r['DECL_BASELINE']:.0%})"
          + (f", evento: {r['EVENTO']}" if r["EVENTO"] else ", sin campaña vigente"))

print(f"\n✅ Guardado: {EXCEL_OUTPUT}")
print("═" * 65)
