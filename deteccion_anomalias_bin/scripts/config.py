# =============================================================================
#  config.py  —  Detección y Caracterización de Anomalías Transaccionales
#                por Rango de BIN (BIN6 → BIN10)
#  Scotiabank Peru — Prevención de Fraude
# =============================================================================
#  INSTRUCCIONES:
#  1. Pon los Excel de Monitor (journals) en  data/journals/
#     Idealmente 2 meses de historia del BIN6 / rango a investigar.
#  2. Revisa el diccionario COLS y ajusta valores si tu Monitor usa
#     nombres distintos (es el mismo diccionario de ecommerce_comercio).
#  3. Registra campañas conocidas en CALENDARIO_EVENTOS / EVENTOS_RANGO.
#  4. Ejecuta en orden:
#       python scripts/consolidar.py      → journals → consolidado.parquet
#       python scripts/agregacion.py      → series diarias por rango de BIN
#       python scripts/deteccion.py       → z-score robusto → alertas
#       python scripts/atribucion.py      → contribución + chi2 + calendario → Excel
#     Fase 2 (opcional, tras validar el baseline):
#       python ml/isolation_forest.py
# =============================================================================

from pathlib import Path

# ─── NOMBRE / ETIQUETA DEL ANÁLISIS ──────────────────────────────────────────
ANALISIS_NOMBRE = "RANGO_BIN"    # Ej: "BIN421355", "DEBITO_CLASICA"

# ─── RUTAS ───────────────────────────────────────────────────────────────────
BASE_DIR            = Path(__file__).resolve().parent.parent
FOLDER_JOURNALS     = BASE_DIR / "data" / "journals"
PARQUET_CONSOLIDADO = BASE_DIR / "data" / "consolidado.parquet"

# Detalle transaccional reducido (lo genera agregacion.py; lo usa atribucion.py)
PARQUET_DETALLE     = BASE_DIR / "data" / "detalle_trx.parquet"

# Series diarias por nivel de agregación
PARQUET_SERIE_BIN10_COMERCIO = BASE_DIR / "data" / "serie_bin10_comercio.parquet"
PARQUET_SERIE_BIN10_MCC      = BASE_DIR / "data" / "serie_bin10_mcc.parquet"
PARQUET_SERIE_BIN6           = BASE_DIR / "data" / "serie_bin6.parquet"

# Alertas
PARQUET_ALERTAS     = BASE_DIR / "data" / "alertas.parquet"
PARQUET_IF          = BASE_DIR / "data" / "if_scores.parquet"

EXCEL_OUTPUT        = BASE_DIR / "output" / f"alertas_{ANALISIS_NOMBRE}.xlsx"
EXCEL_IF            = BASE_DIR / "output" / f"isolation_forest_{ANALISIS_NOMBRE}.xlsx"

# ─── TIPO DE JOURNAL ─────────────────────────────────────────────────────────
#  Este proyecto NECESITA aprobadas + denegadas: la tasa de declinación es
#  una de las firmas principales de card testing. Si el journal solo trae
#  aprobadas, la detección de volumen funciona pero TASA_DECLINACION saldrá 0.
SOLO_APROBADAS = False

# ─── FILA DE ENCABEZADO ──────────────────────────────────────────────────────
SKIPROWS = 4    # El header está en la fila 5 → saltar las 4 primeras

# =============================================================================
#  PARÁMETROS DE DETECCIÓN  (Paso 2-3: baseline z-score robusto)
# =============================================================================
DETECCION = {
    # Ventana móvil del baseline (mediana + MAD). Sugerido 14-28 días.
    "ventana_dias"     : 21,

    # Mínimo de días de historia previa para poder calcular baseline.
    # Series más nuevas que esto no generan alerta (evita falsos positivos
    # de BINs/comercios recién aparecidos).
    "min_dias_historia": 7,

    # Umbral del z-score robusto: z = 0.6745 * (x - mediana) / MAD
    "z_umbral"         : 4.0,

    # Piso del MAD para series muy planas (MAD = 0 dispara z infinito).
    # Con MAD_min = 1.0, una serie que siempre hace 3 trx/día necesita
    # un salto absoluto real para alertar, no basta pasar de 3 a 4.
    "mad_min"          : 1.0,

    # Volumen mínimo del día para que valga la pena alertar
    # (un salto de 1 → 6 trx es z alto pero irrelevante operativamente).
    "min_trx_dia"      : 10,
}

