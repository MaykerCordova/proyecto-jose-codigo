"""
==============================================================================
PIPELINE RT CRÉDITO - ARQUITECTURA MEDALLION (Bronze → Silver → Gold)
==============================================================================
Bronze: Data cruda tal cual se descarga (Excel), sin tocar
Silver: Todas las columnas procesadas y estandarizadas
Gold:   Solo las columnas seleccionadas para Power BI (configurable)

Incluye:
  - Schema validator: alerta cambios de columnas antes de cada carga
  - Schema evolution: columnas nuevas se agregan, faltantes con null
  - Bootstrap desde Access (consolidado RT TC UBA)
  - Carga incremental diaria (1 Excel .xlsx con skiprows=4)

Input diario: 1 archivo Excel (.xlsx) con skiprows=4
Columnas Excel: ACF-Condición, ACF-Fecha TRX, ACF-Hora TRX, ACF-Monto Único,
                ACF-Monto TRX, ACF-MCC, ACF-Código Comercio, ACF-Nombre Comercio,
                ACF-BIN, ACF-Tarjeta SHA256

Autor: Mayker Cordova
Fecha: Abril 2026
==============================================================================
"""

import hashlib
import shutil
import sqlite3
import warnings
from datetime import date, datetime
from pathlib import Path

import polars as pl

warnings.filterwarnings("ignore")


# ============================================================================
# CONFIGURACIÓN CENTRAL
# ============================================================================

class Config:
    """Configuración centralizada del pipeline RT Crédito."""

    # === RUTAS BASE ===
    BASE_DIR = Path(r"C:\Users\s4930359\Data_Herramientas")

    # Estructura Medallion
    BRONZE_DIR   = BASE_DIR / "data" / "bronze" / "rt_credito"
    SILVER_DIR   = BASE_DIR / "data" / "silver"
    GOLD_DIR     = BASE_DIR / "data" / "gold"
    METADATA_DIR = BASE_DIR / "data" / "metadata"

    # Archivos
    SILVER_PARQUET = SILVER_DIR / "rt_credito_consolidated.parquet"
    GOLD_PARQUET   = GOLD_DIR   / "rt_credito_gold.parquet"
    METADATA_DB    = METADATA_DIR / "ingestion_log.db"

    # === ACCESS (consolidado - solo para bootstrap) ===
    ACCESS_PATH  = BASE_DIR / "BBDD_Real_Time_TC_UBA.accdb"
    ACCESS_TABLE = "BBDD_Real_Time_TC_UBA"

    # === SCHEMA: Mapeo Excel (ACF-) → Silver (RT-) ===
    COLUMN_MAP = {
        "ACF-Fecha TRX":       "RT-Fecha TRX",
        "ACF-Monto Único":     "RT-Monto TRX",
        "ACF-Monto Unico":     "RT-Monto TRX",       # sin tilde (fallback)
        "ACF-MCC":             "RT-MCC",
        "ACF-Nombre Comercio": "RT-Nombre Comercio",
        "ACF-Código Comercio": "RT-Codigo Comercio",
        "ACF-Codigo Comercio": "RT-Codigo Comercio",  # sin tilde (fallback)
        "ACF-Condición":       "RT-Condiciones Cumplidas",
        "ACF-Condicion":       "RT-Condiciones Cumplidas",  # sin tilde (fallback)
        "ACF-BIN":             "ACF-BIN",
        "ACF-Tarjeta SHA256":  "ACF-Tarjeta SHA256",
    }

    # Columnas del Silver final (orden definitivo)
    SILVER_SCHEMA = [
        "RT-Fecha TRX",
        "RT-Numero Trx",
        "RT-Monto TRX",
        "RT-MCC",
        "RT-Nombre Comercio",
        "RT-Codigo Comercio",
        "RT-Condiciones Cumplidas",
        "Condicion",
        "ACF-BIN",
        "AnoMes_Trx",
        "Dia_Trx",
        "ACF-Tarjeta SHA256",
    ]

    # =========================================================================
    # GOLD: Columnas que quieres en Power BI
    # =========================================================================
    # Para agregar una columna: ponla en la lista
    # Para quitar una columna: bórrala de la lista
    # El Silver siempre tiene TODAS las columnas, no se toca
    # =========================================================================
    GOLD_COLUMNS = [
        "RT-Fecha TRX",
        "RT-Numero Trx",
        "RT-Monto TRX",
        "RT-MCC",
        "RT-Nombre Comercio",
        "RT-Codigo Comercio",
        "RT-Condiciones Cumplidas",
        "Condicion",
        "ACF-BIN",
        "AnoMes_Trx",
        "Dia_Trx",
        "ACF-Tarjeta SHA256",
    ]


