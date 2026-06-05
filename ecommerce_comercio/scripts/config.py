# =============================================================================
#  config.py  —  Pipeline de Análisis Ecommerce por Comercio
#  Scotiabank Peru — Prevención de Fraude
# =============================================================================
#  INSTRUCCIONES:
#  1. Pon COMERCIO_NOMBRE con el nombre del comercio a analizar
#  2. Pon los Excel de Monitor en  data/journals/
#  3. Indica si el journal tiene solo aprobadas o aprobadas+denegadas (SOLO_APROBADAS)
#  4. Revisa el diccionario COLS y ajusta valores si tu Monitor usa nombres distintos
#  5. Ejecuta en orden:
#       python scripts/consolidar.py
#       python scripts/feature_engineering.py
#       python scripts/analisis.py
# =============================================================================

from pathlib import Path

# ─── NOMBRE / ETIQUETA DEL ANÁLISIS ──────────────────────────────────────────
COMERCIO_NOMBRE = "COMERCIO_EJEMPLO"   # Ej: "SAGAFALABELLA", "AMAZON", "ZARA"
                                       # Para análisis LIKE: poner el patrón buscado, ej: "ZARA_LIKE"

# =============================================================================
#  MODO DE ANÁLISIS
#  Cambia este valor según qué tipo de análisis estás haciendo.
#
#  "COMERCIO"  → Un solo comercio exacto          (ej: "ZARA")
#  "MULTI"     → Varios comercios bajados con LIKE (ej: "AIRBNB%", "ZARA%")
#                Hoja 0 mostrará el ranking de comercios por fraude
#  "MCC"       → Análisis por código MCC           (ej: MCC 5411 = Supermercados)
#                Hoja 0 mostrará el ranking de MCC y comercios dentro del MCC
#  "BIN"       → Análisis centrado en BIN          (ej: investigar un BIN específico)
#                Hoja 0 mostrará el ranking de BINs con clientes + monto
#  "SEGMENTO"  → Análisis por segmento de cliente  (ej: comportamiento por Mass/Affluent)
#                Hoja 0 mostrará el ranking de segmentos
#  "PAIS"      → Análisis por país de origen       (ej: fraude transnacional)
#                Hoja 0 mostrará el ranking de países
# =============================================================================
MODO_ANALISIS = "COMERCIO"

# ─── RUTAS ───────────────────────────────────────────────────────────────────
BASE_DIR            = Path(__file__).resolve().parent.parent
FOLDER_JOURNALS     = BASE_DIR / "data" / "journals"
PARQUET_CONSOLIDADO = BASE_DIR / "data" / "consolidado.parquet"
PARQUET_FEATURES    = BASE_DIR / "data" / "consolidado_features.parquet"
EXCEL_OUTPUT        = BASE_DIR / "output" / f"analisis_{COMERCIO_NOMBRE}.xlsx"

# ─── TIPO DE JOURNAL ─────────────────────────────────────────────────────────
#  True  → solo transacciones APROBADAS (no se calculan features de rechazo)
#  False → APROBADAS + DENEGADAS (análisis completo, recomendado)
SOLO_APROBADAS = False

# ─── FILA DE ENCABEZADO ──────────────────────────────────────────────────────
SKIPROWS = 4    # El header está en la fila 5 → saltar las 4 primeras
                # Nota: ajustar si cambias de comercio y el journal tiene diferente estructura

