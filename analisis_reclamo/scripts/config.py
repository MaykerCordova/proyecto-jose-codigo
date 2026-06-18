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
    "fecha_txn"         : "POS_1_FECHA_TRX",           # fecha de la transacción (AAAAMMDD)
    "hora_txn"          : "POS_1_HORA_TRX",            # hora de la transacción (HH:MM:SS)
    "fecha_hora"        : "FECHA_HORA",                 # construida por el script (no viene en la base)
    # mes_anio se deriva de fecha_txn en feature_engineering — no se necesita columna

    # ── FECHA DE RECLAMO (exclusivo de esta base) ─────────────────────────────
    "fecha_reclamo"     : "POS_1_FECHA_RECLAMO",
    # IMPORTANTE: 1475 celdas vacías en esta columna — el script las maneja así:
    #   - Filas con fecha_reclamo vacía → DIAS_HASTA_RECLAMO = NaN, BUCKET_RECLAMO = "SIN_DATO"
    #   - Se agrega FLAG_SIN_FECHA_RECLAMO = 1 para identificarlas
    #   - NO se eliminan — siguen en el análisis para MCC, canal, BIN, monto, etc.

    # ── MONTOS ────────────────────────────────────────────────────────────────
    "monto"             : "POS_1_MONTO_MONEDA_LOCAL",  # monto en soles
    "monto_dolar"       : "POS_1_MONTO_DOLLAR",        # equivalente en dólares
    "monto_original"    : "POS_1_MONTO_ORIGINAL_TRX",  # monto en moneda original de la txn
    # moneda_trx eliminado — no disponible en esta base

    # ── TARJETA / CLIENTE ─────────────────────────────────────────────────────
    "tarjeta"           : "POS_1_TARJETA",              # PAN desencriptado — BIN10/11/12 se extraen de aquí
    "bin"               : "POS_1_BIN",                  # primeros 6 dígitos del PAN
    "id_cliente"        : "POS_1_ID_CLIENTE",
    "fecha_vencimiento" : "POS_1_V_TO",                 # vencimiento (formato MMYY, ej: "0130" = ene-2030)
    "tipo_producto"     : "POS_1_TIPO_PROD_TC",         # TC=Crédito | TD=Débito
    "marca"             : "POS_1_MARCA_O_FRANQUICIA",   # marca de la tarjeta (Visa/MC)
    "segmento"          : "POS_1_SEGMENTO_CLIENTE",     # segmento ya viene como texto — no necesita mapeo
    "organizacion"      : "POS_1_ORGANIZACION",         # SBP / CSF
    # tarjeta_col1, tarjeta_col2, tarjeta_enc, saldo, num_autorizacion,
    # num_trx, cod_hash eliminados — no disponibles o no necesarios

    # ── COMERCIO / CANAL ──────────────────────────────────────────────────────
    "comercio_nom"      : "POS_1_NOMBRE_COMERCIO",
    "localidad_com"     : "POS_1_LOCALIDAD_COMERCIO",
    "mcc"               : "POS_1_MCC",
    "canal"             : "POS_1_CANAL",
    "entry_mode"        : "POS_1_ENTRY_MODE",
    "cod_cio"           : "POS_1_CODIGO_CIO",
    "cod_trx"           : "POS_1_COD_TRX",
    "pais"              : "POS_1_PAIS_ORIGEN",
    # NOTA pais: viene como nombre completo (ej: "PERU", "ESTADOS UNIDOS"),
    #            NO como código ISO. El script filtra por texto, no por número.
    "reverso"           : "POS_1_REVERSO",

    # ── ADQUIRIENTE ───────────────────────────────────────────────────────────
    "tipo_adquiriente"  : "POS_1_TIPO_ADQUIRIENTE",
    # Valores: Niubiz, Izipay, Culqi, Openpay, VendeMas, etc.
    # Útil para identificar si ciertos adquirientes concentran más reclamos

    # ── MICROPAGO ─────────────────────────────────────────────────────────────
    "tipo_micropago"    : "POS_1_TIPO_MICROPAGO",
    # Valores: "MICROPAGO" (monto ≤ 150 soles) | "NO MICROPAGO"
    # Señal de card testing: muchos MICROPAGO de mismo BIN en el mismo día

    # ── SEGURIDAD ─────────────────────────────────────────────────────────────
    "eci"               : "POS_1_ECI_UCAF",             # 3DS (Visa=5 | MC=2)
    "cod_red_comercio"  : "POS_1_COD_RED_COMERCIO",     # tipo CVV: S=Estático, D=Dinámico, E/N=Sin CVV
    "ind_recurrente"    : "POS_1_IND_RECURRENTE_MOTO",  # R=recurrente | M/O/T=MOTO

    # ── RESPUESTA ─────────────────────────────────────────────────────────────
    "cod_respuesta"     : "POS_1_COD_RPTA",
    "razon_respuesta"   : "POS_1_RAZON_RESPUESTA",
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
