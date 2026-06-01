"""
app.py — Dashboard Tarjetas Comprometidas N7 Débito
────────────────────────────────────────────────────
Ejecutar: streamlit run app.py  (desde carpeta analisis_tarjetas)

Tabs:
  1. Resumen            KPIs y distribución por indicador
  2. BIN-céntrico       Deciles dinámicos por BIN seleccionado + violin+jitter
  3. País & Horario     Distribución geográfica y temporal
  4. Velocidad          Ventanas por cliente y por tarjeta
  5. Monto              Distribución y deciles de monto
  6. Score & Vínculos   Score marca TC + flags de vínculo del cliente
  7. Perfil de Riesgo   SCORE_RIESGO, flags
  8. Simulador Reglas   Evalúa umbrales en tiempo real
  9. Muestra            Tabla filtrable de transacciones
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
    COLS, PARQUET_FEATURES, ANALISIS_NOMBRE, SOLO_APROBADAS, UMBRALES_REGLA,
)

C = COLS

st.set_page_config(
    page_title=f"Tarjetas Comprometidas — {ANALISIS_NOMBRE}",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded",
)

COLORS = {
    "F": "#E74C3C", "G": "#27AE60", "B": "#2ECC71",
    "P": "#F39C12", "D": "#95A5A6", "N": "#3498DB",
}
IND_ORDEN = ["F", "G", "B", "P", "D", "N"]


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
col_pais  = C.get("pais", "")
has_ind   = col_ind in df_raw.columns
ind_pres  = [i for i in IND_ORDEN if has_ind and i in df_raw[col_ind].unique()]


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — FILTROS GLOBALES
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.title("🔐 Tarjetas Comprometidas")
st.sidebar.subheader(ANALISIS_NOMBRE)

if has_ind:
    inds_sel = st.sidebar.multiselect(
        "Indicadores a mostrar",
        options=ind_pres,
        default=ind_pres,
        help="F=Fraude N=Normal G=Buena P=Pendiente D=Descarte",
    )
else:
    inds_sel = []

if "TIPO_PRODUCTO_TEXTO" in df_raw.columns:
    prods = df_raw["TIPO_PRODUCTO_TEXTO"].dropna().unique().tolist()
    prods_sel = st.sidebar.multiselect("Tipo producto", options=prods, default=prods)
else:
    prods_sel = []

# Aplicar filtros
df = df_raw.copy()
if inds_sel and has_ind:
    df = df[df[col_ind].isin(inds_sel)]
if prods_sel and "TIPO_PRODUCTO_TEXTO" in df.columns:
    df = df[df["TIPO_PRODUCTO_TEXTO"].isin(prods_sel)]

st.sidebar.metric("Filas filtradas", f"{len(df):,}")
st.sidebar.metric("Tarjetas únicas", f"{df['TARJETA'].nunique():,}" if "TARJETA" in df.columns else "N/A")

mask_f = (df[col_ind] == "F") if has_ind else pd.Series(False, index=df.index)
mask_n = (df[col_ind] == "N") if has_ind else pd.Series(False, index=df.index)
n_f    = int(mask_f.sum())
n_n    = int(mask_n.sum())


# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tabs = st.tabs([
    "📊 Resumen",
    "🎯 BIN-céntrico",
    "🌍 País & Horario",
    "⚡ Velocidad",
    "💰 Monto",
    "🧬 Score & Vínculos",
    "🏆 Perfil Riesgo",
    "🔮 Simulador Reglas",
    "🔎 Muestra",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — RESUMEN
# ══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.header("📊 Resumen General")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total txn", f"{len(df):,}")
    c2.metric("Fraudes (F)", f"{n_f:,}")
    tasa = round(n_f / len(df) * 100, 2) if len(df) > 0 else 0
    c3.metric("Tasa F%", f"{tasa}%")
    monto_f = df.loc[mask_f, col_monto].sum() if n_f > 0 else 0
    c4.metric("Monto fraude S/", f"{monto_f:,.0f}")
    c5.metric("Normales (N)", f"{n_n:,}")

    if has_ind:
        col_a, col_b = st.columns(2)
        with col_a:
            dist = df[col_ind].value_counts().reset_index()
            dist.columns = ["Indicador", "N"]
            dist["Color"] = dist["Indicador"].map(COLORS).fillna("#AAAAAA")
            fig = px.bar(dist, x="Indicador", y="N", color="Indicador",
                         color_discrete_map=COLORS, title="Distribución por Indicador")
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            if df[col_fh].notna().any():
                df["_mes"] = df[col_fh].dt.to_period("M").astype(str)
                evol = df.groupby(["_mes", col_ind], observed=True).size().reset_index(name="N")
                evol_f = evol[evol[col_ind] == "F"]
                fig2 = px.line(evol_f, x="_mes", y="N", title="Evolución mensual de Fraudes (F)",
                               markers=True, color_discrete_sequence=["#E74C3C"])
                st.plotly_chart(fig2, use_container_width=True)
                df.drop(columns=["_mes"], inplace=True)

    if has_ind:
        st.subheader("KPIs por Indicador")
        rows = []
        for ind in ind_pres:
            s = df.loc[df[col_ind] == ind, col_monto].dropna()
            rows.append({
                "Indicador": ind,
                "N_txn": len(s),
                "Monto_total": round(s.sum(), 0),
                "Ticket_med": round(s.median(), 2),
                "Ticket_max": round(s.max(), 2) if len(s) > 0 else 0,
                "Pct_del_total%": round(len(s) / len(df) * 100, 2) if len(df) > 0 else 0,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — BIN-CÉNTRICO (dinámico) + VIOLIN+JITTER
# ══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.header("🎯 Análisis BIN-céntrico")
    col_bin = C.get("bin", "")

    if col_bin not in df.columns:
        st.warning("Columna BIN no encontrada.")
    else:
        # ── Selector de BIN ──────────────────────────────────────────────────
        bins_disponibles = df[col_bin].value_counts().head(30).index.tolist()
        bin_sel = st.selectbox(
            "Selecciona un BIN para analizar (o deja en blanco para ver todos)",
            options=["TODOS"] + bins_disponibles,
        )
        df_bin = df if bin_sel == "TODOS" else df[df[col_bin] == bin_sel]
        mask_f_b = (df_bin[col_ind] == "F") if has_ind else pd.Series(False, index=df_bin.index)
        mask_n_b = (df_bin[col_ind] == "N") if has_ind else pd.Series(False, index=df_bin.index)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Txn en BIN", f"{len(df_bin):,}")
        c2.metric("Fraudes", f"{mask_f_b.sum():,}")
        c3.metric("Tasa F%", f"{round(mask_f_b.sum()/len(df_bin)*100,2) if len(df_bin)>0 else 0}%")
        s_f_b = df_bin.loc[mask_f_b, col_monto].dropna()
        s_n_b = df_bin.loc[mask_n_b, col_monto].dropna()
        ratio_fn = round(s_f_b.median() / s_n_b.median(), 2) if len(s_n_b) > 0 and s_n_b.median() > 0 else "-"
        c4.metric("Ratio F/N monto", str(ratio_fn))

        st.markdown("---")
        col_a, col_b_col = st.columns(2)

        with col_a:
            # ── Violin + Jitter plot ──────────────────────────────────────────
            st.subheader("Violin + Jitter — Monto por Indicador")
            st.caption("Puntos rojos = Fraude (F) | Puntos azules claros = Normal (N)")

            df_viz = df_bin[df_bin[col_ind].isin(["F","N","G"])].copy()
            p99_viz = df_viz[col_monto].quantile(0.99)
            df_viz = df_viz[df_viz[col_monto] <= p99_viz]

            # Violin base
            fig_v = go.Figure()
            for ind_v, color_v in [("N","#AED6F1"), ("G","#A9DFBF"), ("F","#E74C3C")]:
                sub_v = df_viz[df_viz[col_ind] == ind_v]
                if len(sub_v) == 0:
                    continue
                # Violin
                fig_v.add_trace(go.Violin(
                    x=sub_v[col_ind], y=sub_v[col_monto],
                    name=ind_v, box_visible=True, meanline_visible=True,
                    line_color=color_v, fillcolor=color_v,
                    opacity=0.5, showlegend=True,
                ))
                # Jitter (puntos superpuestos)
                n_pts = min(300, len(sub_v))
                sub_sample = sub_v.sample(n_pts, random_state=42)
                jitter_x = [ind_v] * n_pts
                fig_v.add_trace(go.Scatter(
                    x=jitter_x,
                    y=sub_sample[col_monto],
                    mode="markers",
                    marker=dict(
                        color=color_v if ind_v != "F" else "#C0392B",
                        size=4 if ind_v == "F" else 3,
                        opacity=0.8 if ind_v == "F" else 0.3,
                        symbol="circle",
                    ),
                    name=f"{ind_v} puntos",
                    showlegend=False,
                ))
            fig_v.update_layout(
                title=f"Distribución de Monto — {'BIN: ' + bin_sel if bin_sel != 'TODOS' else 'Todos los BINs'} (hasta P99)",
                yaxis_title="Monto S/",
                xaxis_title="Indicador",
                violinmode="overlay",
            )
            st.plotly_chart(fig_v, use_container_width=True)

        with col_b_col:
            # ── Deciles dinámicos para el BIN seleccionado ────────────────────
            st.subheader(f"Deciles de Monto — {bin_sel}")
            if "DECIL_MONTO" in df_bin.columns and has_ind:
                # Recalcular deciles para este BIN específico
                df_bin2 = df_bin.copy()
                try:
                    df_bin2["_decil_bin"] = pd.qcut(
                        df_bin2[col_monto], q=10, labels=False, duplicates="drop"
                    ) + 1
                    dec_dyn = df_bin2.groupby("_decil_bin", observed=True).agg(
                        N_trx=(col_monto,"count"),
                        Monto_min=(col_monto,"min"),
                        Monto_max=(col_monto,"max"),
                        Monto_med=(col_monto,"median"),
                        N_F=(col_ind, lambda x: (x=="F").sum()),
                        N_N=(col_ind, lambda x: (x=="N").sum()),
                    ).reset_index()
                    dec_dyn["TASA_F%"] = (dec_dyn["N_F"] / dec_dyn["N_trx"] * 100).round(2)
                    dec_dyn["Monto_min"] = dec_dyn["Monto_min"].round(2)
                    dec_dyn["Monto_max"] = dec_dyn["Monto_max"].round(2)
                    dec_dyn["Monto_med"] = dec_dyn["Monto_med"].round(2)

                    fig_dec = px.bar(dec_dyn, x="_decil_bin", y="TASA_F%",
                                     color="TASA_F%", color_continuous_scale="Reds",
                                     title=f"TASA_F% por Decil — BIN {bin_sel}",
                                     labels={"_decil_bin": "Decil", "TASA_F%": "Tasa F%"})
                    st.plotly_chart(fig_dec, use_container_width=True)
                    st.dataframe(dec_dyn, use_container_width=True)
                except Exception as e:
                    st.warning(f"No se pudo calcular deciles para este BIN: {e}")

        st.markdown("---")
        # ── Heatmap BIN × Hora × TASA_F% ─────────────────────────────────────
        st.subheader("Heatmap Multivariado: BIN × Hora × Tasa F%")
        if "HORA_DIA" in df.columns and col_bin in df.columns and has_ind:
            top5_bins = df[col_bin].value_counts().head(5).index.tolist()
            df_heat = df[df[col_bin].isin(top5_bins)].copy()
            heat_data = df_heat.groupby([col_bin, "HORA_DIA"], observed=True).agg(
                N=(col_monto,"count"),
                N_F=(col_ind, lambda x: (x=="F").sum()),
            ).reset_index()
            heat_data["TASA_F%"] = (heat_data["N_F"] / heat_data["N"] * 100).round(2)
            heat_pivot = heat_data.pivot(index=col_bin, columns="HORA_DIA", values="TASA_F%").fillna(0)
            fig_heat = px.imshow(
                heat_pivot,
                color_continuous_scale="Reds",
                title="TASA_F% por BIN (top 5) × Hora del Día",
                labels=dict(x="Hora", y="BIN", color="Tasa F%"),
                aspect="auto",
            )
            st.plotly_chart(fig_heat, use_container_width=True)
            st.caption("Celdas rojas intensas = combinación BIN+hora con mayor concentración de fraude → candidatas a regla")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PAÍS & HORARIO
# ══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.header("🌍 País y Horario")

    col_a, col_b = st.columns(2)

    with col_a:
        if col_pais and col_pais in df.columns and has_ind:
            pais_f = df.groupby(col_pais, observed=True).agg(
                N=(col_monto, "count"),
                N_F=(col_ind, lambda x: (x == "F").sum()),
            ).reset_index()
            pais_f["TASA_F%"] = (pais_f["N_F"] / pais_f["N"] * 100).round(2)
            top_paises = pais_f.sort_values("N_F", ascending=False).head(15)
            fig = px.bar(top_paises, x=col_pais, y="N_F", color="TASA_F%",
                         color_continuous_scale="Reds",
                         title="Top 15 países por N° de Fraudes")
            st.plotly_chart(fig, use_container_width=True)

        if "FLAG_PAIS_DISTINTO_CLIENTE" in df.columns and has_ind:
            pdc = df.groupby("FLAG_PAIS_DISTINTO_CLIENTE", observed=True).agg(
                N=(col_monto, "count"),
                N_F=(col_ind, lambda x: (x == "F").sum()),
            ).reset_index()
            pdc["TASA_F%"] = (pdc["N_F"] / pdc["N"] * 100).round(2)
            pdc["Pais_distinto"] = pdc["FLAG_PAIS_DISTINTO_CLIENTE"].map({0: "País habitual", 1: "País distinto"})
            st.subheader("País distinto al habitual del cliente")
            st.dataframe(pdc[["Pais_distinto","N","N_F","TASA_F%"]], use_container_width=True)

    with col_b:
        if "HORA_DIA" in df.columns and has_ind:
            hora_f = df.groupby("HORA_DIA", observed=True).agg(
                N=(col_monto, "count"),
                N_F=(col_ind, lambda x: (x == "F").sum()),
                N_N=(col_ind, lambda x: (x == "N").sum()),
            ).reset_index()
            hora_f["TASA_F%"] = (hora_f["N_F"] / hora_f["N"] * 100).round(2)
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=hora_f["HORA_DIA"], y=hora_f["N_F"],
                                  name="Fraudes", marker_color="#E74C3C"))
            fig2.add_trace(go.Scatter(x=hora_f["HORA_DIA"], y=hora_f["TASA_F%"],
                                      name="Tasa F%", yaxis="y2",
                                      line=dict(color="#9B59B6", width=2)))
            fig2.update_layout(
                title="Fraudes por Hora del Día",
                yaxis2=dict(overlaying="y", side="right", title="Tasa F%"),
                bargap=0.2,
            )
            st.plotly_chart(fig2, use_container_width=True)

        if "FRANJA_HORARIA" in df.columns and has_ind:
            franja_f = df.groupby("FRANJA_HORARIA", observed=True).agg(
                N=(col_monto, "count"),
                N_F=(col_ind, lambda x: (x == "F").sum()),
            ).reset_index()
            franja_f["TASA_F%"] = (franja_f["N_F"] / franja_f["N"] * 100).round(2)
            st.subheader("Por Franja Horaria")
            st.dataframe(franja_f.sort_values("TASA_F%", ascending=False), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — VELOCIDAD
# ══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.header("⚡ Velocidad")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Ventanas por Cliente")
        vars_vel = [v for v in ["TRX_CLIENTE_5MIN","TRX_CLIENTE_1H","TRX_CLIENTE_24H","GAP_MINUTOS"] if v in df.columns]
        if vars_vel and has_ind:
            rows_v = []
            for v in vars_vel:
                for ind in ind_pres:
                    s = df.loc[df[col_ind] == ind, v].dropna()
                    if len(s) > 0:
                        rows_v.append({"Variable": v, "Indicador": ind,
                                       "Media": round(s.mean(), 2), "Mediana": round(s.median(), 2),
                                       "P90": round(s.quantile(0.9), 2)})
            if rows_v:
                st.dataframe(pd.DataFrame(rows_v), use_container_width=True)

    with col_b:
        st.subheader("Ventanas por Tarjeta (nuevo)")
        vars_tar = [v for v in ["TRX_TARJETA_5MIN","TRX_TARJETA_1H","TRX_TARJETA_24H","MNT_TARJETA_24H"] if v in df.columns]
        if vars_tar and has_ind:
            rows_t = []
            for v in vars_tar:
                for ind in ind_pres:
                    s = df.loc[df[col_ind] == ind, v].dropna()
                    if len(s) > 0:
                        rows_t.append({"Variable": v, "Indicador": ind,
                                       "Media": round(s.mean(), 2), "Mediana": round(s.median(), 2),
                                       "P90": round(s.quantile(0.9), 2)})
            if rows_t:
                st.dataframe(pd.DataFrame(rows_t), use_container_width=True)

    if "TRX_CLIENTE_5MIN" in df.columns and has_ind:
        st.subheader("Distribución TRX_CLIENTE_5MIN por Indicador")
        fig = px.box(
            df[df[col_ind].isin(["F","N","G"])].assign(
                Monto_clip=df[col_monto].clip(upper=df[col_monto].quantile(0.99))
            ),
            x=col_ind, y="TRX_CLIENTE_5MIN", color=col_ind,
            color_discrete_map=COLORS, title="Transacciones en 5 min por cliente",
            points=False,
        )
        st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — MONTO
# ══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.header("💰 Análisis de Monto")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Distribución por Indicador")
        p99 = df[col_monto].quantile(0.99)
        df_clip = df[df[col_monto].notna() & (df[col_monto] <= p99)]
        if has_ind:
            fig = px.histogram(
                df_clip[df_clip[col_ind].isin(["F","N"])],
                x=col_monto, color=col_ind, barmode="overlay",
                color_discrete_map=COLORS, nbins=50,
                title="Distribución Monto — F vs N (hasta P99)",
                opacity=0.6,
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        if "DECIL_MONTO" in df.columns and has_ind:
            st.subheader("Tasa F% por Decil de Monto")
            dec_stats = df.groupby("DECIL_MONTO", observed=True).agg(
                N=(col_monto, "count"),
                N_F=(col_ind, lambda x: (x == "F").sum()),
                Monto_med=(col_monto, "median"),
            ).reset_index()
            dec_stats["TASA_F%"] = (dec_stats["N_F"] / dec_stats["N"] * 100).round(2)
            fig2 = px.bar(dec_stats, x="DECIL_MONTO", y="TASA_F%",
                          color="TASA_F%", color_continuous_scale="Reds",
                          title="TASA_F% por Decil — deciles calientes son candidatos a regla")
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Estadísticas de Monto por Indicador")
    if has_ind:
        rows_s = []
        for ind in ind_pres:
            s = df.loc[df[col_ind] == ind, col_monto].dropna()
            if len(s) > 0:
                rows_s.append({
                    "Indicador": ind, "N": len(s),
                    "Min": round(s.min(), 2), "P10": round(s.quantile(0.1), 2),
                    "Mediana": round(s.median(), 2), "Media": round(s.mean(), 2),
                    "P90": round(s.quantile(0.9), 2), "P99": round(s.quantile(0.99), 2),
                    "Max": round(s.max(), 2),
                })
        st.dataframe(pd.DataFrame(rows_s), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — SCORE DE MARCA TC + VÍNCULOS DEL CLIENTE
# ══════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.header("🧬 Score de Marca TC y Vínculos del Cliente")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Score Normalizado — Visa (0-99) / MC (0-999)")
        if "SCORE_NORMALIZADO" in df.columns and has_ind:
            df_tc_sc = df[df["SCORE_NORMALIZADO"].notna()].copy()
            if len(df_tc_sc) > 0:
                fig_sc = px.box(
                    df_tc_sc[df_tc_sc[col_ind].isin(["F","N","G"])],
                    x=col_ind, y="SCORE_NORMALIZADO", color=col_ind,
                    color_discrete_map=COLORS,
                    title="Score Normalizado por Indicador (TC crédito)",
                    points=False,
                )
                st.plotly_chart(fig_sc, use_container_width=True)

                # Score por marca
                if "MARCA_TARJETA" in df_tc_sc.columns:
                    sc_marca = df_tc_sc.groupby(["MARCA_TARJETA", col_ind], observed=True)["SCORE_NORMALIZADO"]\
                        .median().reset_index().rename(columns={"SCORE_NORMALIZADO": "Score_mediana"})
                    st.subheader("Score Mediana por Marca × Indicador")
                    st.dataframe(sc_marca.round(3), use_container_width=True)
        else:
            st.info("Score de marca no disponible en los datos (requiere columna 'SCORE DE RIESGO' en Monitor).")

    with col_b:
        st.subheader("Vínculos: Efectividad como reglas")
        FLAGS_V = [f for f in [
            "FLAG_CLIENTE_YA_FRAUDULENTO","FLAG_CLIENTE_MULTIFRAUDE",
            "FLAG_PRIMERA_TRX_CLI_TOTAL","FLAG_TRX_DIA_ANOMALA",
            "FLAG_MONTO_ALTO_CLI_COMERCIO","FLAG_CLI_OUTLIER_TICKET_COMERCIO",
            "FLAG_CLI_OUTLIER_VELOCIDAD_COMERCIO","FLAG_SCORE_ALTO_TC",
        ] if f in df.columns and has_ind]
        if FLAGS_V:
            rows_vt = []
            nf_t = int(mask_f.sum()); nnf_t = int((~mask_f).sum())
            for fl in FLAGS_V:
                mf2 = df[fl].fillna(0).astype(bool)
                n_imp2 = int(mf2.sum()); n_fc2 = int((mf2 & mask_f).sum())
                n_nf2  = int((mf2 & ~mask_f).sum())
                pf2  = round(n_fc2 / nf_t * 100, 2) if nf_t > 0 else 0
                pnf2 = round(n_nf2 / nnf_t * 100, 2) if nnf_t > 0 else 0
                ratio2 = round(pf2 / pnf2, 2) if pnf2 > 0 else 999.0
                rows_vt.append({
                    "Flag": fl.replace("FLAG_",""), "N_F": n_fc2,
                    "Pct_F%": pf2, "Pct_noF%": pnf2,
                    "Ratio": ratio2,
                    "Precision%": round(n_fc2 / n_imp2 * 100, 2) if n_imp2 > 0 else 0,
                })
            df_vt = pd.DataFrame(rows_vt).sort_values("Ratio", ascending=False)
            fig_vt = px.bar(df_vt, x="Flag", y="Ratio", color="Ratio",
                            color_continuous_scale="Greens",
                            title="Ratio F/noF por Flag de Vínculo (>3 = regla efectiva)")
            fig_vt.add_hline(y=3, line_dash="dash", line_color="red",
                             annotation_text="Umbral Ratio=3")
            st.plotly_chart(fig_vt, use_container_width=True)
            st.dataframe(df_vt.style.background_gradient(subset=["Ratio"], cmap="Greens"),
                         use_container_width=True)

    # ── Evolución del fraude en clientes reincidentes ─────────────────────────
    if "N_FRAUDES_PREVIOS_CLI" in df.columns and has_ind:
        st.subheader("Distribución N_FRAUDES_PREVIOS_CLI × Indicador")
        st.caption("¿Los fraudes de hoy vienen de clientes que ya tuvieron fraude antes?")
        buckets_fp = pd.cut(
            df["N_FRAUDES_PREVIOS_CLI"].clip(0, 5),
            bins=[-1, 0, 1, 2, 3, 5],
            labels=["0 (nuevo)","1 fraude prev","2 prev","3 prev","4-5 prev"],
            include_lowest=True,
        )
        df_fp_dist = (
            df.assign(_bucket=buckets_fp)
              .groupby(["_bucket", col_ind], observed=True).size()
              .unstack(col_ind, fill_value=0)
        )
        df_fp_dist.columns.name = None
        df_fp_dist = df_fp_dist.reindex(columns=[c for c in IND_ORDEN if c in df_fp_dist.columns])
        df_fp_dist["TOTAL"] = df_fp_dist.sum(axis=1)
        if "F" in df_fp_dist.columns:
            df_fp_dist["TASA_F%"] = (df_fp_dist["F"] / df_fp_dist["TOTAL"] * 100).round(2)
        st.dataframe(df_fp_dist.reset_index(), use_container_width=True)
        st.caption("Si TASA_F% sube con los fraudes previos → los reincidentes son de mayor riesgo.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 (antes 6) — PERFIL DE RIESGO
# ══════════════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.header("🏆 Perfil de Riesgo")

    if "SCORE_RIESGO" in df.columns and has_ind:
        col_a, col_b = st.columns(2)
        with col_a:
            sc_stats = df.groupby(["SCORE_RIESGO", col_ind], observed=True).size().unstack(fill_value=0)
            sc_stats.columns.name = None
            sc_stats = sc_stats.reindex(columns=[c for c in IND_ORDEN if c in sc_stats.columns])
            sc_stats["TOTAL"] = sc_stats.sum(axis=1)
            if "F" in sc_stats.columns:
                sc_stats["TASA_F%"] = (sc_stats["F"] / sc_stats["TOTAL"] * 100).round(2)
            sc_stats = sc_stats.reset_index()
            fig = px.bar(sc_stats, x="SCORE_RIESGO", y="TASA_F%",
                         color="TASA_F%", color_continuous_scale="Reds",
                         title="TASA_F% por SCORE_RIESGO")
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            if "PERFIL_RIESGO" in df.columns:
                perf = df.groupby("PERFIL_RIESGO", observed=True).agg(
                    N=(col_monto, "count"),
                    N_F=(col_ind, lambda x: (x == "F").sum()),
                ).reset_index()
                perf["TASA_F%"] = (perf["N_F"] / perf["N"] * 100).round(2)
                fig2 = px.bar(perf, x="PERFIL_RIESGO", y="N", color="TASA_F%",
                              color_continuous_scale="Reds",
                              title="Volumen por Perfil de Riesgo",
                              category_orders={"PERFIL_RIESGO": ["BAJO","MEDIO","ALTO","MUY_ALTO"]})
                st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Efectividad de FLAGS nuevos (tarjeta/país/MCC)")
    FLAGS_NUEVOS = [f for f in [
        "FLAG_TARJETA_RAFAGA_5MIN","FLAG_TARJETA_VEL_ALTA_1H",
        "FLAG_PAIS_DISTINTO_CLIENTE","FLAG_MULTI_PAIS_24H",
        "ES_TRX_EXTRANJERO","FLAG_MCC_ALTO_RIESGO","FLAG_MCC_ATM_CASH",
        "FLAG_ECOMMERCE","FLAG_ECOM_MADRUGADA","FLAG_ECOM_EXTRANJERO",
    ] if f in df.columns and has_ind]

    rows_fl = []
    n_fraudes_t = int(mask_f.sum()); n_no_f_t = int((~mask_f).sum())
    for fl in FLAGS_NUEVOS:
        mf = df[fl].fillna(0).astype(bool)
        n_imp = int(mf.sum())
        n_fc  = int((mf & mask_f).sum())
        n_nf  = int((mf & ~mask_f).sum())
        pct_f = round(n_fc / n_fraudes_t * 100, 2) if n_fraudes_t > 0 else 0
        pct_nf= round(n_nf / n_no_f_t * 100, 2) if n_no_f_t > 0 else 0
        ratio = round(pct_f / pct_nf, 2) if pct_nf > 0 else 999.0
        prec  = round(n_fc / n_imp * 100, 2) if n_imp > 0 else 0
        rows_fl.append({"Flag": fl, "N_impacta": n_imp, "N_F": n_fc,
                        "Pct_F%": pct_f, "Pct_noF%": pct_nf,
                        "Ratio_F_noF": ratio, "Precision%": prec})
    if rows_fl:
        df_fl = pd.DataFrame(rows_fl).sort_values("Ratio_F_noF", ascending=False)
        st.dataframe(df_fl.style.background_gradient(subset=["Ratio_F_noF"], cmap="Greens"),
                     use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 8 — SIMULADOR DE REGLAS
# ══════════════════════════════════════════════════════════════════════════════
with tabs[7]:
    st.header("🔮 Simulador de Reglas Segmentadas")
    st.info("Construye una regla combinada y ve cuánto fraude captura vs cuántos normales impacta.")

    if not has_ind:
        st.warning("Requiere columna indicador en los datos.")
    else:
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.subheader("Filtro de Monto")
            monto_min_sim = st.slider(
                "Monto mínimo (S/)",
                min_value=0.0,
                max_value=float(df[col_monto].quantile(0.95)),
                value=25.0, step=5.0,
            )
        with col_b:
            st.subheader("Filtro de País")
            solo_extranjero = st.checkbox("Solo transacciones en país extranjero", value=False)
            solo_pais_distinto = st.checkbox("Solo país distinto al habitual del cliente", value=False)
        with col_c:
            st.subheader("Filtro de Horario")
            solo_madrugada = st.checkbox("Solo madrugada (0-6h)", value=False)
            solo_finsemana = st.checkbox("Solo fin de semana", value=False)
            solo_ecommerce = st.checkbox("Solo ecommerce (tarjeta no presente)", value=False)

        mask_sim = df[col_monto] >= monto_min_sim
        if solo_extranjero and "ES_TRX_EXTRANJERO" in df.columns:
            mask_sim = mask_sim & (df["ES_TRX_EXTRANJERO"] == 1)
        if solo_pais_distinto and "FLAG_PAIS_DISTINTO_CLIENTE" in df.columns:
            mask_sim = mask_sim & (df["FLAG_PAIS_DISTINTO_CLIENTE"] == 1)
        if solo_madrugada and "ES_MADRUGADA" in df.columns:
            mask_sim = mask_sim & (df["ES_MADRUGADA"] == 1)
        if solo_finsemana and "ES_FIN_SEMANA" in df.columns:
            mask_sim = mask_sim & (df["ES_FIN_SEMANA"] == 1)
        if solo_ecommerce and "FLAG_ECOMMERCE" in df.columns:
            mask_sim = mask_sim & (df["FLAG_ECOMMERCE"] == 1)

        n_imp  = int(mask_sim.sum())
        n_fc   = int((mask_sim & mask_f).sum())
        n_nfc  = int((mask_sim & ~mask_f).sum())
        n_nc   = int((mask_sim & mask_n).sum())
        n_fr_t = int(mask_f.sum())
        n_n_t  = int(mask_n.sum())

        pct_f_cap = round(n_fc / n_fr_t * 100, 2) if n_fr_t > 0 else 0
        pct_n_af  = round(n_nc / n_n_t * 100, 2)  if n_n_t > 0 else 0
        precision = round(n_fc / n_imp * 100, 2)   if n_imp > 0 else 0
        ratio     = round(pct_f_cap / pct_n_af, 2) if pct_n_af > 0 else (999.0 if n_fc > 0 else 0.0)

        st.markdown("---")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Txn impactadas", f"{n_imp:,}")
        m2.metric("Fraudes capturados", f"{n_fc:,}", f"{pct_f_cap}% del total")
        m3.metric("Normales afectados", f"{n_nc:,}", f"{pct_n_af}% del total")
        m4.metric("Precisión%", f"{precision}%")
        color_ratio = "🟢" if ratio >= 3 else ("🟡" if ratio >= 1.5 else "🔴")
        m5.metric("Ratio F/noF", f"{color_ratio} {ratio}")

        if ratio >= 3:
            st.success(f"✅ Regla EFECTIVA — Ratio {ratio} ≥ 3. Candidata para implementación.")
        elif ratio >= 1.5:
            st.warning(f"⚠️ Regla MODERADA — Ratio {ratio}. Combina con más condiciones.")
        else:
            st.error(f"❌ Regla DÉBIL — Ratio {ratio} < 1.5. Necesita más segmentación.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 9 — MUESTRA
# ══════════════════════════════════════════════════════════════════════════════
with tabs[8]:
    st.header("🔎 Muestra de Transacciones")

    COLS_SHOW = [c for c in [
        col_cli, col_fh, "TARJETA", col_monto, col_ind,
        "TIPO_PRODUCTO_TEXTO", "MARCA_TARJETA", "SEG_NOMBRE",
        col_pais, "ES_TRX_EXTRANJERO", "FLAG_PAIS_DISTINTO_CLIENTE",
        "TIPO_ENTRADA", "SEGURO",
        "TRX_CLIENTE_5MIN", "TRX_TARJETA_24H",
        "MNT_CLIENTE_24H", "MNT_TARJETA_24H",
        "FLAG_ECOM_EXTRANJERO", "FLAG_MCC_ALTO_RIESGO",
        "SCORE_RIESGO", "PERFIL_RIESGO",
    ] if c in df.columns]

    col_a, col_b = st.columns(2)
    with col_a:
        score_min = st.number_input("Score mínimo", min_value=0, max_value=17, value=0, step=1)
    with col_b:
        solo_fraudes = st.checkbox("Solo fraudes (F)", value=False)

    df_show = df.copy()
    if "SCORE_RIESGO" in df_show.columns:
        df_show = df_show[df_show["SCORE_RIESGO"] >= score_min]
    if solo_fraudes and has_ind:
        df_show = df_show[df_show[col_ind] == "F"]

    n_show = min(1000, len(df_show))
    st.metric("Filas mostradas", f"{n_show:,} de {len(df_show):,}")
    st.dataframe(
        df_show[COLS_SHOW].sample(n_show, random_state=42).reset_index(drop=True),
        use_container_width=True,
    )

    csv = df_show[COLS_SHOW].to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Descargar CSV", data=csv,
                       file_name=f"muestra_{ANALISIS_NOMBRE}.csv", mime="text/csv")
