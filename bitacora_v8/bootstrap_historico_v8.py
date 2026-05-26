"""
╔══════════════════════════════════════════════════════════════════╗
║  BOOTSTRAP HISTÓRICO V8 — Reconstrucción desde Outlook          ║
║  Ejecutar UNA SOLA VEZ antes de activar bitacoraV8.py           ║
╠══════════════════════════════════════════════════════════════════╣
║  Qué hace:                                                      ║
║  1. Lee TODOS los correos de Bitacora_Solicitudes y             ║
║     Bitacora_Respuestas desde FECHA_INICIO (sin filtro          ║
║     de no leídos — procesa el historial completo).              ║
║  2. Limpia el SQLite anterior (MODO_RESET = True) y             ║
║     reconstruye con el nuevo esquema V8:                        ║
║     → ConversationID como llave primaria                        ║
║     → Columna Sustento_Respuesta                                ║
║  3. NO marca correos como leídos — no toca el estado           ║
║     de Outlook, solo lee.                                       ║
║  4. Para solicitudes sin formato correcto, no las descarta:     ║
║     las registra con los campos disponibles y "-" en los        ║
║     que faltan (modo tolerante para datos históricos).          ║
║  5. Muestra resumen con correlativo máximo para verificar       ║
║     que V8 arranca desde el número correcto.                    ║
║                                                                  ║
║  Rutas dinámicas — detecta el usuario de Windows               ║
║  automáticamente. No hay que editar nada al cambiar de PC.      ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import re
import sqlite3
import win32com.client
from datetime import datetime

# ══════════════════════════════════════════════════════════════════
# ▶  CONFIGURACIÓN — solo editar estas variables
# ══════════════════════════════════════════════════════════════════

# Procesar correos desde esta fecha en adelante
FECHA_INICIO = datetime(2026, 1, 1)

# True = limpia el SQLite antes de reconstruir (recomendado para primera vez)
# False = solo agrega los que no existen (si ya corriste el bootstrap
#         una vez y quieres agregar correos nuevos sin resetear)
MODO_RESET = True

# Número desde el que debe arrancar el correlativo.
# Si el SQLite ya tiene registros con correlativos mayores, continúa desde ahí.
CORRELATIVO_INICIAL = 2671

# Las rutas se construyen automáticamente desde el usuario de Windows actual
_BASE = os.path.join(
    os.path.expanduser("~"),
    "OneDrive - The Bank of Nova Scotia",
    "Bitacora_Reglas",
)

RUTA_DB_SQLITE  = os.path.join(_BASE, "Respaldo_Blindado.db")
RUTA_BACKUP_MSG = os.path.join(_BASE, "Correos_Respaldo")

FOLDER_SOLICITUDES = "Bitacora_Solicitudes"
FOLDER_RESPUESTAS  = "Bitacora_Respuestas"

MAPA_ESTIMACION = {
    "PMFD":  "15:01",
    "CORE":  "N/A",
    "ITC":   "N/A",
    "RT TD": "5:01",
    "RT TC": "5:01",
    "VRM":   "5:01",
    "VCAS":  "5:01",
    "FRM":   "5:01",
}

PALABRAS_APROBACION = [
    "OK", "CONFORME", "APROBADO", "APROBADA",
    "VOBO", "PROCEDER", "ACUERDO",
]

REGEX_ID = r"\[([^\]]+)\]"

PATRONES_CUERPO = {
    "Solicitado_Por":    r"(?i)SOLICITADO\s*POR:\s*(.*)",
    "Herramienta":       r"(?i)HERRAMIENTA:\s*(.*)",
    "Accion":            r"(?i)ACCI[OÓ]N:\s*(.*)",
    "Institucion":       r"(?i)INSTITUCI[OÓ]N:\s*(.*)",
    "Codigo_Condicion":  r"(?i)C[OÓ]DIGO\s*(?:DE)?\s*CONDICI[OÓ]N:\s*(.*)",
    "Nombre_Condicion":  r"(?i)NOMBRE\s*(?:DE)?\s*CONDICI[OÓ]N:\s*(.*)",
    "Estatus_Condicion": r"(?i)ESTATUS\s*(?:DE)?\s*CONDICI[OÓ]N:\s*(.*)",
    "Tipo_Condicion":    r"(?i)TIPO\s*(?:DE)?\s*CONDICI[OÓ]N:\s*(.*)",
    "Canal":             r"(?i)CANAL:\s*(.*)",
    "Consideraciones":   r"(?i)CONSIDERACIONES:\s*(.*)",
    "Objetivo":          r"(?i)OBJETIVO:\s*(.*)",
}


# ══════════════════════════════════════════════════════════════════
# FUNCIONES AUXILIARES
# ══════════════════════════════════════════════════════════════════

def calcular_estimacion(herramienta: str) -> str:
    h = str(herramienta).strip().upper()
    for key, value in MAPA_ESTIMACION.items():
        if key in h:
            return value
    return "ND"


def extraer_id(asunto: str):
    match = re.search(REGEX_ID, asunto)
    return match.group(1).strip().upper() if match else None


def parsear_cuerpo(cuerpo: str) -> dict:
    datos = {}
    for k, patron in PATRONES_CUERPO.items():
        match = re.search(patron, cuerpo)
        datos[k] = (
            match.group(1).strip().replace('\r', '').replace('\n', ' ')
            if match else "-"
        )
    return datos


def guardar_msg(mail, nombre: str) -> str:
    os.makedirs(RUTA_BACKUP_MSG, exist_ok=True)
    clean = re.sub(r'[\\/*?:"<>|]', "_", nombre)
    ruta  = os.path.join(RUTA_BACKUP_MSG, f"{clean}.msg")
    try:
        mail.SaveAs(ruta)
        return ruta
    except Exception:
        return "Error guardando MSG"


def init_sqlite(ruta_db: str, reset: bool):
    os.makedirs(os.path.dirname(ruta_db), exist_ok=True)
    with sqlite3.connect(ruta_db) as conn:
        if reset:
            conn.execute("DROP TABLE IF EXISTS Bitacora")
            conn.execute("DROP TABLE IF EXISTS Bitacora_Pendientes")
            conn.commit()
            print("  🗑️  SQLite limpiado. Reconstruyendo desde Outlook...")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS Bitacora (
                Nro_Correlativo    INTEGER,
                Fecha              TEXT,
                Hora               TEXT,
                Codigo_Generado    TEXT,
                Maker              TEXT,
                Solicitado_Por     TEXT,
                Herramienta        TEXT,
                Accion             TEXT,
                Institucion        TEXT,
                Codigo_Condicion   TEXT,
                Nombre_Condicion   TEXT,
                Estatus_Condicion  TEXT,
                Tipo_Condicion     TEXT,
                Consideraciones    TEXT,
                Objetivo           TEXT,
                Estimacion         TEXT,
                Sustento           TEXT,
                Sustento_Respuesta TEXT,
                Checker            TEXT,
                Fecha_Revision     TEXT,
                Hora_Revision      TEXT,
                Mes_Revision       TEXT,
                Anio_Revision      TEXT,
                Enviado_Jefatura   TEXT,
                Conformidad        TEXT,
                Canal              TEXT,
                ID_Sistema         TEXT,
                ConversationID     TEXT PRIMARY KEY
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS Bitacora_Pendientes (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                Fecha_Captura    TEXT,
                ConversationID   TEXT,
                ID_Sistema       TEXT,
                Asunto           TEXT,
                Remitente        TEXT,
                Campos_Faltantes TEXT,
                Cuerpo_Raw       TEXT,
                Procesado        INTEGER DEFAULT 0
            )
        """)
        conn.commit()


