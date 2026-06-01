"""
run_diario.py — Script de ejecución diaria del pipeline completo.

INSTRUCCIONES DE USO:
=====================
1. Edita la sección "ARCHIVOS DEL DÍA" con las rutas de los archivos nuevos.
2. Corre este script: python run_diario.py
3. Espera a que termine — al final tienes MASTER_POWERBI.parquet listo y
   recibes el correo de reporte automáticamente.

ORDEN DE EJECUCIÓN:
===================
1. VCAS        → auto-detecta Excels nuevos, no necesitas ruta
2. VRM         → necesitas los 2 CSVs del día
3. RT_DEBITO   → necesitas el Excel del día
4. RT_CREDITO  → necesitas el Excel del día
5. Consolidado → une todos los Golds + post-procesamiento + correo
"""

import sys
import time
from pathlib import Path

# Agregar el consolidado al path (está en otra carpeta del repo)
sys.path.insert(0, str(Path(__file__).parent.parent / "consolidado_declinaciones" / "version_oop"))


# ============================================================================
# ARCHIVOS DEL DÍA — EDITAR AQUÍ CADA VEZ
# ============================================================================

FECHA_HOY = "2026-05-31"  # <-- cambiar a la fecha del día

# VRM: 2 archivos CSV (listas de VRM del día)
VRM_CSV_FILES = [
    # r"C:\FRAUDES\HERRAMIENTAS\VRM\DATA\lista1_20260531.csv",
    # r"C:\FRAUDES\HERRAMIENTAS\VRM\DATA\lista2_20260531.csv",
]

# RT_DEBITO: 1 archivo Excel del día
RT_DEBITO_EXCEL = ""
# r"C:\Users\s4930359\Data_Herramientas\BBDD_Real_Time\debito_20260531.xlsx"

# RT_CREDITO: 1 archivo Excel del día
RT_CREDITO_EXCEL = ""
# r"C:\FRAUDES\HERRAMIENTAS\RT_TC_UBA\DATA\R0852_20260531.xlsx"

# VCAS: no necesita ruta, detecta automáticamente los Excels nuevos


# ============================================================================
# EJECUCIÓN
# ============================================================================

def main():
    t_inicio = time.time()
    print("=" * 65)
    print(f"  PIPELINE DIARIO DECLINACIONES — {FECHA_HOY}")
    print("=" * 65)

    errores = []

    # ------------------------------------------------------------------
    # PASO 1: VCAS
    # ------------------------------------------------------------------
    print("\n[1/5] VCAS — procesando Excels nuevos...")
    try:
        from VCAS.vcas_pipeline_medallion import run as vcas_run
        vcas_run()
        print("  ✔ VCAS Gold generado")
    except Exception as e:
        print(f"  ✘ VCAS falló: {e}")
        errores.append(f"VCAS: {e}")

    # ------------------------------------------------------------------
    # PASO 2: VRM
    # ------------------------------------------------------------------
    print("\n[2/5] VRM — carga incremental diaria...")
    if VRM_CSV_FILES:
        try:
            from VRM.vrm_pipeline_medallion import run_daily as vrm_daily
            vrm_daily(VRM_CSV_FILES, FECHA_HOY)
            print("  ✔ VRM Gold actualizado")
        except Exception as e:
            print(f"  ✘ VRM falló: {e}")
            errores.append(f"VRM: {e}")
    else:
        print("  ⚠ VRM_CSV_FILES vacío — saltando VRM")

    # ------------------------------------------------------------------
    # PASO 3: RT_DEBITO
    # ------------------------------------------------------------------
    print("\n[3/5] RT_DEBITO — carga incremental diaria...")
    if RT_DEBITO_EXCEL:
        try:
            from RT_DEBITO.rt_debito_pipeline_medallion import run_daily as rtd_daily
            rtd_daily(RT_DEBITO_EXCEL, FECHA_HOY)
            print("  ✔ RT_DEBITO Gold actualizado")
        except Exception as e:
            print(f"  ✘ RT_DEBITO falló: {e}")
            errores.append(f"RT_DEBITO: {e}")
    else:
        print("  ⚠ RT_DEBITO_EXCEL vacío — saltando RT_DEBITO")

    # ------------------------------------------------------------------
    # PASO 4: RT_CREDITO
    # ------------------------------------------------------------------
    print("\n[4/5] RT_CREDITO — carga incremental diaria...")
    if RT_CREDITO_EXCEL:
        try:
            from RT_CREDITO.rt_credito_pipeline_medallion import run_daily as rtc_daily
            rtc_daily(RT_CREDITO_EXCEL, FECHA_HOY)
            print("  ✔ RT_CREDITO Gold actualizado")
        except Exception as e:
            print(f"  ✘ RT_CREDITO falló: {e}")
            errores.append(f"RT_CREDITO: {e}")
    else:
        print("  ⚠ RT_CREDITO_EXCEL vacío — saltando RT_CREDITO")

    # ------------------------------------------------------------------
    # PASO 5: Consolidado + Post-procesamiento + Correo
    # ------------------------------------------------------------------
    print("\n[5/5] CONSOLIDADO — uniendo todas las herramientas...")
    try:
        from main import main as consolidado_main
        consolidado_main()
        print("  ✔ Consolidado, Power BI parquet y correo generados")
    except Exception as e:
        print(f"  ✘ Consolidado falló: {e}")
        errores.append(f"Consolidado: {e}")

    # ------------------------------------------------------------------
    # RESUMEN FINAL
    # ------------------------------------------------------------------
    duracion = time.time() - t_inicio
    print(f"\n{'=' * 65}")
    if errores:
        print(f"  COMPLETADO CON {len(errores)} ERROR(ES) en {duracion:.1f}s")
        for err in errores:
            print(f"    ✘ {err}")
    else:
        print(f"  ✔ PIPELINE COMPLETO en {duracion:.1f}s — todo OK")
    print("=" * 65)


if __name__ == "__main__":
    main()
