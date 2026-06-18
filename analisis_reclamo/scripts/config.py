# =============================================================================
#  config.py  —  Análisis de Reclamos (Base 8850 / Master File)
#  Scotiabank Peru — Prevención de Fraude
# =============================================================================
#  INSTRUCCIONES:
#  1. Reemplaza cada valor entre comillas con el nombre EXACTO de la columna
#     en tu archivo de reclamos.
#  2. Si una columna no existe en tu base, deja el valor como "" (cadena vacía).
#  3. Ajusta PERIODO_INICIO y PERIODO_FIN según el rango que quieres analizar.
# =============================================================================

from pathlib import Path

# ─── RUTAS ───────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).resolve().parent.parent
FOLDER_DATA     = BASE_DIR / "data"
PARQUET_RAW     = FOLDER_DATA / "reclamos_raw.parquet"
PARQUET_FEATURES= FOLDER_DATA / "reclamos_features.parquet"
EXCEL_EDA       = BASE_DIR / "output" / "eda_reclamos_tdmc.xlsx"

# ─── PARÁMETROS DE ANÁLISIS ──────────────────────────────────────────────────
SEGMENTO_FOCO   = "TD_MC"      # "TD_MC" | "TD_VISA" | "TC" | "TODOS"
SKIPROWS        = 0            # 0 = encabezado en fila 1
FECHA_DAYFIRST  = True         # fechas vienen en formato dd/mm/yyyy

# Período de análisis (formato YYYY-MM-DD)
PERIODO_INICIO  = "2025-11-25"
PERIODO_FIN     = "2026-06-17"

# Flag: marcar enero-febrero como período de ataque Google
# (no excluye, solo agrega columna ES_PERIODO_GOOGLE para filtros)
MARCAR_PERIODO_GOOGLE = True
GOOGLE_INICIO   = "2026-01-01"
GOOGLE_FIN      = "2026-02-28"

# =============================================================================
#  DICCIONARIO DE COLUMNAS
#  CLAVE (izquierda) = nombre interno del script — NO tocar
#  VALOR (derecha)   = nombre EXACTO en tu archivo
# =============================================================================
COLS = {

    # ── FECHAS ────────────────────────────────────────────────────────────────
    "fecha_txn"         : "POS1_ACF-FECHA TRX",        # formato dd/mm/yyyy  ej: 28/09/2025
    "hora_txn"          : "POS1_ACF-HORA TRX",         # llega como "01/01/1900 12:51:45" — el script extrae solo HH:MM:SS
    "fecha_hora"        : "FECHA_HORA",                 # construida por el script (no viene en la base)
    # mes_anio se deriva de fecha_txn en feature_engineering — no se necesita columna

    # ── FECHA DE RECLAMO (exclusivo de esta base) ─────────────────────────────
    "fecha_reclamo"     : "POS1_ACF-FECHA ALERTA",     # formato dd/mm/yyyy — 1475 celdas vacías
    # IMPORTANTE: 1475 celdas vacías en esta columna — el script las maneja así:
    #   - Filas con fecha_reclamo vacía → DIAS_HASTA_RECLAMO = NaN, BUCKET_RECLAMO = "SIN_DATO"
    #   - Se agrega FLAG_SIN_FECHA_RECLAMO = 1 para identificarlas
    #   - NO se eliminan — siguen en el análisis para MCC, canal, BIN, monto, etc.

    # ── MONTOS ────────────────────────────────────────────────────────────────
    "monto"             : "POS1_ACF-MONTO EN MONEDA LOCAL",  # monto en soles
    "monto_dolar"       : "POS1_ACF-MONTO DOLLAR",           # equivalente en dólares
    "monto_original"    : "POS1_ACF-MONTO ORIGINAL TRX",     # monto en moneda original de la txn
    # moneda_trx eliminado — no disponible en esta base

    # ── TARJETA / CLIENTE ─────────────────────────────────────────────────────
    "tarjeta"           : "POS1_ACF-TARJETA",           # PAN desencriptado — BIN10/11/12 se extraen de aquí
    "bin"               : "POS1_ACF-BIN",               # primeros 6 dígitos del PAN
    "id_cliente"        : "POS1_ACF-ID CLIENTE",
    "fecha_vencimiento" : "POS1_ACF-V/TO",              # vencimiento (formato MMYY, ej: "0130" = ene-2030)
    "tipo_producto"     : "POS1_ACF-TIPO PROD TC",      # TC=Crédito | TD=Débito
    "marca"             : "POS1_ACF-MARCA O FRANQUICIA",
    "segmento"          : "POS1_ACF-SEGMENTO CLIENTE",  # ya viene como texto — sin mapeo de diccionario
    "organizacion"      : "POS1_ACF-ORGANIZACION",

    # ── COMERCIO / CANAL ──────────────────────────────────────────────────────
    "comercio_nom"      : "POS1_ACF-NOMBRE COMERCIO",
    "localidad_com"     : "POS1_ACF-LOCALIDAD COMERCIO",
    "mcc"               : "POS1_ACF-MCC",
    "canal"             : "POS1_ACF-CANAL",
    "entry_mode"        : "POS1_ACF-ENTRY MODE",
    "cod_cio"           : "POS1_ACF-CODIGO CIO",
    "cod_trx"           : "POS1_ACF-COD TRX",
    "pais"              : "POS1_ACF-PAIS ORIGEN",
    # NOTA pais: viene como nombre completo (ej: "PERU", "ESTADOS UNIDOS")
    "reverso"           : "POS1_ACF-REVERSO",

    # ── ADQUIRIENTE ───────────────────────────────────────────────────────────
    "tipo_adquiriente"  : "POS1_ACF-TIPO ADQUIRIENTE",
    # Valores: Niubiz, Izipay, Culqi, Openpay, VendeMas, etc.

    # ── MICROPAGO ─────────────────────────────────────────────────────────────
    "tipo_micropago"    : "POS1_ACF-TIPO MICROPAGO",
    # Valores: "MICROPAGO" (monto ≤ 150 soles) | "NO MICROPAGO"

    # ── SEGURIDAD ─────────────────────────────────────────────────────────────
    "eci"               : "POS1_ACF-ECI UCAF",          # 3DS (Visa=5 | MC=2)
    "cod_red_comercio"  : "POS1_ACF-COD RED COMERCIO",  # tipo CVV: S=Estático, D=Dinámico, E/N=Sin CVV
    "ind_recurrente"    : "POS1_ACF-IND RECURRENTE MOTO", # R=recurrente | M/O/T=MOTO

    # ── RESPUESTA ─────────────────────────────────────────────────────────────
    "cod_respuesta"     : "POS1_ACF-COD RPTA",
    "razon_respuesta"   : "POS1_ACF-RAZON RESPUESTA",
    # billetera, indicador, score_riesgo_mon, grupo_horario, q_transaccional
    # eliminados — no disponibles en esta base o toda la data es fraude confirmado
    # grupo_horario se crea en feature_engineering desde hora_txn
}

