"""
reporte_correo.py — Genera y envía el reporte diario de declinaciones por Outlook.

Flujo:
    1. Recibe el resultado del DetectorAnomalias
    2. Genera gráficas con matplotlib (PNG temporales)
    3. Construye un correo HTML con las imágenes embebidas (CID)
    4. Envía vía win32com (Outlook corporativo)

Requisito: Outlook debe estar instalado y configurado en el equipo.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # sin interfaz gráfica, solo genera archivos
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd


# Paleta de colores por herramienta (profesional, alto contraste)
COLORES_HERRAMIENTA = {
    "VCAS":       "#1F77B4",
    "VRM":        "#FF7F0E",
    "RT_DEBITO":  "#2CA02C",
    "RT_CREDITO": "#D62728",
    "FRM":        "#9467BD",
}
COLOR_DEFAULT = "#8C8C8C"


class ReporteCorreo:
    """
    Construye y envía el correo diario de alertas de declinaciones.

    El correo incluye:
    - Resumen ejecutivo: fecha, total transacciones, estado (Normal / ALERTA)
    - Gráfica 1: evolutivo de volumen por herramienta (últimos 30 días)
    - Gráfica 2: evolutivo de monto rechazado por herramienta (últimos 30 días)
    - Tabla de alertas si hay anomalías detectadas
    - Top 10 comercios y BIN6 con mayor Z-score
    """

    def __init__(
        self,
        resultado_detector: dict,
        destinatarios: list[str],
        remitente: Optional[str] = None,
    ) -> None:
        self.res          = resultado_detector
        self.destinatarios = destinatarios
        self.remitente    = remitente
        self._archivos_temp: list[str] = []

    def enviar(self) -> None:
        """Genera gráficas, construye el HTML y envía por Outlook."""
        print("  Generando reporte y enviando correo...")
        try:
            imagenes = self._generar_graficas()
            html     = self._construir_html(imagenes)
            self._enviar_outlook(html, imagenes)
            print(f"  Correo enviado a: {', '.join(self.destinatarios)}")
        finally:
            self._limpiar_temporales()

    # ------------------------------------------------------------------
    # Generación de gráficas
    # ------------------------------------------------------------------

    def _generar_graficas(self) -> dict[str, str]:
        """Genera los PNG y devuelve {cid: ruta_archivo}."""
        imagenes = {}
        imagenes["grafica_volumen"] = self._grafica_evolutivo(
            columna="volumen",
            titulo="Transacciones Declinadas por Día",
            ylabel="N° Transacciones",
            cid="grafica_volumen",
        )
        imagenes["grafica_monto"] = self._grafica_evolutivo(
            columna="monto",
            titulo="Monto Rechazado (USD) por Día",
            ylabel="Monto USD",
            cid="grafica_monto",
        )
        # Siempre generar el gráfico de Z-scores (no solo cuando hay alertas)
        if self.res.get("top_comercio") or self.res.get("top_bin6"):
            imagenes["grafica_zscore"] = self._grafica_zscore()
        return imagenes

    def _grafica_evolutivo(
        self,
        columna: str,
        titulo: str,
        ylabel: str,
        cid: str,
    ) -> str:
        df: pd.DataFrame = self.res["df_evolutivo"]
        fecha_t1: date   = self.res["fecha_t1"]

        fig, ax = plt.subplots(figsize=(12, 5))
        fig.patch.set_facecolor("#F8F9FA")
        ax.set_facecolor("#F8F9FA")

        for herramienta, grupo in df.groupby("herramienta"):
            color = COLORES_HERRAMIENTA.get(herramienta, COLOR_DEFAULT)
            grupo = grupo.sort_values("dia").reset_index(drop=True)
            x_idx = range(len(grupo))
            y_vals = grupo[columna].values

            # Intentar curva spline cúbica (respeta todos los valores, suaviza ángulos)
            try:
                from scipy.interpolate import make_interp_spline
                import numpy as np
                if len(grupo) >= 4:
                    x_dense = np.linspace(0, len(grupo) - 1, len(grupo) * 5)
                    spl = make_interp_spline(list(x_idx), y_vals, k=3)
                    y_dense = spl(x_dense)
                    # Mapear x_dense a fechas reales
                    fechas_dense = pd.to_datetime(
                        pd.Series(x_dense).apply(
                            lambda i: grupo["dia"].iloc[min(int(i), len(grupo)-1)]
                        )
                    )
                    ax.plot(fechas_dense, y_dense, label=herramienta, color=color, linewidth=2.2)
                else:
                    ax.plot(grupo["dia"], y_vals, label=herramienta, color=color, linewidth=2.2)
            except ImportError:
                # Sin scipy: línea simple (ya es razonablemente suave)
                ax.plot(grupo["dia"], y_vals, label=herramienta, color=color, linewidth=2.2)

            # Punto T-1 destacado (sobre el dato real)
            t1_row = grupo[grupo["dia"] == fecha_t1]
            if not t1_row.empty:
                ax.scatter(t1_row["dia"], t1_row[columna], color=color, s=90, zorder=5)

        # Línea vertical T-1
        ax.axvline(x=fecha_t1, color="#555555", linestyle="--", linewidth=1, alpha=0.6, label="T-1 (hoy)")

        ax.set_title(titulo, fontsize=14, fontweight="bold", pad=12)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.set_xlabel("")
        ax.legend(loc="upper left", fontsize=9, framealpha=0.8)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.spines[["top", "right"]].set_visible(False)
        plt.xticks(rotation=30, ha="right", fontsize=8)
        plt.tight_layout()

        ruta = self._guardar_temp(fig, cid)
        plt.close(fig)
        return ruta

    def _grafica_zscore(self) -> str:
        """
        Gráfica de barras horizontales con Z-score de top comercios y BIN6.
        Se muestra SIEMPRE (no solo cuando hay alertas) para ver quién
        está más cerca de alertar aunque todo sea Normal.
        Barras rojas = cruzan umbral ±2σ. Barras azules/naranjas = dentro del rango.
        """
        top_c = self.res.get("top_comercio", [])[:10]
        top_b = self.res.get("top_bin6", [])[:10]

        etiquetas, zscores, colores, es_alerta_lista = [], [], [], []
        for a in top_c:
            etiquetas.append(f"{a.grupo[:28]} ({a.herramienta})")
            zscores.append(a.zscore_volumen)
            colores.append("#D62728" if a.es_alerta else COLORES_HERRAMIENTA.get(a.herramienta, COLOR_DEFAULT))
            es_alerta_lista.append(a.es_alerta)
        for a in top_b:
            etiquetas.append(f"BIN {a.grupo} ({a.herramienta})")
            zscores.append(a.zscore_volumen)
            colores.append("#D62728" if a.es_alerta else COLORES_HERRAMIENTA.get(a.herramienta, COLOR_DEFAULT))
            es_alerta_lista.append(a.es_alerta)

        if not etiquetas:
            return ""

        fig, ax = plt.subplots(figsize=(12, max(5, len(etiquetas) * 0.55)))
        fig.patch.set_facecolor("#F8F9FA")
        ax.set_facecolor("#F8F9FA")

        y_pos = list(range(len(etiquetas)))
        bars = ax.barh(y_pos, zscores, color=colores, alpha=0.85, height=0.6)

        ax.axvline(x= 2, color="#D62728", linestyle="--", linewidth=1.5, label="Umbral ±2σ")
        ax.axvline(x=-2, color="#D62728", linestyle="--", linewidth=1.5)
        ax.axvline(x= 0, color="#555555", linewidth=0.8)
        ax.axvspan(-2, 2, alpha=0.05, color="#2CA02C")  # zona verde = normal

        ax.set_yticks(y_pos)
        ax.set_yticklabels(etiquetas, fontsize=9)
        ax.set_xlabel("Z-score (desviaciones de la media de 30 días)", fontsize=10)
        ax.set_title("Top Comercios y BIN6 — Z-score Volumen T-1", fontsize=13, fontweight="bold", pad=12)
        ax.legend(fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)

        for bar, val in zip(bars, zscores):
            offset = 0.08 if val >= 0 else -0.08
            ha = "left" if val >= 0 else "right"
            ax.text(val + offset, bar.get_y() + bar.get_height() / 2,
                    f"{val:+.2f}σ", va="center", ha=ha, fontsize=8, fontweight="bold")

        plt.tight_layout()
        ruta = self._guardar_temp(fig, "grafica_zscore")
        plt.close(fig)
        return ruta

    def _guardar_temp(self, fig, nombre: str) -> str:
        tf = tempfile.NamedTemporaryFile(
            suffix=".png", prefix=f"{nombre}_", delete=False
        )
        fig.savefig(tf.name, dpi=130, bbox_inches="tight", facecolor=fig.get_facecolor())
        self._archivos_temp.append(tf.name)
        tf.close()
        return tf.name

    # ------------------------------------------------------------------
    # Construcción del HTML
    # ------------------------------------------------------------------

    def _construir_html(self, imagenes: dict[str, str]) -> str:
        fecha_t1     = self.res["fecha_t1"]
        total_alertas = self.res["total_alertas"]
        resumen      = self.res["resumen_herramienta"]

        estado_color = "#D62728" if total_alertas > 0 else "#2CA02C"
        estado_texto = f"⚠ {total_alertas} ALERTA(S) DETECTADA(S)" if total_alertas > 0 else "✔ Comportamiento Normal"

        # Tabla resumen herramientas (cada una con su última fecha disponible)
        filas_resumen = ""
        for _, row in resumen.iterrows():
            fecha_dato = row.get("fecha_dato", str(fecha_t1))
            es_hoy     = str(fecha_dato) == str(fecha_t1)
            color_fecha = "#212529" if es_hoy else "#DC3545"  # rojo si no es T-1
            filas_resumen += f"""
            <tr>
                <td style="padding:6px 12px;">{row['herramienta']}</td>
                <td style="padding:6px 12px; text-align:right;">{int(row['transacciones']):,}</td>
                <td style="padding:6px 12px; text-align:right;">USD {float(row['monto_usd']):,.0f}</td>
                <td style="padding:6px 12px; text-align:center; color:{color_fecha}; font-size:11px;">{fecha_dato}</td>
            </tr>"""

        # Tabla alertas herramienta
        filas_alertas_h = ""
        for a in self.res["alertas_herramienta"]:
            if a.es_alerta:
                color_fila = "#FFF3CD" if abs(a.zscore_volumen) < 3 else "#F8D7DA"
                filas_alertas_h += f"""
                <tr style="background:{color_fila};">
                    <td style="padding:6px 12px;">{a.herramienta}</td>
                    <td style="padding:6px 12px; text-align:right;">{a.volumen_hoy:,}</td>
                    <td style="padding:6px 12px; text-align:right;">{a.media_volumen:,.0f}</td>
                    <td style="padding:6px 12px; text-align:right; font-weight:bold;">{a.zscore_volumen:+.2f}σ</td>
                    <td style="padding:6px 12px;">USD {a.monto_hoy:,.0f}</td>
                    <td style="padding:6px 12px; text-align:right; font-weight:bold;">{a.zscore_monto:+.2f}σ</td>
                </tr>"""

        seccion_alertas_h = ""
        if filas_alertas_h:
            seccion_alertas_h = f"""
            <h3 style="color:#D62728; margin-top:24px;">Alertas por Herramienta</h3>
            <table style="border-collapse:collapse; width:100%; font-size:13px;">
                <thead style="background:#343A40; color:white;">
                    <tr>
                        <th style="padding:8px 12px; text-align:left;">Herramienta</th>
                        <th style="padding:8px 12px;">Transacc. Hoy</th>
                        <th style="padding:8px 12px;">Media 30d</th>
                        <th style="padding:8px 12px;">Z-score Vol.</th>
                        <th style="padding:8px 12px;">Monto Hoy</th>
                        <th style="padding:8px 12px;">Z-score Monto</th>
                    </tr>
                </thead>
                <tbody>{filas_alertas_h}</tbody>
            </table>"""

        # Tablas granulares (siempre visibles, no solo cuando hay alertas)
        tabla_comercio = self._tabla_top_grupos(
            self.res.get("top_comercio", []), "Top Comercios por Z-score — Volumen T-1"
        )
        tabla_bin6 = self._tabla_top_grupos(
            self.res.get("top_bin6", []), "Top BIN6 por Z-score — Volumen T-1"
        )

        # Imágenes embebidas
        img_vol    = '<img src="cid:grafica_volumen" style="width:100%; max-width:700px;">'
        img_monto  = '<img src="cid:grafica_monto"   style="width:100%; max-width:700px;">'
        img_zscore = '<img src="cid:grafica_zscore"  style="width:100%; max-width:700px;">' if "grafica_zscore" in imagenes else ""

        html = f"""
        <html><body style="font-family:Calibri, Arial, sans-serif; color:#212529; max-width:780px; margin:auto;">

        <div style="background:#1B3A5C; color:white; padding:18px 24px; border-radius:6px 6px 0 0;">
            <h2 style="margin:0; font-size:20px;">Reporte Diario — Consolidado de Declinaciones</h2>
            <p style="margin:4px 0 0 0; font-size:13px; opacity:0.85;">
                Fecha de análisis: <strong>{fecha_t1.strftime('%d/%m/%Y')}</strong> (T-1)
            </p>
        </div>

        <div style="background:#F8F9FA; padding:14px 24px; border:1px solid #DEE2E6;">
            <span style="font-size:15px; font-weight:bold; color:{estado_color};">{estado_texto}</span>
        </div>

        <div style="padding:16px 24px;">

            <h3 style="color:#1B3A5C;">Resumen del Día T-1</h3>
            <table style="border-collapse:collapse; width:100%; font-size:13px;">
                <thead style="background:#343A40; color:white;">
                    <tr>
                        <th style="padding:8px 12px; text-align:left;">Herramienta</th>
                        <th style="padding:8px 12px; text-align:right;">Transacciones</th>
                        <th style="padding:8px 12px; text-align:right;">Monto Rechazado</th>
                        <th style="padding:8px 12px; text-align:center;">Fecha dato</th>
                    </tr>
                </thead>
                <tbody>{filas_resumen}</tbody>
            </table>

            {seccion_alertas_h}

            <h3 style="color:#1B3A5C; margin-top:28px;">
                Evolutivo últimos 30 días — Volumen
                <span style="font-size:11px; font-weight:normal; color:#6C757D;">
                  (línea suavizada = media 7 días · puntos = dato diario real)
                </span>
            </h3>
            {img_vol}

            <h3 style="color:#1B3A5C; margin-top:28px;">Evolutivo últimos 30 días — Monto USD</h3>
            {img_monto}

            <h3 style="color:#1B3A5C; margin-top:28px;">
                Z-score por Comercio y BIN6 — T-1
                <span style="font-size:11px; font-weight:normal; color:#6C757D;">
                  (zona verde = comportamiento normal · rojo = alerta)
                </span>
            </h3>
            {img_zscore}

            {tabla_comercio}
            {tabla_bin6}

        </div>

        <div style="background:#F1F3F5; padding:10px 24px; border-top:1px solid #DEE2E6;
                    font-size:11px; color:#6C757D; border-radius:0 0 6px 6px;">
            Generado automáticamente · Consolidado Herramientas v2 ·
            Ventana Z-score: 30 días · Umbral: ±2σ
        </div>

        </body></html>
        """
        return html

    def _tabla_top_grupos(self, grupos: list, titulo: str) -> str:
        """Genera tabla HTML con top N grupos por Z-score, siempre visible."""
        if not grupos:
            return ""

        filas = ""
        for a in grupos:
            bg = "#F8D7DA" if abs(a.zscore_volumen) >= 3 else \
                 "#FFF3CD" if a.es_alerta else "white"
            icono = "⚠" if a.es_alerta else "·"
            filas += f"""
            <tr style="background:{bg};">
                <td style="padding:5px 10px;">{icono}</td>
                <td style="padding:5px 10px;">{a.herramienta}</td>
                <td style="padding:5px 10px;">{a.grupo[:40]}</td>
                <td style="padding:5px 10px; text-align:right;">{a.volumen_hoy:,}</td>
                <td style="padding:5px 10px; text-align:right;">{a.media_volumen:,.0f}</td>
                <td style="padding:5px 10px; text-align:right; font-weight:bold;">{a.zscore_volumen:+.2f}σ</td>
                <td style="padding:5px 10px; text-align:right;">USD {a.monto_hoy:,.0f}</td>
                <td style="padding:5px 10px; text-align:right; font-weight:bold;">{a.zscore_monto:+.2f}σ</td>
            </tr>"""

        return f"""
        <h4 style="color:#1B3A5C; margin-top:24px;">{titulo}</h4>
        <table style="border-collapse:collapse; width:100%; font-size:12px;">
            <thead style="background:#495057; color:white;">
                <tr>
                    <th style="padding:6px 10px;"></th>
                    <th style="padding:6px 10px; text-align:left;">Herramienta</th>
                    <th style="padding:6px 10px; text-align:left;">Grupo</th>
                    <th style="padding:6px 10px; text-align:right;">Vol. Hoy</th>
                    <th style="padding:6px 10px; text-align:right;">Media 30d</th>
                    <th style="padding:6px 10px; text-align:right;">Z-score Vol.</th>
                    <th style="padding:6px 10px; text-align:right;">Monto Hoy</th>
                    <th style="padding:6px 10px; text-align:right;">Z-score Monto</th>
                </tr>
            </thead>
            <tbody>{filas}</tbody>
        </table>"""

    # ------------------------------------------------------------------
    # Envío por Outlook (win32com)
    # ------------------------------------------------------------------

    def _enviar_outlook(self, html: str, imagenes: dict[str, str]) -> None:
        try:
            import win32com.client as win32
        except ImportError:
            raise ImportError(
                "pywin32 no está instalado. Ejecuta: pip install pywin32"
            )

        outlook = win32.Dispatch("outlook.application")
        mail    = outlook.CreateItem(0)  # 0 = olMailItem

        mail.To      = "; ".join(self.destinatarios)
        mail.Subject = self._asunto()
        mail.HTMLBody = html

        # Embeber imágenes con Content-ID (CID) para que aparezcan inline
        PR_ATTACH_CONTENT_ID = "http://schemas.microsoft.com/mapi/proptag/0x3712001E"
        for cid, ruta in imagenes.items():
            if ruta and os.path.exists(ruta):
                attachment = mail.Attachments.Add(ruta)
                attachment.PropertyAccessor.SetProperty(PR_ATTACH_CONTENT_ID, cid)

        mail.Send()

    def _asunto(self) -> str:
        fecha_t1     = self.res["fecha_t1"]
        total_alertas = self.res["total_alertas"]
        estado = f"⚠ {total_alertas} ALERTA(S)" if total_alertas > 0 else "✔ Normal"
        return f"[Declinaciones] Reporte {fecha_t1.strftime('%d/%m/%Y')} — {estado}"

    # ------------------------------------------------------------------
    # Limpieza
    # ------------------------------------------------------------------

    def _limpiar_temporales(self) -> None:
        for archivo in self._archivos_temp:
            try:
                os.remove(archivo)
            except OSError:
                pass
        self._archivos_temp.clear()
