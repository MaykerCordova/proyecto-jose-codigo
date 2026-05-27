"""
app.py — Dashboard Interactivo Ecommerce por Comercio
──────────────────────────────────────────────────────
Ejecutar: streamlit run ecommerce_comercio/app.py

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
    "F": "#E74C3C",
    "G": "#27AE60",
    "B": "#2ECC71",
    "P": "#F39C12",
    "D": "#95A5A6",
    "N": "#3498DB",
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
    df[C["monto"]]      = pd.to_numeric(df[C["monto"]], errors="coerce")
    df[C["fecha_hora"]] = pd.to_datetime(df[C["fecha_hora"]], errors="coerce")
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
col_prod  = "TIPO_PRODUCTO_TEXTO"
col_marca = "MARCA_TARJETA"
col_seg   = "SEG_NOMBRE"
col_eci   = "SEGURO"

IND_ORDEN = ["F","G","B","P","D","N"]
has_ind   = col_ind in df_raw.columns
ind_pres  = [i for i in IND_ORDEN if has_ind and i in df_raw[col_ind].unique()]


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — FILTROS GLOBALES
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔍 Filtros Globales")
    st.caption(f"Comercio: **{COMERCIO_NOMBRE}**")
    st.caption(f"Modo: {'Solo aprobadas' if SOLO_APROBADAS else 'Aprobadas + Denegadas'}")
    st.divider()

    # Rango de fechas
    fecha_min = df_raw[col_fh].dropna().min().date()
    fecha_max = df_raw[col_fh].dropna().max().date()
    f_ini, f_fin = st.date_input(
        "Rango de fechas",
        value=(fecha_min, fecha_max),
        min_value=fecha_min,
        max_value=fecha_max,
    )

    # Indicador
    ind_sel = st.multiselect(
        "Indicador de fraude",
        options=ind_pres,
        default=ind_pres,
        help="F=Fraude  G=Buena  P=Pendiente  D=Descarte  N=Normal (el grueso)"
    )

    # Tipo producto
    opciones_tp = sorted(df_raw[col_prod].dropna().unique()) if col_prod in df_raw.columns else []
    tp_sel = st.multiselect("Tipo de producto", opciones_tp, default=opciones_tp)

    # Marca
    opciones_marca = sorted(df_raw[col_marca].dropna().unique()) if col_marca in df_raw.columns else []
    marca_sel = st.multiselect("Marca tarjeta", opciones_marca, default=opciones_marca)

    # Segmento
    opciones_seg = sorted(df_raw[col_seg].dropna().unique()) if col_seg in df_raw.columns else []
    seg_sel = st.multiselect("Segmento cliente", opciones_seg, default=opciones_seg)

    # ECI / 3DS
    opciones_eci = sorted(df_raw[col_eci].dropna().unique()) if col_eci in df_raw.columns else []
    eci_sel = st.multiselect("Seguridad 3DS", opciones_eci, default=opciones_eci)

    # BIN (top 40 por volumen)
    if col_bin in df_raw.columns:
        top_bins = (df_raw[col_bin].value_counts().head(40).index.astype(str).tolist())
        bin_opciones = sorted(df_raw[col_bin].dropna().astype(str).unique().tolist())
        bin_sel = st.multiselect(
            "BIN (dejar vacío = todos)",
            options=bin_opciones,
            default=[],
            help="Filtra por BIN de la tarjeta. Vacío = sin filtro."
        )
    else:
        bin_sel = []

    st.divider()
    st.caption(f"Total registros raw: {len(df_raw):,}")


# ─────────────────────────────────────────────────────────────────────────────
# APLICAR FILTROS
# ─────────────────────────────────────────────────────────────────────────────
df = df_raw.copy()
df = df[(df[col_fh].dt.date >= f_ini) & (df[col_fh].dt.date <= f_fin)]

if has_ind and ind_sel:
    df = df[df[col_ind].isin(ind_sel)]
if tp_sel and col_prod in df.columns:
    df = df[df[col_prod].isin(tp_sel)]
if marca_sel and col_marca in df.columns:
    df = df[df[col_marca].isin(marca_sel)]
if seg_sel and col_seg in df.columns:
    df = df[df[col_seg].isin(seg_sel)]
if eci_sel and col_eci in df.columns:
    df = df[df[col_eci].isin(eci_sel)]
if bin_sel and col_bin in df.columns:
    df = df[df[col_bin].astype(str).isin(bin_sel)]

# Máscaras globales (sobre df filtrado)
mask_f_df   = (df[col_ind] == "F")         if has_ind else pd.Series(False, index=df.index)
mask_bg_df  = df[col_ind].isin({"G","B"})  if has_ind else pd.Series(False, index=df.index)
mask_d_df   = (df[col_ind] == "D")         if has_ind else pd.Series(False, index=df.index)
mask_p_df   = (df[col_ind] == "P")         if has_ind else pd.Series(False, index=df.index)
mask_n_df   = (df[col_ind] == "N")         if has_ind else pd.Series(False, index=df.index)
mask_nof_df = (df[col_ind] != "F")         if has_ind else pd.Series(True,  index=df.index)

n_f    = int(mask_f_df.sum())
n_bg   = int(mask_bg_df.sum())
n_d    = int(mask_d_df.sum())
n_p    = int(mask_p_df.sum())
n_norm = int(mask_n_df.sum())
n_nof  = int(mask_nof_df.sum())
n_tot  = len(df)
tasa_f = round(n_f / n_tot * 100, 3) if n_tot > 0 else 0


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: calcular efectividad de una regla (máscara booleana)
# Devuelve: n_imp, n_f_c, n_g_a, n_n_a, n_d_a, n_p_a,
#           pct_f, pct_g, pct_n, pct_nof, precision, ratio
# ─────────────────────────────────────────────────────────────────────────────
def calcular_efectividad(mask_regla):
    n_imp   = int(mask_regla.sum())
    n_f_c   = int((mask_regla & mask_f_df).sum())
    n_g_a   = int((mask_regla & mask_bg_df).sum())
    n_n_a   = int((mask_regla & mask_n_df).sum())
    n_d_a   = int((mask_regla & mask_d_df).sum())
    n_p_a   = int((mask_regla & mask_p_df).sum())
    n_nof_a = int((mask_regla & mask_nof_df).sum())
    pct_f   = round(n_f_c   / n_f    * 100, 2) if n_f    > 0 else 0
    pct_g   = round(n_g_a   / n_bg   * 100, 2) if n_bg   > 0 else 0
    pct_n   = round(n_n_a   / n_norm * 100, 2) if n_norm > 0 else 0
    pct_nof = round(n_nof_a / n_nof  * 100, 2) if n_nof  > 0 else 0
    prec    = round(n_f_c   / n_imp  * 100, 2) if n_imp  > 0 else 0
    ratio   = round(pct_f / pct_nof, 2) if pct_nof > 0 else (999.0 if pct_f > 0 else 0.0)
    return n_imp, n_f_c, n_g_a, n_n_a, n_d_a, n_p_a, pct_f, pct_g, pct_n, pct_nof, prec, ratio


def mostrar_resultado(res, key_prefix=""):
    n_imp, n_f_c, n_g_a, n_n_a, n_d_a, n_p_a, pct_f, pct_g, pct_n, pct_nof, prec, ratio = res
    ca, cb, cc, cd = st.columns(4)
    ca.metric("Txn impactadas",         f"{n_imp:,}",  delta=f"{round(n_imp/n_tot*100,1)}% del total")
    cb.metric("Fraudes capturados (F)", f"{n_f_c:,}",  delta=f"{pct_f}% de los fraudes")
    cc.metric("Normales afectadas (N)", f"{n_n_a:,}",  delta=f"−{pct_n}% de las N", delta_color="inverse")
    cd.metric("Precisión / Ratio",      f"{prec}% / {ratio}x")

    # Detalle por indicador
    st.caption(
        f"**Impacto desglosado →**  "
        f"F capturado: **{n_f_c:,}** ({pct_f}%)  ·  "
        f"N afectadas: **{n_n_a:,}** ({pct_n}%)  ·  "
        f"G afectadas: **{n_g_a:,}** ({pct_g}%)  ·  "
        f"D afectadas: **{n_d_a:,}**  ·  "
        f"P afectadas: **{n_p_a:,}**  ·  "
        f"Total no-fraude afectado: **{n_imp-n_f_c:,}** ({pct_nof}%)"
    )
    if ratio >= 3 and pct_f >= 10:
        st.success(f"✅ Regla efectiva — captura **{pct_f}%** del fraude afectando solo **{pct_nof}%** del no-fraude.")
    elif pct_n > 20:
        st.error(f"⚠️ Alto daño colateral: **{pct_n}%** de las N (normales) serían bloqueadas.")
    elif pct_f >= 30:
        st.warning(f"Captura alta ({pct_f}%) — revisa el impacto en N ({pct_n}%).")
    else:
        st.info("Ajusta el umbral para mejorar la captura o reducir el impacto en N.")


# ─────────────────────────────────────────────────────────────────────────────
# PESTAÑAS
# ─────────────────────────────────────────────────────────────────────────────
tabs = st.tabs([
    "📊 Resumen",
    "🎯 BINs & Vectores",
    "⚡ Velocidad",
    "💰 Monto",
    "📅 Comportamiento",
    "🏆 Perfil de Riesgo",
    "🔮 Simulador de Reglas",
    "🃏 Card Testing",
    "🔎 Muestra",
])


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — RESUMEN
# ══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.header(f"Resumen — {COMERCIO_NOMBRE}")
    st.caption(f"Periodo: {f_ini} → {f_fin}  |  Registros filtrados: {n_tot:,}")

    # KPIs
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total txn",        f"{n_tot:,}")
    c2.metric("Fraudes (F)",      f"{n_f:,}",   delta=f"{tasa_f}% tasa")
    c3.metric("Normales (N)",     f"{n_norm:,}")
    c4.metric("Buenas (G)",       f"{n_bg:,}")
    c5.metric("Monto total S/",   f"{df[col_monto].sum():,.0f}")
    c6.metric("Ticket promedio",  f"S/ {df[col_monto].mean():.2f}")

    st.divider()
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Distribución por indicador")
        if has_ind:
            cnt = df[col_ind].value_counts().reindex(ind_pres, fill_value=0).reset_index()
            cnt.columns = ["Indicador","N"]
            fig = px.bar(cnt, x="Indicador", y="N", color="Indicador",
                         color_discrete_map=COLORS, text="N")
            fig.update_traces(textposition="outside")
            fig.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig, use_container_width=True)
            st.caption("F=Fraude · G=Buena · P=Pendiente · D=Descarte · N=Normal (sin alerta)")

    with col_r:
        st.subheader("Fraudes por día")
        if has_ind and "FECHA_DIA" in df.columns:
            diario = (df[mask_f_df].groupby("FECHA_DIA")
                      .agg(N_fraudes=(col_monto,"count"), Monto_F=(col_monto,"sum"))
                      .reset_index())
            fig2 = px.line(diario, x="FECHA_DIA", y="N_fraudes",
                           hover_data=["Monto_F"],
                           labels={"FECHA_DIA":"Fecha","N_fraudes":"N Fraudes"})
            fig2.update_traces(line_color="#E74C3C")
            fig2.update_layout(height=350)
            st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        st.subheader("Por producto")
        if col_prod in df.columns and has_ind:
            p = df.groupby([col_prod, col_ind], observed=True).size().unstack(fill_value=0)
            p.columns.name = None
            p["TOTAL"] = p.sum(axis=1)
            if "F" in p.columns:
                p["TASA_F%"] = (p["F"] / p["TOTAL"] * 100).round(2)
            st.dataframe(p.reset_index(), use_container_width=True)

    with col_b:
        st.subheader("Por marca")
        if col_marca in df.columns and has_ind:
            p = df.groupby([col_marca, col_ind], observed=True).size().unstack(fill_value=0)
            p.columns.name = None
            p["TOTAL"] = p.sum(axis=1)
            if "F" in p.columns:
                p["TASA_F%"] = (p["F"] / p["TOTAL"] * 100).round(2)
            st.dataframe(p.reset_index(), use_container_width=True)

    with col_c:
        st.subheader("Por 3DS (ECI)")
        if col_eci in df.columns and has_ind:
            p = df.groupby([col_eci, col_ind], observed=True).size().unstack(fill_value=0)
            p.columns.name = None
            p["TOTAL"] = p.sum(axis=1)
            if "F" in p.columns:
                p["TASA_F%"] = (p["F"] / p["TOTAL"] * 100).round(2)
            st.dataframe(p.reset_index(), use_container_width=True)

    st.subheader("Por segmento de cliente")
    if col_seg in df.columns and has_ind:
        seg_df = (df.groupby([col_seg, col_ind], observed=True).size().reset_index(name="N"))
        fig3 = px.bar(seg_df, x=col_seg, y="N", color=col_ind,
                      color_discrete_map=COLORS, barmode="stack",
                      labels={col_seg:"Segmento","N":"N transacciones"})
        fig3.update_layout(height=350)
        st.plotly_chart(fig3, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — BINs & VECTORES
# ══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.header("BINs & Vectores de Fraude")
    st.caption("BIN = primeros 6 dígitos. Identifica el emisor y tipo de tarjeta. BINs con TASA_F% alta son vectores concentrados.")

    if col_bin not in df.columns:
        st.warning("Columna BIN no disponible en los datos.")
    else:
        # ── Top BINs ──────────────────────────────────────────────────────────
        st.subheader("Top 30 BINs por volumen — Tasa de fraude")
        bin_grp = df.groupby(col_bin, observed=True).agg(
            N    = (col_monto, "count"),
            F    = (col_ind,   lambda x: (x == "F").sum()) if has_ind else (col_monto, "count"),
            G    = (col_ind,   lambda x: x.isin({"G","B"}).sum()) if has_ind else (col_monto, "count"),
            D    = (col_ind,   lambda x: (x == "D").sum()) if has_ind else (col_monto, "count"),
            N_tx = (col_ind,   lambda x: (x == "N").sum()) if has_ind else (col_monto, "count"),
        ).reset_index()
        bin_grp.rename(columns={"N_tx":"N_ind"}, inplace=True)
        bin_grp["TASA_F%"] = (bin_grp["F"] / bin_grp["N"] * 100).round(2)
        bin_top30 = bin_grp.sort_values("N", ascending=False).head(30)

        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            st.dataframe(
                bin_top30[[col_bin,"N","F","G","D","N_ind","TASA_F%"]]
                .sort_values("TASA_F%", ascending=False)
                .style.background_gradient(subset=["TASA_F%"], cmap="Reds"),
                use_container_width=True,
                height=420,
            )
        with col_b2:
            fig_bin = px.bar(
                bin_top30.sort_values("TASA_F%", ascending=False).head(15),
                x=col_bin, y="TASA_F%",
                hover_data=["N","F"],
                color="TASA_F%",
                color_continuous_scale="Reds",
                labels={col_bin:"BIN","TASA_F%":"Tasa Fraude %"},
                title="Top 15 BINs por tasa de fraude"
            )
            fig_bin.update_layout(height=420, xaxis_tickangle=-45)
            st.plotly_chart(fig_bin, use_container_width=True)

        st.divider()

        # ── Cruce BIN × Producto ──────────────────────────────────────────────
        if col_prod in df.columns:
            st.subheader("Cruce BIN × Tipo de Producto")
            cruce_bp = df.groupby([col_bin, col_prod], observed=True).size().unstack(fill_value=0)
            cruce_bp.columns.name = None
            cruce_bp["TOTAL"] = cruce_bp.sum(axis=1)
            if has_ind:
                frd_bp = df[mask_f_df].groupby(col_bin, observed=True).size().rename("N_FRAUDE")
                cruce_bp = cruce_bp.join(frd_bp, how="left").fillna(0)
                cruce_bp["N_FRAUDE"] = cruce_bp["N_FRAUDE"].astype(int)
                cruce_bp["TASA_F%"]  = (cruce_bp["N_FRAUDE"] / cruce_bp["TOTAL"] * 100).round(2)
            top_bins_prod = cruce_bp.sort_values("TOTAL", ascending=False).head(20)
            st.dataframe(
                top_bins_prod.reset_index().style.background_gradient(subset=["TASA_F%"], cmap="Reds"),
                use_container_width=True,
            )
            st.caption("BINs con fraude exclusivamente en Débito o Crédito indican que el ataque es específico de un tipo de tarjeta.")

        st.divider()

        # ── Cruce Producto × Segmento ─────────────────────────────────────────
        if col_prod in df.columns and col_seg in df.columns and has_ind:
            st.subheader("Cruce Producto × Segmento — Tasa de Fraude")
            cruce_ps = df.groupby([col_prod, col_seg], observed=True).agg(
                N = (col_monto, "count"),
                F = (col_ind, lambda x: (x=="F").sum()),
            ).reset_index()
            cruce_ps["TASA_F%"] = (cruce_ps["F"] / cruce_ps["N"] * 100).round(2)
            pivot_ps = cruce_ps.pivot(index=col_prod, columns=col_seg, values="TASA_F%").fillna(0)
            fig_heat = px.imshow(
                pivot_ps,
                color_continuous_scale="Reds",
                title="Tasa Fraude % — Producto × Segmento",
                labels=dict(color="TASA_F%"),
                aspect="auto",
            )
            fig_heat.update_layout(height=300)
            st.plotly_chart(fig_heat, use_container_width=True)

            col_ps1, col_ps2 = st.columns(2)
            with col_ps1:
                st.markdown("**Transacciones totales**")
                pivot_n = cruce_ps.pivot(index=col_prod, columns=col_seg, values="N").fillna(0)
                st.dataframe(pivot_n.style.background_gradient(cmap="Blues"), use_container_width=True)
            with col_ps2:
                st.markdown("**Fraudes (F)**")
                pivot_f = cruce_ps.pivot(index=col_prod, columns=col_seg, values="F").fillna(0)
                st.dataframe(pivot_f.style.background_gradient(cmap="Reds"), use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 3 — VELOCIDAD
# ══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.header("Velocidad — Ventanas temporales por cliente")

    VARS_V = [c for c in [
        "TRX_CLIENTE_2MIN","TRX_CLIENTE_5MIN","TRX_CLIENTE_10MIN",
        "TRX_CLIENTE_1H","TRX_CLIENTE_24H","GAP_MINUTOS",
    ] if c in df.columns]

    if not VARS_V:
        st.warning("Variables de velocidad no encontradas. Ejecuta feature_engineering.py.")
    else:
        var_sel = st.selectbox(
            "Variable a visualizar",
            VARS_V,
            index=VARS_V.index("TRX_CLIENTE_5MIN") if "TRX_CLIENTE_5MIN" in VARS_V else 0
        )

        col_v1, col_v2 = st.columns(2)
        with col_v1:
            st.subheader("Distribución por indicador")
            if has_ind:
                fig_box = px.box(
                    df[df[var_sel].notna()],
                    x=col_ind, y=var_sel, color=col_ind,
                    color_discrete_map=COLORS,
                    category_orders={col_ind: ind_pres},
                    points=False,
                    labels={col_ind:"Indicador", var_sel:var_sel},
                )
                fig_box.update_layout(height=380, showlegend=False)
                st.plotly_chart(fig_box, use_container_width=True)

        with col_v2:
            st.subheader("Distribución del GAP entre transacciones")
            if "GAP_MINUTOS" in df.columns:
                buckets = pd.cut(
                    df["GAP_MINUTOS"].clip(0, 1440),
                    bins=[-0.001, 1, 2, 5, 15, 60, 1440],
                    labels=["≤1min","1-2min","2-5min","5-15min","15-60min",">60min"],
                    include_lowest=True,
                )
                if has_ind:
                    gap_df = (pd.DataFrame({"Bucket": buckets, col_ind: df[col_ind]})
                              .groupby(["Bucket", col_ind], observed=True).size()
                              .reset_index(name="N"))
                    fig_gap = px.bar(gap_df, x="Bucket", y="N", color=col_ind,
                                     color_discrete_map=COLORS, barmode="group",
                                     labels={"Bucket":"GAP","N":"N transacciones"})
                    fig_gap.update_layout(height=380)
                    st.plotly_chart(fig_gap, use_container_width=True)

        st.info(
            "**Patrón ráfaga:** fraudes concentrados en ≤1min o 1-2min → card testing activo.  \n"
            "**Primera transacción:** >60min = sin historial previo, fraude en primer intento.  \n"
            "**Normales (N):** gap mediano de horas o días → clientes reales espacian sus compras."
        )

        st.subheader("Media / Mediana / P90 por indicador")
        rows = []
        for var in VARS_V:
            if var not in df.columns: continue
            r = {"Variable": var}
            for ind in (ind_pres if has_ind else []):
                s = df.loc[df[col_ind] == ind, var].dropna()
                r[f"{ind}_media"]   = round(s.mean(),   2) if len(s) > 0 else None
                r[f"{ind}_mediana"] = round(s.median(), 2) if len(s) > 0 else None
                r[f"{ind}_P90"]     = round(s.quantile(.90), 2) if len(s) > 0 else None
            rows.append(r)
        if rows:
            st.dataframe(pd.DataFrame(rows).set_index("Variable"), use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 4 — MONTO
# ══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.header("Análisis de Monto")

    col_m1, col_m2 = st.columns(2)

    with col_m1:
        st.subheader("Distribución del monto por indicador")
        max_monto = float(df[col_monto].quantile(0.99))
        df_hist   = df[df[col_monto] <= max_monto]
        if has_ind:
            fig_hist = px.histogram(
                df_hist, x=col_monto, color=col_ind,
                color_discrete_map=COLORS, barmode="overlay",
                opacity=0.6, nbins=50,
                labels={col_monto:"Monto S/"},
            )
            fig_hist.update_layout(height=380)
            st.plotly_chart(fig_hist, use_container_width=True)
            st.caption("Truncado en P99. Si fraude se concentra en un rango estrecho, es monto fijo (card testing).")

    with col_m2:
        st.subheader("TASA_F% por decil de monto")
        if has_ind and n_tot > 0:
            df["_DECIL"] = pd.qcut(df[col_monto], q=10, labels=False, duplicates="drop") + 1
            decil_df = df.groupby("_DECIL", observed=True).agg(
                N       = (col_monto, "count"),
                N_F     = (col_ind,   lambda x: (x=="F").sum()),
                Monto_min = (col_monto, "min"),
                Monto_max = (col_monto, "max"),
                Monto_med = (col_monto, "median"),
            ).reset_index()
            decil_df["TASA_F%"] = (decil_df["N_F"] / decil_df["N"] * 100).round(2)
            fig_dec = px.bar(
                decil_df, x="_DECIL", y="TASA_F%",
                hover_data=["N","N_F","Monto_min","Monto_max","Monto_med"],
                labels={"_DECIL":"Decil (1=más bajo, 10=más alto)","TASA_F%":"Tasa Fraude %"},
                color="TASA_F%", color_continuous_scale="Reds",
            )
            fig_dec.update_layout(height=380)
            st.plotly_chart(fig_dec, use_container_width=True)
            st.caption("Si la tasa es alta en deciles 3-4, el fraude es de ticket bajo (card testing). Si es alta en 9-10, es fraude de alto valor.")

    st.divider()

    # Estadísticas descriptivas por indicador
    st.subheader("Estadísticas del monto por indicador")
    if has_ind:
        rows_s = []
        for ind in ind_pres:
            s = df.loc[df[col_ind] == ind, col_monto].dropna()
            if len(s) == 0: continue
            rows_s.append({
                "Indicador" : ind,
                "N"         : len(s),
                "Media"     : round(s.mean(), 2),
                "Mediana"   : round(s.median(), 2),
                "Desv_Std"  : round(s.std(), 2),
                "Min"       : round(s.min(), 2),
                "P10"       : round(s.quantile(.10), 2),
                "P25"       : round(s.quantile(.25), 2),
                "P75"       : round(s.quantile(.75), 2),
                "P90"       : round(s.quantile(.90), 2),
                "P99"       : round(s.quantile(.99), 2),
                "Max"       : round(s.max(), 2),
                "Monto_Total": round(s.sum(), 0),
            })
        if rows_s:
            st.dataframe(
                pd.DataFrame(rows_s).style.background_gradient(subset=["Mediana","P90"], cmap="RdYlGn"),
                use_container_width=True,
            )

    # Z-Score vs historial cliente
    if "ZSCORE_MONTO_CLIENTE" in df.columns:
        st.subheader("Z-Score del monto vs historial del cliente")
        zs_clip = df[df["ZSCORE_MONTO_CLIENTE"].between(-5, 10)][["ZSCORE_MONTO_CLIENTE", col_ind]].dropna()
        if has_ind:
            fig_z = px.box(zs_clip, x=col_ind, y="ZSCORE_MONTO_CLIENTE",
                           color=col_ind, color_discrete_map=COLORS, points=False,
                           labels={col_ind:"Indicador","ZSCORE_MONTO_CLIENTE":"Z-Score"})
            fig_z.add_hline(y=2, line_dash="dash", line_color="orange",
                            annotation_text="Z=2")
            fig_z.update_layout(height=350, showlegend=False)
            st.plotly_chart(fig_z, use_container_width=True)
            st.caption("Z-Score < 0 en Fraude = el fraude gasta MENOS que el promedio del cliente → card testing de bajo monto.")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 5 — COMPORTAMIENTO DIARIO
# ══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.header("Comportamiento — Transaccionalidad Diaria por Cliente")
    st.caption("¿Cuántas veces compra un cliente en el mismo día? Compara F vs N para detectar ráfagas.")

    if "FECHA_DIA" not in df.columns or not has_ind:
        st.warning("Requiere columna FECHA_DIA e indicador.")
    else:
        # Calcular txn por cliente por día
        txn_dia = (df.groupby([col_cli, "FECHA_DIA", col_ind], observed=True)
                   .size().reset_index(name="N_txn_dia"))
        txn_dia["_BUCKET_DIA"] = pd.cut(
            txn_dia["N_txn_dia"],
            bins=[0, 1, 2, 3, 4, 5, 100],
            labels=["1 txn","2 txn","3 txn","4 txn","5 txn","6+ txn"],
            include_lowest=True,
        )

        bucket_ind = (txn_dia.groupby(["_BUCKET_DIA", col_ind], observed=True)
                     .agg(N_trx=(col_ind,"count"), N_clientes=(col_cli,"nunique"))
                     .reset_index())

        col_cd1, col_cd2 = st.columns(2)
        with col_cd1:
            st.subheader("Distribución de txn/día — Clientes únicos")
            fig_cd = px.bar(
                bucket_ind, x="_BUCKET_DIA", y="N_clientes", color=col_ind,
                barmode="group", color_discrete_map=COLORS,
                labels={"_BUCKET_DIA":"Txn por día","N_clientes":"Clientes únicos"},
            )
            fig_cd.update_layout(height=380)
            st.plotly_chart(fig_cd, use_container_width=True)

        with col_cd2:
            st.subheader("Tabla comparativa F vs N")
            pivot_cd = (bucket_ind[bucket_ind[col_ind].isin(["F","N"])]
                        .pivot(index="_BUCKET_DIA", columns=col_ind, values="N_clientes")
                        .fillna(0).astype(int))
            pivot_cd.columns.name = None
            pivot_cd.index.name = "Txn/día"
            if "F" in pivot_cd.columns and "N" in pivot_cd.columns:
                pivot_cd["F%_del_total_F"] = (pivot_cd["F"] / pivot_cd["F"].sum() * 100).round(1)
                pivot_cd["N%_del_total_N"] = (pivot_cd["N"] / pivot_cd["N"].sum() * 100).round(1)
            st.dataframe(pivot_cd.style.background_gradient(subset=["F%_del_total_F"], cmap="Reds"),
                         use_container_width=True)
            st.info(
                "Si la mayoría de clientes F tienen 1-2 txn/día (igual que N), "
                "el fraude es sigiloso y las reglas de velocidad por día no discriminan bien. "
                "Confirma que los controles deben basarse en BIN/monto, no solo en frecuencia."
            )

    # Distribución por hora y día semana
    st.divider()
    st.subheader("Distribución temporal — Hora del día y día de la semana")
    col_t1, col_t2 = st.columns(2)

    with col_t1:
        hora_col = C.get("hora_sin_min","")
        if hora_col in df.columns and has_ind:
            hora_df = df.groupby([hora_col, col_ind], observed=True).size().reset_index(name="N")
            fig_hora = px.bar(hora_df, x=hora_col, y="N", color=col_ind,
                              color_discrete_map=COLORS, barmode="stack",
                              labels={hora_col:"Hora del día","N":"N txn"})
            fig_hora.update_layout(height=320)
            st.plotly_chart(fig_hora, use_container_width=True)
            st.caption("Horas con proporción alta de F pueden justificar reglas de horario de riesgo.")

    with col_t2:
        dia_col = C.get("dia_semana_mon","")
        if dia_col in df.columns and has_ind:
            dia_df = df.groupby([dia_col, col_ind], observed=True).size().reset_index(name="N")
            fig_dia = px.bar(dia_df, x=dia_col, y="N", color=col_ind,
                             color_discrete_map=COLORS, barmode="stack",
                             labels={dia_col:"Día semana","N":"N txn"})
            fig_dia.update_layout(height=320)
            st.plotly_chart(fig_dia, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 6 — PERFIL DE RIESGO
# ══════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.header("Perfil de Riesgo — Score Compuesto y Flags")

    if "SCORE_RIESGO" in df.columns and has_ind:
        col_pr1, col_pr2 = st.columns(2)

        with col_pr1:
            st.subheader("Distribución SCORE_RIESGO × Indicador")
            score_df = df.groupby(["SCORE_RIESGO", col_ind], observed=True).size().reset_index(name="N")
            fig_sc = px.bar(score_df, x="SCORE_RIESGO", y="N", color=col_ind,
                            color_discrete_map=COLORS, barmode="stack",
                            labels={"SCORE_RIESGO":"Score (0=sin flags, 9=todos)","N":"N txn"})
            fig_sc.update_layout(height=380)
            st.plotly_chart(fig_sc, use_container_width=True)

        with col_pr2:
            st.subheader("TASA_F% por Score")
            sc_tasa = df.groupby("SCORE_RIESGO", observed=True).agg(
                N    = (col_monto, "count"),
                N_F  = (col_ind,   lambda x: (x=="F").sum()),
            ).reset_index()
            sc_tasa["TASA_F%"] = (sc_tasa["N_F"] / sc_tasa["N"] * 100).round(2)
            fig_sc2 = px.bar(sc_tasa, x="SCORE_RIESGO", y="TASA_F%",
                             hover_data=["N","N_F"],
                             color="TASA_F%", color_continuous_scale="Reds",
                             labels={"SCORE_RIESGO":"Score","TASA_F%":"Tasa Fraude %"})
            fig_sc2.update_layout(height=380)
            st.plotly_chart(fig_sc2, use_container_width=True)

        st.dataframe(sc_tasa.style.background_gradient(subset=["TASA_F%"], cmap="Reds"),
                     use_container_width=True)

        if "PERFIL_RIESGO" in df.columns:
            st.divider()
            st.subheader("Perfil Riesgo Categórico × Indicador")
            perf_df = df.groupby(["PERFIL_RIESGO", col_ind], observed=True).size().reset_index(name="N")
            fig_p = px.bar(perf_df, x="PERFIL_RIESGO", y="N", color=col_ind,
                           color_discrete_map=COLORS, barmode="group",
                           category_orders={"PERFIL_RIESGO":["BAJO","MEDIO","ALTO","MUY_ALTO"]},
                           labels={"PERFIL_RIESGO":"Perfil","N":"N txn"})
            fig_p.update_layout(height=350)
            st.plotly_chart(fig_p, use_container_width=True)
    else:
        st.warning("SCORE_RIESGO no disponible. Ejecuta feature_engineering.py.")

    # Tabla de efectividad de todos los flags
    st.divider()
    st.subheader("Efectividad de todos los flags como regla individual")
    st.caption("Ratio_F_vs_noFraude > 3 = regla efectiva. Muestra impacto sobre F, N, G, D, P.")

    FLAGS_APP = [c for c in df.columns
                 if (c.startswith("FLAG_") or c.startswith("HUBO_")
                     or c in {"ES_MADRUGADA","ES_FIN_SEMANA","ES_CODIGO_CRITICO"})
                 and df[c].dropna().isin({0, 1, True, False}).all()]

    if FLAGS_APP and has_ind:
        rows_fl = []
        for flag in FLAGS_APP:
            mask_fl = df[flag].fillna(0).astype(bool)
            if mask_fl.sum() == 0: continue
            n_i, n_fc, n_ga, n_na, n_da, n_pa, pf, pg, pn, pnof, pr, rt = calcular_efectividad(mask_fl)
            rows_fl.append({
                "Flag"             : flag,
                "N_impacta"        : n_i,
                "Pct_txn%"         : round(n_i / n_tot * 100, 2),
                "F_capturado"      : n_fc,
                "Pct_F%"           : pf,
                "N_afectadas"      : n_na,
                "Pct_N%"           : pn,
                "G_afectadas"      : n_ga,
                "Pct_G%"           : pg,
                "Precision%"       : pr,
                "Ratio_F_vs_noFraude": rt,
            })
        if rows_fl:
            df_fl = pd.DataFrame(rows_fl).sort_values("Pct_F%", ascending=False)
            st.dataframe(
                df_fl.style.background_gradient(subset=["Pct_F%","Ratio_F_vs_noFraude"], cmap="RdYlGn"),
                use_container_width=True,
            )
    elif not has_ind:
        st.warning("Requiere columna indicador.")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 7 — SIMULADOR DE REGLAS
# ══════════════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.header("🔮 Simulador de Reglas de Control")
    st.info(
        "Cada regla muestra cuánto **fraude captura** vs cuánto **no-fraude afecta** (N + G + D + P).  \n"
        "**Ratio > 3** y **Precisión > 10%** = regla apta para bloqueo.  \n"
        "**N = transacciones normales sin alerta** — son el 97%+ del volumen; minimizar su impacto es clave."
    )

    if not has_ind:
        st.warning("Requiere columna indicador.")
        st.stop()

    n_f_total   = n_f
    n_bg_total  = n_bg
    n_n_total   = n_norm
    n_nof_total = n_nof

    # ── REGLA BIN ──────────────────────────────────────────────────────────────
    st.subheader("⭐ Regla BIN — Bloqueo por familia de tarjeta")
    st.caption("La regla más directa cuando el fraude está concentrado en uno o pocos BINs.")

    if col_bin not in df.columns:
        st.warning("Columna BIN no disponible.")
    else:
        col_rb1, col_rb2, col_rb3 = st.columns(3)
        bins_disponibles = sorted(df[col_bin].dropna().astype(str).unique().tolist())

        # Sugerir los BINs más riesgosos como default
        top_bins_riesgo = (df.groupby(col_bin, observed=True)
                           .apply(lambda x: (x[col_ind]=="F").mean() if has_ind else 0)
                           .sort_values(ascending=False).head(5).index.astype(str).tolist())

        bins_regla = col_rb1.multiselect(
            "Selecciona BINs a bloquear",
            options=bins_disponibles,
            default=top_bins_riesgo[:2] if top_bins_riesgo else [],
            key="bins_regla",
        )
        solo_debito_bin = col_rb2.checkbox("Solo Débito (TD)", value=True, key="solo_td_bin")
        monto_max_bin   = col_rb3.slider(
            "Monto máximo S/ (0 = sin límite)",
            min_value=0, max_value=500, value=0, step=10, key="monto_max_bin"
        )

        if bins_regla:
            mask_bin_regla = df[col_bin].astype(str).isin(bins_regla)
            if solo_debito_bin and col_prod in df.columns:
                mask_bin_regla = mask_bin_regla & (df[col_prod].str.contains("Debi|TD", case=False, na=False))
            if monto_max_bin > 0:
                mask_bin_regla = mask_bin_regla & (df[col_monto] <= monto_max_bin)
            mostrar_resultado(calcular_efectividad(mask_bin_regla), "bin")
        else:
            st.caption("Selecciona al menos un BIN para ver el impacto.")

    st.divider()

    # ── REGLA BIN + RANGO DE MONTO ────────────────────────────────────────────
    st.subheader("⭐ Regla BIN + Rango de Monto")
    st.caption("Máxima precisión: filtra solo los montos donde el fraude se concentra (evita bloquear ticket alto legítimo).")

    if col_bin in df.columns:
        col_bm1, col_bm2 = st.columns(2)
        bins_bm = col_bm1.multiselect(
            "BINs",
            options=bins_disponibles,
            default=top_bins_riesgo[:2] if top_bins_riesgo else [],
            key="bins_bm",
        )
        monto_rng = col_bm2.slider(
            "Rango de monto S/",
            min_value=0.0,
            max_value=float(df[col_monto].quantile(0.95)),
            value=(29.0, 110.0),
            step=5.0,
            key="monto_rng_bm"
        )
        solo_td_bm = st.checkbox("Solo Débito (TD)", value=True, key="solo_td_bm")

        if bins_bm:
            mask_bm = df[col_bin].astype(str).isin(bins_bm)
            mask_bm = mask_bm & df[col_monto].between(monto_rng[0], monto_rng[1])
            if solo_td_bm and col_prod in df.columns:
                mask_bm = mask_bm & (df[col_prod].str.contains("Debi|TD", case=False, na=False))
            mostrar_resultado(calcular_efectividad(mask_bm), "bm")
        else:
            st.caption("Selecciona al menos un BIN.")

    st.divider()

    # ── REGLA MONTO ACUMULADO 24H ─────────────────────────────────────────────
    st.subheader("Regla Monto Acumulado 24h (MNT_CLIENTE_24H)")
    if "MNT_CLIENTE_24H" in df.columns:
        max_mnt = min(float(df["MNT_CLIENTE_24H"].quantile(0.99)), 5000.0)
        umbral_mnt = st.slider("Bloquear si MNT_CLIENTE_24H ≥ S/",
                               min_value=50.0, max_value=max_mnt,
                               value=300.0, step=50.0, key="s1")
        mostrar_resultado(calcular_efectividad(df["MNT_CLIENTE_24H"] >= umbral_mnt), "s1")
    else:
        st.warning("MNT_CLIENTE_24H no disponible")

    st.divider()

    # ── REGLA VELOCIDAD 5MIN ──────────────────────────────────────────────────
    st.subheader("Regla Velocidad — Transacciones en 5 minutos (TRX_CLIENTE_5MIN)")
    if "TRX_CLIENTE_5MIN" in df.columns:
        umbral_trx = st.slider("Bloquear si TRX_CLIENTE_5MIN ≥",
                               min_value=2, max_value=10, value=3, step=1, key="s2")
        mostrar_resultado(calcular_efectividad(df["TRX_CLIENTE_5MIN"] >= umbral_trx), "s2")
    else:
        st.warning("TRX_CLIENTE_5MIN no disponible")

    st.divider()

    # ── REGLA COMBINADA ────────────────────────────────────────────────────────
    st.subheader("Regla Combinada (MNT_24H ≥ X AND TRX_5MIN ≥ N)")
    if "MNT_CLIENTE_24H" in df.columns and "TRX_CLIENTE_5MIN" in df.columns:
        c3a, c3b = st.columns(2)
        max_mnt2 = min(float(df["MNT_CLIENTE_24H"].quantile(0.99)), 5000.0)
        u_mnt2 = c3a.slider("MNT_CLIENTE_24H ≥ S/", 50.0, max_mnt2, 300.0, 50.0, key="s3a")
        u_trx2 = c3b.slider("TRX_CLIENTE_5MIN ≥", 2, 10, 3, 1, key="s3b")
        mask_combo = (df["MNT_CLIENTE_24H"] >= u_mnt2) & (df["TRX_CLIENTE_5MIN"] >= u_trx2)
        mostrar_resultado(calcular_efectividad(mask_combo), "s3")

    st.divider()

    # ── REGLA SCORE ────────────────────────────────────────────────────────────
    st.subheader("Regla Score de Riesgo Compuesto (SCORE_RIESGO ≥ N)")
    if "SCORE_RIESGO" in df.columns:
        max_score    = max(int(df["SCORE_RIESGO"].max()), 2)
        umbral_score = st.slider("Bloquear si SCORE_RIESGO ≥",
                                 min_value=1, max_value=max_score, value=2, step=1, key="s4")
        mostrar_resultado(calcular_efectividad(df["SCORE_RIESGO"] >= umbral_score), "s4")

    st.divider()

    # ── CURVA DE EFECTIVIDAD ───────────────────────────────────────────────────
    st.subheader("Curva de efectividad — TRX_CLIENTE_5MIN")
    if "TRX_CLIENTE_5MIN" in df.columns:
        curva = []
        for u in range(2, 11):
            mask_u  = df["TRX_CLIENTE_5MIN"] >= u
            res_u   = calcular_efectividad(mask_u)
            _, _, _, _, _, _, pf_u, _, pn_u, pnof_u, prec_u, rat_u = res_u
            curva.append({"Umbral":u, "Fraude_%":pf_u, "Normal_%":pn_u, "noFraude_%":pnof_u, "Precision_%":prec_u})
        df_curva = pd.DataFrame(curva)
        fig_curva = go.Figure()
        fig_curva.add_trace(go.Scatter(x=df_curva["Umbral"], y=df_curva["Fraude_%"],
                                       mode="lines+markers", name="Fraude capturado %",
                                       line=dict(color="#E74C3C")))
        fig_curva.add_trace(go.Scatter(x=df_curva["Umbral"], y=df_curva["Normal_%"],
                                       mode="lines+markers", name="Normales (N) afectadas %",
                                       line=dict(color="#3498DB")))
        fig_curva.add_trace(go.Scatter(x=df_curva["Umbral"], y=df_curva["noFraude_%"],
                                       mode="lines+markers", name="Total no-fraude afectado %",
                                       line=dict(color="#95A5A6", dash="dot")))
        fig_curva.update_layout(
            xaxis_title="Umbral TRX_CLIENTE_5MIN ≥",
            yaxis_title="% transacciones",
            height=380,
            legend=dict(x=0.55, y=0.95),
        )
        st.plotly_chart(fig_curva, use_container_width=True)
        st.caption("Punto óptimo: línea roja alta, línea azul baja. La línea punteada muestra el impacto real incluyendo N+G+D+P.")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 8 — CARD TESTING
# ══════════════════════════════════════════════════════════════════════════════
with tabs[7]:
    st.header("Card Testing — BIN Extendido (BIN12)")
    st.info(
        "**Card testing:** misma raíz BIN12 aparece en múltiples tarjetas distintas el mismo día. "
        "El defraudador genera números de tarjeta secuencialmente para verificar cuáles tienen saldo."
    )

    c1, c2, c3 = st.columns(3)
    if "FLAG_BIN12_REPETIDO_DIA" in df.columns:
        n_ct = int(df["FLAG_BIN12_REPETIDO_DIA"].sum())
        c1.metric("Txn con BIN12 repetido",  f"{n_ct:,}")
        c2.metric("% del total",             f"{n_ct/n_tot*100:.2f}%")
        if has_ind:
            fraudes_ct = int((df["FLAG_BIN12_REPETIDO_DIA"].fillna(0).astype(bool) & mask_f_df).sum())
            c3.metric("Fraudes en BIN12 repetido", f"{fraudes_ct:,}",
                      delta=f"{round(fraudes_ct/n_f*100,1)}% de todos los fraudes" if n_f > 0 else "")

    st.divider()

    if "TARJETAS_MISMO_BIN12_DIA" in df.columns and has_ind:
        st.subheader("Distribución de tarjetas por BIN12 por día")
        df_ct = df[df["TARJETAS_MISMO_BIN12_DIA"] > 1].copy()
        if len(df_ct) > 0:
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                ct_dist = df_ct.groupby("TARJETAS_MISMO_BIN12_DIA", observed=True).size().reset_index(name="N")
                fig_ct  = px.bar(ct_dist, x="TARJETAS_MISMO_BIN12_DIA", y="N",
                                 labels={"TARJETAS_MISMO_BIN12_DIA":"Tarjetas con mismo BIN12 ese día"})
                fig_ct.update_layout(height=300)
                st.plotly_chart(fig_ct, use_container_width=True)
            with col_t2:
                if "FECHA_DIA" in df_ct.columns and "BIN_12" in df_ct.columns:
                    top_dias = (df_ct.groupby("FECHA_DIA")
                                .agg(BINs_activos=("BIN_12","nunique"),
                                     Tarjetas=(col_bin if col_bin in df_ct.columns else "BIN_12","nunique"))
                                .sort_values("BINs_activos", ascending=False)
                                .head(10).reset_index())
                    st.dataframe(top_dias, use_container_width=True)
                    st.caption("Top 10 días con más BINs de card testing activos")

    # Top BINs por tasa de fraude
    if col_bin in df.columns and has_ind:
        st.subheader("Top 20 BINs por tasa de fraude")
        bin_tbl = df.groupby(col_bin, observed=True).agg(
            N   = (col_monto, "count"),
            N_F = (col_ind,   lambda x: (x=="F").sum()),
        ).reset_index()
        bin_tbl["TASA_F%"] = (bin_tbl["N_F"] / bin_tbl["N"] * 100).round(2)
        bin_top20 = bin_tbl.nlargest(20, "TASA_F%")
        fig_bin2  = px.bar(bin_top20, x=col_bin, y="TASA_F%",
                           hover_data=["N","N_F"],
                           color="TASA_F%", color_continuous_scale="Reds",
                           labels={col_bin:"BIN","TASA_F%":"Tasa Fraude %"})
        fig_bin2.update_layout(height=350, xaxis_tickangle=-45)
        st.plotly_chart(fig_bin2, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 9 — MUESTRA
# ══════════════════════════════════════════════════════════════════════════════
with tabs[8]:
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
        col_prod, col_marca, col_seg, col_eci, col_bin,
        "TRX_CLIENTE_5MIN","TRX_CLIENTE_1H","MNT_CLIENTE_24H","GAP_MINUTOS",
        "ZSCORE_MONTO_CLIENTE","FLAG_RAFAGA_5MIN",
        "HUBO_CVV_FAIL_PREVIO","HUBO_FRAUDE_PREVIO_24H",
        "FLAG_BIN12_REPETIDO_DIA","SCORE_RIESGO","PERFIL_RIESGO",
    ] if c in df_m.columns]

    df_show = df_m[COLS_SHOW].sample(min(n_muestra, len(df_m)), random_state=42).reset_index(drop=True)
    st.caption(f"Mostrando {len(df_show):,} de {len(df_m):,} registros filtrados")
    st.dataframe(df_show, use_container_width=True)

    csv = df_show.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Descargar CSV", csv, "muestra_fraude.csv", "text/csv")


# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    f"Pipeline ecommerce_comercio — {COMERCIO_NOMBRE}  |  "
    f"Scotiabank Peru Prevención de Fraude  |  "
    f"Datos: {n_tot:,} txn  |  "
    f"Impacto real: F vs N+G+D+P  |  "
    f"Actualizar: consolidar → feature_engineering → relanzar app"
)