def get_max_correlativo(ruta_db: str) -> int:
    with sqlite3.connect(ruta_db) as conn:
        r = conn.execute(
            "SELECT MAX(Nro_Correlativo) FROM Bitacora"
        ).fetchone()[0]
    return 0 if r is None else int(r)


def existe_conversation(ruta_db: str, conv_id: str) -> bool:
    with sqlite3.connect(ruta_db) as conn:
        r = conn.execute(
            "SELECT COUNT(*) FROM Bitacora WHERE ConversationID = ?",
            (conv_id,)
        ).fetchone()[0]
    return r > 0


def insertar_solicitud(ruta_db: str, datos: dict):
    sql = """
        INSERT OR IGNORE INTO Bitacora VALUES (
            :Nro_Correlativo, :Fecha, :Hora, :Codigo_Generado,
            :Maker, :Solicitado_Por, :Herramienta, :Accion,
            :Institucion, :Codigo_Condicion, :Nombre_Condicion,
            :Estatus_Condicion, :Tipo_Condicion, :Consideraciones,
            :Objetivo, :Estimacion, :Sustento, :Sustento_Respuesta,
            :Checker, :Fecha_Revision, :Hora_Revision, :Mes_Revision,
            :Anio_Revision, :Enviado_Jefatura, :Conformidad,
            :Canal, :ID_Sistema, :ConversationID
        )
    """
    with sqlite3.connect(ruta_db) as conn:
        conn.execute(sql, datos)
        conn.commit()