# =============================================================================
#  DICCIONARIO DE COLUMNAS
#  - La CLAVE (izquierda) la usa el script internamente. NO la toques.
#  - El VALOR (derecha) es el nombre real de la columna en tu Excel de Monitor.
#    Cámbialo si tu archivo usa un nombre distinto.
# =============================================================================
COLS = {

    # ── TARJETA (se construye combinando dos columnas) ────────────────────────
    # Python: col1[:6] + col2 + col1[12:]
    # Power Query: Text.Start(col1, 6) & col2 & Text.Middle(col1, 12)
    "tarjeta_col1"     : "ACF-TARJETA REGISTRO 750",         # primera columna
    "tarjeta_col2"     : "ACF-TARJETA POS 7,6 DIGITOS",      # dígitos del medio (pos 7-12)
    # Columna TARJETA la crea el script automáticamente en consolidar.py
    "tarjeta_enc"      : "ACF-NUMERO DE TARJETA ENCRIPTADO AES",  # versión encriptada (auditoría)

    # ── IDENTIFICADORES ───────────────────────────────────────────────────────
    "bin"              : "ACF-BIN",
    "id_cliente"       : "ACF-ID CLIENTE",                   # base de todas las ventanas temporales
    "num_autorizacion" : "ACF-AUTORIZACION",
    "num_trx"          : "ACF-NUMERO TRX",
    "cod_hash"         : "ACF-CODIGO HASH",

    # ── FECHAS Y HORA ─────────────────────────────────────────────────────────
    "fecha_trx"        : "ACF-FECHA TRX",                    # formato AAAAMMDD → se convierte a date
    "hora_trx"         : "ACF-HORA TRX",                     # formato HH:MM:SS
    "hora_sin_min"     : "ACF-HORA SIN MINUTOS DE LA TRX",   # hora entera (Int)
    "mes_anio"         : "ACF-MES DEL ANO DE LA TRX",
    # Columna construida por consolidar.py (no viene en Monitor):
    "fecha_hora"       : "FECHA_HORA",                       # datetime YYYY-MM-DD HH:MM:SS

    # ── MONTOS ────────────────────────────────────────────────────────────────
    "monto"            : "ACF-MONTO EN MONEDA LOCAL",
    "monto_dolar"      : "ACF-MONTO DOLLAR",

    # ── TARJETA / CLIENTE ─────────────────────────────────────────────────────
    "tipo_producto"    : "ACF-TIPO PROD TC",                  # TC = crédito | TD = débito
    "saldo"            : "ACF-SALDO DISPONIBLE EN MONEDA TRX",
    "segmento"         : "VAA-EVENTO DE COMPROMISO OTRA FUENTE",
    "organizacion"     : "ACF-ORGANIZACION",                  # código numérico como string — ver ORG_NOMBRE
    "marca"            : "ACF-MARCA",                         # ← ajusta al nombre real de la columna
                                                              # Valores: 4 = Visa | 5 = Mastercard

    # ── COMERCIO / TRANSACCIÓN ────────────────────────────────────────────────
    "comercio_nom"     : "ACF-NOMBRE/LOCALIZACION COMERCIO",
    "localidad_com"    : "ACF-LOCALIDAD COMERCIO",
    "canal"            : "ACF-CANAL",
    "entry_mode"       : "ACF-ENTRY MODE",                   # modo ingreso tarjeta
    "mcc"              : "ACF-MCC +",                        # MCC con + (débito usa esta)
    "cod_cio"          : "ACF-CODIGO CIO/AGENCIA/OFICINA ORIGEN",
    "cod_trx"          : "ACF-COD TRX",
    "v_to"             : "ACF-V/TO",
    "reverso"          : "ACF-REVERSO",

    # ── SEGURIDAD / CVV ───────────────────────────────────────────────────────
    "eci"              : "ACF-ECI/UCAF",                     # Seguro: Visa=5/05 | MC=2/02
    "cod_red_comercio" : "ACF-COD RED COMERCIO",             # S=Estático TD D=Dinámico E=Estático TC N=Sin CVV
    "ind_recurrente"   : "ACF-INDICADOR RECURRENTE / MOTO",  # MOTO = Mail Order / Telephone Order

    # ── BILLETERA DIGITAL (tokenizada) ───────────────────────────────────────
    "billetera"        : "RESERVADO ALFA 2",                 # primeros 5 chars → ver BILLETERA_LABEL

    # ── RESPUESTA / RECHAZO ───────────────────────────────────────────────────
    "indicador"        : "ACF-INDICADOR DE FRAUDE",          # F=fraude G=buena P=pendiente D=descarte N=normal
    "cod_respuesta"    : "ACF-COD RPTA",                     # 0/00/000 = APROBADA; resto = DENEGADA
    "razon_respuesta"  : "ACF-RAZON RESPUESTA",              # texto que interpreta el código
    "cod_rpta_vplus"   : "CODIGO DE RESPUESTA VISION PLUS",  # código del sistema Vision Plus

    # ── COMERCIO — PRECALCULADAS POR MONITOR ─────────────────────────────────
    "q_transaccional"  : "CC : K05_COUNTMP_TAMANO COMERCIO", # txn del comercio el mes anterior
                                                              # → identifica si es comercio nuevo o grande
    "score_riesgo_mon" : "SCORE DE RIESGO",                  # score que ya calcula Monitor

    # ── COLUMNAS YA PROCESADAS POR MONITOR ───────────────────────────────────
    "grupo_horario"    : "ACF-GRUPO DE HORARIO",
    "dia_semana_mon"   : "ACF-DIA DE LA SEMANA DE LA TRX",

    # ── PAÍS ──────────────────────────────────────────────────────────────────
    "pais"             : "ACF-PAIS ORIGEN 87519",            # país donde se realizó la txn

}

# =============================================================================
#  UMBRALES DE REGLAS (configurables)
#  Se usan en la hoja "Recomendaciones_Regla" del Excel para simular
#  cuánto fraude capturaría cada umbral vs cuántas txn buenas afectaría.
# =============================================================================
UMBRALES_REGLA = {
    "monto_acum_24h" : [200, 300, 500, 1000],    # S/ — monto acumulado por cliente en 24h
    "trx_en_5min"    : [2, 3, 4, 5],             # número de txn en 5 min
    "trx_en_10min"   : [3, 4, 5],
    "trx_en_1h"      : [5, 7, 10],
}

