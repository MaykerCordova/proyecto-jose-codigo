# =============================================================================
#  config.py  —  Pipeline Análisis Tarjetas Comprometidas N7 Débito
#  Scotiabank Peru — Prevención de Fraude
# =============================================================================
#  INSTRUCCIONES:
#  1. Deja ANALISIS_NOMBRE tal como está o renómbralo (aparece en el Excel output)
#  2. Pon los Excel de Monitor en  data/comprometidas/
#  3. Indica si el journal tiene solo aprobadas o aprobadas+denegadas (SOLO_APROBADAS)
#  4. Revisa COLS y ajusta valores si tu Monitor usa nombres distintos
#  5. Ejecuta en orden:
#       python scripts/consolidar.py
#       python scripts/feature_engineering.py
#       python scripts/analisis.py
# =============================================================================

from pathlib import Path

# ─── NOMBRE DEL ANÁLISIS ─────────────────────────────────────────────────────
ANALISIS_NOMBRE = "TARJETAS_COMPROMETIDAS_N7"

# ─── RUTAS ───────────────────────────────────────────────────────────────────
BASE_DIR            = Path(__file__).resolve().parent.parent
FOLDER_JOURNALS     = BASE_DIR / "data" / "comprometidas"
PARQUET_CONSOLIDADO = BASE_DIR / "data" / "consolidado.parquet"
PARQUET_FEATURES    = BASE_DIR / "data" / "consolidado_features.parquet"
EXCEL_OUTPUT        = BASE_DIR / "output" / f"analisis_{ANALISIS_NOMBRE}.xlsx"

# ─── TIPO DE JOURNAL ─────────────────────────────────────────────────────────
#  True  → solo transacciones APROBADAS
#  False → APROBADAS + DENEGADAS (recomendado para tarjetas comprometidas)
SOLO_APROBADAS = False

# ─── FILA DE ENCABEZADO ──────────────────────────────────────────────────────
SKIPROWS = 4    # El header está en la fila 5 → saltar las 4 primeras

