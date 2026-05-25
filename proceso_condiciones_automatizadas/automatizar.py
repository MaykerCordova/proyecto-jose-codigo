# automatizar.py
# ============================================================
# Orquestador completo del pipeline de condiciones.
# Ejecuta los 3 pasos en orden:
#   1. Lee Outlook → descarga Excel pendientes
#   2. Corre pipeline por cada Excel (en orden de fecha)
#   3. Envía TXT + resumen por correo
#
# Uso:
#   python automatizar.py
#   python automatizar.py --solo-pipeline "Entrada\Archivo_Base_24052026.xlsx" --fecha 24052026
# ============================================================

import argparse
import sys
from pathlib import Path
from datetime import datetime

from lector_outlook      import LectorOutlook,     CARPETA_OUTLOOK
from pipeline_condiciones import PipelineCondiciones
from notificador_correo  import NotificadorCorreo,  DESTINATARIO


# ── CONFIGURACIÓN ────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
# ─────────────────────────────────────────────────────────────


def ejecutar_pipeline_completo():
    """Flujo completo: Outlook → Pipeline → Correo"""

    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  AUTOMATIZACIÓN COMPLETA — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{sep}")

    # ── PASO 1: Descargar Excel de Outlook ──────────────────
    print("\n[1/3] Leyendo Outlook...")
    lector   = LectorOutlook(carpeta_outlook=CARPETA_OUTLOOK, base_dir=BASE_DIR)
    pendientes = lector.extraer_pendientes()

    if not pendientes:
        print("\n  No hay archivos nuevos pendientes en Outlook. Fin del proceso.")
        return

    # ── PASO 2: Correr pipeline por cada Excel ──────────────
    print(f"\n[2/3] Procesando {len(pendientes)} archivo(s)...")
    todos_resultados = {}
    todos_grupos     = {}

    for item in pendientes:
        ruta      = item["ruta"]
        fecha_str = item["fecha"]

        print(f"\n  --- Procesando: {ruta.name} (fecha: {fecha_str}) ---")
        try:
            pipeline = PipelineCondiciones(
                ruta_excel = str(ruta),
                base_dir   = str(BASE_DIR),
                fecha_str  = fecha_str,
            )
            salida = pipeline.ejecutar()
        except Exception as e:
            print(f"  [SKIP] {ruta.name} no se pudo procesar: {e}")
            continue

        if salida:
            # Acumular resultados de todas las fechas procesadas
            for cod, res in salida["resultados"].items():
                # Si ya existe la condición, conservar el último resultado
                todos_resultados[cod] = res

            for cod, df in salida["grupos"].items():
                if cod not in todos_grupos:
                    todos_grupos[cod] = df
                else:
                    # Concatenar grupos de varios días para el resumen de comercios
                    import pandas as pd
                    todos_grupos[cod] = pd.concat(
                        [todos_grupos[cod], df], ignore_index=True
                    )

    # ── PASO 3: Enviar correo con resultados ────────────────
    print(f"\n[3/3] Enviando correo a {DESTINATARIO}...")
    fecha_envio = datetime.now().strftime("%d%m%Y")
    notificador = NotificadorCorreo(destinatario=DESTINATARIO)
    notificador.enviar(
        resultados = todos_resultados,
        grupos     = todos_grupos,
        fecha_str  = fecha_envio,
    )

    print(f"\n{sep}")
    print("  PROCESO COMPLETADO")
    print(f"{sep}\n")


def ejecutar_solo_pipeline(ruta_excel: str, fecha: str = None):
    """
    Corre solo el pipeline (sin Outlook ni correo).
    Útil para reprocesar un archivo manualmente.
    """
    pipeline = PipelineCondiciones(
        ruta_excel = ruta_excel,
        base_dir   = str(BASE_DIR),
        fecha_str  = fecha,
    )
    pipeline.ejecutar()


# ── ENTRADA ─────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Automatización completa de condiciones — Scotiabank Perú"
    )
    parser.add_argument(
        "--solo-pipeline",
        metavar="RUTA_EXCEL",
        default=None,
        help="Corre solo el pipeline para un Excel específico (sin Outlook ni correo)."
    )
    parser.add_argument(
        "--fecha",
        default=None,
        help="Fecha en formato DDMMYYYY. Solo aplica con --solo-pipeline."
    )
    args = parser.parse_args()

    if args.solo_pipeline:
        ejecutar_solo_pipeline(args.solo_pipeline, args.fecha)
    else:
        ejecutar_pipeline_completo()
