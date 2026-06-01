"""
==============================================================================
PIPELINE VRM - ARQUITECTURA MEDALLION (Bronze → Silver → Gold)
==============================================================================
Bronze: Data cruda tal cual se descarga (CSV/Excel), sin tocar
Silver: Todas las columnas procesadas y estandarizadas (111 cols max)
Gold:   Solo las columnas seleccionadas para Power BI (configurable)

Incluye:
  - Schema validator: alerta cambios de columnas antes de cada carga
  - Schema evolution: columnas nuevas se agregan, faltantes se llenan con null
  - Bootstrap desde consolidados históricos (Excel)
  - Carga incremental diaria (2 listas CSV)

Autor: Mayker Cordova
Fecha: Abril 2026
==============================================================================
"""

import polars as pl
import hashlib
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
    """Configuración centralizada del pipeline VRM."""

    # === RUTAS FUENTE (absolutas — datos originales) ===
    BASE_DIR       = Path(r"C:\Users\s4930359\Data_Herramientas")
    HISTORICOS_DIR = BASE_DIR / "BBDD_VRM"

    # === RUTAS DE SALIDA (relativas a 10_proceso_declinaciones/) ===
    DATA_DIR     = Path(__file__).parent.parent / "data"
    BRONZE_DIR   = DATA_DIR / "bronze" / "vrm"
    SILVER_DIR   = DATA_DIR / "silver"
    GOLD_DIR     = DATA_DIR / "gold"
    METADATA_DIR = DATA_DIR / "metadata"

    # Archivos
    SILVER_PARQUET = SILVER_DIR / "vrm_silver.parquet"
    GOLD_PARQUET   = GOLD_DIR   / "vrm_gold.parquet"
    METADATA_DB    = METADATA_DIR / "ingestion_log.db"
    SCHEMA_FILE    = METADATA_DIR / "vrm_schema_registry.json"
    HISTORICOS = [
        "Consolidado.xlsx",
        "vrm_2.xlsx",
        "vrm_3.xlsx",
        "vrm_4.xlsx",
    ]

    # === REGLAS DE NEGOCIO ===
    BIN_CSF = "422052"  # BIN para entidad CSF (Santander)

    # === LECTURA CSV ===
    CSV_READ_OPTS = dict(
        encoding="latin-1",
        infer_schema_length=0,
        truncate_ragged_lines=True,
        ignore_errors=True,
    )

    # =========================================================================
    # GOLD: Columnas que quieres en Power BI
    # =========================================================================
    # Para agregar una columna: ponla en la lista
    # Para quitar una columna: bórrala de la lista
    # El Silver siempre tiene TODAS las columnas, no se toca
    # =========================================================================
    GOLD_COLUMNS = [
        "TARJETA",
        "MONTO USD",
        "TIPO DE MONEDA",
        "Fecha",
        "BIN",
        "MCC",
        "LOCALIDAD",
        "NOMBRE DE COMERCIO",
        "COD REDP 59",
        "ENTRY MODE",
        "CALIFICACION",
        "ECI",
        "VISA TRANSSACTION ID",
        "CODIGO DE COMERCIO",
        "ID ANALISTA",
        "NAME ANALISTA",
        "LAST NAME ANALISTA",
        "CODIGO PAIS",
        "RTD REGLA",
        "CVV2",
        "NOMBRE REGLA",
        "CODIGO REGLA",
        "TIPO DE TOKEN",
        "NUMERO DE TOKEN",
        "Dia_reporte",
        "AnoMes_reporte",
        "Entidad",
        "Gestion",
        "Cuenta",
        "Fuente",
        "SCORE",
        "VCAS Score",
        "VAAI Score",
        "STIP Reason Code",
    ]


# ============================================================================
# SCHEMA VALIDATOR
# ============================================================================

