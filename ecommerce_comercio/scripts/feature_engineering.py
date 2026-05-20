"""
feature_engineering.py
──────────────────────
Lee data/consolidado.parquet y genera features de fraude para ecommerce.

Bloques:
  A  Velocidad / frecuencia  → N_TRX_5MIN, N_TRX_15MIN, N_TRX_1H, N_TRX_24H, GAP_MINUTOS, ES_RAFAGA
  B  Monto y patrones        → MONTO_ACUM_2H, MONTO_ACUM_24H, ZSCORE_MONTO_CLI, RATIO_MONTO_AVG_CLI,
                               RATIO_MONTO_SALDO, ES_MONTO_REDONDO, ES_MONTO_BAJO
  C  Comportamiento comercio → ES_PRIMERA_VEZ_COMERCIO, N_TRX_HISTORICAS_COMERCIO, DIAS_DESDE_PRIMERA_COMPRA
  D  Cascada de fraude       → HUBO_FRAUDE_PREVIO_24H, HUBO_FRAUDE_PREVIO_7D, PREV_FUE_FRAUDE,
                               MIN_DESDE_ULTIMO_FRAUDE
  E  Geográficas / IP        → PAIS_DISTINTO_HABITUAL, CAMBIO_PAIS_VS_PREV, N_PAISES_DISTINTOS_24H,
                               IP_NUEVA_CLIENTE, N_CLIENTES_MISMA_IP_24H
  F  Rechazos / CVV          → N_RECHAZOS_24H, N_CVV_FAIL_24H, HUBO_CVV_FAIL_PREVIO, MOTIVO_RECH
  G  Score de riesgo         → SCORE_RIESGO, PERFIL_RIESGO (BAJO/MEDIO/ALTO/MUY_ALTO)

Salida: data/consolidado_features.parquet
"""

import sys
import warnings
import pandas as pd
import numpy as np
import polars as pl
from pathlib import Path

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    COLS, PARQUET_CONSOLIDADO, PARQUET_FEATURES,
    COMERCIO_NOMBRE, SEG_NOMBRE, SEG_GRUPO, COD_RED_LABEL,
    clasificar_motivo,
)

C = COLS

# ─────────────────────────────────────────────────────────────────────────────
# CARGA
# ─────────────────────────────────────────────────────────────────────────────
ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else PARQUET_CONSOLIDADO

if not ruta.exists():
    print(f"\n❌  No se encontró: {ruta}")
    print("    Ejecuta primero: python scripts/consolidar.py")
    sys.exit(1)

print("═" * 65)
print(f"FEATURE ENGINEERING — {COMERCIO_NOMBRE}")
print("═" * 65)
print(f"  Cargando: {ruta}")
df_raw = pd.read_parquet(ruta)

# Renombrar columnas ACF → claves cortas internas
col_map = {v: k for k, v in C.items() if v and v in df_raw.columns}
df = df_raw.rename(columns=col_map).copy()

faltantes = [k for k, v in C.items() if v and v not in df_raw.columns]
if faltantes:
    print(f"  ⚠️  Columnas no encontradas (features dependientes se omiten): {faltantes}")

# Castear tipos
df["monto"]  = pd.to_numeric(df.get("monto",  pd.Series(dtype=float)), errors="coerce")
df["saldo"]  = pd.to_numeric(df.get("saldo",  pd.Series(dtype=float)), errors="coerce") if "saldo" in df.columns else np.nan
df["fecha_hora"] = pd.to_datetime(df["fecha_hora"], errors="coerce") if "fecha_hora" in df.columns else pd.NaT
df["fecha"] = df["fecha_hora"].dt.normalize()
df["mes"]   = df["fecha_hora"].dt.to_period("M").astype(str)

for c in ["indicador","cod_respuesta","cod_motivo","razon_respuesta","canal",
          "eci","cod_red_comercio","segmento","tipo_producto","entry_mode",
          "pais","region","ciudad","ip"]:
    if c in df.columns:
        df[c] = df[c].astype(str).str.strip().str.upper()

if "bin" in df.columns:
    df["bin"] = df["bin"].astype(str).str.split(".").str[0].str.strip()

