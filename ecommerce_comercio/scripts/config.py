# =============================================================================
#  config.py  —  Pipeline de Análisis Ecommerce por Comercio
# =============================================================================
#  INSTRUCCIONES:
#  1. Cambia COMERCIO_NOMBRE al nombre del comercio que vas a analizar
#  2. Pon los Excel de Monitor en  data/journals/
#  3. Ejecuta:  python scripts/consolidar.py
#              python scripts/feature_engineering.py
#              python scripts/analisis.py
# =============================================================================

from pathlib import Path

# ─── NOMBRE DEL COMERCIO ─────────────────────────────────────────────────────
COMERCIO_NOMBRE = "COMERCIO_EJEMPLO"   # <-- CAMBIA AQUÍ (ej. "AMAZON", "SAGAFALABELLA")

# ─── RUTAS ───────────────────────────────────────────────────────────────────
BASE_DIR           = Path(__file__).resolve().parent.parent   # carpeta ecommerce_comercio/
FOLDER_JOURNALS    = BASE_DIR / "data" / "journals"           # aquí van los Excel de Monitor
PARQUET_CONSOLIDADO= BASE_DIR / "data" / "consolidado.parquet"
PARQUET_FEATURES   = BASE_DIR / "data" / "consolidado_features.parquet"
EXCEL_OUTPUT       = BASE_DIR / "output" / f"analisis_{COMERCIO_NOMBRE}.xlsx"

# ─── TIPO DE JOURNAL ─────────────────────────────────────────────────────────
#  True  → el journal contiene SOLO transacciones APROBADAS
#           (features de rechazo/CVV no se calculan — no hay denegadas)
#  False → el journal contiene APROBADAS + DENEGADAS (análisis completo)
SOLO_APROBADAS = False

# ─── CARGA DE JOURNALS ───────────────────────────────────────────────────────
SKIPROWS = 3    # header en fila 4 → saltar las 3 primeras

# ─── COLUMNAS REALES DE MONITOR (prefijo ACF) ────────────────────────────────
#  Cambia el VALOR si tu parquet usa un nombre distinto.
#  No toques la CLAVE porque el script la usa internamente.
COLS = {
    # ── Identificadores ──────────────────────────────────────────────────────
    "tarjeta"          : "ACF-TARJETA REGISTRO 750",           # débito; crédito = ACF-Tarjeta SHA256
    "bin"              : "ACF-BIN",
    "id_cliente"       : "ACF-ID CLIENTE",
    "comercio_nom"     : "ACF-NOMBRE/LOCALIZACION COMERCIO",

    # ── Fechas (columnas crudas de Monitor) ───────────────────────────────────
    "fecha_trx"        : "ACF-FECHA TRX",                      # formato AAAAMMDD (ej. 20250115)
    "hora_trx"         : "ACF-HORA TRX",                       # formato HH:MM:SS  (ej. 14:32:07)
    # columna construida por consolidar.py:
    "fecha_hora"       : "FECHA_HORA",                         # datetime combinado YYYY-MM-DD HH:MM:SS

    # ── Montos ────────────────────────────────────────────────────────────────
    "monto"            : "ACF-MONTO EN MONEDA LOCAL",
    "monto_dolar"      : "ACF-MONTO DOLLAR",

    # ── Tarjeta / cliente ─────────────────────────────────────────────────────
    "tipo_producto"    : "ACF-TIPO PROD TC",                   # tipo de producto (TC/TD)
    "saldo"            : "ACF-SALDO DISPONIBLE EN MONEDA TRX",
    "segmento"         : "VAA-EVENTO DE COMPROMISO OTRA FUENTE",
    "organizacion"     : "ACF-ORGANIZACION",                   # SBP = Scotiabank | CSF = Santander
    "marca"            : "",                                   # franquicia: 4=Visa 5=MC — configurar manual

    # ── Comercio / transacción ────────────────────────────────────────────────
    "canal"            : "ACF-CANAL",
    "entry_mode"       : "ACF-ENTRY MODE",
    "mcc"              : "ACF-MCC",                            # débito usa "ACF-MCC +"
    "eci"              : "ACF-ECI/UCAF",
    "cod_red_comercio" : "ACF-COD RED COMERCIO",               # S=Estático TD D=Dinámico E=Estático TC N=Sin CVV
    "pais"             : "ACF-PAIS ORIGEN 87519",
    "region"           : "ACF-REGION",
    "ciudad"           : "ACF-CIUDAD",
    "ip"               : "ACF-IP",

    # ── Respuesta / rechazo ───────────────────────────────────────────────────
    "indicador"        : "ACF-INDICADOR DE FRAUDE",            # F=fraude B/G=buena D=descarte P=pendiente N=normal
    "cod_respuesta"    : "ACF-COD RPTA",
    "cod_motivo"       : "ACF-COD MOTIVO RECHAZO",
    "razon_respuesta"  : "ACF-RAZON RESPUESTA",
}

# ─── TABLAS DE REFERENCIA ─────────────────────────────────────────────────────
SEG_NOMBRE = {
    "30":"Polo Direccion","99":"Polo Direccion","31":"Premium","32":"Preferente",
    "33":"Personal","34":"Estandar","5":"Inst. Financieras","21":"Corporativo",
    "2":"Mediano Empresas","15":"Sector Gobierno","16":"Otras Instituciones",
    "3":"Pequenas Empresas","4":"Negocios 2","7":"Negocios 3","8":"Negocios 1","13":"Microempresas",
}
SEG_GRUPO = {
    "30":"Affluent","99":"Affluent","31":"Emerging Affluent","32":"Emerging Affluent",
    "33":"Top of Mass","34":"Mass","5":"Corporate","21":"Corporate","2":"Commercial",
    "15":"Commercial","16":"Commercial","3":"Small Business","4":"Small Business",
    "7":"Small Business","8":"Small Business","13":"Small Business",
}
COD_RED_LABEL = {
    "S": "Estatico (TD)",
    "D": "Dinamico (TD/TC)",
    "E": "Estatico (TC)",
    "N": "No Match / Sin CVV",
}

# ─── CLASIFICADOR DE MOTIVOS DE RECHAZO ──────────────────────────────────────
def clasificar_motivo(razon: str) -> str:
    r = str(razon).upper()
    if any(k in r for k in ["CVV","CVC","CODIGO SEGURIDAD","SECURITY CODE"]):
        return "CVV_FAIL"
    if any(k in r for k in ["FONDOS","SALDO","NSF","INSUFFICIENT"]):
        return "FONDOS_INSUF"
    if any(k in r for k in ["EXCEDE","LIMITE","LIMIT","EXCEED"]):
        return "EXCEDE_LIMITE"
    if any(k in r for k in ["BLOQUEAD","BLOCKED","RESTRICT"]):
        return "TARJETA_BLOQ"
    if any(k in r for k in ["EXPIR","VENCID"]):
        return "TARJETA_EXP"
    if any(k in r for k in ["PIN"]):
        return "PIN_FAIL"
    if any(k in r for k in ["3DS","AUTHEN","AUTENT"]):
        return "AUTH_FAIL"
    if any(k in r for k in ["INVALID","INVAL","NO MATCH","NO COINCID"]):
        return "DATO_INVALIDO"
    return "OTRO"
