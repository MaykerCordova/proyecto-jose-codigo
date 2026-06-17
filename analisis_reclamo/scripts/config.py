# =============================================================================
#  config.py  —  Análisis de Reclamos (Base 8850 / Master File)
#  Scotiabank Peru — Prevención de Fraude
# =============================================================================
#  INSTRUCCIONES:
#  1. Reemplaza cada valor entre comillas con el nombre EXACTO de la columna
#     en tu archivo de reclamos (todas tienen prefijo POS_1_ adelante).
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
SKIPROWS        = 4            # filas a saltear antes del encabezado (ajustar)

# Período de análisis (formato YYYY-MM-DD)
PERIODO_INICIO  = "2025-11-25"   # inicio fiscal year canadiense
PERIODO_FIN     = "2026-06-16"   # hoy

# Flag: marcar enero-febrero como período de ataque Google
# (no excluye, solo agrega columna ES_PERIODO_GOOGLE para filtros)
MARCAR_PERIODO_GOOGLE = True
GOOGLE_INICIO   = "2026-01-01"
GOOGLE_FIN      = "2026-02-28"

# =============================================================================
#  DICCIONARIO DE COLUMNAS
#  CLAVE (izquierda) = nombre interno del script — NO tocar
#  VALOR (derecha)   = nombre EXACTO en tu archivo con prefijo POS_1_
#                      Reemplaza "POS_1_NOMBRE_COLUMNA" por el nombre real.
# =============================================================================
COLS = {

    # ── FECHAS ────────────────────────────────────────────────────────────────
    "fecha_txn"         : "POS_1_FECHA_TRX",           # fecha de la transacción (AAAAMMDD)
    "hora_txn"          : "POS_1_HORA_TRX",            # hora de la transacción (HH:MM:SS)
    "fecha_hora"        : "FECHA_HORA",                 # construida por el script (no viene en la base)
    "mes_anio"          : "POS_1_MES_DEL_ANO",         # mes y año de la txn

    # ── FECHA DE RECLAMO (exclusivo de esta base) ─────────────────────────────
    "fecha_reclamo"     : "POS_1_FECHA_RECLAMO",       # fecha en que el cliente reclamó
    # Nota: DIAS_HASTA_RECLAMO = fecha_reclamo - fecha_txn (calculado en feature_engineering)
    # Si la base trae otro nombre para fecha de reclamo, ajustar aquí

    # ── MONTOS ────────────────────────────────────────────────────────────────
    "monto"             : "POS_1_MONTO_MONEDA_LOCAL",  # monto en soles
    "monto_dolar"       : "POS_1_MONTO_DOLLAR",        # equivalente en dólares
    "monto_original"    : "POS_1_MONTO_ORIGINAL_TRX",  # monto en moneda original de la txn
    "moneda_trx"        : "POS_1_COD_MONEDA_TRX",      # código ISO de moneda (604=PEN, 840=USD)

    # ── TARJETA / CLIENTE ─────────────────────────────────────────────────────
    "tarjeta_col1"      : "POS_1_TARJETA_REG_750",     # posiciones 1-6 y 13+ del PAN
    "tarjeta_col2"      : "POS_1_TARJETA_POS_7_6D",    # posiciones 7-12 (6 dígitos del medio)
    "tarjeta_enc"       : "POS_1_TARJETA_ENCRIPTADA",  # versión encriptada (auditoría)
    "bin"               : "POS_1_BIN",                  # primeros 6 dígitos del PAN
    "id_cliente"        : "POS_1_ID_CLIENTE",           # clave de cliente
    "fecha_vencimiento" : "POS_1_V_TO",                 # vencimiento de la tarjeta (ACF-V/TO)
    "tipo_producto"     : "POS_1_TIPO_PROD_TC",         # TC=Crédito | TD=Débito
    "marca"             : "POS_1_MARCA_O_FRANQUICIA",   # marca de la tarjeta (Visa/MC)
    "segmento"          : "POS_1_SEGMENTO_CLIENTE",     # segmento del cliente
    "organizacion"      : "POS_1_ORGANIZACION",         # organización (SBP / CSF)
    "saldo"             : "POS_1_SALDO_DISPONIBLE",     # saldo disponible

    # ── IDENTIFICADORES DE TRANSACCIÓN ───────────────────────────────────────
    "num_autorizacion"  : "POS_1_AUTORIZACION",         # código de autorización
    "num_trx"           : "POS_1_NUMERO_TRX",           # número de transacción
    "cod_hash"          : "POS_1_CODIGO_HASH",          # hash único de la transacción

    # ── COMERCIO / CANAL ──────────────────────────────────────────────────────
    "comercio_nom"      : "POS_1_NOMBRE_COMERCIO",      # nombre del comercio
    "localidad_com"     : "POS_1_LOCALIDAD_COMERCIO",   # ciudad/localidad del comercio
    "mcc"               : "POS_1_MCC",                  # código de categoría de comercio
    "canal"             : "POS_1_CANAL",                 # canal de la transacción
    "entry_mode"        : "POS_1_ENTRY_MODE",            # modo de ingreso de tarjeta
    "cod_cio"           : "POS_1_CODIGO_CIO",            # código de comercio (CIO)
    "cod_trx"           : "POS_1_COD_TRX",               # código de tipo de operación
    "pais"              : "POS_1_PAIS_ORIGEN",           # país de origen de la txn
    "reverso"           : "POS_1_REVERSO",               # S/N si fue reversada

    # ── SEGURIDAD ─────────────────────────────────────────────────────────────
    "eci"               : "POS_1_ECI_UCAF",              # seguridad 3DS (Visa=5 | MC=2)
    "cod_red_comercio"  : "POS_1_COD_RED_COMERCIO",      # tipo CVV (S/D/E/N)
    "ind_recurrente"    : "POS_1_IND_RECURRENTE_MOTO",   # R=recurrente | M/O/T=MOTO

    # ── BILLETERA DIGITAL ────────────────────────────────────────────────────
    "billetera"         : "POS_1_RESERVADO_ALFA_2",      # primeros 5 chars = billetera

    # ── INDICADOR Y RESPUESTA ─────────────────────────────────────────────────
    "indicador"         : "POS_1_INDICADOR_FRAUDE",      # en reclamos: F o vacío
    "cod_respuesta"     : "POS_1_COD_RPTA",              # código de respuesta
    "razon_respuesta"   : "POS_1_RAZON_RESPUESTA",       # texto de respuesta

    # ── SCORE DEL MONITOR ─────────────────────────────────────────────────────
    "score_riesgo_mon"  : "POS_1_SCORE_DE_RIESGO",       # Visa: 0-99 | MC: 0-999
    "grupo_horario"     : "POS_1_GRUPO_DE_HORARIO",
    "q_transaccional"   : "POS_1_K05_COUNTMP",           # volumen del comercio mes anterior
}