# =============================================================================
#  DICCIONARIO DE COLUMNAS
#  - La CLAVE (izquierda) la usa el script internamente. NO la toques.
#  - El VALOR (derecha) es el nombre real de la columna en tu Excel de Monitor.
# =============================================================================
COLS = {

    # ── TARJETA (se construye combinando dos columnas) ────────────────────────
    "tarjeta_col1"     : "ACF-TARJETA REGISTRO 750",
    "tarjeta_col2"     : "ACF-TARJETA POS 7,6 DIGITOS",
    "tarjeta_enc"      : "ACF-NUMERO DE TARJETA ENCRIPTADO AES",

    # ── IDENTIFICADORES ───────────────────────────────────────────────────────
    "bin"              : "ACF-BIN",
    "id_cliente"       : "ACF-ID CLIENTE",
    "num_autorizacion" : "ACF-AUTORIZACION",
    "num_trx"          : "ACF-NUMERO TRX",
    "cod_hash"         : "ACF-CODIGO HASH",

    # ── FECHAS Y HORA ─────────────────────────────────────────────────────────
    "fecha_trx"        : "ACF-FECHA TRX",
    "hora_trx"         : "ACF-HORA TRX",
    "hora_sin_min"     : "ACF-HORA SIN MINUTOS DE LA TRX",
    "mes_anio"         : "ACF-MES DEL ANO DE LA TRX",
    "fecha_hora"       : "FECHA_HORA",

    # ── MONTOS ────────────────────────────────────────────────────────────────
    "monto"            : "ACF-MONTO EN MONEDA LOCAL",
    "monto_dolar"      : "ACF-MONTO DOLLAR",
    "monto_original"   : "ACF-MONTO ORIGINAL DE LA TRANSACCION",
    # monto_original == monto_dolar  → transacción en USD
    # monto_original == monto_local  → transacción en PEN (soles)

    # ── TARJETA / CLIENTE ─────────────────────────────────────────────────────
    "tipo_producto"    : "ACF-TIPO PROD TC",
    "saldo"            : "ACF-SALDO DISPONIBLE EN MONEDA TRX",
    "segmento"         : "VAA-EVENTO DE COMPROMISO OTRA FUENTE",
    "organizacion"     : "ACF-ORGANIZACION",
    "marca"            : "ACF-MARCA",

    # ── COMERCIO / TRANSACCIÓN ────────────────────────────────────────────────
    "comercio_nom"     : "ACF-NOMBRE/LOCALIZACION COMERCIO",
    "localidad_com"    : "ACF-LOCALIDAD COMERCIO",
    "canal"            : "ACF-CANAL",
    "entry_mode"       : "ACF-ENTRY MODE",
    "mcc"              : "ACF-MCC +",
    "cod_cio"          : "ACF-CODIGO CIO/AGENCIA/OFICINA ORIGEN",
    "cod_trx"          : "ACF-COD TRX",
    "v_to"             : "ACF-V/TO",
    "reverso"          : "ACF-REVERSO",

    # ── SEGURIDAD / CVV ───────────────────────────────────────────────────────
    "eci"              : "ACF-ECI/UCAF",
    "cod_red_comercio" : "ACF-COD RED COMERCIO",
    "ind_recurrente"   : "ACF-INDICADOR RECURRENTE / MOTO",

    # ── BILLETERA DIGITAL ─────────────────────────────────────────────────────
    "billetera"        : "RESERVADO ALFA 2",

    # ── RESPUESTA / INDICADOR ─────────────────────────────────────────────────
    "indicador"        : "ACF-INDICADOR DE FRAUDE",   # F=fraude G=buena P=pendiente D=descarte N=normal
    "cod_respuesta"    : "ACF-COD RPTA",
    "razon_respuesta"  : "ACF-RAZON RESPUESTA",
    "cod_rpta_vplus"   : "CODIGO DE RESPUESTA VISION PLUS",

    # ── COMERCIO — PRECALCULADAS POR MONITOR ─────────────────────────────────
    "q_transaccional"  : "CC : K05_COUNTMP_TAMANO COMERCIO",
    "score_riesgo_mon" : "SCORE DE RIESGO",

    # ── COLUMNAS YA PROCESADAS POR MONITOR ───────────────────────────────────
    "grupo_horario"    : "ACF-GRUPO DE HORARIO",
    "dia_semana_mon"   : "ACF-DIA DE LA SEMANA DE LA TRX",

    # ── PAÍS ──────────────────────────────────────────────────────────────────
    "pais"             : "ACF-PAIS ORIGEN 87519",

}

# =============================================================================
#  UMBRALES DE REGLAS CONFIGURABLES
#  Punto de partida: tu jefe mencionó >25 soles como referencia.
#  El script generará un análisis de efectividad por cada umbral.
# =============================================================================
UMBRALES_REGLA = {
    "monto_acum_24h" : [25, 50, 100, 200, 500],   # S/ acumulado por tarjeta en 24h
    "trx_en_5min"    : [2, 3, 4, 5],
    "trx_en_10min"   : [3, 4, 5],
    "trx_en_1h"      : [3, 5, 7, 10],
}

# =============================================================================
#  RANGOS DE MONTO — referencia para tarjetas débito comprometidas
# =============================================================================
RANGOS_MONTO_RUBRO = {
    "CARD_TESTING"  : [0,   5,  10,   25,  99999],   # montos típicos de prueba de tarjeta
    "BAJO_VALOR"    : [0,  25,  50,  100,  99999],
    "MEDIO_VALOR"   : [0, 100, 200,  500,  99999],
    "ALTO_VALOR"    : [0, 200, 500, 1000,  99999],
}

# =============================================================================
#  TABLAS DE REFERENCIA
# =============================================================================

ORG_NOMBRE = {}

SEG_NOMBRE = {
    "30": "Beyond",             "99": "Beyond",
    "31": "Premium",            "32": "Preferente",
    "33": "Personal",           "34": "Estandar",
    "5":  "Inst. Financieras",  "21": "Corporativo",
    "2":  "Mediano Empresas",   "15": "Sector Gobierno",
    "16": "Otras Instituciones",
    "3":  "Pequenas Empresas",  "4":  "Negocios 2",
    "7":  "Negocios 3",         "8":  "Negocios 1",
    "13": "Microempresas",
}
SEG_GRUPO = {
    "30": "Beyond",             "99": "Beyond",
    "31": "Emerging Affluent",  "32": "Emerging Affluent",
    "33": "Top of Mass",        "34": "Mass",
    "5":  "Corporate",          "21": "Corporate",
    "2":  "Commercial",         "15": "Commercial",
    "16": "Commercial",
    "3":  "Small Business",     "4":  "Small Business",
    "7":  "Small Business",     "8":  "Small Business",
    "13": "Small Business",
}

