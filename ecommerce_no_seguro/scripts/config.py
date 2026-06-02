# ─────────────────────────────────────────────────────────────────────────────
#  DICCIONARIO DE COLUMNAS  —  ecommerce_fraude
#  Cambia el VALOR de cada entrada con el nombre real de tu parquet.
#  No toques las CLAVES (lado izquierdo) porque el script las usa internamente.
# ─────────────────────────────────────────────────────────────────────────────

COLS = {
    # ── Identificadores ──────────────────────────────────────────────────────
    "tarjeta"          : "TARJETA",           # número de tarjeta (masked)
    "bin"              : "BIN",               # BIN de la tarjeta
    "comercio_id"      : "COMERCIO_ID",       # ID o código del comercio
    "comercio_nom"     : "COMERCIO_NOMBRE",   # nombre del comercio (si no existe, pon igual que comercio_id)

    # ── Fechas ───────────────────────────────────────────────────────────────
    "fecha_hora_trx"   : "POS1_FECHA_HORA_TRX",  # datetime combinado  formato YYYY-MM-DD HH:MM:SS  ej. 2025-07-02 17:18:49
    "fecha_cierre"     : "FECHA_CIERRE",          # fecha de cierre del caso  formato YYYY-MM-DD  ej. 2025-08-10

    # ── Montos ────────────────────────────────────────────────────────────────
    "monto"            : "IMPORTE",           # monto en moneda local (numérico)
    "monto_dolar"      : "IMPORTE_USD",       # monto en dólares (numérico)

    # ── Tarjeta / cliente ─────────────────────────────────────────────────────
    "tipo_tarjeta"     : "TIPO_TARJETA",      # CREDITO / DEBITO
    "nivel_tarjeta"    : "NIVEL_TARJETA",     # ej. CLASSIC, GOLD, PLATINUM, BLACK
    "saldo_disponible" : "SALDO_DISPONIBLE",  # saldo disponible al momento de la transacción
    "segmento"         : "SEGMENTO",          # segmento del cliente
    "organizacion"     : "ORGANIZACION",      # SVP = Scotiabank  |  CSF = Santander

    # ── Comercio / transacción ────────────────────────────────────────────────
    "canal"            : "CANAL",             # canal de la transacción
    "mcc"              : "MCC",               # Merchant Category Code
    "cvv_dinamico"     : "CVV_DINAMICO",      # ¿CVV dinámico? (S/N o 1/0). Pon None si no tienes.

    # ── Fraude ────────────────────────────────────────────────────────────────
    "modalidad_fraude" : "MODALIDAD_FRAUDE",  # modalidad del fraude (ej. CNP, SKIMMING, PHISHING…)
}

# ── Ruta del parquet de entrada ───────────────────────────────────────────────
PARQUET_INPUT  = "fraudes_comercios_no_seguros.parquet"   # <-- cambia aquí

# ── Ruta del parquet de salida (enriquecido) ──────────────────────────────────
PARQUET_OUTPUT = "fraudes_comercios_no_seguros_features.parquet"