# ============================================================================
# UTILIDADES
# ============================================================================

def crear_estructura_directorios():
    """Crea la estructura de carpetas Medallion si no existe."""
    for d in [Config.BRONZE_DIR, Config.SILVER_DIR, Config.GOLD_DIR, Config.METADATA_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    print("Estructura de directorios verificada.")


def log_ingestion(metadata: dict):
    """Registra la ejecución en la base de metadata SQLite."""
    Config.METADATA_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(Config.METADATA_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_log (
            run_id TEXT, tool_name TEXT, source_file TEXT,
            rows_read INTEGER, rows_new INTEGER, rows_updated INTEGER,
            rows_skipped INTEGER, errors INTEGER, duration_sec REAL,
            status TEXT, created_at TEXT
        )
    """)
    conn.execute(
        "INSERT INTO ingestion_log VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            metadata.get("run_id", ""),
            metadata.get("tool_name", "rt_credito"),
            metadata.get("source_file", ""),
            metadata.get("rows_read", 0),
            metadata.get("rows_new", 0),
            metadata.get("rows_updated", 0),
            metadata.get("rows_skipped", 0),
            metadata.get("errors", 0),
            metadata.get("duration_sec", 0.0),
            metadata.get("status", "SUCCESS"),
            datetime.now().isoformat(),
        )
    )
    conn.commit()
    conn.close()


# ============================================================================
# EXTRACTOR: Lectura de Excel diario (Bronze)
# ============================================================================

class RTCreditoExtractor:
    """Lee el Excel diario de RT TC UBA."""

    @staticmethod
    def guardar_en_bronze(excel_path: str, fecha_descarga: str = None):
        """Copia el Excel original a la carpeta Bronze particionada por fecha."""
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
        """Lee el Excel diario. Los datos empiezan desde la fila 5 (skiprows=4)."""
        try:
            df = pl.read_excel(excel_path, read_options={"skip_rows": skip_rows})
        except Exception as e:
            print(f"  Error leyendo con skip_rows={skip_rows}: {e}")
            import pandas as pd
            df_pd = pd.read_excel(excel_path, skiprows=skip_rows)
            df = pl.from_pandas(df_pd)

        print(f"  Excel leído: {df.shape[0]:,} filas x {df.shape[1]} columnas")
        return df


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
        cols_nuevas = set(df_new.columns)

        nuevas   = cols_nuevas - cols_existentes
        perdidas = cols_existentes - cols_nuevas

        if nuevas:
            print(f"  ⚠ COLUMNAS NUEVAS ({len(nuevas)}): {sorted(nuevas)}")
        if perdidas:
            print(f"  ⚠ COLUMNAS PERDIDAS ({len(perdidas)}): {sorted(perdidas)}")
        if not nuevas and not perdidas:
            print(f"  ✔ Schema consistente con Silver existente")

        return True


# ============================================================================
# TRANSFORMER: Mapeo de columnas + reglas de negocio
# ============================================================================

class RTCreditoTransformer:
    """Transforma los datos crudos de RT TC UBA al schema Silver/Gold."""

    @staticmethod
    def mapear_columnas(df: pl.DataFrame) -> pl.DataFrame:
        """Renombra columnas ACF- → RT- según el COLUMN_MAP."""
        rename_map = {}
        columnas_presentes = set(df.columns)

        for col_excel, col_silver in Config.COLUMN_MAP.items():
            if col_excel in columnas_presentes:
                if col_silver not in rename_map.values():
                    rename_map[col_excel] = col_silver

        df = df.rename(rename_map)

        cols_to_keep = [col for col in df.columns if col in Config.COLUMN_MAP.values()]
        df = df.select(cols_to_keep)

        cols_existentes = set(df.columns)
        for col_faltante in set(Config.COLUMN_MAP.values()) - cols_existentes:
            df = df.with_columns(pl.lit(None).cast(pl.Utf8).alias(col_faltante))

        print(f"  Columnas mapeadas: {len(rename_map)} de {len(Config.COLUMN_MAP)}")
        return df

    @staticmethod
    def parsear_fecha(df: pl.DataFrame) -> pl.DataFrame:
        """Parsea RT-Fecha TRX. Genera AnoMes_Trx y Dia_Trx."""
        fecha_col = "RT-Fecha TRX"

        if df[fecha_col].dtype in [pl.Date, pl.Datetime]:
            df = df.with_columns(pl.col(fecha_col).cast(pl.Date).alias(fecha_col))
        else:
            df = df.with_columns(
                pl.col(fecha_col).cast(pl.Utf8).str.strip_chars()
                .str.to_date("%d/%m/%Y", strict=False)
                .alias(fecha_col)
            )

        df = df.with_columns([
            (
                pl.col(fecha_col).dt.year().cast(pl.Utf8)
                + pl.col(fecha_col).dt.month().cast(pl.Utf8).str.pad_start(2, "0")
            ).alias("AnoMes_Trx"),
            pl.col(fecha_col).dt.day().cast(pl.Utf8).str.pad_start(2, "0").alias("Dia_Trx"),
        ])

        print(f"  Fecha parseada. Rango: {df[fecha_col].min()} a {df[fecha_col].max()}")
        return df

    @staticmethod
    def aplicar_reglas_negocio(df: pl.DataFrame) -> pl.DataFrame:
        """RT-Numero Trx = 0, Condicion = LEFT(RT-Condiciones Cumplidas, 4)."""
        df = df.with_columns([
            pl.lit("0").alias("RT-Numero Trx"),
            pl.col("RT-Condiciones Cumplidas").cast(pl.Utf8).str.slice(0, 4).alias("Condicion"),
            pl.col("RT-Codigo Comercio").cast(pl.Utf8).str.strip_chars().alias("RT-Codigo Comercio"),
            pl.col("RT-MCC").cast(pl.Utf8).str.strip_chars().alias("RT-MCC"),
            pl.col("ACF-BIN").cast(pl.Utf8).str.strip_chars().alias("ACF-BIN"),
        ])
        print(f"  Reglas de negocio aplicadas.")
        return df

    @staticmethod
    def tipar_columnas(df: pl.DataFrame) -> pl.DataFrame:
        """Aplica tipos de datos correctos."""
        df = df.with_columns([
            pl.col("RT-Monto TRX").cast(pl.Float64, strict=False).alias("RT-Monto TRX"),
        ])
        text_cols = [c for c in df.columns if c not in ["RT-Monto TRX", "RT-Fecha TRX"]]
        df = df.with_columns([
            pl.col(c).cast(pl.Utf8, strict=False) for c in text_cols if c in df.columns
        ])
        print(f"  Tipos de datos aplicados.")
        return df

    @staticmethod
    def generar_hashes(df: pl.DataFrame) -> pl.DataFrame:
        """Hash SHA-256 para deduplicación."""
        df = df.with_columns(
            (
                pl.col("RT-Fecha TRX").cast(pl.Utf8).fill_null("")
                + "|" + pl.col("RT-Monto TRX").cast(pl.Utf8).fill_null("")
                + "|" + pl.col("ACF-BIN").cast(pl.Utf8).fill_null("")
                + "|" + pl.col("RT-Nombre Comercio").cast(pl.Utf8).fill_null("")
                + "|" + pl.col("RT-Condiciones Cumplidas").cast(pl.Utf8).fill_null("")
            ).alias("_composite_key")
        )
        df = df.with_columns(
            pl.col("_composite_key")
            .map_elements(
                lambda x: hashlib.sha256(x.encode("utf-8")).hexdigest(),
                return_dtype=pl.Utf8
            )
            .alias("_row_hash")
        )
        df = df.drop("_composite_key")
        print(f"  Hashes generados: {df.shape[0]:,} registros")
        return df

    @classmethod
    def transformar(cls, df: pl.DataFrame) -> pl.DataFrame:
        """Pipeline completo de transformación Silver."""
        print("\n--- TRANSFORMACION SILVER ---")
        df = cls.mapear_columnas(df)
        df = cls.parsear_fecha(df)
        df = cls.aplicar_reglas_negocio(df)
        df = cls.tipar_columnas(df)

        final_cols = [c for c in Config.SILVER_SCHEMA if c in df.columns]
        df = df.select(final_cols)

        print(f"  Schema final: {len(final_cols)} columnas | Filas: {df.shape[0]:,}")
        return df

    @staticmethod
    def generar_gold(df_silver: pl.DataFrame) -> pl.DataFrame:
        """
        Genera el Gold seleccionando solo las columnas configuradas.
        Las columnas que no existen en Silver se ignoran silenciosamente.
        Para agregar/quitar columnas: editar Config.GOLD_COLUMNS.
        """
        cols_disponibles = [c for c in Config.GOLD_COLUMNS if c in df_silver.columns]
        cols_faltantes   = [c for c in Config.GOLD_COLUMNS if c not in df_silver.columns]

        if cols_faltantes:
            print(f"  Gold: {len(cols_faltantes)} columnas no disponibles en Silver: {cols_faltantes}")

        df_gold = df_silver.select(cols_disponibles)
        print(f"  Gold generado: {df_gold.shape[0]:,} filas x {df_gold.shape[1]} columnas")
        return df_gold


# ============================================================================
# LOADER: Persistencia en Parquet Silver + Gold
# ============================================================================

class SilverLoader:
    """Maneja la persistencia y upsert del Parquet Silver."""

    @staticmethod
    def bootstrap_from_access(access_df: pl.DataFrame) -> pl.DataFrame:
        """Inicializa el Silver Parquet desde el consolidado de Access."""
        print("\n--- BOOTSTRAP DESDE ACCESS ---")

        if access_df["RT-Fecha TRX"].dtype == pl.Utf8:
            access_df = access_df.with_columns(
                pl.col("RT-Fecha TRX").str.strip_chars()
                .str.to_date("%d/%m/%Y", strict=False)
                .alias("RT-Fecha TRX")
            )
        elif access_df["RT-Fecha TRX"].dtype in [pl.Datetime]:
            access_df = access_df.with_columns(
                pl.col("RT-Fecha TRX").cast(pl.Date).alias("RT-Fecha TRX")
            )

        access_df = RTCreditoTransformer.tipar_columnas(access_df)
        final_cols = [c for c in Config.SILVER_SCHEMA if c in access_df.columns]
        access_df = access_df.select(final_cols)

        Config.SILVER_DIR.mkdir(parents=True, exist_ok=True)
        access_df.write_parquet(Config.SILVER_PARQUET, compression="zstd")

        size_mb = Config.SILVER_PARQUET.stat().st_size / (1024 * 1024)
        print(f"  Silver base creado: {Config.SILVER_PARQUET}")
        print(f"  Filas: {access_df.shape[0]:,} | Tamano: {size_mb:.1f} MB")
        return access_df

    @staticmethod
    def append_incremental(df_new: pl.DataFrame) -> dict:
        """Append directo al Silver existente con schema evolution."""
        print("\n--- APPEND INCREMENTAL ---")
        metrics = {"rows_read": df_new.shape[0], "rows_new": df_new.shape[0],
                   "rows_updated": 0, "rows_skipped": 0}

        if not Config.SILVER_PARQUET.exists():
            Config.SILVER_DIR.mkdir(parents=True, exist_ok=True)
            df_new.write_parquet(Config.SILVER_PARQUET, compression="zstd")
            print(f"  Silver creado: {df_new.shape[0]:,} filas")
            return metrics

        df_existing = pl.read_parquet(Config.SILVER_PARQUET)
        print(f"  Silver existente: {df_existing.shape[0]:,} filas")

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

        df_new = df_new.select(df_existing.columns)
        df_final = pl.concat([df_existing, df_new], how="diagonal")

        backup_path = Config.SILVER_DIR / f"rt_credito_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
        shutil.copy2(Config.SILVER_PARQUET, backup_path)

        df_final.write_parquet(Config.SILVER_PARQUET, compression="zstd")
        size_mb = Config.SILVER_PARQUET.stat().st_size / (1024 * 1024)
        print(f"  Silver actualizado: {df_final.shape[0]:,} filas | {size_mb:.1f} MB")
        return metrics


# ============================================================================
# ORQUESTADOR
# ============================================================================

def run_bootstrap(access_df: pl.DataFrame):
    """
    BOOTSTRAP: Ejecutar UNA SOLA VEZ para inicializar Silver + Gold desde Access.

    Uso:
        import pyodbc, polars as pl
        conn = pyodbc.connect(r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=ruta.accdb;")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM [BBDD_Real_Time_TC_UBA]")
        cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        access_df = pl.DataFrame([dict(zip(cols, row)) for row in rows])
        conn.close()

        run_bootstrap(access_df)
    """
    print("=" * 60)
    print("BOOTSTRAP: Access → Silver → Gold (RT CREDITO)")
    print("=" * 60)

    start = datetime.now()
    crear_estructura_directorios()

    df_silver = SilverLoader.bootstrap_from_access(access_df)

    print("\n--- GENERANDO GOLD ---")
    df_gold = RTCreditoTransformer.generar_gold(df_silver)
    Config.GOLD_DIR.mkdir(parents=True, exist_ok=True)
    df_gold.write_parquet(Config.GOLD_PARQUET, compression="zstd")
    print(f"  Gold creado: {Config.GOLD_PARQUET}")

    duration = (datetime.now() - start).total_seconds()
    log_ingestion({
        "run_id": datetime.now().isoformat(), "tool_name": "rt_credito",
        "source_file": "ACCESS_BOOTSTRAP", "rows_read": df_silver.shape[0],
        "rows_new": df_silver.shape[0], "rows_updated": 0, "rows_skipped": 0,
        "errors": 0, "duration_sec": duration, "status": "SUCCESS",
    })
    print(f"\nBootstrap completado en {duration:.1f} segundos.")
    return df_silver


def run_daily(excel_path: str, fecha_descarga: str = None):
    """
    CARGA DIARIA: Procesa el Excel del día, actualiza Silver y regenera Gold.

    Uso:
        run_daily(
            excel_path=r"C:\\FRAUDES\\HERRAMIENTAS\\RT_TC_UBA\\DATA\\R0852_20260405.xlsx",
            fecha_descarga="2026-04-05"
        )
    """
    print("=" * 60)
    print("CARGA INCREMENTAL DIARIA (RT CREDITO)")
    print("=" * 60)

    start = datetime.now()
    crear_estructura_directorios()

    print("\n1. BRONZE: Guardando archivo original...")
    RTCreditoExtractor.guardar_en_bronze(excel_path, fecha_descarga)

    print("\n2. EXTRACCION: Leyendo Excel...")
    df_raw = RTCreditoExtractor.leer_excel(excel_path)

    print("\n3. VALIDACION DE SCHEMA:")
    SchemaValidator.validar(df_raw, Path(excel_path).name)

    print("\n4. TRANSFORMACION:")
    df_transformed = RTCreditoTransformer.transformar(df_raw)

    print("\n5. CARGA SILVER:")
    metrics = SilverLoader.append_incremental(df_transformed)

    print("\n6. GENERANDO GOLD:")
    df_silver = pl.read_parquet(Config.SILVER_PARQUET)
    df_gold = RTCreditoTransformer.generar_gold(df_silver)
    Config.GOLD_DIR.mkdir(parents=True, exist_ok=True)
    df_gold.write_parquet(Config.GOLD_PARQUET, compression="zstd")
    print(f"  Gold actualizado: {Config.GOLD_PARQUET}")

    duration = (datetime.now() - start).total_seconds()
    source = f"{Path(excel_path).name}_{fecha_descarga or date.today().isoformat()}"
    log_ingestion({
        "run_id": datetime.now().isoformat(), "tool_name": "rt_credito",
        "source_file": source, "rows_read": metrics["rows_read"],
        "rows_new": metrics["rows_new"], "rows_updated": metrics["rows_updated"],
        "rows_skipped": metrics["rows_skipped"], "errors": 0,
        "duration_sec": duration, "status": "SUCCESS",
    })

    print(f"\n{'=' * 60}")
    print(f"RESUMEN")
    print(f"{'=' * 60}")
    print(f"  Filas leidas    : {metrics['rows_read']:,}")
    print(f"  Nuevas          : {metrics['rows_new']:,}")
    print(f"  Duracion        : {duration:.1f} seg")
    print(f"  Silver          : {Config.SILVER_PARQUET.name}")
    print(f"  Gold            : {Config.GOLD_PARQUET.name}")
    print(f"{'=' * 60}")


def regenerar_gold():
    """
    Regenera el Gold desde el Silver existente sin modificar nada.
    Usar cuando cambias Config.GOLD_COLUMNS.

    Uso:
        from rt_credito_pipeline_medallion import regenerar_gold
        regenerar_gold()
    """
    print("REGENERANDO GOLD DESDE SILVER")
    if not Config.SILVER_PARQUET.exists():
        print("  ERROR: No existe Silver. Ejecuta run_bootstrap primero.")
        return

    df_silver = pl.read_parquet(Config.SILVER_PARQUET)
    df_gold = RTCreditoTransformer.generar_gold(df_silver)
    Config.GOLD_DIR.mkdir(parents=True, exist_ok=True)
    df_gold.write_parquet(Config.GOLD_PARQUET, compression="zstd")
    print(f"  Gold regenerado: {Config.GOLD_PARQUET}")
    print(f"  Filas: {df_gold.shape[0]:,} | Columnas: {df_gold.shape[1]}")


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    """
    PASO 1 - BOOTSTRAP (una sola vez):
    ====================================
    import pyodbc, polars as pl

    conn = pyodbc.connect(
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        r"DBQ=C:\\Users\\s4930359\\Data_Herramientas\\BBDD_Real_Time_TC_UBA.accdb;"
    )
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM [BBDD_Real_Time_TC_UBA]")
    cols = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    access_df = pl.DataFrame([dict(zip(cols, row)) for row in rows])
    conn.close()

    run_bootstrap(access_df)


    PASO 2 - CARGA DIARIA:
    ====================================
    run_daily(
        excel_path=r"C:\\FRAUDES\\HERRAMIENTAS\\RT_TC_UBA\\DATA\\R0852_20260405.xlsx",
        fecha_descarga="2026-04-05"
    )


    PASO 3 - REGENERAR GOLD (cuando cambias GOLD_COLUMNS):
    ====================================
    regenerar_gold()
    """
    print("Pipeline RT Credito (Medallion) listo.")
    print("Funciones disponibles:")
    print("  run_bootstrap(access_df) - Inicializar desde Access (una vez)")
    print("  run_daily(excel_path)    - Carga incremental diaria")
    print("  regenerar_gold()         - Actualizar Gold sin tocar Silver")
