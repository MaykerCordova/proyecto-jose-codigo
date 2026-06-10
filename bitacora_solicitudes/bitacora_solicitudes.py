"""
╔══════════════════════════════════════════════════════════════════╗
║     BITÁCORA SOLICITUDES DE CLIENTES — V1                        ║
║     Scotiabank Peru — Prevención de Fraude                       ║
╠══════════════════════════════════════════════════════════════════╣
║  Basado en la arquitectura de Bitácora Analytics V8:             ║
║                                                                  ║
║  • ConversationID de Outlook como llave primaria.                ║
║    El analista responde sobre el correo original, así que        ║
║    solicitud y respuesta comparten el mismo ConversationID.      ║
║  • SQLite es la fuente de verdad; el Excel se regenera desde     ║
║    SQLite en cada corrida (nunca al revés).                      ║
║  • Correos de solicitud y de respuesta se guardan como .msg      ║
║    para auditoría (columnas Sustento y Sustento_Respuesta).      ║
║                                                                  ║
║  DIFERENCIAS CLAVE respecto a V8:                                ║
║                                                                  ║
║  1. NO hay carpetas dedicadas en Outlook. Todo vive en el        ║
║     buzón: las solicitudes de los funcionarios llegan a la       ║
║     BANDEJA DE ENTRADA y las respuestas de los analistas         ║
║     salen por ELEMENTOS ENVIADOS del mismo buzón.                ║
║                                                                  ║
║  2. El robot reconoce las solicitudes por el ASUNTO:             ║
║                                                                  ║
║      Segmento - Tipo de Solicitud - DNI - Nombre de Cliente      ║
║                                                                  ║
║     Tipos reconocidos: Aviso de Compra, Cliente Viajero,         ║
║     VCAS, Error 59, Error 63, Reporte de cuenta.                 ║
║     Los correos cuyo asunto no contiene ningún tipo se           ║
║     ignoran (son correo normal del buzón).                       ║
║                                                                  ║
║  3. NO se usa el estado leído/no-leído (en un buzón              ║
║     compartido lo leen los analistas). El robot revisa los       ║
║     correos de los últimos DIAS_VENTANA días y el                ║
║     ConversationID ya registrado en SQLite evita duplicar.       ║
║     El robot NUNCA marca correos como leídos.                    ║
║                                                                  ║
║  4. Se calcula el TIEMPO DE RESPUESTA (cuánto demoró el          ║
║     analista en responder) cuando se detecta la respuesta.       ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import re
import sqlite3
import unicodedata
import win32com.client
import pandas as pd
from datetime import datetime, timedelta
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
    # ⚠️ AJUSTAR: buzón donde llegan los correos.
    #   ""  → tu cuenta personal (la cuenta por defecto de Outlook)
    #   "Prevencion de Fraude" → nombre EXACTO del buzón compartido,
    #   tal como aparece en el panel izquierdo de Outlook.
    "BUZON": "",
    # Cuántos días hacia atrás revisa el robot en cada corrida.
    # Si el robot deja de correr más días que esto, subir el número
    # temporalmente para no perder correos.
    "DIAS_VENTANA": 7,
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
    def es_solicitud(asunto: str) -> bool:
        """True si el asunto menciona alguno de los tipos de solicitud.
        Es el filtro que separa las solicitudes del resto del correo
        que llega a la bandeja de entrada."""
        return detectar_tipo(asunto) != ""

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

    def existe_pendiente(self, conv_id: str) -> bool:
        """Evita reinsertar el mismo asunto sin formato en cada corrida."""
        with sqlite3.connect(self.ruta_db) as conn:
            r = conn.execute(
                "SELECT COUNT(*) FROM Solicitudes_Pendientes "
                "WHERE ConversationID = ?",
                (conv_id,)
            ).fetchone()[0]
        return r > 0

    def get_estado(self, conv_id: str):
        """'Pendiente', 'Completado' o None si no existe."""
        with sqlite3.connect(self.ruta_db) as conn:
            r = conn.execute(
                "SELECT Estado FROM Solicitudes WHERE ConversationID = ?",
                (conv_id,)
            ).fetchone()
        return r[0] if r else None

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

    def __init__(self, buzon: str = ""):
        """buzon: nombre del buzón compartido; "" usa la cuenta por defecto."""
        self.outlook  = None
        self.inbox    = None   # Bandeja de entrada (solicitudes)
        self.enviados = None   # Elementos enviados (respuestas de analistas)
        try:
            self.outlook = (
                win32com.client
                .Dispatch("Outlook.Application")
                .GetNamespace("MAPI")
            )
            if buzon:
                store         = self.outlook.Folders[buzon]
                self.inbox    = self._subcarpeta(
                    store, "Bandeja de entrada", "Inbox")
                self.enviados = self._subcarpeta(
                    store, "Elementos enviados", "Sent Items")
                if self.inbox is None:
                    print(f"  ▲ No se encontró la Bandeja de entrada "
                          f"del buzón '{buzon}'.")
                if self.enviados is None:
                    print(f"  ▲ No se encontró Elementos enviados "
                          f"del buzón '{buzon}'.")
            else:
                self.inbox    = self.outlook.GetDefaultFolder(6)
                self.enviados = self.outlook.GetDefaultFolder(5)
        except Exception as e:
            print(f"  ▲ Error conectando a Outlook: {e}")

    @staticmethod
    def _subcarpeta(store, *nombres):
        """La carpeta puede llamarse distinto según el idioma de Outlook."""
        for nombre in nombres:
            try:
                return store.Folders[nombre]
            except Exception:
                continue
        return None

    @property
    def conectado(self) -> bool:
        return self.outlook is not None and self.inbox is not None

    @staticmethod
    def correos_desde(carpeta, fecha: datetime) -> list:
        """Correos de la carpeta recibidos/enviados desde `fecha`,
        ordenados del más antiguo al más reciente. NO altera nada."""
        items = carpeta.Items
        items.Sort("[ReceivedTime]")
        # El filtro Restrict usa formato de fecha US: MM/DD/YYYY
        filtro = f"[ReceivedTime] >= '{fecha.strftime('%m/%d/%Y')} 00:00'"
        try:
            return list(items.Restrict(filtro))
        except Exception:
            # Fallback: recorrer todo y filtrar en Python
            out = []
            for m in items:
                try:
                    rt = m.ReceivedTime
                    if datetime(rt.year, rt.month, rt.day) >= fecha:
                        out.append(m)
                except Exception:
                    continue
            return out

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


def a_naive(fecha_com) -> datetime:
    """Convierte la fecha COM de Outlook a datetime naive (sin tz)."""
    return datetime(fecha_com.year, fecha_com.month, fecha_com.day,
                    fecha_com.hour, fecha_com.minute)


# ══════════════════════════════════════════════════════════════════
# 8. FASES DE PROCESAMIENTO
#    (compartidas entre el robot diario y el bootstrap histórico)
# ══════════════════════════════════════════════════════════════════

def procesar_solicitudes(
    outlook: HerramientasOutlook, sql: GestorBackupSQL,
    desde: datetime, tolerante: bool = False
) -> tuple:
    """Escanea la Bandeja de entrada y registra las solicitudes.

    tolerante=True (bootstrap): registra aunque falten campos.
    tolerante=False (diario): los incompletos van a Pendientes.
    Devuelve (registrados, pendientes).
    """
    registrados = 0
    pendientes  = 0

    msgs = outlook.correos_desde(outlook.inbox, desde)
    print(f"  Correos en bandeja desde {desde.strftime('%d/%m/%Y')}: {len(msgs)}\n")

    for m in msgs:
        try:
            asunto = m.Subject or ""

            # Filtro: solo correos cuyo asunto menciona un tipo de solicitud
            if not ProcesadorAsunto.es_solicitud(asunto):
                continue

            # Las respuestas/reenvíos del mismo hilo también llegan a la
            # bandeja; la solicitud original es la que NO tiene prefijo RE:/RV:
            es_reply = bool(re.match(r"(?i)^\s*(RE|RV|FW|FWD)\s*:", asunto))

            conv_id = m.ConversationID

            if sql.existe_conversation(conv_id) or sql.existe_pendiente(conv_id):
                continue

            if es_reply:
                # Reply de un hilo que no está registrado: lo dejamos pasar,
                # la solicitud original aparecerá en el escaneo.
                continue

            print(f"  [+] Nueva solicitud: {asunto[:60]}")

            d                = ProcesadorAsunto.parsear(asunto)
            campos_faltantes = ProcesadorAsunto.validar(d)

            if campos_faltantes and not tolerante:
                sql.registrar_pendiente(
                    conv_id          = conv_id,
                    asunto           = asunto,
                    remitente        = m.SenderName,
                    campos_faltantes = campos_faltantes,
                )
                outlook.guardar_msg(m, f"PENDIENTE_{asunto[:40]}")
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
                "Asunto":             asunto,
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
            print(f"  ✔  Correlativo: {correlativo:04d} "
                  f"[{d['Tipo_Solicitud']}]\n")

        except Exception as e:
            print(f"  ▲ Error solicitud [{getattr(m, 'Subject', '?')[:60]}]: {e}")

    return registrados, pendientes


def procesar_respuestas(
    outlook: HerramientasOutlook, sql: GestorBackupSQL, desde: datetime
) -> int:
    """Escanea Elementos enviados del buzón: si un correo enviado
    pertenece a un hilo registrado y aún Pendiente, es la respuesta
    del analista. Devuelve cuántas respuestas se registraron."""
    respuestas = 0

    if outlook.enviados is None:
        print("  ▲ Sin acceso a Elementos enviados — fase omitida.")
        return 0

    msgs = outlook.correos_desde(outlook.enviados, desde)
    print(f"  Enviados desde {desde.strftime('%d/%m/%Y')}: {len(msgs)}\n")

    for m in msgs:
        try:
            conv_id = m.ConversationID

            # Solo nos interesan hilos registrados y aún sin respuesta
            if sql.get_estado(conv_id) != "Pendiente":
                continue

            print(f"  [✓] Respuesta detectada: {(m.Subject or '')[:60]}")

            ruta_resp  = outlook.guardar_msg(m, f"RESP_{conv_id[:20]}")
            fecha_resp = m.SentOn
            inicio     = sql.get_fecha_solicitud(conv_id)
            demora     = (
                formatear_demora(inicio, a_naive(fecha_resp))
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

        except Exception as e:
            print(f"  ▲ Error respuesta [{getattr(m, 'Subject', '?')[:60]}]: {e}")

    return respuestas


# ══════════════════════════════════════════════════════════════════
# 9. ORQUESTADOR PRINCIPAL
# ══════════════════════════════════════════════════════════════════

def main():
    sep = "═" * 65
    print(f"\n{sep}")
    print("  🤖  ROBOT BITÁCORA Solicitudes de Clientes — V1")
    print(f"  🕐  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  👤  Usuario: {os.getenv('USERNAME', 'desconocido')}")
    print(f"  📂  Base: {_BASE}")
    print(f"  📬  Buzón: {CONFIG['BUZON'] or '(cuenta por defecto)'}")
    print(f"{sep}\n")

    outlook = HerramientasOutlook(CONFIG["BUZON"])
    sql     = GestorBackupSQL(CONFIG["RUTA_DB_SQLITE"])

    if not outlook.conectado:
        print("❌ No se pudo conectar a Outlook. Abortando.")
        return

    desde = datetime.now() - timedelta(days=CONFIG["DIAS_VENTANA"])
    desde = datetime(desde.year, desde.month, desde.day)

    # ── FASE 1: SOLICITUDES (Bandeja de entrada) ──────────────────
    print(f"{'─'*40}")
    print("  FASE 1 — Solicitudes (Bandeja de entrada)")
    print(f"{'─'*40}\n")

    registrados, pendientes = procesar_solicitudes(
        outlook, sql, desde, tolerante=False
    )

    # ── FASE 2: RESPUESTAS (Elementos enviados) ───────────────────
    print(f"\n{'─'*40}")
    print("  FASE 2 — Respuestas (Elementos enviados)")
    print(f"{'─'*40}\n")

    respuestas = procesar_respuestas(outlook, sql, desde)

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
    print(f"  Solicitudes nuevas              : {registrados}")
    print(f"  Respuestas registradas          : {respuestas}")
    print(f"  Asuntos sin formato (pendientes): {pendientes}")
    if pendientes > 0:
        print("  → Revisar: Solicitudes_Sin_Formato.xlsx")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