# Columnas derivadas de negocio
df["ESTADO"] = df["cod_respuesta"].apply(
    lambda x: "APROBADA" if str(x).strip() in ["00","0000","000","0"] else "DENEGADA"
)
df["ES_FRAUDE"]          = (df["indicador"] == "F").astype(int)
df["ES_FRAUDE_APROBADO"] = ((df["indicador"] == "F") & (df["ESTADO"] == "APROBADA")).astype(int)

if "eci" in df.columns:
    df["SEGURO"] = df["eci"].apply(
        lambda x: "Seguro" if str(x).strip() in ["2","5","02","05"] else "No Seguro"
    )
else:
    df["SEGURO"] = "No Seguro"

df["SEG_NOMBRE"]    = df["segmento"].map(SEG_NOMBRE).fillna("Otro/Sin seg") if "segmento" in df.columns else "Otro/Sin seg"
df["SEG_GRUPO"]     = df["segmento"].map(SEG_GRUPO).fillna("Otro/Sin seg")  if "segmento" in df.columns else "Otro/Sin seg"
df["COD_RED_LABEL"] = df["cod_red_comercio"].map(COD_RED_LABEL).fillna("Otro") if "cod_red_comercio" in df.columns else "Otro"

if "razon_respuesta" in df.columns:
    df["MOTIVO_RECH"] = df["razon_respuesta"].apply(clasificar_motivo)
    df.loc[df["ESTADO"] == "APROBADA", "MOTIVO_RECH"] = "N/A"
else:
    df["MOTIVO_RECH"] = "N/A"

df_ap  = df[df["ESTADO"] == "APROBADA"].copy()
df_den = df[df["ESTADO"] == "DENEGADA"].copy()

NOMBRE_COMERCIO = df["comercio_nom"].mode().iloc[0] if "comercio_nom" in df.columns and len(df) > 0 else COMERCIO_NOMBRE
print(f"\n  Comercio: {NOMBRE_COMERCIO}")
print(f"  Total: {len(df):,} | Aprobadas: {len(df_ap):,} | Denegadas: {len(df_den):,}")
print(f"  Fraude total: {df['ES_FRAUDE'].sum():,} | Fraude aprobado: {df['ES_FRAUDE_APROBADO'].sum():,}")


# ─────────────────────────────────────────────────────────────────────────────
# INGENIERÍA DE VARIABLES CON POLARS
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("FEATURE ENGINEERING (Polars)")
print("─" * 65)

cols_base = ["id_cliente","fecha_hora","comercio_nom","monto",
             "ES_FRAUDE","ES_FRAUDE_APROBADO","ESTADO","indicador",
             "SEG_NOMBRE","SEG_GRUPO","tipo_producto","SEGURO",
             "canal","COD_RED_LABEL","mes","MOTIVO_RECH"]
for opt in ["saldo","bin","pais","region","ciudad","ip"]:
    if opt in df.columns:
        cols_base.append(opt)

cols_base = [c for c in cols_base if c in df.columns]
plf = pl.from_pandas(df[cols_base].reset_index(drop=True))
plf = plf.with_columns(pl.col("fecha_hora").cast(pl.Datetime("us")))
plf = plf.sort(["id_cliente","fecha_hora"])

plf_ap  = plf.filter(pl.col("ESTADO") == "APROBADA")
plf_den = plf.filter(pl.col("ESTADO") == "DENEGADA")


# ── A. VELOCIDAD / FRECUENCIA ─────────────────────────────────────────────────
print("\n[A] Velocidad / Frecuencia")

for periodo, alias in [("5m","N_TRX_5MIN"),("15m","N_TRX_15MIN"),
                       ("1h","N_TRX_1H"),("24h","N_TRX_24H")]:
    print(f"  {alias}...")
    plf_s = plf_ap.sort("fecha_hora")
    roll = (
        plf_s
        .rolling(index_column="fecha_hora", period=periodo, group_by="id_cliente")
        .agg(pl.len().alias(f"_c"))
    )
    plf_ap = plf_ap.with_row_index("_i")
    roll   = roll.with_row_index("_i")
    plf_ap = plf_ap.join(roll.select(["_i","_c"]), on="_i", how="left")
    plf_ap = plf_ap.with_columns(
        (pl.col("_c") - 1).clip(0, None).cast(pl.Int32).alias(alias)
    ).drop(["_i","_c"])

