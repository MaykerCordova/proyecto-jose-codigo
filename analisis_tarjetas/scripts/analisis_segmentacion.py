"""
analisis_segmentacion.py — Matriz de segmentación para reglas Monitor
Tarjetas Comprometidas N7 Débito — Scotiabank Peru

Cruza las señales top del modelo ML contra tres dimensiones:
  1. SEGMENTO  (Beyond / Premium / Preferente / Personal / Estándar / Empresas)
  2. BIN       (primeros 6 dígitos de la tarjeta)
  3. MCC GRUPO (categoría de comercio agrupada)

Para cada combinación calcula:
  - Tasa de fraude base (sin señal)
  - Tasa de fraude CON cada señal activa
  - Lift = tasa_con_señal / tasa_base
  - Precision = fraudes / (fraudes + legítimas) marcadas

Las combinaciones con Precision > UMBRAL_PRECISION se proponen
automáticamente como reglas Monitor candidatas.

Ejecutar DESPUÉS de feature_engineering.py:
    python scripts/analisis_segmentacion.py

Output:
    output/segmentacion_TARJETAS_COMPROMETIDAS_N7.xlsx
"""

import sys
import warnings
import pandas as pd
import numpy as np
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    COLS, PARQUET_FEATURES, ANALISIS_NOMBRE, BASE_DIR,
    SEG_NOMBRE, SEG_GRUPO
)

C        = COLS
col_ind  = C["indicador"]
col_mto  = C["monto"]
col_cli  = C["id_cliente"]
col_seg  = C["segmento"]
col_bin  = C["bin"]
col_mcc  = C["mcc"]

OUTPUT   = BASE_DIR / "output" / f"segmentacion_{ANALISIS_NOMBRE}.xlsx"

# ─── Umbral para proponer regla automáticamente ──────────────────────────────
UMBRAL_PRECISION  = 25.0   # % — si precision >= esto → candidata a regla
UMBRAL_MIN_FRAUDE = 5      # mínimo de fraudes para que la celda sea confiable

print("═" * 65)
print(f"ANÁLISIS DE SEGMENTACIÓN — {ANALISIS_NOMBRE}")
print("═" * 65)

# ─────────────────────────────────────────────────────────────────────────────
# CARGA
# ─────────────────────────────────────────────────────────────────────────────
ruta = PARQUET_FEATURES
if not ruta.exists():
    print(f"\n❌  No encontrado: {ruta}")
    print("    Ejecuta primero: python scripts/feature_engineering.py")
    sys.exit(1)

df = pd.read_parquet(ruta)
df[col_mto] = pd.to_numeric(df[col_mto], errors="coerce").fillna(0)
df["ES_FRAUDE"] = (df[col_ind] == "F").astype(int)

total_txn    = len(df)
total_fraude = int(df["ES_FRAUDE"].sum())
tasa_base    = total_fraude / total_txn * 100

print(f"\n  Transacciones : {total_txn:,}")
print(f"  Fraudes       : {total_fraude:,}  (tasa base = {tasa_base:.2f}%)")


# ─────────────────────────────────────────────────────────────────────────────
# DEFINIR SEÑALES TOP DEL MODELO
# ─────────────────────────────────────────────────────────────────────────────
senales = {}

if "FLAG_RAFAGA_5MIN" in df.columns:
    senales["Ráfaga_5min"]     = df["FLAG_RAFAGA_5MIN"] == 1
if "TRX_TARJETA_24H" in df.columns:
    senales["Velocidad_24h"]   = df["TRX_TARJETA_24H"] >= 5
if "ES_SEGURO" in df.columns:
    senales["Sin_3DS"]         = df["ES_SEGURO"] == 0
if "FLAG_ECOMMERCE" in df.columns:
    senales["Ecommerce"]       = df["FLAG_ECOMMERCE"] == 1
if "GAP_MINUTOS" in df.columns:
    senales["Gap_corto"]       = df["GAP_MINUTOS"] <= 10
if "TRX_TARJETA_24H" in df.columns and "FLAG_RAFAGA_5MIN" in df.columns:
    senales["Ráfaga+Vel"]      = (df["FLAG_RAFAGA_5MIN"] == 1) & (df["TRX_TARJETA_24H"] >= 5)

