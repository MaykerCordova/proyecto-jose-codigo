# lector_outlook.py
# ============================================================
# Lee la carpeta de Outlook asignada, extrae los adjuntos Excel
# y los renombra con la fecha en que llegó el correo.
#
# Requiere: pip install pywin32
# ============================================================

import win32com.client
from pathlib import Path
from datetime import datetime, timedelta


# ── CONFIGURACIÓN ────────────────────────────────────────────
# Nombre de la carpeta dentro de tu Bandeja de entrada donde
# llegan los correos de condiciones automatizadas.
CARPETA_OUTLOOK = "Condiciones Automatizadas"

# Carpeta local donde se guardan los Excel descargados
CARPETA_DESTINO = "Entrada"

# Solo procesa correos de los últimos N días (evita históricos)
DIAS_ATRAS = 2
# ─────────────────────────────────────────────────────────────


class LectorOutlook:

    def __init__(
        self,
        carpeta_outlook: str = CARPETA_OUTLOOK,
        destino: str = None,
        base_dir: Path = None,
        dias_atras: int = DIAS_ATRAS,
    ):
        self.carpeta_outlook = carpeta_outlook
        self.base_dir        = Path(base_dir) if base_dir else Path(__file__).resolve().parent
        self.destino         = self.base_dir / (destino or CARPETA_DESTINO)
        self.dias_atras      = dias_atras
        self.destino.mkdir(parents=True, exist_ok=True)

    def extraer_pendientes(self) -> list:
        """
        Recorre la carpeta de Outlook y descarga los adjuntos Excel
        de los últimos DIAS_ATRAS días que aún no existen en Entrada/.

        Retorna lista ordenada por fecha (más antiguo primero):
        [
            {"ruta": Path("Entrada/Archivo_Base_24052026.xlsx"), "fecha": "24052026"},
            {"ruta": Path("Entrada/Archivo_Base_25052026.xlsx"), "fecha": "25052026"},
            ...
        ]
        """
        print(f"\n[Outlook] Conectando a carpeta: '{self.carpeta_outlook}'...")
        print(f"  Buscando correos de los últimos {self.dias_atras} días...")

        outlook      = win32com.client.Dispatch("Outlook.Application")
        ns           = outlook.GetNamespace("MAPI")
        fecha_limite = datetime.now() - timedelta(days=self.dias_atras)

        carpeta = self._encontrar_carpeta(ns)
        items   = carpeta.Items
        items.Sort("[ReceivedTime]", False)   # ordena de más antiguo a más nuevo

        descargados = []

        for mail in items:
            # Solo ítems de tipo MailItem (no reuniones, etc.)
            try:
                if mail.Class != 43:           # 43 = olMailItem
                    continue
                if mail.Attachments.Count == 0:
                    continue
            except Exception:
                continue

            fecha_recibido = mail.ReceivedTime
            # ReceivedTime es un objeto pywintypes.datetime → convertir a datetime nativo
            fecha_dt  = datetime(
                fecha_recibido.year,
                fecha_recibido.month,
                fecha_recibido.day,
                fecha_recibido.hour,
                fecha_recibido.minute,
                fecha_recibido.second,
            )

            # Saltar correos más antiguos que el límite
            if fecha_dt < fecha_limite:
                continue

            fecha_str = fecha_dt.strftime("%d%m%Y")

            for i in range(1, mail.Attachments.Count + 1):
                att    = mail.Attachments.Item(i)
                nombre = att.FileName or ""
                if not nombre.lower().endswith((".xlsx", ".xls")):
                    continue

                # Nombre destino con fecha del correo
                nuevo_nombre  = f"Archivo_Base_{fecha_str}.xlsx"
                ruta_destino  = self.destino / nuevo_nombre

                if ruta_destino.exists():
                    print(f"  [SKIP] Ya existe: {nuevo_nombre}")
                    continue   # ← ya procesado, no agregar a la lista

                att.SaveAsFile(str(ruta_destino))
                print(f"  [OK]   Descargado: {nuevo_nombre}  "
                      f"(correo del {fecha_dt.strftime('%d/%m/%Y %H:%M')})")
                descargados.append({
                    "ruta":     ruta_destino,
                    "fecha":    fecha_str,
                    "fecha_dt": fecha_dt,
                })

        # Ordenar por fecha ascendente y eliminar duplicados de fecha
        descargados.sort(key=lambda x: x["fecha_dt"])
        vistos   = set()
        unicos   = []
        for item in descargados:
            if item["fecha"] not in vistos:
                vistos.add(item["fecha"])
                unicos.append(item)

        print(f"  Total pendientes a procesar: {len(unicos)}")
        return unicos

    # ── privado ─────────────────────────────────────────────

    def _encontrar_carpeta(self, ns):
        """
        Busca la carpeta por nombre dentro de la Bandeja de entrada.
        Si no la encuentra lanza un error descriptivo.
        """
        inbox = ns.GetDefaultFolder(6)   # 6 = olFolderInbox

        # Búsqueda directa en el primer nivel
        for folder in inbox.Folders:
            if folder.Name.lower() == self.carpeta_outlook.lower():
                return folder

        # Búsqueda parcial (por si el nombre tiene variantes)
        for folder in inbox.Folders:
            if self.carpeta_outlook.lower() in folder.Name.lower():
                print(f"  [AVISO] Carpeta encontrada como '{folder.Name}' "
                      f"(buscaba '{self.carpeta_outlook}')")
                return folder

        # Listar carpetas disponibles para ayudar al usuario
        disponibles = [f.Name for f in inbox.Folders]
        raise ValueError(
            f"No se encontró la carpeta '{self.carpeta_outlook}' en tu Bandeja de entrada.\n"
            f"Carpetas disponibles: {disponibles}\n"
            f"Ajusta la variable CARPETA_OUTLOOK en lector_outlook.py"
        )