print("  GAP_MINUTOS...")
plf_ap = plf_ap.sort(["id_cliente","fecha_hora"])
plf_ap = plf_ap.with_columns(
    pl.col("fecha_hora").shift(1).over("id_cliente").alias("_prev")
)
plf_ap = plf_ap.with_columns(
    ((pl.col("fecha_hora") - pl.col("_prev")).dt.total_seconds() / 60).alias("GAP_MINUTOS")
).drop("_prev")

plf_ap = plf_ap.with_columns(
    (pl.col("N_TRX_15MIN") >= 2).cast(pl.Int32).alias("ES_RAFAGA")
)


# ── B. MONTO ──────────────────────────────────────────────────────────────────
print("\n[B] Monto y patrones")

for periodo, alias_acum in [("2h","MONTO_ACUM_2H"),("24h","MONTO_ACUM_24H")]:
    print(f"  {alias_acum}...")
    plf_s = plf_ap.sort("fecha_hora")
    roll_m = (
        plf_s
        .rolling(index_column="fecha_hora", period=periodo, group_by="id_cliente")
        .agg(pl.col("monto").sum().alias("_ma"))
    )
    plf_ap = plf_ap.with_row_index("_i")
    roll_m = roll_m.with_row_index("_i")
    plf_ap = plf_ap.join(roll_m.select(["_i","_ma"]), on="_i", how="left")
    plf_ap = plf_ap.with_columns(
        (pl.col("_ma") - pl.col("monto")).clip(0, None).alias(alias_acum)
    ).drop(["_i","_ma"])

print("  ZSCORE y RATIO_MONTO_AVG_CLI...")
plf_ap = plf_ap.with_columns([
    pl.col("monto").mean().over("id_cliente").alias("_mean"),
    pl.col("monto").std().over("id_cliente").alias("_std"),
])
plf_ap = plf_ap.with_columns([
    pl.when(pl.col("_std") > 0)
      .then((pl.col("monto") - pl.col("_mean")) / pl.col("_std"))
      .otherwise(0.0).alias("ZSCORE_MONTO_CLI"),
    pl.when(pl.col("_mean") > 0)
      .then(pl.col("monto") / pl.col("_mean"))
      .otherwise(1.0).alias("RATIO_MONTO_AVG_CLI"),
]).drop(["_mean","_std"])

if "saldo" in plf_ap.columns:
    plf_ap = plf_ap.with_columns(
        pl.when(pl.col("saldo") > 0)
          .then(pl.col("monto") / pl.col("saldo"))
          .otherwise(None).alias("RATIO_MONTO_SALDO")
    )

plf_ap = plf_ap.with_columns([
    ((pl.col("monto") % 50 == 0) & (pl.col("monto") >= 50)).cast(pl.Int32).alias("ES_MONTO_REDONDO"),
    (pl.col("monto") < 20).cast(pl.Int32).alias("ES_MONTO_BAJO"),
])


# ── C. COMPORTAMIENTO EN EL COMERCIO ──────────────────────────────────────────
print("\n[C] Comportamiento del cliente en el comercio")

plf_ap = plf_ap.with_columns(
    pl.lit(1).cum_sum().over("id_cliente").alias("_rank")
)
plf_ap = plf_ap.with_columns([
    (pl.col("_rank") == 1).cast(pl.Int32).alias("ES_PRIMERA_VEZ_COMERCIO"),
    (pl.col("_rank") - 1).cast(pl.Int32).alias("N_TRX_HISTORICAS_COMERCIO"),
]).drop("_rank")

plf_ap = plf_ap.with_columns(
    pl.col("fecha_hora").min().over("id_cliente").alias("_first")
)
plf_ap = plf_ap.with_columns(
    ((pl.col("fecha_hora") - pl.col("_first")).dt.total_seconds() / 86400)
    .alias("DIAS_DESDE_PRIMERA_COMPRA")
).drop("_first")


# ── D. CASCADA DE FRAUDE ──────────────────────────────────────────────────────
print("\n[D] Cascada de fraude")