# =============================================================================
#  FILTROS DE SEGMENTACIÓN
#  Ajustar según el segmento que analizas
# =============================================================================
FILTRO_MARCA = {
    "TD_MC"  : {"tipo": ["TD", "Debito"], "marca": ["5", "MASTERCARD", "MC"]},
    "TD_VISA": {"tipo": ["TD", "Debito"], "marca": ["4", "VISA"]},
    "TC"     : {"tipo": ["TC", "Credito"], "marca": []},   # TC todas las marcas
    "TODOS"  : {},
}

# =============================================================================
#  TABLAS DE REFERENCIA (igual que pipeline ecommerce)
# =============================================================================
MARCA_LABEL = {
    "4": "VISA",
    "5": "MASTERCARD",
}

TIPO_PROD_LABEL = {
    "TC": "Credito",
    "TD": "Debito",
}

# Segmento cliente
SEG_NOMBRE = {
    "30": "Beyond",             "99": "Polo Dirección",
    "31": "Premium",            "32": "Preferente",
    "33": "Personal",           "34": "Estándar",
    "5" : "Inst. Financieras",  "21": "Corporativo",
    "2" : "Mediano Empresas",   "15": "Sector Gobierno",
    "16": "Otras Instituciones",
    "3" : "Pequeñas Empresas",  "4" : "Negocios 2",
    "7" : "Negocios 3",         "8" : "Negocios 1",
    "13": "Microempresas",
}

# Billetera digital
BILLETERA_LABEL = {
    "75001": "Google Pay VISA",
    "32703": "Apple Pay VISA / MC",
    "34693": "Apple Pay MC",
    "99999": "No tokenizada",
}

# Entry mode
ENTRY_MODE_LABEL = {
    "01": "Manual / Digitada",
    "05": "Chip",
    "07": "Chip sin contacto (NFC)",
    "10": "Telefonia",
    "79": "Chip (fallback)",
    "80": "Chip fallback banda",
    "90": "Banda magnetica",
    "91": "Contactless / NFC",
    "00": "Sin especificar",
}
ENTRY_MODE_PRESENTE = {"05", "07", "79", "80", "90", "91"}
ENTRY_MODE_NP       = {"01", "10"}

# Umbrales para análisis de reclamos
UMBRAL_RECLAMO_TARDIO_DIAS  = 60   # reclamo después de 60 días → señal de autofraud
UMBRAL_RECLAMO_RAPIDO_DIAS  = 7    # reclamo antes de 7 días → cliente muy alerta
