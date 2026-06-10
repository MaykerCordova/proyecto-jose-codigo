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
╚══════════════════════════════════════════════════════════════════╝
"""

from datetime import datetime

from bitacora_solicitudes import (
    CONFIG, _BASE,
    GestorBackupSQL, HerramientasOutlook,
    procesar_solicitudes, procesar_respuestas,
    exportar_excel_desde_sqlite,
)

# Solo se procesan correos recibidos/enviados desde esta fecha
FECHA_INICIO = datetime(2026, 1, 1)


def main():
    sep = "═" * 65
    print(f"\n{sep}")
    print("  🏗️   BOOTSTRAP HISTÓRICO — Solicitudes de Clientes")
    print(f"  🕐  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  📂  Base: {_BASE}")
    print(f"  📬  Buzón: {CONFIG['BUZON'] or '(cuenta por defecto)'}")
    print(f"  📅  Desde: {FECHA_INICIO.strftime('%d/%m/%Y')}")
    print(f"{sep}\n")

    outlook = HerramientasOutlook(CONFIG["BUZON"])
    sql     = GestorBackupSQL(CONFIG["RUTA_DB_SQLITE"])

    if not outlook.conectado:
        print("❌ No se pudo conectar a Outlook. Abortando.")
        return

    # ── FASE 1: SOLICITUDES HISTÓRICAS (modo tolerante) ───────────
    print(f"{'─'*40}")
    print("  FASE 1 — Solicitudes históricas")
    print(f"{'─'*40}\n")

    registrados, _ = procesar_solicitudes(
        outlook, sql, FECHA_INICIO, tolerante=True
    )

    # ── FASE 2: RESPUESTAS HISTÓRICAS ─────────────────────────────
    print(f"\n{'─'*40}")
    print("  FASE 2 — Respuestas históricas")
    print(f"{'─'*40}\n")

    respuestas = procesar_respuestas(outlook, sql, FECHA_INICIO)

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
    main()