class SchemaValidator:
    """Valida cambios de schema antes de cada carga."""

    @staticmethod
    def validar(df_new: pl.DataFrame, nombre_archivo: str = "") -> bool:
        """
        Compara las columnas del archivo nuevo contra el Silver existente.
        Imprime alertas si hay cambios.
        Retorna True si pasa la validación.
        """
        print(f"\n--- VALIDACION DE SCHEMA ---")

        if not Config.SILVER_PARQUET.exists():
            print(f"  No existe Silver previo. Primera carga, sin validacion.")
            print(f"  Columnas del archivo: {df_new.shape[1]}")
            return True

        df_existing = pl.read_parquet(Config.SILVER_PARQUET, n_rows=0)
        cols_existentes = set(df_existing.columns)
        cols_nuevas_set = set(df_new.columns)

        # Columnas nuevas (no estaban en Silver)
        nuevas = cols_nuevas_set - cols_existentes
        # Columnas faltantes (estaban en Silver pero no vienen en el archivo)
        faltantes = cols_existentes - cols_nuevas_set
        # Columnas comunes
        comunes = cols_existentes & cols_nuevas_set

        hay_cambios = False

        if nuevas:
            hay_cambios = True
            print(f"  COLUMNAS NUEVAS detectadas ({len(nuevas)}):")
            for col in sorted(nuevas):
                print(f"    + {col}")

        if faltantes:
            hay_cambios = True
            # Filtrar columnas derivadas que no vienen en el CSV crudo
            derivadas = {"Dia_reporte", "AnoMes_reporte", "Entidad", "Gestion", "Cuenta", "Fuente", "_row_hash"}
            faltantes_reales = faltantes - derivadas
            if faltantes_reales:
                print(f"  COLUMNAS FALTANTES ({len(faltantes_reales)}):")
                for col in sorted(faltantes_reales):
                    print(f"    - {col}")

        if not hay_cambios:
            print(f"  Schema OK - sin cambios ({len(comunes)} columnas)")

        print(f"  Archivo: {nombre_archivo}")
        print(f"  Columnas archivo: {df_new.shape[1]} | Silver: {len(cols_existentes)}")

        return True  # Siempre continua, solo alerta


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
            rows_read INTEGER, rows_new INTEGER,
            duration_sec REAL, status TEXT, created_at TEXT
        )
    """)
    conn.execute(
        "INSERT INTO ingestion_log VALUES (?,?,?,?,?,?,?,?)",
        (
            metadata.get("run_id", ""),
            metadata.get("tool_name", "vrm"),
            metadata.get("source_file", ""),
            metadata.get("rows_read", 0),
            metadata.get("rows_new", 0),
            metadata.get("duration_sec", 0.0),
            metadata.get("status", "SUCCESS"),
            datetime.now().isoformat(),
        )
    )
    conn.commit()
    conn.close()


# ============================================================================
# EXTRACTOR
# ============================================================================

class VRMExtractor:
    """Lee archivos de VRM (CSV diario o Excel histórico)."""

    @staticmethod
    def guardar_en_bronze(lista1_path: str, lista2_path: str, fecha_descarga: str = None):
        """Copia los CSVs originales a Bronze particionado por fecha."""
        if fecha_descarga is None:
            fecha_descarga = date.today().isoformat()

        year, month, day = fecha_descarga.split("-")
        bronze_folder = Config.BRONZE_DIR / year / month / day
        bronze_folder.mkdir(parents=True, exist_ok=True)

        shutil.copy2(lista1_path, bronze_folder / f"vrm_lista1_{fecha_descarga.replace('-', '')}.csv")
        shutil.copy2(lista2_path, bronze_folder / f"vrm_lista2_{fecha_descarga.replace('-', '')}.csv")

        print(f"  Bronze: Archivos guardados en {bronze_folder}")
        return bronze_folder

    @staticmethod
    def leer_listas_csv(lista1_path: str, lista2_path: str) -> pl.DataFrame:
        """Lee y combina las 2 listas diarias de VRM (CSV)."""
        df1 = pl.read_csv(lista1_path, **Config.CSV_READ_OPTS)
        df2 = pl.read_csv(lista2_path, **Config.CSV_READ_OPTS)

        print(f"  Lista 1: {df1.shape[0]:,} filas x {df1.shape[1]} columnas")
        print(f"  Lista 2: {df2.shape[0]:,} filas x {df2.shape[1]} columnas")

        df = pl.concat([df1, df2], how="diagonal")
        print(f"  Union: {df.shape[0]:,} filas x {df.shape[1]} columnas")
        return df

    @staticmethod
    def leer_excel_historico(ruta: str) -> pl.DataFrame:
        """Lee un consolidado histórico (Excel)."""
        try:
            df = pl.read_excel(ruta)
        except Exception:
            import pandas as pd
            df = pl.from_pandas(pd.read_excel(ruta))

        print(f"  {Path(ruta).name}: {df.shape[0]:,} filas x {df.shape[1]} columnas")
        return df


# ============================================================================
# TRANSFORMER
# ============================================================================

class VRMTransformer:
    """Transforma datos de VRM para Silver y Gold."""

    # Mapeo de columnas CSV crudo → nombres del Silver
    # Esto se usa SOLO para las cargas diarias (CSV de VRM)
    # Los consolidados ya tienen los nombres procesados por Marcial
    CSV_TO_SILVER_MAP = {
        "Account Number":                          "TARJETA",
        "Transaction Amount (U.S. $)":             "MONTO USD",
        "Acquirer Currency Code":                  "TIPO DE MONEDA",
        "Authorization Timestamp (America/Bogota)": "_TIMESTAMP_RAW",
        "Authorization Timestamp (America/Lima)":   "_TIMESTAMP_RAW",
        "Issuer BIN":                              "BIN",
        "Acquirer BIN":                            "Acquirer BIN",
        "Merchant Category Code (MCC)":            "MCC",
        "Merchant Location":                       "LOCALIDAD",
        "Merchant Name":                           "NOMBRE DE COMERCIO",
        "Authorization Response Code":             "COD REDP 59",
        "POS Entry Mode":                          "ENTRY MODE",
        "Status":                                  "CALIFICACION",
        "MOTO/ECI/Recurring":                      "ECI",
        "Visa Transaction ID":                     "VISA TRANSSACTION ID",
        "Merchant ID":                             "CODIGO DE COMERCIO",
        "Statused By User ID":                     "ID ANALISTA",
        "Statused By First Name":                  "NAME ANALISTA",
        "Statused By Last Name":                   "LAST NAME ANALISTA",
        "Card Acceptor Country Code":              "CODIGO PAIS",
        "CC Rule Name":                            "RTD REGLA",
        "CVV2 Result Code":                        "CVV2",
        "RTD Rule Name":                           "NOMBRE REGLA",
        "RTD Rule Version":                        "CODIGO REGLA",
        "Token Type":                              "TIPO DE TOKEN",
        "Token Number":                            "NUMERO DE TOKEN",
        "Advanced Authorization Risk Score":       "SCORE",
        "VCAS Score":                              "VCAS Score",
        "VAAI Score":                              "VAAI Score",
        "STIP Reason Code":                        "STIP Reason Code",
        # Todas las demás columnas del CSV pasan tal cual
    }

    # Meses en español para parseo de timestamp
    MESES_MAP = {
        "ene": "01", "feb": "02", "mar": "03", "abr": "04",
        "may": "05", "jun": "06", "jul": "07", "ago": "08",
        "sept": "09", "sep": "09", "oct": "10", "nov": "11", "dic": "12",
    }

    @classmethod
    def transformar_csv(cls, df: pl.DataFrame) -> pl.DataFrame:
        """
        Transforma CSV diario de VRM al schema Silver.
        Renombra columnas conocidas, mantiene las demás tal cual.
        """
        print("\n--- TRANSFORMACION SILVER (CSV) ---")

        # Renombrar columnas conocidas
        rename_map = {}
        for col_csv, col_silver in cls.CSV_TO_SILVER_MAP.items():
            if col_csv in df.columns:
                rename_map[col_csv] = col_silver

        df = df.rename(rename_map)
        print(f"  Columnas renombradas: {len(rename_map)}")

        # Parsear timestamp
        df = cls._parsear_timestamp(df)

        # Limpiar TARJETA y VISA TRANSSACTION ID (quitar ="...")
        for col in ["TARJETA", "VISA TRANSSACTION ID", "NUMERO DE TOKEN"]:
            if col in df.columns:
                df = df.with_columns(
                    pl.col(col).cast(pl.Utf8).str.replace_all(r'[=""]', "").str.strip_chars().alias(col)
                )

        # Aplicar reglas de negocio
        df = cls._aplicar_reglas_negocio(df)

        # Tipar MONTO USD
        if "MONTO USD" in df.columns:
            df = df.with_columns(
                pl.col("MONTO USD").cast(pl.Utf8).str.replace_all(",", "").cast(pl.Float64, strict=False).alias("MONTO USD")
            )

        # Castear columnas numéricas a Float64 y el resto a Utf8 (igual que historico)
        COLUMNAS_NUMERICAS = {
            "Fecha", "MONTO USD", "SCORE", "VCAS Score", "VAAI Score",
            "Acquirer Transaction Amount", "Cashback Amount", "Issuer Amount",
            "Aggregate Transaction Amount", "Transaction Amount Difference",
            "Token Age", "Token Transaction Counter", "Token Transaction Last Counter",
            "Token Transaction Elapsed Time", "VCAS VCAS Device ID Velocity Count",
            "VCAS VCAS Device IP-Address Velocity Count",
        }

        for col in df.columns:
            if col in COLUMNAS_NUMERICAS:
                if col != "Fecha":
                    df = df.with_columns(
                        pl.col(col).cast(pl.Float64, strict=False).alias(col)
                    )
            elif df[col].dtype != pl.Utf8:
                df = df.with_columns(
                    pl.col(col).cast(pl.Utf8, strict=False).alias(col)
                )

        print(f"  Schema final: {df.shape[1]} columnas, {df.shape[0]:,} filas")
        return df

    @classmethod
    def transformar_historico(cls, df: pl.DataFrame) -> pl.DataFrame:
        """
        Transforma consolidado histórico (Excel) al schema Silver.
        Los consolidados ya tienen nombres procesados por Marcial.
        """
        print("\n--- TRANSFORMACION SILVER (HISTORICO) ---")

        # Asegurar Fecha como Date
        if "Fecha" in df.columns:
            if df["Fecha"].dtype == pl.Utf8:
                df = df.with_columns(
                    pl.col("Fecha").str.to_date("%Y-%m-%d", strict=False).alias("Fecha")
                )
            elif df["Fecha"].dtype in [pl.Datetime]:
                df = df.with_columns(
                    pl.col("Fecha").cast(pl.Date).alias("Fecha")
                )

        # Tipar MONTO USD
        if "MONTO USD" in df.columns:
            df = df.with_columns(
                pl.col("MONTO USD").cast(pl.Float64, strict=False).alias("MONTO USD")
            )

        # Castear TODAS las demás columnas a Utf8 para evitar conflictos de tipo al concatenar
        # EXCEPTO las que deben ser numéricas
        COLUMNAS_NUMERICAS = {
            "Fecha", "MONTO USD", "SCORE", "VCAS Score", "VAAI Score",
            "Acquirer Transaction Amount", "Cashback Amount", "Issuer Amount",
            "Aggregate Transaction Amount", "Transaction Amount Difference",
            "Token Age", "Token Transaction Counter", "Token Transaction Last Counter",
            "Token Transaction Elapsed Time", "VCAS VCAS Device ID Velocity Count",
            "VCAS VCAS Device IP-Address Velocity Count",
        }

        for col in df.columns:
            if col in COLUMNAS_NUMERICAS:
                if col != "Fecha":
                    df = df.with_columns(
                        pl.col(col).cast(pl.Float64, strict=False).alias(col)
                    )
            elif df[col].dtype != pl.Utf8:
                df = df.with_columns(
                    pl.col(col).cast(pl.Utf8, strict=False).alias(col)
                )

        # Generar columnas derivadas si no existen
        df = cls._aplicar_reglas_negocio(df)

        print(f"  Schema final: {df.shape[1]} columnas, {df.shape[0]:,} filas")
        return df

    @staticmethod
    def _parsear_timestamp(df: pl.DataFrame) -> pl.DataFrame:
        """Parsea timestamp VRM: '31 mar. 2026 22:52:29' → Date."""
        if "_TIMESTAMP_RAW" not in df.columns:
            return df

        df = df.with_columns(
            pl.col("_TIMESTAMP_RAW").str.replace_all(r"\s+", " ").str.strip_chars().alias("_ts_clean")
        )

        for mes_es, mes_num in VRMTransformer.MESES_MAP.items():
            df = df.with_columns(
                pl.col("_ts_clean").str.replace(f" {mes_es}. ", f" {mes_num} ", literal=True).alias("_ts_clean")
            )
            df = df.with_columns(
                pl.col("_ts_clean").str.replace(f" {mes_es} ", f" {mes_num} ", literal=True).alias("_ts_clean")
            )

        df = df.with_columns([
            pl.col("_ts_clean").str.extract(r"^(\d{1,2})\s", 1).cast(pl.Int32, strict=False).alias("DIA"),
            pl.col("_ts_clean").str.extract(r"^\d{1,2}\s(\d{1,2})\s", 1).cast(pl.Int32, strict=False).alias("MES"),
            pl.col("_ts_clean").str.extract(r"^\d{1,2}\s\d{1,2}\s(\d{4})", 1).cast(pl.Int32, strict=False).alias("ANIO"),
            pl.col("_ts_clean").str.extract(r"\d{4}\s(\d{2}:\d{2}:\d{2})", 1).alias("HORA"),
        ])

        df = df.with_columns(
            pl.date(pl.col("ANIO"), pl.col("MES"), pl.col("DIA")).alias("Fecha")
        )

        df = df.drop(["_TIMESTAMP_RAW", "_ts_clean"])

        print(f"  Timestamp parseado. Rango: {df['Fecha'].min()} a {df['Fecha'].max()}")
        return df

    @staticmethod
    def _aplicar_reglas_negocio(df: pl.DataFrame) -> pl.DataFrame:
        """Genera columnas derivadas si no existen."""
        # Dia_reporte
        if "Dia_reporte" not in df.columns and "Fecha" in df.columns:
            df = df.with_columns(
                pl.col("Fecha").cast(pl.Date, strict=False).dt.day().cast(pl.Int32, strict=False).alias("Dia_reporte")
            )

        # AnoMes_reporte
        if "AnoMes_reporte" not in df.columns and "Fecha" in df.columns:
            df = df.with_columns(
                (
                    pl.col("Fecha").cast(pl.Date, strict=False).dt.year().cast(pl.Utf8)
                    + pl.col("Fecha").cast(pl.Date, strict=False).dt.month().cast(pl.Utf8).str.pad_start(2, "0")
                ).alias("AnoMes_reporte")
            )

        # Entidad
        if "Entidad" not in df.columns and "BIN" in df.columns:
            df = df.with_columns(
                pl.when(pl.col("BIN").cast(pl.Utf8).str.strip_chars() == Config.BIN_CSF)
                .then(pl.lit("CSF"))
                .otherwise(pl.lit("SBP"))
                .alias("Entidad")
            )

        # Gestion
        if "Gestion" not in df.columns and "ID ANALISTA" in df.columns:
            df = df.with_columns(
                pl.when(
                    pl.col("ID ANALISTA").is_not_null()
                    & (pl.col("ID ANALISTA").cast(pl.Utf8).str.strip_chars() != "")
                    & (pl.col("ID ANALISTA").cast(pl.Utf8).str.strip_chars() != "N.A.")
                    & (pl.col("ID ANALISTA").cast(pl.Utf8).str.to_lowercase() != "na")
                    & (pl.col("ID ANALISTA").cast(pl.Utf8).str.to_lowercase() != "nan")
                )
                .then(pl.lit("GESTIONADA"))
                .otherwise(pl.lit("NO GESTIONADA"))
                .alias("Gestion")
            )

        # Cuenta
        if "Cuenta" not in df.columns:
            df = df.with_columns(pl.lit("1").alias("Cuenta"))

        # Fuente
        if "Fuente" not in df.columns:
            df = df.with_columns(pl.lit("VRM").alias("Fuente"))

        return df

    # Filtros de negocio aplicados al Gold
    STIP_EXCLUIDOS = {"9212", "9224"}  # Códigos STIP que no aplican a declinaciones reales

    @staticmethod
    def generar_gold(df_silver: pl.DataFrame) -> pl.DataFrame:
        """
        Genera el Gold seleccionando solo las columnas configuradas
        y aplicando los filtros de negocio propios de VRM.
        Las columnas que no existen en Silver se ignoran silenciosamente.
        """
        cols_disponibles = [c for c in Config.GOLD_COLUMNS if c in df_silver.columns]
        cols_faltantes = [c for c in Config.GOLD_COLUMNS if c not in df_silver.columns]

        if cols_faltantes:
            print(f"  Gold: {len(cols_faltantes)} columnas no disponibles en Silver: {cols_faltantes}")

        df_gold = df_silver.select(cols_disponibles)

        # Filtrar códigos STIP excluidos
        if "STIP Reason Code" in df_gold.columns:
            df_gold = df_gold.filter(
                ~pl.col("STIP Reason Code").cast(pl.Utf8).is_in(VRMTransformer.STIP_EXCLUIDOS)
            )

        print(f"  Gold generado: {df_gold.shape[0]:,} filas x {df_gold.shape[1]} columnas")
        return df_gold


# ============================================================================
# LOADER
# ============================================================================

class SilverLoader:
    """Persistencia Silver y Gold."""

    @staticmethod
    def bootstrap_historicos() -> pl.DataFrame:
        """
        Lee todos los consolidados históricos, los une y crea el Silver base.
        Usa concat diagonal para manejar schema evolution automáticamente.
        """
        print("\n--- BOOTSTRAP DESDE HISTORICOS ---")
        dfs = []

        for archivo in Config.HISTORICOS:
            ruta = Config.HISTORICOS_DIR / archivo
            if not ruta.exists():
                print(f"  WARN: {archivo} no encontrado, saltando...")
                continue

            df = VRMExtractor.leer_excel_historico(str(ruta))
            df = VRMTransformer.transformar_historico(df)
            dfs.append(df)

        # Unir todos con concat diagonal (maneja columnas diferentes)
        df_silver = pl.concat(dfs, how="diagonal")
        print(f"\n  Total unificado: {df_silver.shape[0]:,} filas x {df_silver.shape[1]} columnas")

        # Guardar Silver
        Config.SILVER_DIR.mkdir(parents=True, exist_ok=True)
        df_silver.write_parquet(Config.SILVER_PARQUET, compression="zstd")

        size_mb = Config.SILVER_PARQUET.stat().st_size / (1024 * 1024)
        print(f"  Silver creado: {Config.SILVER_PARQUET}")
        print(f"  Tamano: {size_mb:.1f} MB")

        # Generar Gold
        df_gold = VRMTransformer.generar_gold(df_silver)
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

            df_gold = VRMTransformer.generar_gold(df_new)
            Config.GOLD_DIR.mkdir(parents=True, exist_ok=True)
            df_gold.write_parquet(Config.GOLD_PARQUET, compression="zstd")

            print(f"  Silver y Gold creados: {df_new.shape[0]:,} filas")
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

        # Asegurar mismo orden y mismos tipos de columnas
        df_new = df_new.select(df_existing.columns)

        # Forzar que df_new tenga los mismos tipos que df_existing
        for col in df_existing.columns:
            if col in df_new.columns and df_new[col].dtype != df_existing[col].dtype:
                try:
                    df_new = df_new.with_columns(
                        pl.col(col).cast(df_existing[col].dtype, strict=False).alias(col)
                    )
                except Exception:
                    # Si no se puede castear, ambos a Utf8
                    df_new = df_new.with_columns(pl.col(col).cast(pl.Utf8, strict=False).alias(col))
                    df_existing = df_existing.with_columns(pl.col(col).cast(pl.Utf8, strict=False).alias(col))

        # Append
        df_final = pl.concat([df_existing, df_new], how="diagonal")

        # Backup Silver
        backup_path = Config.SILVER_DIR / f"vrm_silver_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
        shutil.copy2(Config.SILVER_PARQUET, backup_path)
        print(f"  Backup: {backup_path.name}")

        # Guardar Silver
        df_final.write_parquet(Config.SILVER_PARQUET, compression="zstd")
        size_mb = Config.SILVER_PARQUET.stat().st_size / (1024 * 1024)
        print(f"  Silver actualizado: {df_final.shape[0]:,} filas | {size_mb:.1f} MB")

        # Regenerar Gold
        df_gold = VRMTransformer.generar_gold(df_final)
        df_gold.write_parquet(Config.GOLD_PARQUET, compression="zstd")
        print(f"  Gold regenerado: {df_gold.shape[0]:,} filas x {df_gold.shape[1]} columnas")

        metrics["rows_new"] = df_new.shape[0]
        return metrics


# ============================================================================
# ORQUESTADOR
# ============================================================================

def run_bootstrap():
    """
    BOOTSTRAP: Une todos los consolidados históricos → Silver → Gold.
    Ejecutar UNA SOLA VEZ.

    Uso:
        from vrm_pipeline_medallion import run_bootstrap
        run_bootstrap()
    """
    print("=" * 60)
    print("BOOTSTRAP: Historicos -> Silver -> Gold (VRM)")
    print("=" * 60)

    start = datetime.now()
    crear_estructura_directorios()

    df_silver = SilverLoader.bootstrap_historicos()

    duration = (datetime.now() - start).total_seconds()

    log_ingestion({
        "run_id": datetime.now().isoformat(),
        "tool_name": "vrm",
        "source_file": "BOOTSTRAP_HISTORICOS",
        "rows_read": df_silver.shape[0],
        "rows_new": df_silver.shape[0],
        "duration_sec": duration,
        "status": "SUCCESS",
    })

    print(f"\nBootstrap completado en {duration:.1f} segundos.")
    return df_silver


def run_daily(lista1_path: str, lista2_path: str, fecha_descarga: str = None):
    """
    CARGA DIARIA: 2 listas CSV → Bronze → Silver → Gold.

    Uso:
        from vrm_pipeline_medallion import run_daily
        run_daily(
            lista1_path=r"C:\Downloads\lista1.csv",
            lista2_path=r"C:\Downloads\lista2.csv",
            fecha_descarga="2026-04-06"
        )
    """
    print("=" * 60)
    print("CARGA INCREMENTAL DIARIA (VRM)")
    print("=" * 60)

    start = datetime.now()
    crear_estructura_directorios()

    # 1. Bronze
    print("\n1. BRONZE: Guardando archivos originales...")
    VRMExtractor.guardar_en_bronze(lista1_path, lista2_path, fecha_descarga)

    # 2. Extraccion
    print("\n2. EXTRACCION: Leyendo listas...")
    df_raw = VRMExtractor.leer_listas_csv(lista1_path, lista2_path)

    # 3. Validacion de schema
    SchemaValidator.validar(df_raw, f"listas_{fecha_descarga}")

    # 4. Transformacion
    print("\n3. TRANSFORMACION:")
    df_transformed = VRMTransformer.transformar_csv(df_raw)

    # 5. Carga
    print("\n4. CARGA:")
    metrics = SilverLoader.append_incremental(df_transformed)

    # 6. Log
    duration = (datetime.now() - start).total_seconds()

    log_ingestion({
        "run_id": datetime.now().isoformat(),
        "tool_name": "vrm",
        "source_file": f"listas_{fecha_descarga or date.today().isoformat()}",
        "rows_read": metrics["rows_read"],
        "rows_new": metrics["rows_new"],
        "duration_sec": duration,
        "status": "SUCCESS",
    })

    print(f"\n{'=' * 60}")
    print(f"RESUMEN")
    print(f"{'=' * 60}")
    print(f"  Filas leidas:     {metrics['rows_read']:,}")
    print(f"  Nuevas:           {metrics['rows_new']:,}")
    print(f"  Duracion:         {duration:.1f} seg")
    print(f"{'=' * 60}")


def regenerar_gold():
    """
    Regenera el Gold desde Silver sin modificar Silver.
    Usar cuando agregas/quitas columnas del GOLD_COLUMNS.

    Uso:
        from vrm_pipeline_medallion import regenerar_gold
        regenerar_gold()
    """
    print("=" * 60)
    print("REGENERANDO GOLD DESDE SILVER")
    print("=" * 60)

    df_silver = pl.read_parquet(Config.SILVER_PARQUET)
    print(f"Silver: {df_silver.shape[0]:,} filas x {df_silver.shape[1]} columnas")

    df_gold = VRMTransformer.generar_gold(df_silver)
    Config.GOLD_DIR.mkdir(parents=True, exist_ok=True)
    df_gold.write_parquet(Config.GOLD_PARQUET, compression="zstd")

    print(f"Gold regenerado: {Config.GOLD_PARQUET}")
    print(f"  {df_gold.shape[0]:,} filas x {df_gold.shape[1]} columnas")


if __name__ == "__main__":
    print("Pipeline VRM Medallion listo.")
    print("  run_bootstrap()    - Primera vez: unir historicos")
    print("  run_daily(...)     - Carga diaria: 2 listas CSV")
    print("  regenerar_gold()   - Actualizar Gold sin tocar Silver")
