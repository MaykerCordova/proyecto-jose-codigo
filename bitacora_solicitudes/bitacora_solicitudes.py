"""
╔══════════════════════════════════════════════════════════════════╗
║     BITÁCORA SOLICITUDES DE CLIENTES — V1                        ║
║     Scotiabank Peru — Prevención de Fraude                       ║
╠══════════════════════════════════════════════════════════════════╣
║  Basado en la arquitectura de Bitácora Analytics V8:             ║
║                                                                  ║
║  • ConversationID de Outlook como llave primaria.                ║
║    El que responde lo hace sobre el correo original, así que     ║
║    solicitud y respuesta comparten el mismo ConversationID.      ║
║  • SQLite es la fuente de verdad; el Excel se regenera desde     ║
║    SQLite en cada corrida (nunca al revés).                      ║
║  • Correos de solicitud y de respuesta se guardan como .msg      ║
║    para auditoría (columnas Sustento y Sustento_Respuesta).      ║
║                                                                  ║
║  DIFERENCIA CLAVE respecto a V8:                                 ║
║  Aquí los datos NO vienen en el cuerpo del correo sino en el     ║
║  ASUNTO, con esta estructura:                                    ║
║                                                                  ║
║      Segmento - Tipo de Solicitud - DNI - Nombre de Cliente      ║
║                                                                  ║
║  Tipos de solicitud reconocidos:                                 ║
║      Aviso de Compra, Cliente Viajero, VCAS,                     ║
║      Error 59, Error 63, Reporte de cuenta                       ║
║                                                                  ║
║  Además se calcula el TIEMPO DE RESPUESTA (cuánto demoró el      ║
║  área en responder) cuando llega la conformidad/respuesta.       ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import re
import sqlite3
import unicodedata
import win32com.client
import pandas as pd
from datetime import datetime
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# ══════════════════════════════════════════════════════════════════
# 1. CONFIGURACIÓN
#    La ruta base se construye automáticamente desde el usuario
#    de Windows actual — no hay que editar nada al cambiar de PC.
# ══════════════════════════════════════════════════════════════════
_BASE = os.path.join(
    os.path.expanduser("~"),
    "OneDrive - The Bank of Nova Scotia",
    "Bitacora_Solicitudes_Clientes",
)

CONFIG = {
    "RUTA_EXCEL":            os.path.join(_BASE, "Bitacora_Solicitudes.xlsx"),
    "RUTA_EXCEL_PENDIENTES": os.path.join(_BASE, "Solicitudes_Sin_Formato.xlsx"),
    "RUTA_DB_SQLITE":        os.path.join(_BASE, "Respaldo_Solicitudes.db"),
    "RUTA_BACKUP_MSG":       os.path.join(_BASE, "Correos_Respaldo"),
    # ⚠️ AJUSTAR: nombres reales de las carpetas en Outlook
    "FOLDER_SOLICITUDES": "Solicitudes_Clientes",
    "FOLDER_RESPUESTAS":  "Solicitudes_Respuestas",
}

# ══════════════════════════════════════════════════════════════════
# 2. LÓGICA DE NEGOCIO — tipos de solicitud
# ══════════════════════════════════════════════════════════════════

def _normalizar(texto: str) -> str:
    """Mayúsculas, sin tildes y sin espacios extras — para comparar."""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().upper()


# Variantes aceptadas → nombre canónico que se guarda en la bitácora
TIPOS_SOLICITUD = {
    "AVISO DE COMPRA":    "Aviso de Compra",
    "CLIENTE VIAJERO":    "Cliente Viajero",
    "VCAS":               "VCAS",
    "ERROR 59":           "Error 59",
    "ERROR 63":           "Error 63",
    "REPORTE DE CUENTA":  "Reporte de cuenta",
    "REPORTAR CUENTA":    "Reporte de cuenta",
}

CAMPOS_REQUERIDOS = ["Segmento", "Tipo_Solicitud", "DNI", "Nombre_Cliente"]


def detectar_tipo(texto: str) -> str:
    """Devuelve el tipo canónico si el texto coincide con alguna variante."""
    limpio = _normalizar(texto)
    if limpio in TIPOS_SOLICITUD:
        return TIPOS_SOLICITUD[limpio]
    # Tolerancia: el tipo aparece dentro del texto (ej. "ERROR 59 - REINTENTO")
    for variante, canonico in TIPOS_SOLICITUD.items():
        if variante in limpio:
            return canonico
    return ""


# ══════════════════════════════════════════════════════════════════
# 3. PROCESADOR DE ASUNTO
#    Estructura esperada:
#    Segmento - Tipo de Solicitud - DNI - Nombre de Cliente
# ══════════════════════════════════════════════════════════════════

class ProcesadorAsunto:

    @staticmethod
    def parsear(asunto: str) -> dict:
        """Extrae Segmento, Tipo_Solicitud, DNI y Nombre_Cliente del asunto.

        Devuelve "-" en los campos que no se pudieron extraer.
        """
        datos = {c: "-" for c in CAMPOS_REQUERIDOS}

        # Quitar prefijos de reenvío/respuesta (RE:, RV:, FW:, FWD:)
        limpio = re.sub(r"(?i)^\s*((RE|RV|FW|FWD)\s*:\s*)+", "", str(asunto)).strip()

        # Separador oficial: guion CON espacios alrededor — así un apellido
        # compuesto tipo "Silva-Rojas" no se parte. Si no alcanza para los
        # 4 campos, se reintenta en modo flexible (guion sin espacios).
        partes = [p.strip() for p in re.split(r"\s+[-–—]\s+", limpio) if p.strip()]
        if len(partes) < 4:
            partes = [p.strip() for p in re.split(r"\s*[-–—]\s*", limpio) if p.strip()]

        if len(partes) >= 4:
            datos["Segmento"] = partes[0]
            tipo = detectar_tipo(partes[1])
            datos["Tipo_Solicitud"] = tipo if tipo else "-"
            datos["DNI"]            = partes[2]
            # El nombre puede contener guiones: unir todo lo que queda
            datos["Nombre_Cliente"] = " - ".join(partes[3:])
        else:
            # Estructura incompleta: rescatar lo que se pueda
            tipo = detectar_tipo(limpio)
            if tipo:
                datos["Tipo_Solicitud"] = tipo
            dni = re.search(r"\b\d{8}\b", limpio)
            if dni:
                datos["DNI"] = dni.group(0)

        return datos

    @staticmethod
    def validar(datos: dict) -> list:
        """Lista de campos que faltan o no se pudieron extraer."""
        return [
            c for c in CAMPOS_REQUERIDOS
            if str(datos.get(c, "-")).strip() in ("-", "")
        ]


# ══════════════════════════════════════════════════════════════════
# 4. GESTOR SQLITE — FUENTE DE VERDAD
# ══════════════════════════════════════════════════════════════════

class GestorBackupSQL:

    def __init__(self, ruta_db: str):
        self.ruta_db = ruta_db
        self._init_tablas()

    def _init_tablas(self):
        os.makedirs(os.path.dirname(self.ruta_db), exist_ok=True)
        with sqlite3.connect(self.ruta_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS Solicitudes (
                    Nro_Correlativo    INTEGER,
                    Fecha              TEXT,
                    Hora               TEXT,
                    Remitente          TEXT,
                    Asunto             TEXT,
                    Segmento           TEXT,
                    Tipo_Solicitud     TEXT,
                    DNI                TEXT,
                    Nombre_Cliente     TEXT,
                    Sustento           TEXT,
                    Respondido_Por     TEXT,
                    Fecha_Respuesta    TEXT,
                    Hora_Respuesta     TEXT,
                    Tiempo_Respuesta   TEXT,
                    Sustento_Respuesta TEXT,
                    Mes                TEXT,
                    Anio               TEXT,
                    Estado             TEXT,
                    ConversationID     TEXT PRIMARY KEY
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS Solicitudes_Pendientes (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    Fecha_Captura    TEXT,
                    ConversationID   TEXT,
                    Asunto           TEXT,
                    Remitente        TEXT,
                    Campos_Faltantes TEXT,
                    Procesado        INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def get_max_correlativo(self) -> int:
        with sqlite3.connect(self.ruta_db) as conn:
            r = conn.execute(
                "SELECT MAX(Nro_Correlativo) FROM Solicitudes"
            ).fetchone()[0]
        return 0 if r is None else int(r)

    def existe_conversation(self, conv_id: str) -> bool:
        with sqlite3.connect(self.ruta_db) as conn:
            r = conn.execute(
                "SELECT COUNT(*) FROM Solicitudes WHERE ConversationID = ?",
                (conv_id,)
            ).fetchone()[0]
        return r > 0

    def get_fecha_solicitud(self, conv_id: str):
        """Fecha y hora de llegada de la solicitud (para calcular demora)."""
        with sqlite3.connect(self.ruta_db) as conn:
            r = conn.execute(
                "SELECT Fecha, Hora FROM Solicitudes WHERE ConversationID = ?",
                (conv_id,)
            ).fetchone()
        if not r:
            return None
        try:
            return datetime.strptime(f"{r[0]} {r[1]}", "%d/%m/%Y %H:%M")
        except ValueError:
            return None

    def insertar_solicitud(self, datos: dict):
        sql = """
            INSERT OR IGNORE INTO Solicitudes VALUES (
                :Nro_Correlativo, :Fecha, :Hora, :Remitente, :Asunto,
                :Segmento, :Tipo_Solicitud, :DNI, :Nombre_Cliente,
                :Sustento, :Respondido_Por, :Fecha_Respuesta,
                :Hora_Respuesta, :Tiempo_Respuesta, :Sustento_Respuesta,
                :Mes, :Anio, :Estado, :ConversationID
            )
        """
        with sqlite3.connect(self.ruta_db) as conn:
            conn.execute(sql, datos)
            conn.commit()
        print("  💾 [SQLite] Solicitud insertada.")

    def registrar_pendiente(self, conv_id, asunto, remitente, campos_faltantes):
        with sqlite3.connect(self.ruta_db) as conn:
            conn.execute("""
                INSERT INTO Solicitudes_Pendientes
                    (Fecha_Captura, ConversationID, Asunto,
                     Remitente, Campos_Faltantes)
                VALUES (?, ?, ?, ?, ?)
            """, (
                datetime.now().strftime("%d/%m/%Y %H:%M"),
                conv_id, asunto, remitente,
                ", ".join(campos_faltantes),
            ))
            conn.commit()
        print(f"  ⚠️  [SQLite] Asunto sin formato → Pendientes: {asunto[:50]}")

    def registrar_respuesta(
        self, conv_id: str, respondido_por: str,
        fecha_resp: str, hora_resp: str,
        tiempo_respuesta: str, ruta_respuesta: str
    ):
        # Solo se registra la PRIMERA respuesta (Estado = 'Pendiente')
        with sqlite3.connect(self.ruta_db) as conn:
            conn.execute("""
                UPDATE Solicitudes
                SET Estado             = 'Completado',
                    Respondido_Por     = ?,
                    Fecha_Respuesta    = ?,
                    Hora_Respuesta     = ?,
                    Tiempo_Respuesta   = ?,
                    Sustento_Respuesta = ?
                WHERE ConversationID = ?
                  AND Estado = 'Pendiente'
            """, (respondido_por, fecha_resp, hora_resp,
                  tiempo_respuesta, ruta_respuesta, conv_id))
            conn.commit()
        print("  ✅ [SQLite] Respuesta registrada.")

    def exportar_bitacora(self) -> pd.DataFrame:
        with sqlite3.connect(self.ruta_db) as conn:
            return pd.read_sql(
                "SELECT * FROM Solicitudes ORDER BY Nro_Correlativo", conn
            )

    def exportar_pendientes(self) -> pd.DataFrame:
        with sqlite3.connect(self.ruta_db) as conn:
            return pd.read_sql(
                "SELECT * FROM Solicitudes_Pendientes WHERE Procesado = 0",
                conn
            )


# ══════════════════════════════════════════════════════════════════
# 5. FORMATO EXCEL
# ══════════════════════════════════════════════════════════════════

COLOR_HEADER   = "0079C1"
COLOR_PENDENTE = "FFC000"


def _aplicar_formato(ws, color: str = COLOR_HEADER):
    header_font  = Font(bold=True, color="FFFFFF")
    header_fill  = PatternFill(start_color=color, end_color=color,
                               fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center")
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
    ws.auto_filter.ref = ws.dimensions
    for col in ws.columns:
        max_len    = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value and len(str(cell.value)) > max_len:
                    max_len = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 2, 50)


def embellecer_excel(ruta: str, color: str = COLOR_HEADER):
    try:
        wb = load_workbook(ruta)
        _aplicar_formato(wb.active, color)
        wb.save(ruta)
        print(f"  🎨 [Excel] Formato aplicado: {os.path.basename(ruta)}")
    except Exception as e:
        print(f"  ▲ Error formato [{os.path.basename(ruta)}]: {e}")


def exportar_excel_desde_sqlite(sql: GestorBackupSQL, ruta: str):
    try:
        df = sql.exportar_bitacora()
        df.to_excel(ruta, index=False)
        embellecer_excel(ruta, COLOR_HEADER)
        print(f"  📊 [Excel] Exportado: {len(df)} registros.")
    except Exception as e:
        print(f"  ▲ Error exportando Excel: {e}")


def exportar_excel_pendientes(sql: GestorBackupSQL, ruta: str):
    try:
        df = sql.exportar_pendientes()
        if df.empty:
            return
        df.to_excel(ruta, index=False)
        embellecer_excel(ruta, COLOR_PENDENTE)
        print(f"  📋 [Excel] Pendientes: {len(df)} registros.")
    except Exception as e:
        print(f"  ▲ Error exportando Pendientes: {e}")


# ══════════════════════════════════════════════════════════════════
# 6. HERRAMIENTAS OUTLOOK
# ══════════════════════════════════════════════════════════════════

class HerramientasOutlook:

    def __init__(self):
        self.outlook = None
        self.inbox   = None
        try:
            self.outlook = (
                win32com.client
                .Dispatch("Outlook.Application")
                .GetNamespace("MAPI")
            )
            self.inbox = self.outlook.GetDefaultFolder(6)
        except Exception as e:
            print(f"  ▲ Error conectando a Outlook: {e}")

    @property
    def conectado(self) -> bool:
        return self.outlook is not None and self.inbox is not None

    def buscar_carpeta(self, nombre: str):
        try:    return self.inbox.Folders[nombre]
        except Exception: pass
        try:    return self.outlook.Folders[nombre]
        except Exception: return None

    def guardar_msg(self, mail, nombre: str) -> str:
        os.makedirs(CONFIG["RUTA_BACKUP_MSG"], exist_ok=True)
        clean = re.sub(r'[\\/*?:"<>|]', "_", nombre)[:120]
        ruta  = os.path.join(CONFIG["RUTA_BACKUP_MSG"], f"{clean}.msg")
        try:
            mail.SaveAs(ruta)
            return ruta
        except Exception as e:
            print(f"  ▲ Error guardando MSG [{nombre}]: {e}")
            return "Error guardando MSG"


# ══════════════════════════════════════════════════════════════════
# 7. UTILIDADES
# ══════════════════════════════════════════════════════════════════

def formatear_demora(inicio: datetime, fin: datetime) -> str:
    """Diferencia entre solicitud y respuesta como 'HH:MM' (horas totales)."""
    if fin < inicio:
        return "-"
    total_min = int((fin - inicio).total_seconds() // 60)
    horas, minutos = divmod(total_min, 60)
    return f"{horas:02d}:{minutos:02d}"


# ══════════════════════════════════════════════════════════════════
# 8. ORQUESTADOR PRINCIPAL
# ══════════════════════════════════════════════════════════════════

def main():
    sep = "═" * 65
    print(f"\n{sep}")
    print("  🤖  ROBOT BITÁCORA Solicitudes de Clientes — V1")
    print(f"  🕐  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  👤  Usuario: {os.getenv('USERNAME', 'desconocido')}")
    print(f"  📂  Base: {_BASE}")
    print(f"{sep}\n")

    outlook = HerramientasOutlook()
    sql     = GestorBackupSQL(CONFIG["RUTA_DB_SQLITE"])

    if not outlook.conectado:
        print("❌ No se pudo conectar a Outlook. Abortando.")
        return

    cambios    = 0
    pendientes = 0

    # ── FASE 1: SOLICITUDES ────────────────────────────────────────
    print(f"{'─'*40}")
    print("  FASE 1 — Solicitudes entrantes")
    print(f"{'─'*40}\n")

    sol_folder = outlook.buscar_carpeta(CONFIG["FOLDER_SOLICITUDES"])

    if not sol_folder:
        print(f"  ▲ Carpeta '{CONFIG['FOLDER_SOLICITUDES']}' no encontrada.")
    else:
        msgs = [m for m in sol_folder.Items if m.UnRead]
        msgs.sort(key=lambda x: x.ReceivedTime)
        print(f"  Correos no leídos: {len(msgs)}\n")

        for m in msgs:
            try:
                conv_id = m.ConversationID

                if sql.existe_conversation(conv_id):
                    print(f"  [DUP] ConversationID ya registrado: {m.Subject[:50]}")
                    m.UnRead = False
                    continue

                print(f"  [+] Nueva solicitud: {m.Subject[:60]}")

                d                = ProcesadorAsunto.parsear(m.Subject)
                campos_faltantes = ProcesadorAsunto.validar(d)

                if campos_faltantes:
                    sql.registrar_pendiente(
                        conv_id          = conv_id,
                        asunto           = m.Subject,
                        remitente        = m.SenderName,
                        campos_faltantes = campos_faltantes,
                    )
                    outlook.guardar_msg(m, f"PENDIENTE_{m.Subject[:40]}")
                    m.UnRead = False
                    pendientes += 1
                    continue

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
                m.UnRead = False
                cambios  += 1
                print(f"  ✔  Correlativo: {correlativo:04d} "
                      f"[{d['Tipo_Solicitud']}]\n")

            except Exception as e:
                print(f"  ▲ Error solicitud [{getattr(m, 'Subject', '?')[:60]}]: {e}")

    # ── FASE 2: RESPUESTAS ─────────────────────────────────────────
    print(f"\n{'─'*40}")
    print("  FASE 2 — Respuestas")
    print(f"{'─'*40}\n")

    resp_folder = outlook.buscar_carpeta(CONFIG["FOLDER_RESPUESTAS"])

    if not resp_folder:
        print(f"  ▲ Carpeta '{CONFIG['FOLDER_RESPUESTAS']}' no encontrada.")
    else:
        msgs = [m for m in resp_folder.Items if m.UnRead]
        msgs.sort(key=lambda x: x.ReceivedTime)
        print(f"  Respuestas no leídas: {len(msgs)}\n")

        for m in msgs:
            try:
                conv_id = m.ConversationID

                if not sql.existe_conversation(conv_id):
                    print(f"  [WARN] ConversationID no registrado: {m.Subject[:60]}")
                    m.UnRead = False
                    continue

                print(f"  [✓] Respuesta detectada: {m.Subject[:60]}")

                ruta_resp = outlook.guardar_msg(
                    m, f"RESP_{conv_id[:20]}"
                )

                fecha_resp = m.ReceivedTime
                # naive datetime para restar contra lo guardado en SQLite
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
                m.UnRead = False
                cambios  += 1

            except Exception as e:
                print(f"  ▲ Error respuesta [{getattr(m, 'Subject', '?')[:60]}]: {e}")

    # ── EXPORTACIÓN ────────────────────────────────────────────────
    print(f"\n{'─'*40}")
    print("  EXPORTACIÓN")
    print(f"{'─'*40}\n")

    exportar_excel_desde_sqlite(sql, CONFIG["RUTA_EXCEL"])

    df_pend = sql.exportar_pendientes()
    if not df_pend.empty:
        exportar_excel_pendientes(sql, CONFIG["RUTA_EXCEL_PENDIENTES"])
    else:
        print("  ✔  Sin asuntos pendientes de formato.")

    # ── RESUMEN ────────────────────────────────────────────────────
    print(f"\n{sep}")
    print(f"  ✅  Finalizado — {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'─'*65}")
    print(f"  Registros nuevos / actualizados : {cambios}")
    print(f"  Asuntos sin formato (pendientes): {pendientes}")
    if pendientes > 0:
        print("  → Revisar: Solicitudes_Sin_Formato.xlsx")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