plf_ap_s = plf_ap.sort("fecha_hora")
for periodo, alias in [("24h","HUBO_FRAUDE_PREVIO_24H"),("7d","HUBO_FRAUDE_PREVIO_7D")]:
    roll_f = (
        plf_ap_s
        .rolling(index_column="fecha_hora", period=periodo, group_by="id_cliente")
        .agg(pl.col("ES_FRAUDE_APROBADO").sum().alias("_sf"))
    )
    plf_ap = plf_ap.with_row_index("_i")
    roll_f = roll_f.with_row_index("_i")
    plf_ap = plf_ap.join(roll_f.select(["_i","_sf"]), on="_i", how="left")
    plf_ap = plf_ap.with_columns(
        ((pl.col("_sf") - pl.col("ES_FRAUDE_APROBADO")).clip(0, None) > 0)
        .cast(pl.Int32).alias(alias)
    ).drop(["_i","_sf"])

plf_ap = plf_ap.sort(["id_cliente","fecha_hora"])
plf_ap = plf_ap.with_columns(
    pl.col("ES_FRAUDE_APROBADO").shift(1).over("id_cliente").alias("_pf")
)
plf_ap = plf_ap.with_columns(
    pl.when(pl.col("_pf") == 1).then(1).otherwise(0).alias("PREV_FUE_FRAUDE")
).drop("_pf")

plf_aux = plf_ap.filter(pl.col("ES_FRAUDE_APROBADO") == 1).select(
    ["id_cliente","fecha_hora"]
).rename({"fecha_hora":"DT_F"}).sort(["id_cliente","DT_F"])

if len(plf_aux) > 0:
    plf_ap_ms = plf_ap.sort(["id_cliente","fecha_hora"])
    merged = plf_ap_ms.join_asof(
        plf_aux, left_on="fecha_hora", right_on="DT_F",
        by="id_cliente", strategy="backward"
    )
    plf_ap = merged.with_columns(
        ((pl.col("fecha_hora") - pl.col("DT_F")).dt.total_seconds() / 60)
        .alias("MIN_DESDE_ULTIMO_FRAUDE")
    ).drop("DT_F")
else:
    plf_ap = plf_ap.with_columns(pl.lit(None).cast(pl.Float64).alias("MIN_DESDE_ULTIMO_FRAUDE"))


# ── E. GEOGRÁFICAS / IP ───────────────────────────────────────────────────────
print("\n[E] Geográficas / IP")

if "pais" in plf_ap.columns:
    pais_top = (
        plf_ap.group_by(["id_cliente","pais"]).agg(pl.len().alias("_n"))
        .sort(["id_cliente","_n"], descending=[False,True])
        .group_by("id_cliente").first()
        .select(["id_cliente", pl.col("pais").alias("PAIS_HABITUAL")])
    )
    plf_ap = plf_ap.join(pais_top, on="id_cliente", how="left")
    plf_ap = plf_ap.with_columns(
        (pl.col("pais") != pl.col("PAIS_HABITUAL")).cast(pl.Int32).alias("PAIS_DISTINTO_HABITUAL")
    )
    plf_ap = plf_ap.sort(["id_cliente","fecha_hora"])
    plf_ap = plf_ap.with_columns(
        pl.col("pais").shift(1).over("id_cliente").alias("_pp")
    )
    plf_ap = plf_ap.with_columns(
        pl.when(pl.col("_pp").is_null()).then(0)
          .otherwise((pl.col("pais") != pl.col("_pp")).cast(pl.Int32))
          .alias("CAMBIO_PAIS_VS_PREV")
    ).drop("_pp")

    plf_ap_s = plf_ap.sort("fecha_hora")
    roll_p = (
        plf_ap_s
        .rolling(index_column="fecha_hora", period="24h", group_by="id_cliente")
        .agg(pl.col("pais").n_unique().alias("_np"))
    )
    plf_ap = plf_ap.with_row_index("_i")
    roll_p = roll_p.with_row_index("_i")
    plf_ap = plf_ap.join(roll_p.select(["_i","_np"]), on="_i", how="left")
    plf_ap = plf_ap.with_columns(
        pl.col("_np").cast(pl.Int32).alias("N_PAISES_DISTINTOS_24H")
    ).drop(["_i","_np"])

