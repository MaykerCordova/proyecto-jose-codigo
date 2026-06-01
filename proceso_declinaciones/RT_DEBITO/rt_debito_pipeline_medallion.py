"""
==============================================================================
PIPELINE RT DEBITO - ARQUITECTURA MEDALLION (Bronze → Silver → Gold)
==============================================================================
Bronze: Data cruda tal cual se descarga (Excel), sin tocar
Silver: Todas las columnas procesadas y estandarizadas (~294 cols)
Gold:   Solo las columnas seleccionadas para Power BI (configurable)

Incluye:
  - Schema validator: alerta cambios de columnas
  - Schema evolution: columnas nuevas se agregan automaticamente
  - Bootstrap desde Excels mensuales + historico Parquet
  - Carga incremental diaria (1 Excel del monitor)

Autor: Mayker Cordova
Fecha: Abril 2026
==============================================================================
"""

import polars as pl
import sqlite3
from pathlib import Path
from datetime import datetime, date
import shutil
import warnings

warnings.filterwarnings("ignore")


# ============================================================================
# CONFIGURACIÓN CENTRAL
# ============================================================================

class Config:
    """Configuración centralizada del pipeline RT Débito."""

    # === RUTAS FUENTE (absolutas — datos originales) ===
    BASE_DIR = Path(r"C:\Users\s4930359\Data_Herramientas")

    # === RUTAS DE SALIDA (relativas a 10_proceso_declinaciones/) ===
    DATA_DIR     = Path(__file__).parent.parent / "data"
    BRONZE_DIR   = DATA_DIR / "bronze" / "rt_debito"
    SILVER_DIR   = DATA_DIR / "silver"
    GOLD_DIR     = DATA_DIR / "gold"
    METADATA_DIR = DATA_DIR / "metadata"

    # Archivos
    SILVER_PARQUET = SILVER_DIR / "rt_debito_silver.parquet"
    GOLD_PARQUET = GOLD_DIR / "rt_debito_gold.parquet"

    # === HISTORICOS (para bootstrap) ===
    HISTORICOS_DIR = BASE_DIR / "BBDD_Real_Time"  # <-- AJUSTAR
    HISTORICOS = [
        "debito_enero.xlsx",
        "debito_febrero.xlsx",
        "debito_marzo.xlsx",
        "debito_abril.xlsx",
    ]

    # Parquet historico anterior (2024-2025, 17 columnas)
    PARQUET_HISTORICO = SILVER_DIR / "rt_debito_consolidated.parquet"

    # =========================================================================
    # GOLD: Columnas que quieres en Power BI
    # =========================================================================
    # Para agregar una columna: ponla en la lista
    # Para quitar una columna: bórrala de la lista
    # El Silver siempre tiene TODAS las columnas, no se toca
    # =========================================================================
    GOLD_COLUMNS = [
        # --- 17 originales ---
        "USUARIO",
        "GENERO ALERTA",
        "ACF-MONTO DOLLAR",
        "ACF-FECHA TRX",
        "ACF-MONTO EN MONEDA LOCAL",
        "ACF-MCC +",
        "ACF-NOMBRE/LOCALIZACION COMERCIO",
        "ACF-PAIS ORIGEN 87519",
        "ACF-TARJETA REGISTRO 750",
        "ACF-INDICADOR DE FRAUDE",
        "ACF-BIN",
        "ACF-ENTRY MODE",
        "ACF-TVR",
        "Condiciones Cumplidas",
        "ACF_Fecha_TRX",
        "Anomes_TRX",
        "Dia_TRX",
        # --- 7 nuevas ---
        "ACF-ECI/UCAF",
        "CONDICIONES",
        "ACF-CODIGO CIO/AGENCIA/OFICINA ORIGEN",
        "CONDICION RT",
        "ACF-TIPO MSJ",
        "VAA-EVENTO DE COMPROMISO OTRA FUENTE",
        "ACF-COD RED COMERCIO",
    ]


# ============================================================================
# SCHEMA VALIDATOR
# ============================================================================

