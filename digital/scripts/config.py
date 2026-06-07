# ─────────────────────────────────────────────────────────────────────────────
#  DICCIONARIO DE COLUMNAS  —  digital
#  Cambia el VALOR de cada entrada con el nombre real de tu parquet.
#  No toques las CLAVES (lado izquierdo) porque el script las usa internamente.
# ─────────────────────────────────────────────────────────────────────────────

COLS = {
    # ── Identificadores ──────────────────────────────────────────────────────
    "tarjeta"           : "POS1_ACF-TARJETA",           # número de tarjeta (masked)
    "bin"               : "POS1_ACF-BIN",               # BIN de la tarjeta
    "cliente_id"        : "POS1_ACF-ID CLIENTE",        # ID cliente en el sistema
    "cliente_cod"       : "POS1_ACF-CODIGO CLIENTE",    # código cliente

    # ── Fechas (vienen SEPARADAS — el bloque A las combina en DATETIME_TRX) ──
    "fecha_trx"         : "POS1_ACF-FECHA TRX",         # solo fecha   ej. 2025-07-02
    "hora_trx"          : "POS1_ACF-HORA TRX",          # solo hora    ej. 17:18:49
    "fecha_cierre"      : "POS1_ACF-FECHA CIERRE CASO", # fecha cierre ej. 2025-08-10

    # ── Montos ────────────────────────────────────────────────────────────────
    "monto"             : "POS1_ACF-MONTO EN MONEDA LOCAL",  # monto en soles (numérico)
    "monto_dolar"       : "POS1_ACF-MONTO DOLLAR",           # monto en dólares (numérico)

    # ── Tarjeta / cliente ─────────────────────────────────────────────────────
    "nivel_tarjeta"     : "POS1_NOM_NIVEL_TARJETA",     # CLASSIC, GOLD, PLATINUM, BLACK
    "tipo_tarjeta"      : "POS1_NOM_TIPO_TARJETA",      # tipo de tarjeta
    "segmento"          : "POS1_SEGMENTO_FINAL",        # segmento del cliente
    "organizacion"      : "POS1_ACF-ORGANIZACION",      # SVP = Scotiabank Peru

    # ── Canal digital ─────────────────────────────────────────────────────────
    "canal_digital"     : "POS1_NOM_CANAL_TRX_DIGITAL", # Pasarelas / Transferencias inmediatas / Transferencias a terceros / Yape-Plin-Bim
    "tipo_digital"      : "POS1_NOM_TIPO_DIGITAL",
    "canal_joy"         : "POS1_CANAL_JOY",             # iOS / Android / Web

    # ── Operación ─────────────────────────────────────────────────────────────
    "operacion"         : "POS1_NOM_OPERACION",         # Transferencia QR, Pago TC, Pago servicios, Transferencia CC inmediata, etc.
    "tipo_transaccion"  : "POS1_TIPO DE TRANSACCION",

    # ── Beneficiario / destino ────────────────────────────────────────────────
    "banco_destino"     : "POS1_ACF-COD BANCO DESTINO / ORG DESTINO", # código 3 dígitos ej. "009" = BCP — el nombre viene de diccionario Excel externo
    "cuenta_destino"    : "POS1_ACF-CUENTA DESTINO",
    "tipo_id_destino"   : "POS1_ACF-TIPO ID DESTINO / BENEFICIARIO",  # M = mismo titular / otro valor = tercero

    # ── Autenticación ─────────────────────────────────────────────────────────
    "autenticador"      : "POS1_NOM_MEDIO_AUTENTICADOR_DIGITAL",  # No aplica / OTP / Clave digital / Datos biométricos

    # ── Origen / dispositivo ──────────────────────────────────────────────────
    "ip_terminal"       : "POS1_ACF-ID TERMINAL/DIRECCION IP",          # IP real o ID de terminal
    "agencia_origen"    : "POS1_ACF-CODIGO CIO/AGENCIA/OFICINA ORIGEN", # código agencia si aplica

    # ── Fraude ────────────────────────────────────────────────────────────────
    "modalidad_fraude"  : "POS1_NOM_MODALIDAD_F",       # modalidad final del fraude
    "alertado"          : "ALERTADO",
    "alertas"           : "POS1_ACF-CONDICIONES QUE GENERARON ALERTAS",

    # ── Columnas ya calculadas en el script de extracción ─────────────────────
    "es_ip_real"            : "ES_IP_REAL",             # bool: el campo IP/terminal contiene IP válida
    "tipo_origen_geo"       : "TIPO_ORIGEN_GEO",        # WEB_IP / TERMINAL / AGENCIA / SIN_DATA
    "cuenta_destino_3dig"   : "CUENTA_DESTINO_3DIG",    # primeros 3 dígitos de cuenta destino
    "monto_cero"            : "MONTO_CERO",             # bool: monto local == 0
}

# ── Ruta del parquet de entrada ───────────────────────────────────────────────
PARQUET_INPUT  = "MF_digital.parquet"       # <-- cambia aquí si el nombre es distinto

# ── Ruta del parquet de salida (enriquecido) ──────────────────────────────────
PARQUET_OUTPUT = "MF_digital_features.parquet"

# ── Umbral cuenta mula ────────────────────────────────────────────────────────
UMBRAL_CUENTA_MULA = 3   # nº mínimo de tarjetas distintas que llegan a la misma cuenta destino
