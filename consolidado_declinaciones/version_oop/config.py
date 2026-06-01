"""
config.py — Configuración centralizada del pipeline.

Todas las rutas y constantes viven aquí. Si el proceso se mueve a otro
servidor o cambian los directorios, solo hay que editar este archivo.
"""
from pathlib import Path

DEBUG = False

# ---------------------------------------------------------------------------
# Rutas de entrada (archivos fuente)
# Los Golds los genera 10_proceso_declinaciones/run_diario.py
# y los deposita en 10_proceso_declinaciones/data_gold/
#
# AJUSTAR: cambia DIRECTORIO_PROCESO_DECLINACIONES a la ruta real en tu equipo
# ---------------------------------------------------------------------------
DIRECTORIO_PROCESO_DECLINACIONES = Path(
    r"C:\Users\s4930359\OneDrive - The Bank of Nova Scotia"
    r"\10_proceso_declinaciones"   # <-- ajustar si la ruta es diferente
)
DIRECTORIO_GOLD = DIRECTORIO_PROCESO_DECLINACIONES / "data" / "gold"

RUTA_VCAS       = DIRECTORIO_GOLD / "vcas_gold.parquet"
RUTA_VRM        = DIRECTORIO_GOLD / "vrm_gold.parquet"
RUTA_RT_DEBITO  = DIRECTORIO_GOLD / "rt_debito_gold.parquet"
RUTA_RT_CREDITO = DIRECTORIO_GOLD / "rt_credito_gold.parquet"
RUTA_BD_FRM     = r"C:\Users\s4930359\Data_Herramientas\BBDD_FRM\BBDD_FRM.accdb"

# ---------------------------------------------------------------------------
# Ruta de salida
# ---------------------------------------------------------------------------
DIRECTORIO_SALIDA   = Path(
    r"C:\Users\s4930359\OneDrive - The Bank of Nova Scotia"
    r"\Seguimiento_Consolidado_Herramientas"
)
RUTA_PARQUET_SALIDA  = DIRECTORIO_SALIDA / "MASTER_CONSOLIDADO.parquet"
RUTA_PARQUET_POWERBI = DIRECTORIO_SALIDA / "MASTER_POWERBI.parquet"

# ---------------------------------------------------------------------------
# Configuración de alertas y correo
# ---------------------------------------------------------------------------
VENTANA_DIAS_ZSCORE  = 30     # días de historia para calcular media/std
UMBRAL_ZSCORE        = 2.0    # desviaciones para considerar alerta
TOP_N_ALERTAS        = 10     # top N comercios y BIN6 en el reporte

DESTINATARIOS_CORREO = [
    "tucorreo@scotiabank.com",       # reemplaza con tu correo
    "jefe@scotiabank.com",           # reemplaza con el de tu jefe
    "compañero@scotiabank.com",      # reemplaza con el de tu compañero
]