class SchemaValidator:
    """Valida cambios de schema antes de cada carga."""

    @staticmethod
    def validar(df_new: pl.DataFrame, nombre_archivo: str = "") -> bool:
        print(f"\n--- VALIDACION DE SCHEMA ---")

        if not Config.SILVER_PARQUET.exists():
            print(f"  No existe Silver previo. Primera carga.")
            print(f"  Columnas del archivo: {df_new.shape[1]}")
            return True

        df_existing = pl.read_parquet(Config.SILVER_PARQUET, n_rows=0)
        cols_existentes = set(df_existing.columns)
        cols_nuevas_set = set(df_new.columns)

        nuevas = cols_nuevas_set - cols_existentes
        faltantes = cols_existentes - cols_nuevas_set
        comunes = cols_existentes & cols_nuevas_set

        hay_cambios = False

        if nuevas:
            hay_cambios = True
            print(f"  COLUMNAS NUEVAS detectadas ({len(nuevas)}):")
            for col in sorted(nuevas):
                print(f"    + {col}")

        if faltantes:
            hay_cambios = True
            derivadas = {"ACF_Fecha_TRX", "Anomes_TRX", "Dia_TRX", "ACF-TVR", "Condiciones Cumplidas"}
            faltantes_reales = faltantes - derivadas
            if faltantes_reales:
                print(f"  COLUMNAS FALTANTES ({len(faltantes_reales)}):")
                for col in sorted(faltantes_reales):
                    print(f"    - {col}")

        if not hay_cambios:
            print(f"  Schema OK - sin cambios ({len(comunes)} columnas)")

        print(f"  Archivo: {nombre_archivo}")
        print(f"  Columnas archivo: {df_new.shape[1]} | Silver: {len(cols_existentes)}")
        return True


# ============================================================================
# UTILIDADES
# ============================================================================

