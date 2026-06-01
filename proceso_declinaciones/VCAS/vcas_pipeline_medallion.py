"""
==============================================================================
PIPELINE VCAS - ARQUITECTURA MEDALLION (Bronze → Silver → Gold)
==============================================================================
Bronze: Excels originales (Consolidado_*.xlsx), sin tocar
Silver: Caché Parquet por archivo (solo regenera si el Excel cambió)
Gold:   Consolidado final filtrado y listo para Power BI

Flujo:
  1. Descubrir todos los Consolidado_*.xlsx en BASE_DIR
  2. Por cada Excel: si cambió → leer → normalizar → guardar caché Silver
  3. Leer todos los cachés Silver con scan_parquet (lazy)
  4. Concat + reordenar columnas
  5. Filtrar: solo registros en FILTROS_CONCARESULTADO (default: "Rejected")
  6. collect(streaming=True) → escribir Gold Parquet

Autor: Mayker Cordova
Fecha: Abril 2026
==============================================================================
"""

import re
import time
import warnings
from pathlib import Path

import polars as pl

warnings.filterwarnings("ignore")


# ============================================================================
# CONFIGURACIÓN CENTRAL
# ============================================================================

class Config:
    """Configuración centralizada del pipeline VCAS."""

    # === RUTAS BASE ===
    BASE_DIR = Path(r"C:\Users\s4930359\OneDrive - The Bank of Nova Scotia\Seguimiento_Consolidado_Herramientas\VCAS_unitario")

    # Estructura Medallion
    BRONZE_DIR = BASE_DIR                                        # Excels fuente (OneDrive)
    SILVER_DIR = BASE_DIR / "_cache_vcas_parquet"               # caché junto a los Excels
    GOLD_DIR   = Path(__file__).parent.parent / "data" / "gold" # salida en 10_proceso_declinaciones/data/gold/

    # Archivos de salida
    GOLD_PARQUET = GOLD_DIR / "vcas_gold.parquet"

    # Hoja del Excel
    SHEET_NAME = "Datos"

    # Columnas a leer del Excel (las que nos interesan para el análisis)
    COLUMNS = [
        "Fecha",
        "Monto USD",
        "BIN",
        "Comercio",
        "Merchant Country",
        "Reglas CONCARESULTADO",
        "Score",
        "Authentication Type",
        "Authentication Status",
        "ECI",
        "IP Address",
        "IP Country",
        "Tipo de Regla",
        "Regla",
        "Merchant Category Code (MCC)",
        "Calificacion",
        "Concatenar",
        "Tarjeta",
        "DS Transaction ID",
    ]

    # Orden preferente de columnas en el Gold (el resto va al final)
    PREFERRED_ORDER = [
        "Fecha",
        "BIN",
        "Monto USD",
        "Comercio",
        "Merchant Country",
        "Reglas CONCARESULTADO",
        "origen",
        "periodo",
    ]

    # =========================================================================
    # FILTRO DE NEGOCIO
    # =========================================================================
    # Valores de "Reglas CONCARESULTADO" que se incluyen en el Gold.
    # Opciones disponibles: "Rejected", "Challenge", "Fail With Feedback"
    # Para incluir todo: ["Rejected", "Challenge", "Fail With Feedback"]
    # =========================================================================
    FILTROS_CONCARESULTADO = ["Rejected"]

    # =========================================================================
    # GOLD: Columnas que quieres en Power BI
    # =========================================================================
    GOLD_COLUMNS = [
        "Fecha",
        "Monto USD",
        "BIN",
        "Comercio",
        "Merchant Country",
        "Reglas CONCARESULTADO",
        "Score",
        "Authentication Type",
        "Authentication Status",
        "ECI",
        "Tipo de Regla",
        "Regla",
        "Merchant Category Code (MCC)",
        "Calificacion",
        "Tarjeta",
        "origen",
        "periodo",
    ]


# ============================================================================
# UTILIDADES
# ============================================================================

def periodo_from_filename(path_like: Path) -> str:
    """Extrae 'YYYYMM' (ej: 202501) del nombre del archivo."""
    m = re.search(r"(\d{6})", path_like.stem)
    return m.group(1) if m else ""


