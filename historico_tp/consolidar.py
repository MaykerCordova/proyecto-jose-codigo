"""
Consolidador de histórico TP (Tarjeta Presente)
Lee todos los Excel de las carpetas YYYY_M dentro de la carpeta raíz
y genera un único archivo Parquet consolidado.
"""

import pandas as pd
from pathlib import Path
import re
import logging

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
# Cambiar esta ruta en la laptop de la empresa
CARPETA_HISTORICO = Path(r"C:\RUTA\A\histórico TP")

# Archivo de salida (en la misma carpeta de este script por defecto)
ARCHIVO_SALIDA = Path(__file__).parent / "historico_tp_consolidado.parquet"

# Filas a saltear antes del encabezado (encabezado en fila 5 de Excel = skiprows=4)
SKIP_ROWS = 4
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

PATRON_CARPETA = re.compile(r"^\d{4}_\d{1,2}$")


def leer_excel(ruta: Path, carpeta: str) -> pd.DataFrame | None:
    try:
        df = pd.read_excel(ruta, skiprows=SKIP_ROWS, engine="openpyxl")
        df.columns = df.columns.str.strip()
        df["_fuente_carpeta"] = carpeta
        df["_fuente_archivo"] = ruta.name
        return df
    except Exception as e:
        log.warning(f"  No se pudo leer {ruta.name}: {e}")
        return None


def clave_orden(nombre_carpeta: str) -> tuple[int, int]:
    """Convierte '2025_6' en (2025, 6) para ordenar correctamente."""
    partes = nombre_carpeta.split("_")
    return int(partes[0]), int(partes[1])


def consolidar():
    if not CARPETA_HISTORICO.exists():
        log.error(f"La carpeta no existe: {CARPETA_HISTORICO}")
        return

    carpetas = sorted(
        [c for c in CARPETA_HISTORICO.iterdir() if c.is_dir() and PATRON_CARPETA.match(c.name)],
        key=lambda c: clave_orden(c.name),
    )

    if not carpetas:
        log.error("No se encontraron carpetas con formato YYYY_M dentro de la ruta indicada.")
        return

    log.info(f"Carpetas encontradas: {[c.name for c in carpetas]}")

    frames: list[pd.DataFrame] = []
    columnas_referencia: set | None = None
    advertencias_columnas: list[str] = []

    for carpeta in carpetas:
        excels = sorted(carpeta.glob("*.xlsx")) + sorted(carpeta.glob("*.xls"))
        if not excels:
            log.warning(f"[{carpeta.name}] Sin archivos Excel.")
            continue

        log.info(f"[{carpeta.name}] Procesando {len(excels)} archivo(s)...")

        for excel in excels:
            df = leer_excel(excel, carpeta.name)
            if df is None:
                continue

            columnas_datos = set(df.columns) - {"_fuente_carpeta", "_fuente_archivo"}

            if columnas_referencia is None:
                columnas_referencia = columnas_datos
                log.info(f"  Columnas de referencia ({len(columnas_referencia)}): tomadas de {excel.name}")
            else:
                faltantes = columnas_referencia - columnas_datos
                extras = columnas_datos - columnas_referencia
                if faltantes or extras:
                    msg = f"  [{carpeta.name}/{excel.name}]"
                    if faltantes:
                        msg += f" FALTAN: {sorted(faltantes)}"
                    if extras:
                        msg += f" EXTRAS: {sorted(extras)}"
                    log.warning(msg)
                    advertencias_columnas.append(msg)

            frames.append(df)
            log.info(f"  OK  {excel.name}  ({len(df):,} filas)")

    if not frames:
        log.error("No se pudo leer ningún archivo.")
        return

    log.info("Consolidando...")
    # sort=False respeta el orden de columnas del primer archivo;
    # las columnas que falten en algún frame quedan como NaN automáticamente.
    consolidado = pd.concat(frames, ignore_index=True, sort=False)

    log.info(f"Total filas consolidadas: {len(consolidado):,}")
    log.info(f"Total columnas: {len(consolidado.columns)}")

    # Normalizar columnas con tipos mixtos (ej: '000' string vs número)
    # para que pyarrow pueda guardar el Parquet sin error.
    cols_objeto = consolidado.select_dtypes(include="object").columns
    for col in cols_objeto:
        tiene_mixto = consolidado[col].apply(type).nunique() > 1
        if tiene_mixto:
            log.warning(f"  Columna con tipos mixtos, convirtiendo a texto: '{col}'")
            consolidado[col] = consolidado[col].where(
                consolidado[col].isna(),
                consolidado[col].astype(str),
            )

    consolidado.to_parquet(ARCHIVO_SALIDA, index=False, engine="pyarrow")
    log.info(f"Archivo guardado: {ARCHIVO_SALIDA}")

    if advertencias_columnas:
        log.warning(f"\n{'='*60}")
        log.warning(f"Se encontraron {len(advertencias_columnas)} archivo(s) con columnas distintas:")
        for adv in advertencias_columnas:
            log.warning(adv)
        log.warning("Esas columnas faltantes quedaron como NaN en el consolidado.")
        log.warning("="*60)
    else:
        log.info("Validación de columnas OK: todos los archivos tienen las mismas columnas.")


if __name__ == "__main__":
    consolidar()