print(f"\n  Señales activas: {list(senales.keys())}")


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN CORE: cruzar dimensión × señal
# ─────────────────────────────────────────────────────────────────────────────
def matriz_cruzada(df, col_dimension, etiqueta_dim, senales, top_n=None):
    """
    Para cada valor único de col_dimension × cada señal:
    devuelve tasa base, tasa con señal, lift, precision.
    """
    rows = []

    conteos = df[col_dimension].value_counts()
    if top_n:
        valores = conteos.head(top_n).index.tolist()
    else:
        valores = conteos.index.tolist()

    for val in valores:
        mask_dim = df[col_dimension] == val
        sub      = df[mask_dim]
        n_tot    = len(sub)
        n_f      = int(sub["ES_FRAUDE"].sum())
        tasa_d   = n_f / n_tot * 100 if n_tot > 0 else 0
        monto_f  = sub.loc[sub["ES_FRAUDE"]==1, col_mto].sum()

        # Fila base (sin señal)
        base_row = {
            etiqueta_dim        : val,
            "Señal"             : "— BASE (sin señal) —",
            "Txn_Total"         : n_tot,
            "Fraudes"           : n_f,
            "Tasa_Fraude_%"     : round(tasa_d, 2),
            "Monto_Fraude_S/"   : round(monto_f, 2),
            "Txn_Con_Señal"     : "-",
            "Fraudes_Con_Señal" : "-",
            "Tasa_Con_Señal_%"  : "-",
            "Precision_%"       : "-",
            "Lift"              : "-",
            "Clientes_Fraude"   : sub.loc[sub["ES_FRAUDE"]==1, col_cli].nunique(),
            "Candidata_Regla"   : "",
        }
        rows.append(base_row)

        for nombre_senal, mascara_senal in senales.items():
            mask_comb   = mask_dim & mascara_senal
            n_comb      = int(mask_comb.sum())
            n_f_comb    = int((mask_comb & (df["ES_FRAUDE"]==1)).sum())
            n_l_comb    = int((mask_comb & (df["ES_FRAUDE"]==0)).sum())
            monto_fc    = df.loc[mask_comb & (df["ES_FRAUDE"]==1), col_mto].sum()

            if n_comb == 0:
                continue

            tasa_c  = n_f_comb / n_comb * 100
            prec    = tasa_c
            lift    = tasa_c / tasa_base if tasa_base > 0 else 0
            candidata = ""
            if prec >= UMBRAL_PRECISION and n_f_comb >= UMBRAL_MIN_FRAUDE:
                candidata = "✅ PROPUESTA"

            rows.append({
                etiqueta_dim        : val,
                "Señal"             : nombre_senal,
                "Txn_Total"         : n_tot,
                "Fraudes"           : n_f,
                "Tasa_Fraude_%"     : round(tasa_d, 2),
                "Monto_Fraude_S/"   : round(monto_fc, 2),
                "Txn_Con_Señal"     : n_comb,
                "Fraudes_Con_Señal" : n_f_comb,
                "Tasa_Con_Señal_%"  : round(tasa_c, 2),
                "Precision_%"       : round(prec, 2),
                "Lift"              : round(lift, 2),
                "Clientes_Fraude"   : df.loc[mask_comb & (df["ES_FRAUDE"]==1), col_cli].nunique(),
                "Candidata_Regla"   : candidata,
            })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# DIMENSIÓN 1 — SEGMENTO (decoded)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("DIMENSIÓN 1 — SEGMENTO")
print("─" * 65)

