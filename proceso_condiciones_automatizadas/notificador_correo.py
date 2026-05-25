# notificador_correo.py
# ============================================================
# Envía por correo (via Outlook) los TXT generados + resumen
# del proceso: condiciones, registros y ranking de comercios.
#
# Requiere: pip install pywin32
# ============================================================

import win32com.client
from pathlib import Path
from datetime import datetime


# ── CONFIGURACIÓN ────────────────────────────────────────────
# Correo del compañero que sube los TXT a Monitor
DESTINATARIO = "roberto.palacios@scotiabank.com.pe"
# ─────────────────────────────────────────────────────────────


class NotificadorCorreo:

    def __init__(self, destinatario: str = DESTINATARIO):
        self.destinatario = destinatario

    def enviar(self, resultados: dict, grupos: dict, fecha_str: str):
        """
        resultados : dict retornado por PipelineCondiciones.ejecutar()["resultados"]
        grupos     : dict retornado por PipelineCondiciones.ejecutar()["grupos"]
        fecha_str  : "24052026"
        """
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail    = outlook.CreateItem(0)   # 0 = olMailItem

        mail.To      = self.destinatario
        mail.Subject = self._asunto(fecha_str, resultados)
        mail.Body    = self._cuerpo(resultados, grupos, fecha_str)

        # Adjuntar todos los TXT generados
        adjuntos_agregados = 0
        for cod, res in resultados.items():
            if not res.get("ok"):
                continue
            run_dir = Path(res["run_dir"])
            for txt in sorted(run_dir.glob("*.txt")):
                mail.Attachments.Add(str(txt))
                adjuntos_agregados += 1
                print(f"  [Correo] Adjunto: {txt.name}")

        mail.Send()
        print(f"\n  Correo enviado a {self.destinatario}")
        print(f"  Adjuntos: {adjuntos_agregados} archivo(s) TXT")

    # ── privados ────────────────────────────────────────────

    def _asunto(self, fecha_str: str, resultados: dict) -> str:
        fecha_fmt    = f"{fecha_str[:2]}/{fecha_str[2:4]}/{fecha_str[4:]}"
        conds_ok     = [c for c, r in resultados.items() if r.get("ok")]
        conds_fallo  = [c for c, r in resultados.items() if not r.get("ok")]

        asunto = f"Condiciones Automatizadas — {fecha_fmt} — {len(conds_ok)} condición(es) procesada(s)"
        if conds_fallo:
            asunto += f" — ⚠ {len(conds_fallo)} con error"
        return asunto

    def _cuerpo(self, resultados: dict, grupos: dict, fecha_str: str) -> str:
        fecha_fmt = f"{fecha_str[:2]}/{fecha_str[2:4]}/{fecha_str[4:]}"
        ahora     = datetime.now().strftime("%d/%m/%Y %H:%M")
        lineas    = []

        lineas.append(f"Proceso de condiciones automatizadas — {fecha_fmt}")
        lineas.append(f"Generado: {ahora}")
        lineas.append("=" * 55)
        lineas.append("")

        # ── Resumen por condición ──────────────────────────
        lineas.append("RESUMEN POR CONDICIÓN")
        lineas.append("-" * 40)
        total_registros = 0
        for cod, res in resultados.items():
            if res.get("ok"):
                n = len(grupos.get(cod, []))
                total_registros += n
                lineas.append(f"  [{cod}]  OK  —  {n} registros  —  correlativo final: {res['ultimo']}")
            else:
                lineas.append(f"  [{cod}]  FALLÓ  —  {res.get('error', 'error desconocido')}")

        lineas.append(f"\n  Total registros procesados: {total_registros}")
        lineas.append("")

        # ── Ranking de comercios ───────────────────────────
        lineas.append("RANKING DE COMERCIOS (TOP 10 del día)")
        lineas.append("-" * 40)

        for cod, df in grupos.items():
            if df is None or df.empty:
                continue
            col_comercio = self._encontrar_col_comercio(df)
            if col_comercio is None:
                continue

            conteo = (
                df[col_comercio]
                .fillna("SIN_VALOR")
                .astype(str)
                .str.strip()
                .value_counts()
                .head(10)
            )
            lineas.append(f"\n  Condición {cod}:")
            for rank, (comercio, cantidad) in enumerate(conteo.items(), 1):
                lineas.append(f"    #{rank:>2}  {comercio[:45]:<45}  {cantidad} transac.")

        lineas.append("")
        lineas.append("=" * 55)
        lineas.append("Archivos TXT adjuntos en este correo.")
        lineas.append("Por favor subir a Monitor.")

        return "\n".join(lineas)

    def _encontrar_col_comercio(self, df):
        for col in df.columns:
            if "comercio" in col.lower() or "merchant" in col.lower():
                return col
        return None