# =============================================================================
#  FILTROS DE SEGMENTACIÓN
# =============================================================================
FILTRO_MARCA = {
    "TD_MC"  : {"tipo": ["TD", "Debito"], "marca": ["5", "MASTERCARD", "MC"]},
    "TD_VISA": {"tipo": ["TD", "Debito"], "marca": ["4", "VISA"]},
    "TC"     : {"tipo": ["TC", "Credito"], "marca": []},
    "TODOS"  : {},
}

# =============================================================================
#  TABLAS DE REFERENCIA
# =============================================================================
MARCA_LABEL = {
    "4": "VISA",
    "5": "MASTERCARD",
}

TIPO_PROD_LABEL = {
    "TC": "Credito",
    "TD": "Debito",
}

# Tipo de adquiriente — valores conocidos (se extiende si aparecen nuevos)
ADQUIRIENTE_LABEL = {
    "NIUBIZ"   : "Niubiz",
    "IZIPAY"   : "Izipay",
    "CULQI"    : "Culqi",
    "OPENPAY"  : "Openpay",
    "VENDEMAS" : "VendeMas",
}

# Entry mode
ENTRY_MODE_LABEL = {
    "01": "Manual / Digitada",
    "05": "Chip",
    "07": "Chip NFC",
    "10": "Telefonia",
    "79": "Chip (fallback)",
    "80": "Chip fallback banda",
    "90": "Banda magnetica",
    "91": "Contactless / NFC",
    "00": "Sin especificar",
}
ENTRY_MODE_PRESENTE = {"05", "07", "79", "80", "90", "91"}
ENTRY_MODE_NP       = {"01", "10"}

# Países considerados locales (nombre completo, no código ISO)
PAISES_PERU = {"PERU", "PERÚ", "PE", "PER"}

# Umbrales para análisis de reclamos
UMBRAL_RECLAMO_TARDIO_DIAS  = 60   # reclamo después de 60 días → señal de autofraud
UMBRAL_RECLAMO_RAPIDO_DIAS  = 7    # reclamo antes de 7 días → cliente muy alerta
UMBRAL_MICROPAGO_MONTO      = 150  # monto ≤ 150 soles = micropago (card testing)