if col_seg in df.columns:
    df["SEG_COD"]    = df[col_seg].astype(str).str.strip()
    df["SEG_NOMBRE"] = df["SEG_COD"].map(SEG_NOMBRE).fillna("Desconocido")
    df["SEG_GRUPO"]  = df["SEG_COD"].map(SEG_GRUPO).fillna("Otros")

    # Resumen por segmento
    resumen_seg = (
        df.groupby(["SEG_NOMBRE", "SEG_GRUPO"])
        .agg(
            Txn_Total      = ("ES_FRAUDE", "count"),
            Fraudes        = ("ES_FRAUDE", "sum"),
            Monto_Fraude   = (col_mto, lambda x: x[df.loc[x.index, "ES_FRAUDE"]==1].sum()),
        )
        .reset_index()
    )
    resumen_seg["Tasa_Fraude_%"] = (resumen_seg["Fraudes"] / resumen_seg["Txn_Total"] * 100).round(2)
    resumen_seg = resumen_seg.sort_values("Tasa_Fraude_%", ascending=False)

    print("\n  Tasa de fraude por segmento:")
    for _, r in resumen_seg.iterrows():
        bar = "█" * int(r["Tasa_Fraude_%"] * 5)
        print(f"  {r['SEG_NOMBRE']:<20} {r['Tasa_Fraude_%']:>5.2f}%  {bar}  ({r['Fraudes']:,} fraudes)")

    # Matriz cruzada segmento × señal
    df_seg_matriz = matriz_cruzada(df, "SEG_NOMBRE", "Segmento", senales)
else:
    print("  ⚠️  Columna segmento no encontrada")
    df_seg_matriz = pd.DataFrame()
    resumen_seg   = pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# DIMENSIÓN 2 — BIN (top 30 por volumen de fraude)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("DIMENSIÓN 2 — BIN (top 30 por fraude)")
print("─" * 65)

if col_bin in df.columns:
    df["BIN_STR"] = df[col_bin].astype(str).str.strip().str[:6]

    # Top BINs por volumen de fraude
    bin_fraude = (
        df[df["ES_FRAUDE"]==1]
        .groupby("BIN_STR")["ES_FRAUDE"].count()
        .sort_values(ascending=False)
        .head(30)
    )

    # Resumen por BIN
    resumen_bin = (
        df.groupby("BIN_STR")
        .agg(
            Txn_Total = ("ES_FRAUDE", "count"),
            Fraudes   = ("ES_FRAUDE", "sum"),
        )
        .reset_index()
    )
    resumen_bin["Tasa_Fraude_%"] = (resumen_bin["Fraudes"] / resumen_bin["Txn_Total"] * 100).round(2)
    resumen_bin = resumen_bin[resumen_bin["BIN_STR"].isin(bin_fraude.index)]
    resumen_bin = resumen_bin.sort_values("Fraudes", ascending=False)

    print(f"\n  Top 10 BINs por volumen de fraude:")
    for _, r in resumen_bin.head(10).iterrows():
        bar = "█" * int(r["Tasa_Fraude_%"] * 5)
        print(f"  BIN {r['BIN_STR']}  {r['Tasa_Fraude_%']:>5.2f}%  {bar}  ({r['Fraudes']:,} fraudes / {r['Txn_Total']:,} txn)")

    # Matriz cruzada BIN × señal (solo top 30)
    df_temp_bin  = df[df["BIN_STR"].isin(bin_fraude.index)].copy()
    df_bin_matriz = matriz_cruzada(df_temp_bin, "BIN_STR", "BIN", senales, top_n=30)
else:
    print("  ⚠️  Columna BIN no encontrada")
    df_bin_matriz = pd.DataFrame()
    resumen_bin   = pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# DIMENSIÓN 3 — MCC GRUPO (categorías de comercio)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("DIMENSIÓN 3 — MCC GRUPO")
print("─" * 65)