# =============================================================================
#  PARÁMETROS DE ATRIBUCIÓN  (Paso 4: contribución + chi-cuadrado)
# =============================================================================
ATRIBUCION = {
    # Significancia del chi-cuadrado de mezcla (día anómalo vs baseline).
    # p < alfa → la mezcla (MCC / comercio / horario) CAMBIÓ, no solo el volumen.
    "alfa_chi2"        : 0.01,

    # Frecuencia mínima de una categoría para entrar al chi-cuadrado
    # (categorías raras inflan el estadístico).
    "min_freq_chi2"    : 5,

    # Cuántos contribuyentes mostrar en la descomposición del exceso.
    "top_n"            : 3,

    # Tasa de declinación: se marca FLAG_DECL_ALTA si la tasa del día
    # supera max(ratio * baseline, baseline + delta).
    "decl_ratio"       : 2.0,
    "decl_delta"       : 0.15,
}

# Franjas horarias para el chi-cuadrado de horario
FRANJAS_HORARIAS = {
    "MADRUGADA (0-5)"  : range(0, 6),
    "MANANA (6-11)"    : range(6, 12),
    "TARDE (12-17)"    : range(12, 18),
    "NOCHE (18-23)"    : range(18, 24),
}

# Horas consideradas "nocturnas" para la métrica PCT_NOCTURNAS
HORAS_NOCTURNAS = set(range(0, 6))    # 00:00 – 05:59

# =============================================================================
#  PARÁMETROS ISOLATION FOREST  (Fase 2 — capa multivariada)
# =============================================================================
ISOLATION_FOREST = {
    "n_estimators"  : 300,
    "contamination" : 0.01,     # % esperado de días-serie anómalos
    "random_state"  : 42,
    # Features de la tabla BIN10 × comercio × día que entran al modelo
    "features"      : [
        "N_TRX", "N_TARJETAS", "RATIO_TRX_TARJETA",
        "TASA_DECLINACION", "TICKET_PROM", "N_MCC", "PCT_NOCTURNAS",
    ],
}

# =============================================================================
#  CALENDARIO DE EVENTOS COMERCIALES  (Paso 5: filtro de campañas)
#  Un spike que coincide con evento y mantiene la mezcla estable → prioridad BAJA.
# =============================================================================

# Eventos recurrentes todos los años (formato MM-DD)
CALENDARIO_EVENTOS = {
    "05-11": "Dia de la Madre",
    "06-15": "Dia del Padre",
    "07-28": "Fiestas Patrias",
    "07-29": "Fiestas Patrias",
    "11-11": "11/11 Cyberday",
    "11-29": "Black Friday (aprox)",
    "12-24": "Noche Buena",
    "12-31": "Fin de Anio",
    "02-14": "San Valentin",
}

# Campañas con rango de fechas exactas (inicio, fin, nombre) — formato YYYY-MM-DD.
# ⚠️ AJUSTA estas fechas cada año / cada campaña que conozcas.
EVENTOS_RANGO = [
    ("2026-03-30", "2026-04-01", "Cyber Wow Marzo"),
    ("2026-07-13", "2026-07-15", "Cyber Wow Julio"),
    ("2026-11-02", "2026-11-04", "Cyber Wow Noviembre"),
]

# Días típicos de pago en Peru (quincena, fin de mes) → evento "Dia de pago"
DIAS_PAGO = {15, 30, 31}