def needs_refresh(excel_path: Path, cache_path: Path) -> bool:
    """True si la caché no existe o el Excel es más nuevo que su Parquet."""
    if not cache_path.exists():
        return True
    return excel_path.stat().st_mtime > cache_path.stat().st_mtime


# ============================================================================
# TRANSFORMER: Normalización y metadatos
# ============================================================================

class VCASTransformer:
    """Transforma los datos crudos de VCAS al schema Silver/Gold."""

    @staticmethod
    def leer_excel(excel_path: Path) -> pl.DataFrame:
        """Lee el Excel y selecciona solo las columnas configuradas."""
        try:
            df = pl.read_excel(
                excel_path,
                sheet_name=Config.SHEET_NAME,
            ).select([c for c in Config.COLUMNS if c in pl.read_excel(
                excel_path, sheet_name=Config.SHEET_NAME, n_rows=0
            ).columns])
        except Exception:
            # Fallback: leer todas y filtrar después
            import pandas as pd
            df_pd = pd.read_excel(excel_path, sheet_name=Config.SHEET_NAME)
            df = pl.from_pandas(df_pd)
            cols_disponibles = [c for c in Config.COLUMNS if c in df.columns]
            df = df.select(cols_disponibles)

        print(f"    Excel leído: {df.shape[0]:,} filas x {df.shape[1]} columnas")
        return df

    @staticmethod
    def normalizar(df: pl.DataFrame, periodo: str) -> pl.DataFrame:
        """Agrega metadatos y normaliza columnas de texto."""
        cols_texto = ["BIN", "Comercio", "Merchant Country", "Tarjeta"]
        exprs = [
            pl.lit("VCAS").alias("origen"),
            pl.lit(periodo).alias("periodo"),
        ]
        for col in cols_texto:
            if col in df.columns:
                exprs.append(
                    pl.col(col).cast(pl.Utf8).str.strip_chars().alias(col)
                )

        return df.with_columns(exprs)

    @staticmethod
    def generar_gold(df: pl.LazyFrame) -> pl.LazyFrame:
        """
        Aplica filtro de negocio y selecciona columnas Gold.

        Filtro: solo registros cuyo "Reglas CONCARESULTADO" esté en
        FILTROS_CONCARESULTADO (por defecto: ["Rejected"]).
        """
        # Filtrar por resultado VCAS
        if "Reglas CONCARESULTADO" in df.collect_schema():
            df = df.filter(
                pl.col("Reglas CONCARESULTADO").is_in(Config.FILTROS_CONCARESULTADO)
            )

        # Seleccionar columnas Gold
        schema = df.collect_schema()
        cols_disponibles = [c for c in Config.GOLD_COLUMNS if c in schema]
        cols_faltantes   = [c for c in Config.GOLD_COLUMNS if c not in schema]

        if cols_faltantes:
            print(f"  Gold: columnas no disponibles en Silver: {cols_faltantes}")

        return df.select(cols_disponibles)


# ============================================================================
# ORQUESTADOR
# ============================================================================

