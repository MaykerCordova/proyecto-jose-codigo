@echo off
chcp 65001 >nul
title Pipeline Ecommerce Comercio

:: ─────────────────────────────────────────────────────────────────────────────
::  1_ejecutar_pipeline.bat
::  Ejecuta el pipeline completo en orden:
::    consolidar.py  →  feature_engineering.py  →  analisis.py
::
::  ANTES DE EJECUTAR:
::    1. Pon los archivos Excel de Monitor en:  data\journals\
::    2. Configura el nombre del comercio en:  scripts\config.py
::    3. Indica si tienes solo aprobadas o aprobadas+denegadas (SOLO_APROBADAS)
:: ─────────────────────────────────────────────────────────────────────────────

set PYTHON=python
set BASE=%~dp0
set SCRIPTS=%BASE%scripts

echo.
echo ═══════════════════════════════════════════════════════════════════
echo   PIPELINE ECOMMERCE COMERCIO — SCOTIABANK PERU
echo ═══════════════════════════════════════════════════════════════════
echo   Carpeta base : %BASE%
echo   Python       : %PYTHON%
echo ═══════════════════════════════════════════════════════════════════
echo.

:: ── PASO 1: CONSOLIDAR ────────────────────────────────────────────────────────
echo [PASO 1/3]  CONSOLIDAR — Uniendo journals Excel en parquet...
echo ─────────────────────────────────────────────────────────────────────────
%PYTHON% "%SCRIPTS%\consolidar.py"
if %ERRORLEVEL% neq 0 (
    echo.
    echo ❌  ERROR en consolidar.py — Revisa que haya archivos Excel en data\journals\
    pause
    exit /b 1
)
echo.
echo ✅  Paso 1 completado.
echo.

:: ── PASO 2: FEATURE ENGINEERING ───────────────────────────────────────────────
echo [PASO 2/3]  FEATURE ENGINEERING — Generando ~70 variables nuevas...
echo ─────────────────────────────────────────────────────────────────────────
%PYTHON% "%SCRIPTS%\feature_engineering.py"
if %ERRORLEVEL% neq 0 (
    echo.
    echo ❌  ERROR en feature_engineering.py
    pause
    exit /b 1
)
echo.
echo ✅  Paso 2 completado.
echo.

:: ── PASO 3: ANALISIS ──────────────────────────────────────────────────────────
echo [PASO 3/3]  ANALISIS — Generando Excel con 20 hojas...
echo ─────────────────────────────────────────────────────────────────────────
%PYTHON% "%SCRIPTS%\analisis.py"
if %ERRORLEVEL% neq 0 (
    echo.
    echo ❌  ERROR en analisis.py
    pause
    exit /b 1
)

echo.
echo ═══════════════════════════════════════════════════════════════════
echo   ✅  PIPELINE COMPLETADO EXITOSAMENTE
echo ═══════════════════════════════════════════════════════════════════
echo.
echo   El Excel de análisis está en:  output\
echo   Para abrir el dashboard:       doble clic en 2_abrir_app.bat
echo.
echo ═══════════════════════════════════════════════════════════════════

:: Abrir la carpeta output automáticamente
explorer "%BASE%output"

pause