MCC_GRUPO = {
    # Cash / ATM
    "6011": "Cash/ATM", "6012": "Cash/ATM", "6010": "Cash/ATM",
    # Supermercados / Retail alimentación
    "5411": "Supermercados", "5412": "Supermercados", "5499": "Supermercados",
    # Retail general
    "5999": "Retail_General", "5945": "Retail_General", "5940": "Retail_General",
    "5200": "Retail_General", "5251": "Retail_General", "5261": "Retail_General",
    "5300": "Retail_General", "5311": "Retail_General", "5331": "Retail_General",
    "5651": "Retail_General", "5661": "Retail_General", "5699": "Retail_General",
    "5712": "Retail_General", "5732": "Retail_General", "5734": "Retail_General",
    "5912": "Farmacias",
    # Wire / Transferencias
    "4829": "Wire_Transfer", "6051": "Wire_Transfer", "6540": "Wire_Transfer",
    # Taxis / Transporte
    "4121": "Taxi_Transporte", "4111": "Taxi_Transporte", "4112": "Taxi_Transporte",
    "4131": "Taxi_Transporte", "7523": "Taxi_Transporte",
    # Agencias de viaje / Aerolíneas
    "4722": "Viajes", "4511": "Viajes", "3000": "Viajes", "4112": "Viajes",
    # Restaurantes / Comida
    "5812": "Restaurantes", "5814": "Restaurantes", "5811": "Restaurantes",
    # Telecom / Digital
    "4814": "Telecom_Digital", "4816": "Telecom_Digital", "4899": "Telecom_Digital",
    "7372": "Telecom_Digital", "7374": "Telecom_Digital",
    # Gasolineras
    "5541": "Gasolineras", "5542": "Gasolineras",
    # Entretenimiento / Gambling
    "7995": "Gambling", "7993": "Gambling",
    "7832": "Entretenimiento", "7922": "Entretenimiento", "7941": "Entretenimiento",
    # Salud
    "8011": "Salud", "8021": "Salud", "8049": "Salud", "8099": "Salud",
    # Educación
    "8211": "Educacion", "8220": "Educacion", "8299": "Educacion",
    # Gobierno
    "9311": "Gobierno", "9399": "Gobierno", "9402": "Gobierno",
    # Ecommerce genérico (MCC 5965 = direct marketing, 5961 = catalog)
    "5965": "Ecommerce_Generico", "5961": "Ecommerce_Generico",
    "7994": "Ecommerce_Generico", "5815": "Ecommerce_Generico",
}

if col_mcc in df.columns:
    df["MCC_STR"]   = df[col_mcc].astype(str).str.strip()
    df["MCC_GRUPO"] = df["MCC_STR"].map(MCC_GRUPO).fillna("Otros")

    resumen_mcc = (
        df.groupby("MCC_GRUPO")
        .agg(
            Txn_Total = ("ES_FRAUDE", "count"),
            Fraudes   = ("ES_FRAUDE", "sum"),
            MCCs_distintos = ("MCC_STR", "nunique"),
        )
        .reset_index()
    )
    resumen_mcc["Tasa_Fraude_%"] = (resumen_mcc["Fraudes"] / resumen_mcc["Txn_Total"] * 100).round(2)
    resumen_mcc = resumen_mcc.sort_values("Tasa_Fraude_%", ascending=False)

    print("\n  Tasa de fraude por grupo MCC:")
    for _, r in resumen_mcc.iterrows():
        bar = "█" * int(r["Tasa_Fraude_%"] * 5)
        print(f"  {r['MCC_GRUPO']:<22} {r['Tasa_Fraude_%']:>5.2f}%  {bar}  ({r['Fraudes']:,} fraudes)")

    # Matriz cruzada MCC grupo × señal
    df_mcc_matriz = matriz_cruzada(df, "MCC_GRUPO", "MCC_Grupo", senales)
else:
    print("  ⚠️  Columna MCC no encontrada")
    df_mcc_matriz = pd.DataFrame()
    resumen_mcc   = pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# REGLAS CANDIDATAS — consolidado de las 3 dimensiones
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("REGLAS CANDIDATAS (Precision >= {:.0f}%, Fraudes >= {:,})".format(
    UMBRAL_PRECISION, UMBRAL_MIN_FRAUDE))
print("─" * 65)

reglas_candidatas = []