if "ip" in plf_ap.columns:
    plf_ap = plf_ap.with_columns(
        pl.lit(1).cum_sum().over(["id_cliente","ip"]).alias("_ri")
    )
    plf_ap = plf_ap.with_columns(
        (pl.col("_ri") == 1).cast(pl.Int32).alias("IP_NUEVA_CLIENTE")
    ).drop("_ri")

    plf_ap_ip = plf_ap.sort("fecha_hora")
    roll_ip = (
        plf_ap_ip
        .rolling(index_column="fecha_hora", period="24h", group_by="ip")
        .agg(pl.col("id_cliente").n_unique().alias("_nic"))
    )
    plf_ap = plf_ap.with_row_index("_i")
    roll_ip = roll_ip.with_row_index("_i")
    plf_ap = plf_ap.join(roll_ip.select(["_i","_nic"]), on="_i", how="left")
    plf_ap = plf_ap.with_columns(
        pl.col("_nic").cast(pl.Int32).alias("N_CLIENTES_MISMA_IP_24H")
    ).drop(["_i","_nic"])


# ── F. RECHAZOS / CVV ─────────────────────────────────────────────────────────
print("\n[F] Rechazos / CVV")

if len(plf_den) > 0 and "MOTIVO_RECH" in plf_den.columns:
    plf_den_cum = (
        plf_den.sort(["id_cliente","fecha_hora"])
        .with_columns(pl.lit(1).cum_sum().over("id_cliente").alias("CUM"))
        .select(["id_cliente","fecha_hora","CUM"])
    )
    plf_ap_r = plf_ap.sort("fecha_hora").with_row_index("_ir")
    c_now = plf_ap_r.select(["_ir","id_cliente","fecha_hora"]).join_asof(
        plf_den_cum.rename({"CUM":"CN"}), on="fecha_hora", by="id_cliente", strategy="backward"
    )
    c_24h = plf_ap_r.with_columns(
        (pl.col("fecha_hora") - pl.duration(hours=24)).alias("fh24")
    ).select(["_ir","id_cliente","fh24"]).rename({"fh24":"fecha_hora"}).join_asof(
        plf_den_cum.rename({"CUM":"C24"}), on="fecha_hora", by="id_cliente", strategy="backward"
    )
    rech = c_now.select(["_ir","CN"]).join(
        c_24h.select(["_ir","C24"]), on="_ir", how="left"
    ).with_columns(
        (pl.col("CN").fill_null(0) - pl.col("C24").fill_null(0))
        .clip(0, None).cast(pl.Int32).alias("N_RECHAZOS_24H")
    )
    plf_ap = plf_ap.with_row_index("_ir").join(
        rech.select(["_ir","N_RECHAZOS_24H"]), on="_ir", how="left"
    ).drop("_ir")

    plf_cvv = plf_den.filter(pl.col("MOTIVO_RECH") == "CVV_FAIL").sort(["id_cliente","fecha_hora"])
    if len(plf_cvv) > 0:
        plf_cvv_cum = plf_cvv.with_columns(
            pl.lit(1).cum_sum().over("id_cliente").alias("CC")
        ).select(["id_cliente","fecha_hora","CC"])
        plf_ap_c = plf_ap.sort("fecha_hora").with_row_index("_ic")
        cc_now = plf_ap_c.select(["_ic","id_cliente","fecha_hora"]).join_asof(
            plf_cvv_cum.rename({"CC":"CCN"}), on="fecha_hora", by="id_cliente", strategy="backward"
        )
        cc_24h = plf_ap_c.with_columns(
            (pl.col("fecha_hora") - pl.duration(hours=24)).alias("fh24")
        ).select(["_ic","id_cliente","fh24"]).rename({"fh24":"fecha_hora"}).join_asof(
            plf_cvv_cum.rename({"CC":"CC24"}), on="fecha_hora", by="id_cliente", strategy="backward"
        )
        cvv_j = cc_now.select(["_ic","CCN"]).join(
            cc_24h.select(["_ic","CC24"]), on="_ic", how="left"
        ).with_columns(
            (pl.col("CCN").fill_null(0) - pl.col("CC24").fill_null(0))
            .clip(0, None).cast(pl.Int32).alias("N_CVV_FAIL_24H")
        )
        plf_ap = plf_ap.with_row_index("_ic").join(
            cvv_j.select(["_ic","N_CVV_FAIL_24H"]), on="_ic", how="left"
        ).drop("_ic")
    else:
        plf_ap = plf_ap.with_columns(pl.lit(0).cast(pl.Int32).alias("N_CVV_FAIL_24H"))
else:
    plf_ap = plf_ap.with_columns([
        pl.lit(0).cast(pl.Int32).alias("N_RECHAZOS_24H"),
        pl.lit(0).cast(pl.Int32).alias("N_CVV_FAIL_24H"),
    ])

