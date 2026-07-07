"""
╔══════════════════════════════════════════════════════════════════╗
║     BOOTSTRAP HISTÓRICO — Bitácora Solicitudes de Clientes       ║
║     Scotiabank Peru — Prevención de Fraude                       ║
╠══════════════════════════════════════════════════════════════════╣
║  ⚠️  CORRER UNA SOLA VEZ.                                        ║
║                                                                  ║
║  Reconstruye la base SQLite desde los correos que ya están en    ║
║  el buzón, desde FECHA_INICIO en adelante:                       ║
║                                                                  ║
║  • Solicitudes: Bandeja de entrada (correos cuyo asunto          ║
║    menciona un tipo de solicitud).                               ║
║  • Respuestas: Elementos enviados del mismo buzón.               ║
║                                                                  ║
║  • NO toca el estado leído/no-leído de los correos.              ║
║  • Modo TOLERANTE: si el asunto menciona un tipo pero no         ║
║    cumple el formato completo, igual se registra con "-" en      ║
║    los campos faltantes (no se descarta nada del histórico).     ║
║  • Después de correr esto, el robot diario                       ║
║    (bitacora_solicitudes.py) toma el control de los nuevos.      ║
║                                                                  ║
║  Por defecto arranca desde FECHA_INICIO (abajo). Para pruebas    ║
║  rápidas (ej. últimos 2 días) sin editar el código, se puede     ║
║  pasar la fecha por parámetro:                                   ║
║      python bootstrap_historico_solicitudes.py --desde 2026-07-05║
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
from datetime import datetime

from bitacora_solicitudes import (
    CONFIG, _BASE,
    GestorBackupSQL, HerramientasOutlook,
    procesar_solicitudes, procesar_respuestas,
    exportar_excel_desde_sqlite,
)

# Fecha por defecto si no se pasa --desde: se procesan correos desde aquí.
FECHA_INICIO = datetime(2026, 1, 1)


def _parsear_argumentos():
    parser = argparse.ArgumentParser(
        description="Bootstrap histórico — Bitácora Solicitudes de Clientes"
    )
    parser.add_argument(
        "--desde",
        type=str,
        default=None,
        help="Fecha desde la cual procesar correos, formato YYYY-MM-DD "
             "(ej. 2026-07-05). Si no se indica, usa FECHA_INICIO del código.",
    )
    return parser.parse_args()


def _parsear_fecha(texto: str) -> datetime:
    """Acepta 2026-07-05, 2026_07_05, 2026/07/05 o 05-07-2026."""
    normalizado = texto.strip().replace("_", "-").replace("/", "-")
    for formato in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(normalizado, formato)
        except ValueError:
            continue
    raise ValueError(
        f"No se pudo interpretar la fecha '{texto}'. Usa el formato AAAA-MM-DD "
        f"(ej. 2026-07-05)."
    )


def main():
    args = _parsear_argumentos()
    fecha_inicio = _parsear_fecha(args.desde) if args.desde else FECHA_INICIO

    sep = "═" * 65
    print(f"\n{sep}")
    print("  🏗️   BOOTSTRAP HISTÓRICO — Solicitudes de Clientes")
    print(f"  🕐  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  📂  Base: {_BASE}")
    print(f"  📬  Buzón: {CONFIG['BUZON'] or '(cuenta por defecto)'}")
    print(f"  📅  Desde: {fecha_inicio.strftime('%d/%m/%Y')}")
    print(f"{sep}\n")

    outlook = HerramientasOutlook(CONFIG["BUZON"])
    sql     = GestorBackupSQL(CONFIG["RUTA_DB_SQLITE"])

    if not outlook.conectado:
        print("❌ No se pudo conectar a Outlook. Abortando.")
        return

    # El buzón se recorre UNA sola vez; ambas fases comparten el índice.
    indice = outlook.indexar_correos(fecha_inicio)

    # ── FASE 1: SOLICITUDES HISTÓRICAS (modo tolerante) ───────────
    print(f"{'─'*40}")
    print("  FASE 1 — Solicitudes históricas")
    print(f"{'─'*40}\n")

    registrados, _ = procesar_solicitudes(
        outlook, sql, fecha_inicio, tolerante=True, indice=indice
    )

    # ── FASE 2: RESPUESTAS HISTÓRICAS ─────────────────────────────
    print(f"\n{'─'*40}")
    print("  FASE 2 — Respuestas históricas")
    print(f"{'─'*40}\n")

    respuestas = procesar_respuestas(outlook, sql, fecha_inicio, indice=indice)

    # ── EXPORTACIÓN ────────────────────────────────────────────────
    print(f"\n{'─'*40}")
    print("  EXPORTACIÓN")
    print(f"{'─'*40}\n")

    exportar_excel_desde_sqlite(sql, CONFIG["RUTA_EXCEL"])

    print(f"\n{sep}")
    print(f"  ✅  Bootstrap finalizado — {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'─'*65}")
    print(f"  Solicitudes registradas : {registrados}")
    print(f"  Respuestas vinculadas   : {respuestas}")
    print(f"{sep}\n")


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        print(f"\n❌ {e}\n")