def run():
    """
    Pipeline completo VCAS: Bronze → Silver (caché) → Gold.

    Uso:
        from vcas_pipeline_medallion import run
        run()
    """
    print("=" * 60)
    print("PIPELINE VCAS - ARQUITECTURA MEDALLION")
    print("=" * 60)
    t0 = time.time()

    # Crear directorios
    Config.SILVER_DIR.mkdir(exist_ok=True)
    Config.GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Descubrir Excels
    excel_files = sorted(Config.BRONZE_DIR.glob("Consolidado_*.xlsx"))
    if not excel_files:
        raise FileNotFoundError(
            f"No se encontraron archivos 'Consolidado_*.xlsx' en {Config.BRONZE_DIR}"
        )
    print(f"\n1. BRONZE: {len(excel_files)} archivos encontrados")

    # 2. Construir/usar caché Silver por archivo
    print("\n2. SILVER: Procesando cachés...")
    for xls in excel_files:
        periodo    = periodo_from_filename(xls)
        cache_path = Config.SILVER_DIR / f"{xls.stem}.parquet"

        if needs_refresh(xls, cache_path):
            print(f"  Actualizando: {xls.name} → período {periodo}")
            df = VCASTransformer.leer_excel(xls)
            df = VCASTransformer.normalizar(df, periodo)
            df.write_parquet(cache_path, compression="zstd")
            print(f"  Caché guardado: {cache_path.name}")
        else:
            print(f"  Caché OK: {cache_path.name} (no se regenera)")

    # 3. Leer todos los cachés con scan_parquet (lazy)
    print("\n3. CONSOLIDANDO cachés Silver...")
    cache_files = sorted(Config.SILVER_DIR.glob("Consolidado_*.parquet"))
    if not cache_files:
        raise RuntimeError(f"No se encontraron cachés en {Config.SILVER_DIR}")

    lazy_frames = [pl.scan_parquet(pq) for pq in cache_files]
    lf_full = pl.concat(lazy_frames, how="vertical_relaxed")

    # 4. Reordenar columnas (preferidas primero)
    schema  = lf_full.collect_schema()
    prefer  = [c for c in Config.PREFERRED_ORDER if c in schema]
    others  = [c for c in schema if c not in prefer]
    lf_full = lf_full.select(prefer + others)

    # 5. Generar Gold (filtro + selección de columnas)
    print("\n4. GENERANDO GOLD...")
    print(f"   Filtro activo: Reglas CONCARESULTADO in {Config.FILTROS_CONCARESULTADO}")
    lf_gold = VCASTransformer.generar_gold(lf_full)

    # 6. Colectar y guardar
    df_final = lf_gold.collect(streaming=True)
    df_final.write_parquet(Config.GOLD_PARQUET, compression="zstd")

    print(f"\n{'=' * 60}")
    print(f"RESUMEN")
    print(f"{'=' * 60}")
    print(f"  Excels procesados : {len(excel_files)}")
    print(f"  Filas Gold        : {df_final.shape[0]:,}")
    print(f"  Columnas Gold     : {df_final.shape[1]}")
    print(f"  Fecha máxima      : {df_final['Fecha'].max()}")
    print(f"  Gold guardado en  : {Config.GOLD_PARQUET}")
    print(f"  Tiempo total      : {time.time() - t0:.2f}s")
    print(f"{'=' * 60}")

    return df_final


def regenerar_gold():
    """
    Regenera el Gold desde los cachés Silver existentes sin releer Excels.
    Usar cuando cambias FILTROS_CONCARESULTADO o GOLD_COLUMNS.

    Uso:
        from vcas_pipeline_medallion import regenerar_gold
        regenerar_gold()
    """
    print("REGENERANDO GOLD DESDE SILVER (sin releer Excels)")

    cache_files = sorted(Config.SILVER_DIR.glob("Consolidado_*.parquet"))
    if not cache_files:
        raise RuntimeError(f"No hay cachés en {Config.SILVER_DIR}. Ejecuta run() primero.")

    lazy_frames = [pl.scan_parquet(pq) for pq in cache_files]
    lf_full = pl.concat(lazy_frames, how="vertical_relaxed")

    schema = lf_full.collect_schema()
    prefer = [c for c in Config.PREFERRED_ORDER if c in schema]
    others = [c for c in schema if c not in prefer]
    lf_full = lf_full.select(prefer + others)

    lf_gold  = VCASTransformer.generar_gold(lf_full)
    df_final = lf_gold.collect(streaming=True)

    Config.GOLD_DIR.mkdir(parents=True, exist_ok=True)
    df_final.write_parquet(Config.GOLD_PARQUET, compression="zstd")

    print(f"  Gold regenerado: {df_final.shape[0]:,} filas → {Config.GOLD_PARQUET}")
    return df_final


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    """
    EJECUCIÓN NORMAL (diaria):
    ====================================
    Simplemente corre el script:
        python vcas_pipeline_medallion.py

    O desde otro script/notebook:
        from vcas_pipeline_medallion import run
        run()


    REGENERAR GOLD SIN RELEER EXCELS:
    ====================================
    Útil cuando cambias FILTROS_CONCARESULTADO o GOLD_COLUMNS:
        from vcas_pipeline_medallion import regenerar_gold
        regenerar_gold()
    """
    run()