def actualizar_aprobacion(ruta_db: str, conv_id: str, checker: str,
                           fecha_rev: str, hora_rev: str, mes_rev: str,
                           anio_rev: str, ruta_respuesta: str):
    with sqlite3.connect(ruta_db) as conn:
        conn.execute("""
            UPDATE Bitacora
            SET Conformidad        = 'Completado',
                Checker            = ?,
                Fecha_Revision     = ?,
                Hora_Revision      = ?,
                Mes_Revision       = ?,
                Anio_Revision      = ?,
                Sustento_Respuesta = ?
            WHERE ConversationID = ?
        """, (checker, fecha_rev, hora_rev, mes_rev,
              anio_rev, ruta_respuesta, conv_id))
        conn.commit()


def buscar_carpeta(outlook_ns, inbox, nombre: str):
    try:    return inbox.Folders[nombre]
    except Exception: pass
    try:    return outlook_ns.Folders[nombre]
    except Exception: return None


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    sep = "═" * 65
    print(f"\n{sep}")
    print(f"  🔄  BOOTSTRAP HISTÓRICO V8")
    print(f"  🕐  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  👤  Usuario: {os.getenv('USERNAME', 'desconocido')}")
    print(f"  📂  Base: {_BASE}")
    print(f"  📅  Procesando desde: {FECHA_INICIO.strftime('%d/%m/%Y')}")
    print(f"{sep}\n")

    # ── Conectar Outlook ───────────────────────────────────────────
    try:
        ns    = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        inbox = ns.GetDefaultFolder(6)
        print("  ✔  Outlook conectado.\n")
    except Exception as e:
        print(f"  ❌ Error conectando a Outlook: {e}")
        return

    # ── Inicializar SQLite ─────────────────────────────────────────
    init_sqlite(RUTA_DB_SQLITE, MODO_RESET)

    insertados_sol = 0
    duplicados_sol = 0
    errores_sol    = 0
    actualizados   = 0
    errores_resp   = 0

    # ══ FASE 1: SOLICITUDES HISTÓRICAS ════════════════════════════
    print(f"{'─'*40}")
    print("  FASE 1 — Solicitudes históricas")
    print(f"{'─'*40}\n")

    sol_folder = buscar_carpeta(ns, inbox, FOLDER_SOLICITUDES)

    if not sol_folder:
        print(f"  ▲ Carpeta '{FOLDER_SOLICITUDES}' no encontrada.")
    else:
        todos = []
        for m in sol_folder.Items:
            try:
                if m.ReceivedTime.replace(tzinfo=None) >= FECHA_INICIO:
                    todos.append(m)
            except Exception:
                pass

        todos.sort(key=lambda x: x.ReceivedTime)
        print(f"  Correos encontrados desde {FECHA_INICIO.strftime('%d/%m/%Y')}: {len(todos)}\n")

        for m in todos:
            try:
                conv_id = m.ConversationID
                id_sys  = extraer_id(m.Subject) or "-"

                if existe_conversation(RUTA_DB_SQLITE, conv_id):
                    duplicados_sol += 1
                    continue

                d = parsear_cuerpo(m.Body)

                correlativo  = max(get_max_correlativo(RUTA_DB_SQLITE) + 1, CORRELATIVO_INICIAL)
                parte_corr   = f"{correlativo:04d}"
                parte_fecha  = m.SentOn.strftime("%d%m%y")
                parte_tool   = d.get("Herramienta", "-").strip()
                parte_insti  = d.get("Institucion", "-").strip()
                parte_cond   = d.get("Codigo_Condicion", "-").strip()
                cod_generado = f"{parte_corr}{parte_fecha}{parte_tool}{parte_insti}{parte_cond}"

                nombre_msg = f"REQ_{id_sys}" if id_sys != "-" else f"REQ_HIST_{parte_corr}"
                ruta_msg   = guardar_msg(m, nombre_msg)

                fila = {
                    "Nro_Correlativo":   correlativo,
                    "Fecha":             m.SentOn.strftime("%d/%m/%Y"),
                    "Hora":              m.SentOn.strftime("%H:%M"),
                    "Codigo_Generado":   cod_generado,
                    "Maker":             m.SenderName,
                    "Solicitado_Por":    d.get("Solicitado_Por", "-"),
                    "Herramienta":       d.get("Herramienta", "-"),
                    "Accion":            d.get("Accion", "-"),
                    "Institucion":       d.get("Institucion", "-"),
                    "Codigo_Condicion":  d.get("Codigo_Condicion", "-"),
                    "Nombre_Condicion":  d.get("Nombre_Condicion", "-"),
                    "Estatus_Condicion": d.get("Estatus_Condicion", "-"),
                    "Tipo_Condicion":    d.get("Tipo_Condicion", "-"),
                    "Consideraciones":   d.get("Consideraciones", "-"),
                    "Objetivo":          d.get("Objetivo", "-"),
                    "Estimacion":        calcular_estimacion(d.get("Herramienta", "")),
                    "Sustento":          ruta_msg,
                    "Sustento_Respuesta": "-",
                    "Checker":           "-",
                    "Fecha_Revision":    "-",
                    "Hora_Revision":     "-",
                    "Mes_Revision":      "-",
                    "Anio_Revision":     "-",
                    "Enviado_Jefatura":  "SI",
                    "Conformidad":       "Pendiente",
                    "Canal":             d.get("Canal", "-"),
                    "ID_Sistema":        id_sys,
                    "ConversationID":    conv_id,
                }

                insertar_solicitud(RUTA_DB_SQLITE, fila)
                insertados_sol += 1

                if insertados_sol % 20 == 0:
                    print(f"  ... {insertados_sol} solicitudes procesadas")

            except Exception as e:
                errores_sol += 1
                print(f"  ▲ Error solicitud [{getattr(m, 'Subject', '?')[:60]}]: {e}")

    print(f"\n  Solicitudes insertadas : {insertados_sol}")
    print(f"  Duplicados ignorados   : {duplicados_sol}")
    print(f"  Errores                : {errores_sol}")

    # ══ FASE 2: RESPUESTAS HISTÓRICAS ═════════════════════════════
    print(f"\n{'─'*40}")
    print("  FASE 2 — Respuestas históricas")
    print(f"{'─'*40}\n")

    resp_folder = buscar_carpeta(ns, inbox, FOLDER_RESPUESTAS)

    if not resp_folder:
        print(f"  ▲ Carpeta '{FOLDER_RESPUESTAS}' no encontrada.")
    else:
        todos_resp = []
        for m in resp_folder.Items:
            try:
                if m.ReceivedTime.replace(tzinfo=None) >= FECHA_INICIO:
                    todos_resp.append(m)
            except Exception:
                pass

        todos_resp.sort(key=lambda x: x.ReceivedTime)
        print(f"  Respuestas encontradas desde {FECHA_INICIO.strftime('%d/%m/%Y')}: {len(todos_resp)}\n")

        for m in todos_resp:
            try:
                conv_id      = m.ConversationID
                cuerpo_upper = m.Body.upper()
                es_aprobacion = any(p in cuerpo_upper for p in PALABRAS_APROBACION)

                if not es_aprobacion:
                    continue

                if not existe_conversation(RUTA_DB_SQLITE, conv_id):
                    continue

                id_ref    = extraer_id(m.Subject) or conv_id[:20]
                ruta_resp = guardar_msg(m, f"RESP_{id_ref}")
                fecha_obj = m.ReceivedTime

                actualizar_aprobacion(
                    RUTA_DB_SQLITE,
                    conv_id        = conv_id,
                    checker        = m.SenderName,
                    fecha_rev      = fecha_obj.strftime("%d/%m/%Y"),
                    hora_rev       = fecha_obj.strftime("%H:%M"),
                    mes_rev        = fecha_obj.strftime("%m"),
                    anio_rev       = fecha_obj.strftime("%Y"),
                    ruta_respuesta = ruta_resp,
                )
                actualizados += 1

            except Exception as e:
                errores_resp += 1
                print(f"  ▲ Error respuesta [{getattr(m, 'Subject', '?')[:60]}]: {e}")

    print(f"  Conformidades actualizadas : {actualizados}")
    print(f"  Errores                    : {errores_resp}")

    # ── Verificación final ─────────────────────────────────────────
    with sqlite3.connect(RUTA_DB_SQLITE) as conn:
        total           = conn.execute("SELECT COUNT(*) FROM Bitacora").fetchone()[0]
        max_correlativo = conn.execute(
            "SELECT MAX(Nro_Correlativo) FROM Bitacora"
        ).fetchone()[0]
        completados     = conn.execute(
            "SELECT COUNT(*) FROM Bitacora WHERE Conformidad = 'Completado'"
        ).fetchone()[0]
        pendientes_db   = conn.execute(
            "SELECT COUNT(*) FROM Bitacora WHERE Conformidad = 'Pendiente'"
        ).fetchone()[0]

    print(f"\n{sep}")
    print(f"  ✅  BOOTSTRAP HISTÓRICO COMPLETADO")
    print(f"{'─'*65}")
    print(f"  Total registros en SQLite   : {total}")
    print(f"  Conformidad Completado      : {completados}")
    print(f"  Conformidad Pendiente       : {pendientes_db}")
    print(f"  Correlativo máximo          : {max_correlativo}")
    print(f"  Próximo correlativo (V8)    : {max_correlativo + 1}")
    print(f"{sep}")

    if errores_sol == 0 and errores_resp == 0:
        print(f"\n  🟢 Todo OK. Ya puedes activar bitacoraV8.py.")
        print(f"     El próximo ticket recibirá el correlativo {max_correlativo + 1}.\n")
    else:
        print(f"\n  🟡 Hay errores. Revisa los mensajes arriba antes de activar V8.\n")


if __name__ == "__main__":
    main()