def crear_estructura_directorios():
    for d in [Config.BRONZE_DIR, Config.SILVER_DIR, Config.GOLD_DIR, Config.METADATA_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    print("Estructura de directorios verificada.")


def log_ingestion(metadata: dict):
    pass  # Desactivado


# ============================================================================
# EXTRACTOR
# ============================================================================

class RTDebitoExtractor:
    """Lee archivos de RT Debito (Excel diario o mensual)."""

    @staticmethod
    def guardar_en_bronze(excel_path: str, fecha_descarga: str = None):
        if fecha_descarga is None:
            fecha_descarga = date.today().isoformat()
        year, month, day = fecha_descarga.split("-")
        bronze_folder = Config.BRONZE_DIR / year / month / day
        bronze_folder.mkdir(parents=True, exist_ok=True)
        filename = Path(excel_path).name
        shutil.copy2(excel_path, bronze_folder / filename)
        print(f"  Bronze: Archivo guardado en {bronze_folder}")
        return bronze_folder

    @staticmethod
    def leer_excel(excel_path: str, skip_rows: int = 4) -> pl.DataFrame:
        try:
            df = pl.read_excel(excel_path, read_options={"skip_rows": skip_rows})
        except Exception:
            print(f"  Reintentando con Pandas...")
            import pandas as pd
            df = pl.from_pandas(pd.read_excel(excel_path, skiprows=skip_rows))
        print(f"  {Path(excel_path).name}: {df.shape[0]:,} filas x {df.shape[1]} columnas")
        return df


# ============================================================================
# TRANSFORMER
# ============================================================================

class RTDebitoTransformer:
    """Transforma datos de RT Debito para Silver y Gold."""

    @staticmethod
    def transformar_mensual(df: pl.DataFrame) -> pl.DataFrame:
        """
        Transforma Excel mensual (294 cols) al Silver.
        Guarda TODAS las columnas, solo estandariza tipos y parsea fecha.
        """
        print("\n--- TRANSFORMACION SILVER (MENSUAL) ---")

        # Parsear fecha ACF-FECHA TRX (formato YYYYMMDD, todo junto)
        if "ACF-FECHA TRX" in df.columns:
            if df["ACF-FECHA TRX"].dtype in [pl.Date, pl.Datetime]:
                df = df.with_columns(
                    pl.col("ACF-FECHA TRX").cast(pl.Date).alias("ACF_Fecha_TRX")
                )
            else:
                df = df.with_columns(
                    pl.col("ACF-FECHA TRX")
                    .cast(pl.Utf8)
                    .str.strip_chars()
                    .str.replace_all(r"\.0$", "")
                    .alias("_fecha_raw")
                )

                df = df.with_columns(
                    pl.when(
                        (pl.col("_fecha_raw") == "0")
                        | (pl.col("_fecha_raw") == "")
                        | (pl.col("_fecha_raw") == "None")
                        | (pl.col("_fecha_raw").is_null())
                    )
                    .then(pl.lit(None).cast(pl.Utf8))
                    .otherwise(pl.col("_fecha_raw"))
                    .alias("_fecha_clean")
                )

                df = df.with_columns(
                    pl.when(pl.col("_fecha_clean").is_null())
                    .then(pl.lit(None).cast(pl.Date))
                    .when(pl.col("_fecha_clean").str.contains("/"))
                    .then(pl.col("_fecha_clean").str.to_date("%Y/%m/%d", strict=False))
                    .otherwise(pl.col("_fecha_clean").str.to_date("%Y%m%d", strict=False))
                    .alias("ACF_Fecha_TRX")
                )

                df = df.drop(["_fecha_raw", "_fecha_clean"])

        # Derivar Anomes_TRX y Dia_TRX
        if "ACF_Fecha_TRX" in df.columns:
            df = df.with_columns([
                pl.when(pl.col("ACF_Fecha_TRX").is_not_null())
                .then(
                    pl.col("ACF_Fecha_TRX").dt.year().cast(pl.Utf8)
                    + pl.col("ACF_Fecha_TRX").dt.month().cast(pl.Utf8).str.pad_start(2, "0")
                )
                .otherwise(pl.lit(None).cast(pl.Utf8))
                .alias("Anomes_TRX"),

                pl.when(pl.col("ACF_Fecha_TRX").is_not_null())
                .then(pl.col("ACF_Fecha_TRX").dt.day().cast(pl.Utf8).str.pad_start(2, "0"))
                .otherwise(pl.lit(None).cast(pl.Utf8))
                .alias("Dia_TRX"),
            ])

        # Derivar ACF-TVR y Condiciones Cumplidas desde CONDICION RT
        if "CONDICION RT" in df.columns:
            df = df.with_columns([
                pl.col("CONDICION RT").cast(pl.Utf8).str.slice(0, 4).alias("ACF-TVR"),
                pl.col("CONDICION RT").cast(pl.Utf8).alias("Condiciones Cumplidas"),
            ])

        # Tipar columnas numericas a Float64
        COLUMNAS_NUMERICAS = {"ACF-MONTO DOLLAR", "ACF-MONTO EN MONEDA LOCAL", "USUARIO"}
        for col in df.columns:
            if col in COLUMNAS_NUMERICAS:
                df = df.with_columns(pl.col(col).cast(pl.Float64, strict=False).alias(col))
            elif col != "ACF_Fecha_TRX" and df[col].dtype != pl.Utf8:
                df = df.with_columns(pl.col(col).cast(pl.Utf8, strict=False).alias(col))

        total = df.shape[0]
        if "ACF_Fecha_TRX" in df.columns:
            nulls = df["ACF_Fecha_TRX"].null_count()
            parsed = total - nulls
            print(f"  Fechas parseadas: {parsed:,} de {total:,} ({nulls:,} nulls)")
            if parsed > 0:
                print(f"  Rango: {df['ACF_Fecha_TRX'].drop_nulls().min()} a {df['ACF_Fecha_TRX'].drop_nulls().max()}")

        print(f"  Schema final: {df.shape[1]} columnas, {df.shape[0]:,} filas")
        return df

    @staticmethod
    def transformar_diario(df: pl.DataFrame) -> pl.DataFrame:
        """
        Transforma Excel diario (294 cols) al Silver.
        Mismo proceso que mensual.
        """
        print("\n--- TRANSFORMACION SILVER (DIARIO) ---")
        return RTDebitoTransformer.transformar_mensual(df)

    # Filtros de negocio aplicados al Gold
    BIN6_EXCLUIDOS = {"427158", "200100"}   # BINs que generan registros duplicados o de prueba
    MCC_EXCLUIDOS  = {"4829", "6012", "6010"}  # MCCs fuera del scope del reporte

    @staticmethod
    def generar_gold(df_silver: pl.DataFrame) -> pl.DataFrame:
        """
        Genera el Gold seleccionando solo las columnas configuradas
        y aplicando los filtros de negocio propios de RT Débito.
        Las columnas que no existen en Silver se ignoran.
        """
        cols_disponibles = [c for c in Config.GOLD_COLUMNS if c in df_silver.columns]
        cols_faltantes = [c for c in Config.GOLD_COLUMNS if c not in df_silver.columns]

        if cols_faltantes:
            print(f"  Gold: {len(cols_faltantes)} columnas no disponibles en Silver: {cols_faltantes}")

        df_gold = df_silver.select(cols_disponibles)

        # Filtrar BINs excluidos (primeros 6 dígitos, limpiando posible .0 de Excel)
        if "ACF-BIN" in df_gold.columns:
            bin6 = pl.col("ACF-BIN").cast(pl.Utf8).str.replace(r"\.0$", "").str.slice(0, 6)
            df_gold = df_gold.filter(~bin6.is_in(RTDebitoTransformer.BIN6_EXCLUIDOS))

        # Filtrar MCCs excluidos (limpiando posible .0 de Excel)
        if "ACF-MCC +" in df_gold.columns:
            mcc = pl.col("ACF-MCC +").cast(pl.Utf8).str.replace(r"\.0$", "")
            df_gold = df_gold.filter(~mcc.is_in(RTDebitoTransformer.MCC_EXCLUIDOS))

        print(f"  Gold generado: {df_gold.shape[0]:,} filas x {df_gold.shape[1]} columnas")
        return df_gold


# ============================================================================
# LOADER
# ============================================================================

class SilverLoader:
    """Persistencia Silver y Gold."""

    @staticmethod
    def bootstrap_completo() -> pl.DataFrame:
        """
        Bootstrap completo:
        1. Lee los 4 Excels mensuales (Ene-Abr 2026, ~294 cols) → Silver
        2. Lee el Parquet historico (2024-2025, 17 cols)
        3. Une todo con concat diagonal → Gold
        """
        print("\n--- BOOTSTRAP COMPLETO ---")

        # === PASO 1: Leer Excels mensuales ===
        dfs_mensuales = []
        for archivo in Config.HISTORICOS:
            ruta = Config.HISTORICOS_DIR / archivo
            if not ruta.exists():
                print(f"  WARN: {archivo} no encontrado, saltando...")
                continue
            df = RTDebitoExtractor.leer_excel(str(ruta))
            df = RTDebitoTransformer.transformar_mensual(df)
            dfs_mensuales.append(df)

        if not dfs_mensuales:
            print("  ERROR: No se encontraron archivos historicos.")
            return pl.DataFrame()

        df_silver = pl.concat(dfs_mensuales, how="diagonal")
        print(f"\n  Mensuales unificados: {df_silver.shape[0]:,} filas x {df_silver.shape[1]} columnas")

        # Guardar Silver
        Config.SILVER_DIR.mkdir(parents=True, exist_ok=True)
        df_silver.write_parquet(Config.SILVER_PARQUET, compression="zstd")
        size_mb = Config.SILVER_PARQUET.stat().st_size / (1024 * 1024)
        print(f"  Silver creado: {Config.SILVER_PARQUET} | {size_mb:.1f} MB")

        # === PASO 2: Unir con historico para Gold ===
        print("\n--- GENERANDO GOLD (historico + Silver) ---")

        if Config.PARQUET_HISTORICO.exists():
            df_historico = pl.read_parquet(Config.PARQUET_HISTORICO)
            print(f"  Parquet historico: {df_historico.shape[0]:,} filas x {df_historico.shape[1]} columnas")

            # Seleccionar columnas Gold del Silver
            df_silver_gold = RTDebitoTransformer.generar_gold(df_silver)

            # Seleccionar columnas Gold del historico (las que existan)
            cols_hist = [c for c in Config.GOLD_COLUMNS if c in df_historico.columns]
            df_historico_gold = df_historico.select(cols_hist)

            # Unir con concat diagonal (columnas nuevas quedan null en historico)
            df_gold = pl.concat([df_historico_gold, df_silver_gold], how="diagonal")
            print(f"  Gold unificado: {df_gold.shape[0]:,} filas x {df_gold.shape[1]} columnas")
        else:
            print(f"  No se encontro Parquet historico. Gold solo con mensuales.")
            df_gold = RTDebitoTransformer.generar_gold(df_silver)

        # Guardar Gold
        Config.GOLD_DIR.mkdir(parents=True, exist_ok=True)
        df_gold.write_parquet(Config.GOLD_PARQUET, compression="zstd")
        print(f"  Gold creado: {Config.GOLD_PARQUET}")

        return df_silver

    @staticmethod
    def append_incremental(df_new: pl.DataFrame) -> dict:
        """Append al Silver + regenerar Gold."""
        print("\n--- APPEND INCREMENTAL ---")
        metrics = {"rows_read": df_new.shape[0], "rows_new": df_new.shape[0]}

        if not Config.SILVER_PARQUET.exists():
            print("  No existe Silver. Creando desde cero...")
            Config.SILVER_DIR.mkdir(parents=True, exist_ok=True)
            df_new.write_parquet(Config.SILVER_PARQUET, compression="zstd")

            df_gold = RTDebitoTransformer.generar_gold(df_new)
            Config.GOLD_DIR.mkdir(parents=True, exist_ok=True)
            df_gold.write_parquet(Config.GOLD_PARQUET, compression="zstd")
            return metrics

        df_existing = pl.read_parquet(Config.SILVER_PARQUET)
        print(f"  Silver existente: {df_existing.shape[0]:,} filas")

        # Schema evolution
        for col in df_new.columns:
            if col not in df_existing.columns:
                print(f"  Schema evolution: agregando '{col}' al historico")
                df_existing = df_existing.with_columns(
                    pl.lit(None).cast(df_new[col].dtype).alias(col)
                )

        for col in df_existing.columns:
            if col not in df_new.columns:
                df_new = df_new.with_columns(
                    pl.lit(None).cast(df_existing[col].dtype).alias(col)
                )

        # Asegurar mismo orden y tipos
        df_new = df_new.select(df_existing.columns)
        for col in df_existing.columns:
            if col in df_new.columns and df_new[col].dtype != df_existing[col].dtype:
                try:
                    df_new = df_new.with_columns(pl.col(col).cast(df_existing[col].dtype, strict=False).alias(col))
                except Exception:
                    df_new = df_new.with_columns(pl.col(col).cast(pl.Utf8, strict=False).alias(col))
                    df_existing = df_existing.with_columns(pl.col(col).cast(pl.Utf8, strict=False).alias(col))

        # Append
        df_final = pl.concat([df_existing, df_new], how="diagonal")

        # Backup Silver
        backup_path = Config.SILVER_DIR / f"rt_debito_silver_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
        shutil.copy2(Config.SILVER_PARQUET, backup_path)
        print(f"  Backup: {backup_path.name}")

        df_final.write_parquet(Config.SILVER_PARQUET, compression="zstd")
        size_mb = Config.SILVER_PARQUET.stat().st_size / (1024 * 1024)
        print(f"  Silver actualizado: {df_final.shape[0]:,} filas | {size_mb:.1f} MB")

        # Regenerar Gold completo (historico + silver actualizado)
        print("\n--- REGENERANDO GOLD ---")
        if Config.PARQUET_HISTORICO.exists():
            df_historico = pl.read_parquet(Config.PARQUET_HISTORICO)
            df_silver_gold = RTDebitoTransformer.generar_gold(df_final)
            cols_hist = [c for c in Config.GOLD_COLUMNS if c in df_historico.columns]
            df_historico_gold = df_historico.select(cols_hist)
            df_gold = pl.concat([df_historico_gold, df_silver_gold], how="diagonal")
        else:
            df_gold = RTDebitoTransformer.generar_gold(df_final)

        df_gold.write_parquet(Config.GOLD_PARQUET, compression="zstd")
        print(f"  Gold regenerado: {df_gold.shape[0]:,} filas x {df_gold.shape[1]} columnas")

        return metrics


# ============================================================================
# ORQUESTADOR
# ============================================================================

def run_bootstrap():
    """
    BOOTSTRAP: Une Excels mensuales (2026) + historico (2024-2025) → Silver + Gold.
    Ejecutar UNA SOLA VEZ.

    Uso:
        from rt_debito_pipeline_medallion import run_bootstrap
        run_bootstrap()
    """
    print("=" * 60)
    print("BOOTSTRAP: Historicos -> Silver -> Gold (RT DEBITO)")
    print("=" * 60)

    start = datetime.now()
    crear_estructura_directorios()
    df_silver = SilverLoader.bootstrap_completo()
    duration = (datetime.now() - start).total_seconds()

    print(f"\nBootstrap completado en {duration:.1f} segundos.")
    return df_silver


def run_daily(excel_path: str, fecha_descarga: str = None):
    """
    CARGA DIARIA: Excel del monitor → Bronze → Silver → Gold.

    Uso:
        from rt_debito_pipeline_medallion import run_daily
        run_daily(
            excel_path=r"C:\\Downloads\\journal_20260427.xlsx",
            fecha_descarga="2026-04-27"
        )
    """
    print("=" * 60)
    print("CARGA INCREMENTAL DIARIA (RT DEBITO)")
    print("=" * 60)

    start = datetime.now()
    crear_estructura_directorios()

    # 1. Bronze
    print("\n1. BRONZE: Guardando archivo original...")
    RTDebitoExtractor.guardar_en_bronze(excel_path, fecha_descarga)

    # 2. Extraccion
    print("\n2. EXTRACCION: Leyendo Excel...")
    df_raw = RTDebitoExtractor.leer_excel(excel_path)

    # 3. Validacion de schema
    SchemaValidator.validar(df_raw, f"diario_{fecha_descarga}")

    # 4. Transformacion
    print("\n3. TRANSFORMACION:")
    df_transformed = RTDebitoTransformer.transformar_diario(df_raw)

    # 5. Carga
    print("\n4. CARGA:")
    metrics = SilverLoader.append_incremental(df_transformed)

    duration = (datetime.now() - start).total_seconds()

    print(f"\n{'=' * 60}")
    print(f"RESUMEN")
    print(f"{'=' * 60}")
    print(f"  Filas leidas:     {metrics['rows_read']:,}")
    print(f"  Nuevas:           {metrics['rows_new']:,}")
    print(f"  Duracion:         {duration:.1f} seg")
    print(f"{'=' * 60}")


def regenerar_gold():
    """
    Regenera el Gold desde Silver + historico sin modificar Silver.
    Usar cuando agregas/quitas columnas del GOLD_COLUMNS.

    Uso:
        from rt_debito_pipeline_medallion import regenerar_gold
        regenerar_gold()
    """
    print("=" * 60)
    print("REGENERANDO GOLD DESDE SILVER + HISTORICO")
    print("=" * 60)

    df_silver = pl.read_parquet(Config.SILVER_PARQUET)
    print(f"Silver: {df_silver.shape[0]:,} filas x {df_silver.shape[1]} columnas")

    if Config.PARQUET_HISTORICO.exists():
        df_historico = pl.read_parquet(Config.PARQUET_HISTORICO)
        print(f"Historico: {df_historico.shape[0]:,} filas x {df_historico.shape[1]} columnas")
        df_silver_gold = RTDebitoTransformer.generar_gold(df_silver)
        cols_hist = [c for c in Config.GOLD_COLUMNS if c in df_historico.columns]
        df_historico_gold = df_historico.select(cols_hist)
        df_gold = pl.concat([df_historico_gold, df_silver_gold], how="diagonal")
    else:
        df_gold = RTDebitoTransformer.generar_gold(df_silver)

    Config.GOLD_DIR.mkdir(parents=True, exist_ok=True)
    df_gold.write_parquet(Config.GOLD_PARQUET, compression="zstd")

    print(f"Gold regenerado: {Config.GOLD_PARQUET}")
    print(f"  {df_gold.shape[0]:,} filas x {df_gold.shape[1]} columnas")


if __name__ == "__main__":
    print("Pipeline RT Debito Medallion listo.")
    print("  run_bootstrap()    - Primera vez: unir historicos + mensuales")
    print("  run_daily(...)     - Carga diaria: Excel del monitor")
    print("  regenerar_gold()   - Actualizar Gold sin tocar Silver")