COD_RED_LABEL = {
    "S": "Estatico (TD)",
    "D": "Dinamico (TD/TC)",
    "E": "Estatico (TC)",
    "N": "Sin CVV / No Match",
}

BILLETERA_LABEL = {
    "75001": "Google Pay VISA",
    "32703": "Apple Pay VISA / MC",
    "34693": "Apple Pay MC",
    "99999": "No tokenizada",
}
BILLETERA_DEFAULT = "Tokenizada (no identificada)"

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
ENTRY_MODE_PRESENTE  = {"05", "07", "79", "80", "90", "91"}
ENTRY_MODE_NP        = {"01", "10"}

MARCA_LABEL = {
    "4": "VISA",
    "5": "MASTERCARD",
}

TIPO_PROD_LABEL = {
    "TC": "Credito",
    "TD": "Debito",
}

CODIGOS_CRITICOS = {"N7", "14", "04", "51"}

# MCC de alto riesgo para tarjetas débito comprometidas
MCC_ALTO_RIESGO = {
    "6011", "6012",         # ATM / cash advance
    "7995",                 # gambling
    "4814", "4816",         # telecom / VOIP
    "5912",                 # farmacias (carding frecuente)
    "5411",                 # supermercados (monto test)
    "6051",                 # casas de cambio / crypto
    "5999", "5411",         # misc retail
}

FERIADOS_PERU = {
    "2025-01-01", "2025-04-17", "2025-04-18", "2025-05-01",
    "2025-06-07", "2025-06-29", "2025-07-28", "2025-07-29",
    "2025-08-30", "2025-10-08", "2025-11-01", "2025-12-08", "2025-12-25",
    "2026-01-01", "2026-04-02", "2026-04-03", "2026-05-01",
    "2026-06-07", "2026-06-29", "2026-07-28", "2026-07-29",
    "2026-08-30", "2026-10-08", "2026-11-01", "2026-12-08", "2026-12-25",
}

FECHAS_ESPECIALES = {
    "05-11": "Dia de la Madre",
    "06-15": "Dia del Padre",
    "12-24": "Noche Buena",
    "12-31": "Fin de Anio",
    "11-11": "11/11 Cyberday",
    "11-29": "Black Friday (aprox)",
    "02-14": "San Valentin",
}

DIAS_PAGO = {15, 30, 31}

# =============================================================================
#  CLASIFICADOR DE MOTIVOS DE RECHAZO
# =============================================================================
def clasificar_motivo(razon: str) -> str:
    r = str(razon).upper()
    if any(k in r for k in ["CVV", "CVC", "CODIGO SEGURIDAD", "SECURITY CODE", "N7"]):
        return "CVV_FAIL"
    if any(k in r for k in ["FONDOS", "SALDO", "NSF", "INSUFFICIENT", "51"]):
        return "FONDOS_INSUF"
    if any(k in r for k in ["EXCEDE", "LIMITE", "LIMIT", "EXCEED"]):
        return "EXCEDE_LIMITE"
    if any(k in r for k in ["BLOQUEAD", "BLOCKED", "RESTRICT", "04"]):
        return "TARJETA_BLOQ"
    if any(k in r for k in ["EXPIR", "VENCID"]):
        return "TARJETA_EXP"
    if any(k in r for k in ["PIN"]):
        return "PIN_FAIL"
    if any(k in r for k in ["3DS", "AUTHEN", "AUTENT"]):
        return "AUTH_FAIL"
    if any(k in r for k in ["INVALID", "INVAL", "NO MATCH", "NO COINCID", "14"]):
        return "DATO_INVALIDO"
    if "APROBAD" in r or r.strip() in {"00", "0", "000"}:
        return "N/A"
    return "OTRO"
