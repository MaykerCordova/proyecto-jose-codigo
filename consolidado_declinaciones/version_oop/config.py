"""
config.py — Configuración centralizada del pipeline.

Todas las rutas y constantes viven aquí. Si el proceso se mueve a otro
servidor o cambian los directorios, solo hay que editar este archivo.
"""
from pathlib import Path

DEBUG = False

# ---------------------------------------------------------------------------
# Rutas de entrada (archivos fuente)
# ---------------------------------------------------------------------------
DIRECTORIO_DATOS    = Path(r"C:\Users\s4930359\Data_Herramientas\data\silver")

RUTA_VCAS           = DIRECTORIO_DATOS / "VCAS_unitario.parquet"
RUTA_VRM            = DIRECTORIO_DATOS / "vrm_gold.parquet"
RUTA_RT_DEBITO      = DIRECTORIO_DATOS / "rt_debito_gold.parquet"
RUTA_RT_CREDITO     = DIRECTORIO_DATOS / "rt_credito_consolidated.parquet"
RUTA_BD_FRM         = r"C:\Users\s4930359\Data_Herramientas\BBDD_FRM\BBDD_FRM.accdb"

# ---------------------------------------------------------------------------
# Ruta de salida
# ---------------------------------------------------------------------------
DIRECTORIO_SALIDA   = Path(
    r"C:\Users\s4930359\OneDrive - The Bank of Nova Scotia"
    r"\Seguimiento_Consolidado_Herramientas"
)
RUTA_PARQUET_SALIDA = DIRECTORIO_SALIDA / "MASTER_CONSOLIDADO.parquet"