# =============================================================================
#  DICCIONARIO DE COLUMNAS DE MONITOR
#  Mismo diccionario que ecommerce_comercio/scripts/config.py
#  - La CLAVE (izquierda) la usa el script internamente. NO la toques.
#  - El VALOR (derecha) es el nombre real de la columna en tu Excel de Monitor.
# =============================================================================
COLS = {

    # ── TARJETA ───────────────────────────────────────────────────────────────
    # El número completo se reconstruye en consolidar.py:
    #   TARJETA = tarjeta_col1[:6] + tarjeta_col2 + tarjeta_col1[12:]
    "tarjeta_col1"     : "ACF-TARJETA REGISTRO 750",              # posiciones 1-6 y 13+
    "tarjeta_col2"     : "ACF-TARJETA POS 7,6 DIGITOS",           # posiciones 7-12
    "tarjeta_enc"      : "ACF-NUMERO DE TARJETA ENCRIPTADO AES",  # versión encriptada
    "bin"              : "ACF-BIN",                                # primeros 6 dígitos del PAN

    # ── IDENTIFICADORES ───────────────────────────────────────────────────────
    "id_cliente"       : "ACF-ID CLIENTE",
    "num_autorizacion" : "ACF-AUTORIZACION",
    "num_trx"          : "ACF-NUMERO TRX",
    "cod_hash"         : "ACF-CODIGO HASH",

    # ── FECHAS Y HORA ─────────────────────────────────────────────────────────
    "fecha_trx"        : "ACF-FECHA TRX",               # AAAAMMDD
    "hora_trx"         : "ACF-HORA TRX",                # HH:MM:SS
    "hora_sin_min"     : "ACF-HORA SIN MINUTOS DE LA TRX",
    "mes_anio"         : "ACF-MES DEL ANO DE LA TRX",
    "fecha_hora"       : "FECHA_HORA",                  # construida por consolidar.py

    # ── MONTOS ────────────────────────────────────────────────────────────────
    "monto"            : "ACF-MONTO EN MONEDA LOCAL",
    "monto_dolar"      : "ACF-MONTO DOLLAR",
    "monto_original"   : "ACF-MONTO ORIGINAL TRX",
    "moneda_trx"       : "ACF-COD MONEDA TRX",          # 604=PEN 840=USD 978=EUR

    # ── TARJETA / CLIENTE ─────────────────────────────────────────────────────
    "tipo_producto"    : "ACF-TIPO PROD TC",            # TC=Crédito | TD=Débito
    "saldo"            : "ACF-SALDO DISPONIBLE EN MONEDA TRX",
    "fecha_vencimiento": "ACF-V/TO",
    "segmento"         : "VAA-EVENTO DE COMPROMISO OTRA FUENTE",
    "organizacion"     : "ACF-ORGANIZACION",
    "marca"            : "ACF-MARCA O FRANQUICIA",      # 4=Visa | 5=Mastercard

    # ── COMERCIO / TRANSACCIÓN ────────────────────────────────────────────────
    "comercio_nom"     : "ACF-NOMBRE/LOCALIZACION COMERCIO",
    "localidad_com"    : "ACF-LOCALIDAD COMERCIO",
    "canal"            : "ACF-CANAL",
    "entry_mode"       : "ACF-ENTRY MODE",
    "mcc"              : "ACF-MCC +",
    "cod_cio"          : "ACF-CODIGO CIO/AGENCIA/OFICINA ORIGEN",
    "cod_trx"          : "ACF-COD TRX",
    "reverso"          : "ACF-REVERSO",

    # ── SEGURIDAD / CVV ───────────────────────────────────────────────────────
    "eci"              : "ACF-ECI/UCAF",                # Seguro: Visa=5/05 | MC=2/02
    "cod_red_comercio" : "ACF-COD RED COMERCIO",        # S/D/E/N
    "ind_recurrente"   : "ACF-INDICADOR RECURRENTE / MOTO",

    # ── BILLETERA DIGITAL ─────────────────────────────────────────────────────
    "billetera"        : "RESERVADO ALFA 2",

    # ── RESPUESTA / RECHAZO ───────────────────────────────────────────────────
    "indicador"        : "ACF-INDICADOR DE FRAUDE",     # F/G/P/D/N
    "cod_respuesta"    : "ACF-COD RPTA",                # 0/00/000=APROBADA
    "razon_respuesta"  : "ACF-RAZON RESPUESTA",
    "cod_rpta_vplus"   : "CODIGO DE RESPUESTA VISION PLUS",

    # ── MONITOR — PRECALCULADAS ───────────────────────────────────────────────
    "q_transaccional"  : "CC : K05_COUNTMP_TAMANO COMERCIO",
    "score_riesgo_mon" : "SCORE DE RIESGO",
    "grupo_horario"    : "ACF-GRUPO DE HORARIO",
    "dia_semana_mon"   : "ACF-DIA DE LA SEMANA DE LA TRX",

    # ── PAÍS ──────────────────────────────────────────────────────────────────
    "pais"             : "ACF-PAIS ORIGEN 87519",

}

# Códigos de respuesta críticos (firma de card testing)
CODIGOS_CRITICOS = {"N7", "14", "04", "51"}
# N7 = CVV2 no coincide (card testing)
# 14 = Tarjeta inválida (clonada / número generado)
# 04 = Capturar tarjeta (lista negra)
# 51 = Fondos insuficientes (agotamiento de saldo)

# Feriados Perú (contexto para el calendario)
FERIADOS_PERU = {
    "2026-01-01", "2026-04-02", "2026-04-03", "2026-05-01",
    "2026-06-07", "2026-06-29", "2026-07-28", "2026-07-29",
    "2026-08-30", "2026-10-08", "2026-11-01", "2026-12-08", "2026-12-25",
}