plf_ap = plf_ap.with_columns(
    (pl.col("N_CVV_FAIL_24H") > 0).cast(pl.Int32).alias("HUBO_CVV_FAIL_PREVIO")
)


# ─────────────────────────────────────────────────────────────────────────────
# CONVERTIR A PANDAS Y BUCKETS
# ─────────────────────────────────────────────────────────────────────────────
print("\nConvirtiendo a Pandas y calculando buckets...")
df_feat = plf_ap.to_pandas()

# Hora y franja
df_feat["HORA_NUM"] = pd.to_datetime(df_feat["fecha_hora"]).dt.hour

def franja(h):
    if h <= 5:  return "00-05 Madrugada"
    if h <= 11: return "06-11 Manana"
    if h <= 17: return "12-17 Tarde"
    if h <= 20: return "18-20 Noche"
    return "21-23 Noche Tardia"

df_feat["FRANJA_HORARIA"] = df_feat["HORA_NUM"].apply(franja)

# Buckets para tablas cruzadas
df_feat["BUCKET_N_TRX_5MIN"] = pd.cut(
    df_feat["N_TRX_5MIN"].clip(0,20),
    bins=[-0.001,0,1,2,3,5,20], labels=["0","1","2","3","4-5","6+"], include_lowest=True
)
df_feat["BUCKET_N_TRX_24H"] = pd.cut(
    df_feat["N_TRX_24H"].clip(0,50),
    bins=[-0.001,0,1,2,4,9,50], labels=["0","1","2","3-4","5-9","10+"], include_lowest=True
)
df_feat["BUCKET_GAP_MIN"] = pd.cut(
    df_feat["GAP_MINUTOS"].clip(0,1440),
    bins=[-0.001,1,5,15,60,360,1440],
    labels=["<1min","1-5min","5-15min","15-60min","1-6h",">6h"], include_lowest=True
)
df_feat["BUCKET_ZSCORE"] = pd.cut(
    df_feat["ZSCORE_MONTO_CLI"].clip(-3,3),
    bins=[-3,-2,-1,0,1,2,3],
    labels=["<-2SD","-2a-1SD","-1a0SD","0a1SD","1a2SD",">2SD"], include_lowest=True
)
df_feat["BUCKET_RECHAZOS"] = pd.cut(
    df_feat["N_RECHAZOS_24H"].clip(0,10),
    bins=[-0.001,0,1,2,3,10], labels=["0","1","2","3","4+"], include_lowest=True
)

# ── G. SCORE DE RIESGO ────────────────────────────────────────────────────────
print("\n[G] Score de riesgo compuesto")

flags_riesgo = [
    (df_feat["N_TRX_1H"] >= 3).astype(int),         # velocidad alta
    (df_feat["GAP_MINUTOS"] < 2).astype(int),         # muy rápido
    (df_feat.get("HUBO_FRAUDE_PREVIO_24H", 0)),        # fraude previo
    (df_feat.get("HUBO_CVV_FAIL_PREVIO", 0)),          # CVV fail previo
    df_feat.get("ES_MONTO_REDONDO", 0),               # monto redondo
    (df_feat["FRANJA_HORARIA"] == "00-05 Madrugada").astype(int),  # madrugada
]
df_feat["SCORE_RIESGO"] = sum(f.fillna(0).astype(int) for f in flags_riesgo)
df_feat["PERFIL_RIESGO"] = pd.cut(
    df_feat["SCORE_RIESGO"],
    bins=[-1,0,1,2,99],
    labels=["BAJO","MEDIO","ALTO","MUY_ALTO"]
)

print(f"\n  PERFIL_RIESGO:\n{df_feat['PERFIL_RIESGO'].value_counts().to_string()}")
print(f"\n  Features generadas: {len(df_feat):,} filas")


# ─────────────────────────────────────────────────────────────────────────────
# GUARDAR
# ─────────────────────────────────────────────────────────────────────────────
PARQUET_FEATURES.parent.mkdir(parents=True, exist_ok=True)
df_feat.to_parquet(PARQUET_FEATURES, index=False)
print(f"\n✅ Features guardadas en: {PARQUET_FEATURES}")
print(f"   {len(df_feat):,} filas × {df_feat.shape[1]} columnas")
