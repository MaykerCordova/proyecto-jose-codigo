"""
╔══════════════════════════════════════════════════════════════════╗
║     BOOTSTRAP HISTÓRICO — Bitácora Solicitudes de Clientes       ║
║     Scotiabank Peru — Prevención de Fraude                       ║
╠══════════════════════════════════════════════════════════════════╣
║  ⚠️  CORRER UNA SOLA VEZ.                                        ║
║                                                                  ║
║  Reconstruye la base SQLite desde TODOS los correos reales que   ║
║  ya están en las carpetas de Outlook (leídos o no leídos),       ║
║  desde FECHA_INICIO en adelante.                                 ║
║                                                                  ║
║  • NO toca el estado leído/no-leído de los correos.              ║
║  • Modo TOLERANTE: si el asunto no cumple el formato completo,   ║
║    igual se registra con "-" en los campos faltantes (no se      ║
║    descarta nada del histórico).                                 ║
║  • Después de correr esto, el robot diario                       ║
║    (bitacora_solicitudes.py) toma el control de los nuevos.      ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
from datetime import datetime

from bitacora_solicitudes import (
    CONFIG, _BASE,
    GestorBackupSQL, HerramientasOutlook, ProcesadorAsunto,
    exportar_excel_desde_sqlite, formatear_demora,
)

# Solo se procesan correos recibidos desde esta fecha
FECHA_INICIO = datetime(2026, 1, 1)


def main():
    sep = "═" * 65
    print(f"\n{sep}")
    print("  🏗️   BOOTSTRAP HISTÓRICO — Solicitudes de Clientes")
    print(f"  🕐  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  📂  Base: {_BASE}")
    print(f"  📅  Desde: {FECHA_INICIO.strftime('%d/%m/%Y')}")
    print(f"{sep}\n")

    outlook = HerramientasOutlook()
    sql     = GestorBackupSQL(CONFIG["RUTA_DB_SQLITE"])

    if not outlook.conectado:
        print("❌ No se pudo conectar a Outlook. Abortando.")
        return

    registrados = 0
    respuestas  = 0

    # ── FASE 1: TODAS LAS SOLICITUDES HISTÓRICAS ──────────────────
    print(f"{'─'*40}")
    print("  FASE 1 — Solicitudes históricas")
    print(f"{'─'*40}\n")

    sol_folder = outlook.buscar_carpeta(CONFIG["FOLDER_SOLICITUDES"])

    if not sol_folder:
        print(f"  ▲ Carpeta '{CONFIG['FOLDER_SOLICITUDES']}' no encontrada.")
        return

    msgs = []
    for m in sol_folder.Items:
        try:
            recibido = m.ReceivedTime
            if datetime(recibido.year, recibido.month, recibido.day) >= FECHA_INICIO:
                msgs.append(m)
        except Exception:
            continue
    msgs.sort(key=lambda x: x.ReceivedTime)
    print(f"  Correos en rango: {len(msgs)}\n")

    for m in msgs:
        try:
            conv_id = m.ConversationID

            if sql.existe_conversation(conv_id):
                continue

            # MODO TOLERANTE: se registra aunque falten campos
            d = ProcesadorAsunto.parsear(m.Subject)

            correlativo = sql.get_max_correlativo() + 1
            ruta_msg    = outlook.guardar_msg(
                m, f"REQ_{correlativo:04d}_{d['DNI']}"
            )

            fila = {
                "Nro_Correlativo":    correlativo,
                "Fecha":              m.ReceivedTime.strftime("%d/%m/%Y"),
                "Hora":               m.ReceivedTime.strftime("%H:%M"),
                "Remitente":          m.SenderName,
                "Asunto":             m.Subject,
                "Segmento":           d["Segmento"],
                "Tipo_Solicitud":     d["Tipo_Solicitud"],
                "DNI":                d["DNI"],
                "Nombre_Cliente":     d["Nombre_Cliente"],
                "Sustento":           ruta_msg,
                "Respondido_Por":     "-",
                "Fecha_Respuesta":    "-",
                "Hora_Respuesta":     "-",
                "Tiempo_Respuesta":   "-",
                "Sustento_Respuesta": "-",
                "Mes":                m.ReceivedTime.strftime("%m"),
                "Anio":               m.ReceivedTime.strftime("%Y"),
                "Estado":             "Pendiente",
                "ConversationID":     conv_id,
            }

            sql.insertar_solicitud(fila)
            registrados += 1
            print(f"  ✔  {correlativo:04d} [{d['Tipo_Solicitud']}] "
                  f"{m.Subject[:55]}")

        except Exception as e:
            print(f"  ▲ Error solicitud [{getattr(m, 'Subject', '?')[:60]}]: {e}")

    # ── FASE 2: TODAS LAS RESPUESTAS HISTÓRICAS ───────────────────
    print(f"\n{'─'*40}")
    print("  FASE 2 — Respuestas históricas")
    print(f"{'─'*40}\n")

    resp_folder = outlook.buscar_carpeta(CONFIG["FOLDER_RESPUESTAS"])

    if not resp_folder:
        print(f"  ▲ Carpeta '{CONFIG['FOLDER_RESPUESTAS']}' no encontrada.")
    else:
        msgs = []
        for m in resp_folder.Items:
            try:
                recibido = m.ReceivedTime
                if datetime(recibido.year, recibido.month, recibido.day) >= FECHA_INICIO:
                    msgs.append(m)
            except Exception:
                continue
        msgs.sort(key=lambda x: x.ReceivedTime)
        print(f"  Respuestas en rango: {len(msgs)}\n")

        for m in msgs:
            try:
                conv_id = m.ConversationID

                if not sql.existe_conversation(conv_id):
                    continue

                ruta_resp = outlook.guardar_msg(m, f"RESP_{conv_id[:20]}")

                fecha_resp = m.ReceivedTime
                fecha_resp_naive = datetime(
                    fecha_resp.year, fecha_resp.month, fecha_resp.day,
                    fecha_resp.hour, fecha_resp.minute
                )
                inicio = sql.get_fecha_solicitud(conv_id)
                demora = (
                    formatear_demora(inicio, fecha_resp_naive)
                    if inicio else "-"
                )

                sql.registrar_respuesta(
                    conv_id          = conv_id,
                    respondido_por   = m.SenderName,
                    fecha_resp       = fecha_resp.strftime("%d/%m/%Y"),
                    hora_resp        = fecha_resp.strftime("%H:%M"),
                    tiempo_respuesta = demora,
                    ruta_respuesta   = ruta_resp,
                )
                respuestas += 1
                print(f"  ✔  Respuesta: {m.Subject[:55]}")

            except Exception as e:
                print(f"  ▲ Error respuesta [{getattr(m, 'Subject', '?')[:60]}]: {e}")

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
