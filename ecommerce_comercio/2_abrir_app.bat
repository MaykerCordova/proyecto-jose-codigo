@echo off
chcp 65001 >nul
title Dashboard Ecommerce — Streamlit

:: ─────────────────────────────────────────────────────────────────────────────
::  2_abrir_app.bat
::  Lanza el dashboard Streamlit interactivo
::
::  Requiere haber ejecutado primero:  1_ejecutar_pipeline.bat
::  El navegador se abre automáticamente en http://localhost:8501
:: ─────────────────────────────────────────────────────────────────────────────

set PYTHON=python
set BASE=%~dp0

echo.
echo ═══════════════════════════════════════════════════════════════════
echo   DASHBOARD ECOMMERCE — STREAMLIT
echo ═══════════════════════════════════════════════════════════════════
echo   Abriendo en:  http://localhost:8501
echo   Para cerrar:  Ctrl+C en esta ventana
echo ═══════════════════════════════════════════════════════════════════
echo.

:: Verificar que el parquet exista
if not exist "%BASE%data\consolidado_features.parquet" (
    echo ❌  No se encontró data\consolidado_features.parquet
    echo     Ejecuta primero:  1_ejecutar_pipeline.bat
    pause
    exit /b 1
)

%PYTHON% -m streamlit run "%BASE%app.py" --server.port 8501

pause
