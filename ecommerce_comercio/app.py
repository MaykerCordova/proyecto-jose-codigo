"""
app.py — Dashboard Interactivo Ecommerce por Comercio
──────────────────────────────────────────────────────
Ejecutar: streamlit run ecommerce_comercio/app.py
          (o desde la raíz del proyecto)

Requiere haber ejecutado primero:
    python scripts/consolidar.py
    python scripts/feature_engineering.py
"""

import sys
import warnings
from pathlib import Path

import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

from config import (
    COLS, PARQUET_FEATURES, COMERCIO_NOMBRE, SOLO_APROBADAS, UMBRALES_REGLA,
)

C = COLS

st.set_page_config(
    page_title=f"Fraude Ecommerce — {COMERCIO_NOMBRE}",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

COLORS = {
    "F": "#E74C3C",  # rojo fraude
    "G": "#27AE60",  # verde buena
    "B": "#2ECC71",  # verde claro buena legacy
    "P": "#F39C12",  # naranja pendiente
    "D": "#95A5A6",  # gris descarte
    "N": "#3498DB",  # azul normal
}
PALETA = ["#E74C3C","#27AE60","#3498DB","#F39C12","#9B59B6","#95A5A6"]


# ─────────────────────────────────────────────────────────────────────────────
# CARGA DE DATOS
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Cargando datos...")
def cargar_datos(ruta):
    if not Path(ruta).exists():
        return None
    df = pd.read_parquet(ruta)
    df[C["monto"]]     = pd.to_numeric(df[C["monto"]], errors="coerce")
    df[C["fecha_hora"]]= pd.to_datetime(df[C["fecha_hora"]], errors="coerce")
    return df


df_raw = cargar_datos(str(PARQUET_FEATURES))

if df_raw is None:
    st.error("❌ No se encontró el parquet de features.")
    st.info("Ejecuta primero:\n```\npython scripts/consolidar.py\npython scripts/feature_engineering.py\n```")
    st.stop()

col_ind   = C["indicador"]
col_monto = C["monto"]
col_fh    = C["fecha_hora"]
col_cli   = C["id_cliente"]
col_com   = C["comercio_nom"]
col_bin   = C.get("bin", "")
col_pais  = C.get("pais", "")

IND_ORDEN  = ["F","G","B","P","D","N"]
ind_pres   = [i for i in IND_ORDEN if col_ind in df_raw.columns and i in df_raw[col_ind].unique()]
has_ind    = col_ind in df_raw.columns


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — FILTROS
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔍 Filtros")
    st.caption(f"Comercio: **{COMERCIO_NOMBRE}**")
    st.caption(f"Modo: {'Solo aprobadas' if SOLO_APROBADAS else 'Aprobadas + Denegadas'}")
    st.divider()

    # Rango de fechas
    fecha_min = df_raw[col_fh].min().date()
    fecha_max = df_raw[col_fh].max().date()
    f_ini, f_fin = st.date_input(
        "Rango de fechas",
        value=(fecha_min, fecha_max),
        min_value=fecha_min,
        max_value=fecha_max,
    )

    # Indicador
    ind_sel = st.multiselect("Indicador de fraude",
        options=ind_pres,
        default=ind_pres,
        help="F=Fraude G/B=Buena P=Pendiente D=Descarte N=Normal"
    )

    # Tipo producto
    opciones_tp = []
    if "TIPO_PRODUCTO_TEXTO" in df_raw.columns:
        opciones_tp = sorted(df_raw["TIPO_PRODUCTO_TEXTO"].dropna().unique())
    tp_sel = st.multiselect("Tipo de producto", opciones_tp, default=opciones_tp)

    # Marca
    opciones_marca = []
    if "MARCA_TARJETA" in df_raw.columns:
        opciones_marca = sorted(df_raw["MARCA_TARJETA"].dropna().unique())
    marca_sel = st.multiselect("Marca tarjeta", opciones_marca, default=opciones_marca)

    # Segmento
    opciones_seg = []
    if "SEG_NOMBRE" in df_raw.columns:
        opciones_seg = sorted(df_raw["SEG_NOMBRE"].dropna().unique())
    seg_sel = st.multiselect("Segmento cliente", opciones_seg, default=opciones_seg)

    # ECI/3DS
    opciones_eci = []
    if "SEGURO" in df_raw.columns:
        opciones_eci = sorted(df_raw["SEGURO"].dropna().unique())
    eci_sel = st.multiselect("Seguridad 3DS", opciones_eci, default=opciones_eci)

    st.divider()
    st.caption(f"Total registros raw: {len(df_raw):,}")


# ─────────────────────────────────────────────────────────────────────────────
# APLICAR FILTROS
# ─────────────────────────────────────────────────────────────────────────────
df = df_raw.copy()
df = df[
    (df[col_fh].dt.date >= f_ini) &
    (df[col_fh].dt.date <= f_fin)
]
if has_ind and ind_sel:
    df = df[df[col_ind].isin(ind_sel)]
if tp_sel and "TIPO_PRODUCTO_TEXTO" in df.columns:
    df = df[df["TIPO_PRODUCTO_TEXTO"].isin(tp_sel)]
if marca_sel and "MARCA_TARJETA" in df.columns:
    df = df[df["MARCA_TARJETA"].isin(marca_sel)]
if seg_sel and "SEG_NOMBRE" in df.columns:
    df = df[df["SEG_NOMBRE"].isin(seg_sel)]
if eci_sel and "SEGURO" in df.columns:
    df = df[df["SEGURO"].isin(eci_sel)]

mask_f_df   = (df[col_ind] == "F")          if has_ind else pd.Series(False, index=df.index)
mask_bg_df  = df[col_ind].isin({"G","B"})  if has_ind else pd.Series(False, index=df.index)
mask_n_df   = (df[col_ind] == "N")          if has_ind else pd.Series(False, index=df.index)
mask_nof_df = (df[col_ind] != "F")          if has_ind else pd.Series(True,  index=df.index)
n_f     = int(mask_f_df.sum())
n_bg    = int(mask_bg_df.sum())
n_norm  = int(mask_n_df.sum())
n_nof   = int(mask_nof_df.sum())   # todo lo que no es fraude
n_tot   = len(df)
tasa_f  = round(n_f / n_tot * 100, 3) if n_tot > 0 else 0


# ─────────────────────────────────────────────────────────────────────────────
# PESTAÑAS
# ─────────────────────────────────────────────────────────────────────────────
tabs = st.tabs([
    "📊 Resumen",
    "⚡ Velocidad",
    "💰 Monto",
    "🃏 Card Testing",
    "🎯 Simulador de Reglas",
    "🔎 Muestra",
])


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — RESUMEN
# ══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.header(f"Resumen — {COMERCIO_NOMBRE}")
    st.caption(f"Periodo: {f_ini} → {f_fin}  |  Registros filtrados: {n_tot:,}")

    # KPIs
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total txn",       f"{n_tot:,}")
    c2.metric("Fraudes (F)",     f"{n_f:,}",    delta=f"{tasa_f}% tasa")
    c3.metric("Buenas (G/B)",    f"{n_bg:,}")
    c4.metric("Monto total S/",  f"{df[col_monto].sum():,.0f}")
    c5.metric("Ticket promedio", f"S/ {df[col_monto].mean():.2f}")

    st.divider()

    col_l, col_r = st.columns(2)

    # Distribución por indicador
    with col_l:
        st.subheader("Distribución por indicador")
        if has_ind:
            cnt = df[col_ind].value_counts().reindex(ind_pres, fill_value=0).reset_index()
            cnt.columns = ["Indicador","N"]
            cnt["Color"] = cnt["Indicador"].map(COLORS)
            fig = px.bar(cnt, x="Indicador", y="N", color="Indicador",
                         color_discrete_map=COLORS, text="N")
            fig.update_traces(textposition="outside")
            fig.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig, use_container_width=True)
            st.caption("F=Fraude G/B=Buena P=Pendiente D=Descarte N=Normal")

    # Evolución temporal (fraudes por día)
    with col_r:
        st.subheader("Fraudes por día")
        if has_ind and "FECHA_DIA" in df.columns:
            diario = (
                df[mask_f_df]
                  .groupby("FECHA_DIA")
                  .agg(N_fraudes=(col_monto,"count"), Monto_F=(col_monto,"sum"))
                  .reset_index()
            )
            fig2 = px.line(diario, x="FECHA_DIA", y="N_fraudes",
                           hover_data=["Monto_F"],
                           labels={"FECHA_DIA":"Fecha","N_fraudes":"N Fraudes"})
            fig2.update_traces(line_color="#E74C3C")
            fig2.update_layout(height=350)
            st.plotly_chart(fig2, use_container_width=True)

    # Pivots por dimensión
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        st.subheader("Por producto")
        if "TIPO_PRODUCTO_TEXTO" in df.columns and has_ind:
            p = (df.groupby(["TIPO_PRODUCTO_TEXTO",col_ind], observed=True)
                   .size().unstack(fill_value=0))
            p.columns.name = None
            p["TOTAL"] = p.sum(axis=1)
            if "F" in p.columns:
                p["TASA_F%"] = (p["F"]/p["TOTAL"]*100).round(2)
            st.dataframe(p.reset_index(), use_container_width=True)

    with col_b:
        st.subheader("Por marca")
        if "MARCA_TARJETA" in df.columns and has_ind:
            p = (df.groupby(["MARCA_TARJETA",col_ind], observed=True)
                   .size().unstack(fill_value=0))
            p.columns.name = None
            p["TOTAL"] = p.sum(axis=1)
            if "F" in p.columns:
                p["TASA_F%"] = (p["F"]/p["TOTAL"]*100).round(2)
            st.dataframe(p.reset_index(), use_container_width=True)

    with col_c:
        st.subheader("Por 3DS (ECI)")
        if "SEGURO" in df.columns and has_ind:
            p = (df.groupby(["SEGURO",col_ind], observed=True)
                   .size().unstack(fill_value=0))
            p.columns.name = None
            p["TOTAL"] = p.sum(axis=1)
            if "F" in p.columns:
                p["TASA_F%"] = (p["F"]/p["TOTAL"]*100).round(2)
            st.dataframe(p.reset_index(), use_container_width=True)

    # Por segmento (barras apiladas)
    st.subheader("Por segmento de cliente")
    if "SEG_NOMBRE" in df.columns and has_ind:
        seg_df = (df.groupby(["SEG_NOMBRE",col_ind], observed=True)
                    .size().reset_index(name="N"))
        seg_df = seg_df[seg_df[col_ind].isin(ind_pres)]
        fig3 = px.bar(seg_df, x="SEG_NOMBRE", y="N", color=col_ind,
                      color_discrete_map=COLORS, barmode="stack",
                      labels={"SEG_NOMBRE":"Segmento","N":"N transacciones"})
        fig3.update_layout(height=350)
        st.plotly_chart(fig3, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — VELOCIDAD
# ══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.header("Velocidad — Ventanas temporales por cliente")

    VARS_V = [c for c in [
        "TRX_CLIENTE_2MIN","TRX_CLIENTE_5MIN","TRX_CLIENTE_10MIN",
        "TRX_CLIENTE_1H","TRX_CLIENTE_24H","GAP_MINUTOS",
    ] if c in df.columns]

    if not VARS_V:
        st.warning("Variables de velocidad no encontradas. Ejecuta feature_engineering.py.")
    else:
        # Box plots por indicador
        st.subheader("Distribución por ventana temporal × indicador")
        var_sel = st.selectbox("Variable a visualizar", VARS_V,
                               index=VARS_V.index("TRX_CLIENTE_5MIN") if "TRX_CLIENTE_5MIN" in VARS_V else 0)

        if has_ind:
            fig_box = px.box(
                df[df[var_sel].notna()],
                x=col_ind, y=var_sel, color=col_ind,
                color_discrete_map=COLORS,
                category_orders={col_ind: ind_pres},
                points=False,
                labels={col_ind: "Indicador", var_sel: var_sel},
            )
            fig_box.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig_box, use_container_width=True)

        # Tabla estadística
        st.subheader("Media / Mediana / P90 por indicador")
        rows = []
        for var in VARS_V:
            if var not in df.columns: continue
            r = {"Variable": var}
            for ind in (ind_pres if has_ind else []):
                s = df.loc[df[col_ind]==ind, var].dropna()
                r[f"{ind}_media"]   = round(s.mean(),  2) if len(s)>0 else None
                r[f"{ind}_mediana"] = round(s.median(),2) if len(s)>0 else None
                r[f"{ind}_P90"]     = round(s.quantile(.90),2) if len(s)>0 else None
            rows.append(r)
        if rows:
            st.dataframe(pd.DataFrame(rows).set_index("Variable"), use_container_width=True)

        # Distribución GAP
        if "GAP_MINUTOS" in df.columns:
            st.subheader("Distribución del GAP entre transacciones")
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                buckets = pd.cut(
                    df["GAP_MINUTOS"].clip(0,1440),
                    bins=[-0.001,1,2,5,15,60,1440],
                    labels=["≤1min","1-2min","2-5min","5-15min","15-60min",">60min"],
                    include_lowest=True,
                )
                if has_ind:
                    gap_df = (pd.DataFrame({"Bucket":buckets, col_ind:df[col_ind]})
                               .groupby(["Bucket",col_ind], observed=True).size()
                               .reset_index(name="N"))
                    fig_gap = px.bar(gap_df, x="Bucket", y="N", color=col_ind,
                                     color_discrete_map=COLORS, barmode="group")
                    fig_gap.update_layout(height=350)
                    st.plotly_chart(fig_gap, use_container_width=True)
            with col_g2:
                st.info(
                    "**Interpretar:** Si fraudes (F) se concentran en ≤1min o 1-2min, "
                    "hay patrón de ráfaga. Buenas (G/B) suelen estar en >60min. "
                    "Una diferencia clara confirma que FLAG_RAFAGA_5MIN es un buen "
                    "predictor para este comercio."
                )


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 3 — MONTO
# ══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.header("Análisis de Monto")

    col_m1, col_m2 = st.columns(2)

    # Histograma de montos por indicador
    with col_m1:
        st.subheader("Distribución del monto por indicador")
        max_monto = float(df[col_monto].quantile(0.99))
        df_hist = df[df[col_monto] <= max_monto]
        if has_ind:
            fig_hist = px.histogram(
                df_hist, x=col_monto, color=col_ind,
                color_discrete_map=COLORS, barmode="overlay",
                opacity=0.6, nbins=50,
                labels={col_monto: "Monto S/"},
            )
            fig_hist.update_layout(height=380)
            st.plotly_chart(fig_hist, use_container_width=True)
            st.caption("Truncado en P99 para visualización. Ver hoja 11 del Excel para percentiles completos.")

    # Deciles
    with col_m2:
        st.subheader("TASA_F% por decil de monto")
        if "DECIL_MONTO" in df.columns and has_ind:
            decil_df = df.groupby("DECIL_MONTO", observed=True).agg(
                N=(col_monto,"count"),
                N_F=("ES_FRAUDE","sum") if "ES_FRAUDE" in df.columns else (col_monto,"count"),
                Monto_med=(col_monto,"median"),
            ).reset_index()
            if "ES_FRAUDE" in df.columns:
                decil_df["TASA_F%"] = (decil_df["N_F"]/decil_df["N"]*100).round(2)
                fig_dec = px.bar(decil_df, x="DECIL_MONTO", y="TASA_F%",
                                 hover_data=["N","N_F","Monto_med"],
                                 labels={"DECIL_MONTO":"Decil"})
                fig_dec.update_traces(marker_color="#E74C3C")
                fig_dec.update_layout(height=380)
                st.plotly_chart(fig_dec, use_container_width=True)

    # Estadísticas descriptivas
    st.subheader("Estadísticas del monto por indicador")
    if has_ind:
        rows_s = []
        for ind in ind_pres:
            s = df.loc[df[col_ind]==ind, col_monto].dropna()
            if len(s) == 0: continue
            rows_s.append({
                "Indicador":ind, "N":len(s),
                "Media":round(s.mean(),2), "Mediana":round(s.median(),2),
                "P10":round(s.quantile(.10),2), "P90":round(s.quantile(.90),2),
                "P99":round(s.quantile(.99),2), "Max":round(s.max(),2),
                "Monto_Total":round(s.sum(),0),
            })
        if rows_s:
            st.dataframe(
                pd.DataFrame(rows_s).style.background_gradient(
                    subset=["Mediana","P90"], cmap="RdYlGn"
                ),
                use_container_width=True
            )

    # Análisis ZSCORE
    if "ZSCORE_MONTO_CLIENTE" in df.columns:
        st.subheader("Z-Score del monto vs historial del cliente")
        zs = df[["ZSCORE_MONTO_CLIENTE", col_ind]].dropna()
        zs_clip = zs[zs["ZSCORE_MONTO_CLIENTE"].between(-5, 10)]
        if has_ind:
            fig_z = px.box(zs_clip, x=col_ind, y="ZSCORE_MONTO_CLIENTE",
                           color=col_ind, color_discrete_map=COLORS,
                           points=False,
                           labels={col_ind:"Indicador","ZSCORE_MONTO_CLIENTE":"Z-Score"})
            fig_z.add_hline(y=2, line_dash="dash", line_color="orange",
                            annotation_text="Z=2 (2 desvíos sobre media)")
            fig_z.update_layout(height=350, showlegend=False)
            st.plotly_chart(fig_z, use_container_width=True)
            st.caption("Z-Score > 2 = monto anormalmente alto vs historial del cliente.")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 4 — CARD TESTING