# =============================================================================
#  SCORE POR MARCA (solo tarjeta de crédito — no aplica a débito)
#  Monitor entrega un score de riesgo nativo según la marca:
#    Visa Crédito        → 0 a 99   (mayor score = MENOR riesgo)
#    Mastercard Crédito  → 0 a 999  (mayor score = MENOR riesgo)
#  Se normaliza a [0,1]; score_norm < UMBRAL_SCORE_MON indica alto riesgo.
# =============================================================================
SCORE_VISA_MAX   = 99     # Visa Crédito: rango máximo del score de Monitor
SCORE_MC_MAX     = 999    # Mastercard Crédito: rango máximo
UMBRAL_SCORE_MON = 0.30   # Score normalizado < umbral → FLAG_SCORE_RIESGO_MON_ALTO

# =============================================================================
#  DICCIONARIO DE RANGOS DE MONTO POR RUBRO
#  Cortes en S/. Ajusta según el ticket promedio esperado del comercio.
#  El script también calcula rangos automáticos por árbol de decisión y percentiles.
# =============================================================================
RANGOS_MONTO_RUBRO = {
    "RETAIL_GRANDE"   : [0, 100, 300,  800, 99999],   # Saga, Ripley, Zara
    "STREAMING"       : [0,  20,  50,  150, 99999],   # Netflix, Spotify, PlayStation
    "GAMING"          : [0,  50, 200,  600, 99999],   # Steam, Xbox, PS Store
    "MARKETPLACE"     : [0, 100, 400, 1200, 99999],   # Amazon, MercadoLibre
    "REMESAS"         : [0, 200, 500, 1500, 99999],   # Western Union, MoneyGram
    "OTROS"           : [0,  50, 200,  600, 99999],
}

# =============================================================================
#  TABLAS DE REFERENCIA
# =============================================================================

# Organización — completar con los códigos reales de tu Monitor
# Los códigos vienen como string tipo "000215" (leer siempre como texto)
ORG_NOMBRE = {
    # "000XXX": "Nombre",   ← reemplaza con los valores reales cuando los tengas
}

# Segmento cliente
SEG_NOMBRE = {
    "30": "Polo Direccion",     "99": "Polo Direccion",
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
    "30": "Affluent",           "99": "Affluent",
    "31": "Emerging Affluent",  "32": "Emerging Affluent",
    "33": "Top of Mass",        "34": "Mass",
    "5":  "Corporate",          "21": "Corporate",
    "2":  "Commercial",         "15": "Commercial",
    "16": "Commercial",
    "3":  "Small Business",     "4":  "Small Business",
    "7":  "Small Business",     "8":  "Small Business",
    "13": "Small Business",
}

# CVV / Código Red Comercio
COD_RED_LABEL = {
    "S": "Estatico (TD)",
    "D": "Dinamico (TD/TC)",
    "E": "Estatico (TC)",
    "N": "Sin CVV / No Match",
}

# Billetera digital — primeros 5 chars de RESERVADO ALFA 2
BILLETERA_LABEL = {
    "75001": "Google Pay VISA",
    "32703": "Apple Pay VISA / MC",
    "34693": "Apple Pay MC",
    "99999": "No tokenizada",
}
BILLETERA_DEFAULT = "Tokenizada (no identificada)"  # cualquier otro código

# Entry Mode — modo de ingreso de la tarjeta
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
    # Agrega más códigos si aparecen en tu data
}
# Tarjeta presente vs no presente
ENTRY_MODE_PRESENTE  = {"05", "07", "79", "80", "90", "91"}   # tarjeta física
ENTRY_MODE_NP        = {"01", "10"}                             # no presente / e-commerce

# Marca / Franquicia
MARCA_LABEL = {
    "4": "VISA",
    "5": "MASTERCARD",
}

# Tipo de producto
TIPO_PROD_LABEL = {
    "TC": "Credito",
    "TD": "Debito",
}

# Códigos de respuesta críticos
CODIGOS_CRITICOS = {"N7", "14", "04", "51"}
# N7 = CVV2 no coincide (card testing)
# 14 = Tarjeta inválida (clonada / número generado)
# 04 = Capturar tarjeta (en lista negra, fraude confirmado)
# 51 = Fondos insuficientes (puede indicar agotamiento de saldo por fraude)

# Feriados Perú
FERIADOS_PERU = {
    "2025-01-01", "2025-04-17", "2025-04-18", "2025-05-01",
    "2025-06-07", "2025-06-29", "2025-07-28", "2025-07-29",
    "2025-08-30", "2025-10-08", "2025-11-01", "2025-12-08", "2025-12-25",
    "2026-01-01", "2026-04-02", "2026-04-03", "2026-05-01",
    "2026-06-07", "2026-06-29", "2026-07-28", "2026-07-29",
    "2026-08-30", "2026-10-08", "2026-11-01", "2026-12-08", "2026-12-25",
}

# Fechas de alta transaccionalidad (formato MM-DD, aplica a cualquier año)
FECHAS_ESPECIALES = {
    "05-11": "Dia de la Madre",
    "06-15": "Dia del Padre",
    "12-24": "Noche Buena",
    "12-31": "Fin de Anio",
    "11-11": "11/11 Cyberday",
    "11-29": "Black Friday (aprox)",
    "02-14": "San Valentin",
}

# Días típicos de pago en Peru (quincena, sueldo, CTS)
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