def extraer_candidatas(df_matriz, dim_col, dim_tipo):
    if df_matriz.empty:
        return
    cands = df_matriz[df_matriz.get("Candidata_Regla", "") == "✅ PROPUESTA"].copy()
    for _, r in cands.iterrows():
        val       = r[dim_col]
        senal     = r["Señal"]
        prec      = r["Precision_%"]
        n_f       = r["Fraudes_Con_Señal"]
        tasa_c    = r["Tasa_Con_Señal_%"]
        lift      = r["Lift"]
        reglas_candidatas.append({
            "Dimensión"             : dim_tipo,
            "Valor"                 : val,
            "Señal"                 : senal,
            "Fraudes_Capturados"    : n_f,
            "Precision_%"           : prec,
            "Tasa_Con_Señal_%"      : tasa_c,
            "Lift_vs_Base"          : lift,
            "Condición_Monitor"     : f"{dim_col}='{val}' AND {senal}=1",
            "Prioridad"             : (
                "🔴 ALTA"   if prec >= 50 else
                "🟡 MEDIA"  if prec >= 30 else
                "🟢 BAJA"
            ),
        })

extraer_candidatas(df_seg_matriz,  "Segmento",  "Segmento")
extraer_candidatas(df_bin_matriz,  "BIN",        "BIN")
extraer_candidatas(df_mcc_matriz,  "MCC_Grupo",  "MCC Grupo")

df_candidatas = pd.DataFrame(reglas_candidatas)
if not df_candidatas.empty:
    df_candidatas = df_candidatas.sort_values(
        ["Prioridad", "Precision_%"], ascending=[True, False]
    )
    print(f"\n  {len(df_candidatas)} reglas candidatas encontradas:\n")
    for _, r in df_candidatas.iterrows():
        print(f"  {r['Prioridad']}  {r['Dimensión']:<10} {str(r['Valor']):<22} × {r['Señal']:<18}"
              f"  Precision={r['Precision_%']:.1f}%  Fraudes={r['Fraudes_Capturados']}")
else:
    print("  (No se encontraron combinaciones con precisión suficiente — ajusta UMBRAL_PRECISION)")


# ─────────────────────────────────────────────────────────────────────────────
# EXPORTAR EXCEL
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n[Exportando Excel: {OUTPUT}...]")
OUTPUT.parent.mkdir(exist_ok=True)

try:
    with pd.ExcelWriter(OUTPUT, engine="openpyxl") as writer:

        # Hoja 1 — Resumen segmento
        if not resumen_seg.empty:
            resumen_seg.to_excel(writer, sheet_name="Segmento_Resumen", index=False)

        # Hoja 2 — Matriz segmento × señal
        if not df_seg_matriz.empty:
            df_seg_matriz.to_excel(writer, sheet_name="Segmento_x_Señal", index=False)

        # Hoja 3 — Top BINs resumen
        if not resumen_bin.empty:
            resumen_bin.to_excel(writer, sheet_name="BIN_Top30", index=False)

        # Hoja 4 — Matriz BIN × señal
        if not df_bin_matriz.empty:
            df_bin_matriz.to_excel(writer, sheet_name="BIN_x_Señal", index=False)

        # Hoja 5 — Resumen MCC grupo
        if not resumen_mcc.empty:
            resumen_mcc.to_excel(writer, sheet_name="MCC_Grupo_Resumen", index=False)

        # Hoja 6 — Matriz MCC grupo × señal
        if not df_mcc_matriz.empty:
            df_mcc_matriz.to_excel(writer, sheet_name="MCC_x_Señal", index=False)

        # Hoja 7 — Reglas candidatas consolidadas
        if not df_candidatas.empty:
            df_candidatas.to_excel(writer, sheet_name="Reglas_Candidatas", index=False)

    print(f"  ✅  Excel guardado: {OUTPUT}")

    # Resumen de hojas
    hojas = []
    if not resumen_seg.empty:   hojas.append("Segmento_Resumen")
    if not df_seg_matriz.empty: hojas.append("Segmento_x_Señal")
    if not resumen_bin.empty:   hojas.append("BIN_Top30")
    if not df_bin_matriz.empty: hojas.append("BIN_x_Señal")
    if not resumen_mcc.empty:   hojas.append("MCC_Grupo_Resumen")
    if not df_mcc_matriz.empty: hojas.append("MCC_x_Señal")
    if not df_candidatas.empty: hojas.append("Reglas_Candidatas")
    print(f"  Hojas generadas: {hojas}")

except Exception as e:
    print(f"  ⚠️  Error al exportar: {e}")

print("\n" + "═" * 65)
print("SEGMENTACIÓN COMPLETADA")
print("═" * 65)