# ══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.header("Card Testing — BIN Extendido")
    st.info(
        "Card testing: misma raíz BIN12 aparece en múltiples tarjetas distintas el mismo día. "
        "Los defraudadores generan números de tarjeta secuencialmente para verificar cuáles tienen saldo."
    )

    c1, c2, c3 = st.columns(3)
    if "FLAG_BIN12_REPETIDO_DIA" in df.columns:
        n_ct = int(df["FLAG_BIN12_REPETIDO_DIA"].sum())
        c1.metric("Txn con BIN12 repetido", f"{n_ct:,}")
        c2.metric("% del total", f"{n_ct/n_tot*100:.2f}%")
        if has_ind and "ES_FRAUDE" in df.columns:
            fraudes_ct = int((df["FLAG_BIN12_REPETIDO_DIA"] & mask_f_df).sum())
            c3.metric("Fraudes en BIN12 repetido", f"{fraudes_ct:,}")

    st.divider()

    if "TARJETAS_MISMO_BIN12_DIA" in df.columns and has_ind:
        st.subheader("Distribución de tarjetas por BIN12 por día")
        df_ct = df[df["TARJETAS_MISMO_BIN12_DIA"] > 1].copy()
        if len(df_ct) > 0:
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                ct_dist = (df_ct.groupby("TARJETAS_MISMO_BIN12_DIA", observed=True)
                              .size().reset_index(name="N"))
                fig_ct = px.bar(ct_dist, x="TARJETAS_MISMO_BIN12_DIA", y="N",
                                labels={"TARJETAS_MISMO_BIN12_DIA":"Tarjetas con mismo BIN12 ese día"})
                fig_ct.update_layout(height=300)
                st.plotly_chart(fig_ct, use_container_width=True)
            with col_t2:
                if "FECHA_DIA" in df_ct.columns and "BIN_12" in df_ct.columns:
                    top_dias = (df_ct.groupby("FECHA_DIA")
                                     .agg(BINs_activos=("BIN_12","nunique"),
                                          Tarjetas=("TARJETA" if "TARJETA" in df_ct.columns else col_bin, "nunique"))
                                     .sort_values("BINs_activos", ascending=False)
                                     .head(10).reset_index())
                    st.dataframe(top_dias, use_container_width=True)
                    st.caption("Top 10 días con más BINs de card testing activos")

    # Top BINs con más fraude
    if col_bin in df.columns and has_ind:
        st.subheader("Top 20 BINs por tasa de fraude")
        bin_tbl = (df.groupby(col_bin, observed=True)
                     .agg(N=(col_monto,"count"), N_F=("ES_FRAUDE","sum") if "ES_FRAUDE" in df.columns else (col_monto,"count"))
                     .reset_index())
        if "ES_FRAUDE" in df.columns:
            bin_tbl["TASA_F%"] = (bin_tbl["N_F"]/bin_tbl["N"]*100).round(2)
            bin_top = bin_tbl.sort_values("TASA_F%", ascending=False).head(20)
            fig_bin = px.bar(bin_top, x=col_bin, y="TASA_F%",
                             hover_data=["N","N_F"],
                             color="TASA_F%", color_continuous_scale="Reds")
            fig_bin.update_layout(height=350, xaxis_tickangle=-45)
            st.plotly_chart(fig_bin, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 5 — SIMULADOR DE REGLAS
# ══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.header("Simulador de Reglas")
    st.info(
        "Mueve los sliders para simular el impacto de cada umbral como regla de control. "
        "El objetivo es **maximizar fraude capturado** con el menor impacto posible en transacciones buenas."
    )

    if not has_ind:
        st.warning("Requiere columna indicador para calcular efectividad.")
    else:
        # Totales de referencia para calcular porcentajes
        n_f_total   = int(mask_f_df.sum())
        n_bg_total  = int(mask_bg_df.sum())
        n_n_total   = int(mask_n_df.sum())
        n_nof_total = int(mask_nof_df.sum())

        def calcular_efectividad(mask_regla):
            n_imp   = int(mask_regla.sum())
            n_f_c   = int((mask_regla & mask_f_df).sum())
            n_g_a   = int((mask_regla & mask_bg_df).sum())    # G/B revisadas
            n_n_a   = int((mask_regla & mask_n_df).sum())     # N normales (el grueso)
            n_nof_a = int((mask_regla & mask_nof_df).sum())   # total no-fraude
            pct_f   = round(n_f_c   / n_f_total   * 100, 2) if n_f_total   > 0 else 0
            pct_g   = round(n_g_a   / n_bg_total  * 100, 2) if n_bg_total  > 0 else 0
            pct_n   = round(n_n_a   / n_n_total   * 100, 2) if n_n_total   > 0 else 0
            pct_nof = round(n_nof_a / n_nof_total * 100, 2) if n_nof_total > 0 else 0
            prec    = round(n_f_c   / n_imp * 100, 2) if n_imp > 0 else 0
            ratio   = round(pct_f / pct_nof, 2) if pct_nof > 0 else (999.0 if pct_f > 0 else 0.0)
            return n_imp, n_f_c, n_g_a, n_n_a, pct_f, pct_g, pct_n, pct_nof, prec, ratio

        def mostrar_resultado(n_imp, n_f_c, n_g_a, n_n_a, pct_f, pct_g, pct_n, pct_nof, prec, ratio):
            ca, cb, cc, cd = st.columns(4)
            ca.metric("Txn bloqueadas", f"{n_imp:,}",
                      delta=f"{round(n_imp/n_tot*100,1)}% del total")
            cb.metric("Fraudes capturados", f"{n_f_c:,}",
                      delta=f"{pct_f}% de los fraudes")
            cc.metric("Normales (N) afectadas", f"{n_n_a:,}",
                      delta=f"{pct_n}% de las N", delta_color="inverse")
            cd.metric("Precisión / Ratio", f"{prec}% / {ratio}x")
            st.caption(
                f"Buenas (G) afectadas: **{n_g_a:,}** ({pct_g}%)  ·  "
                f"Total no-fraude afectado: **{n_imp - n_f_c:,}** ({pct_nof}% de todos los no-fraude)"
            )
            if ratio >= 3 and pct_f >= 10:
                st.success(f"✅ Regla efectiva: captura {pct_f}% del fraude afectando solo {pct_nof}% de clientes.")
            elif pct_n > 20:
                st.error(f"⚠️ Alto daño colateral: {pct_n}% de las transacciones normales (N) serían bloqueadas.")
            elif pct_f >= 30:
                st.warning(f"Captura alta ({pct_f}%) pero revisa el impacto en N ({pct_n}%).")
            else:
                st.info("Ajusta el umbral para mejorar la captura o reducir el impacto en N.")

        st.subheader("Regla 1: Monto acumulado en 24h (MNT_CLIENTE_24H)")
        if "MNT_CLIENTE_24H" in df.columns:
            max_mnt = min(float(df["MNT_CLIENTE_24H"].quantile(0.99)), 5000.0)
            umbral_mnt = st.slider("Bloquear si MNT_CLIENTE_24H ≥ S/",
                                   min_value=50.0, max_value=max_mnt,
                                   value=300.0, step=50.0, key="s1")
            r = calcular_efectividad(df["MNT_CLIENTE_24H"] >= umbral_mnt)
            mostrar_resultado(*r)
        else:
            st.warning("MNT_CLIENTE_24H no disponible")

        st.divider()
        st.subheader("Regla 2: Transacciones en 5 minutos (TRX_CLIENTE_5MIN)")
        if "TRX_CLIENTE_5MIN" in df.columns:
            umbral_trx = st.slider("Bloquear si TRX_CLIENTE_5MIN ≥",
                                   min_value=2, max_value=10, value=3, step=1, key="s2")
            r = calcular_efectividad(df["TRX_CLIENTE_5MIN"] >= umbral_trx)
            mostrar_resultado(*r)
        else:
            st.warning("TRX_CLIENTE_5MIN no disponible")

        st.divider()
        st.subheader("Regla 3: Combinada (MNT_24H ≥ X AND TRX_5MIN ≥ N)")
        if "MNT_CLIENTE_24H" in df.columns and "TRX_CLIENTE_5MIN" in df.columns:
            c3a, c3b = st.columns(2)
            max_mnt2 = min(float(df["MNT_CLIENTE_24H"].quantile(0.99)), 5000.0)
            u_mnt2 = c3a.slider("MNT_CLIENTE_24H ≥ S/", 50.0, max_mnt2, 300.0, 50.0, key="s3a")
            u_trx2 = c3b.slider("TRX_CLIENTE_5MIN ≥",   2, 10, 3, 1, key="s3b")
            mask_combo = (df["MNT_CLIENTE_24H"] >= u_mnt2) & (df["TRX_CLIENTE_5MIN"] >= u_trx2)
            r = calcular_efectividad(mask_combo)
            mostrar_resultado(*r)

        st.divider()
        st.subheader("Regla 4: Score de riesgo compuesto (SCORE_RIESGO ≥ N)")
        if "SCORE_RIESGO" in df.columns:
            max_score = int(df["SCORE_RIESGO"].max())
            umbral_score = st.slider("Bloquear si SCORE_RIESGO ≥",
                                     min_value=1, max_value=max_score, value=4, step=1, key="s4")
            r = calcular_efectividad(df["SCORE_RIESGO"] >= umbral_score)
            mostrar_resultado(*r)

        st.divider()
        # Curva de efectividad para TRX_5MIN
        st.subheader("Curva de efectividad — TRX_CLIENTE_5MIN")
        if "TRX_CLIENTE_5MIN" in df.columns:
            curva = []
            for u in range(2, 11):
                mask_u = df["TRX_CLIENTE_5MIN"] >= u
                n_imp_u, n_f_u, n_b_u, pf_u, pb_u, prec_u, rat_u = calcular_efectividad(mask_u)
                curva.append({"Umbral": u, "Fraude_%": pf_u, "Buenas_%": pb_u, "Precision_%": prec_u})
            df_curva = pd.DataFrame(curva)
            fig_curva = go.Figure()
            fig_curva.add_trace(go.Scatter(x=df_curva["Umbral"], y=df_curva["Fraude_%"],
                                           mode="lines+markers", name="Fraude capturado %",
                                           line=dict(color="#E74C3C")))
            fig_curva.add_trace(go.Scatter(x=df_curva["Umbral"], y=df_curva["Buenas_%"],
                                           mode="lines+markers", name="Buenas afectadas %",
                                           line=dict(color="#27AE60")))
            fig_curva.update_layout(
                xaxis_title="Umbral TRX_CLIENTE_5MIN ≥",
                yaxis_title="% transacciones",
                height=350,
                legend=dict(x=0.7, y=0.9),
            )
            st.plotly_chart(fig_curva, use_container_width=True)
            st.caption("El punto óptimo es donde la línea roja es alta y la verde es baja.")

        # Tabla resumen de todos los flags
        st.divider()
        st.subheader("Efectividad de todos los flags disponibles")
        FLAGS_APP = [c for c in df.columns
                     if (c.startswith("FLAG_") or c.startswith("HUBO_") or c in {"ES_MADRUGADA","ES_CODIGO_CRITICO"})
                     and df[c].dropna().isin({0,1}).all()]
        if FLAGS_APP:
            rows_fl = []
            for flag in FLAGS_APP:
                mask_fl = df[flag].fillna(0).astype(bool)
                if mask_fl.sum() == 0: continue
                n_i, n_fc, n_ba, pf, pb, pr, rt = calcular_efectividad(mask_fl)
                rows_fl.append({"Flag": flag, "N_impacta": n_i,
                                 "Fraude_%": pf, "Buenas_%": pb,
                                 "Precision_%": pr, "Ratio": rt})
            if rows_fl:
                df_fl = pd.DataFrame(rows_fl).sort_values("Fraude_%", ascending=False)
                st.dataframe(
                    df_fl.style.background_gradient(subset=["Fraude_%","Ratio"], cmap="RdYlGn"),
                    use_container_width=True,
                )


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 6 — MUESTRA
# ══════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.header("Muestra de transacciones")

    col_filter1, col_filter2, col_filter3 = st.columns(3)
    solo_fraudes = col_filter1.checkbox("Solo fraudes (F)", value=True)
    n_muestra    = col_filter2.slider("Nº de filas", 50, 500, 200, 50)
    score_min    = 0
    if "SCORE_RIESGO" in df.columns:
        score_min = col_filter3.slider("SCORE_RIESGO mínimo", 0, 9, 0)

    df_m = df[mask_f_df] if solo_fraudes and has_ind else df
    if "SCORE_RIESGO" in df_m.columns:
        df_m = df_m[df_m["SCORE_RIESGO"] >= score_min]

    COLS_SHOW = [c for c in [
        col_cli, col_fh, col_com, col_monto, col_ind,
        "TIPO_PRODUCTO_TEXTO","MARCA_TARJETA","SEG_NOMBRE","SEGURO",
        "TRX_CLIENTE_5MIN","TRX_CLIENTE_1H","MNT_CLIENTE_24H","GAP_MINUTOS",
        "ZSCORE_MONTO_CLIENTE","FLAG_RAFAGA_5MIN",
        "HUBO_CVV_FAIL_PREVIO","HUBO_FRAUDE_PREVIO_24H",
        "FLAG_BIN12_REPETIDO_DIA","SCORE_RIESGO","PERFIL_RIESGO",
    ] if c in df_m.columns]

    df_show = df_m[COLS_SHOW].sample(min(n_muestra, len(df_m)), random_state=42).reset_index(drop=True)

    st.caption(f"Mostrando {len(df_show):,} de {len(df_m):,} registros filtrados")
    st.dataframe(df_show, use_container_width=True)

    csv = df_show.to_csv(index=False).encode("utf-8")
    st.download_button("Descargar CSV", csv, "muestra_fraude.csv", "text/csv")


# Footer
st.divider()
st.caption(
    f"Pipeline ecommerce_comercio — {COMERCIO_NOMBRE} | "
    f"Scotiabank Peru Prevención de Fraude | "
    f"Datos: {n_tot:,} txn | "
    f"Actualizar: ejecutar consolidar.py → feature_engineering.py → relanzar app"
)
