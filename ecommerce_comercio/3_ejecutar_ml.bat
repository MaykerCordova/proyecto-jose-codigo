@echo off
chcp 65001 >nul
title ML No Supervisado — Ecommerce Comercio

:: ─────────────────────────────────────────────────────────────────────────────
::  3_ejecutar_ml.bat
::  Ejecuta el módulo de ML no supervisado (Isolation Forest + HDBSCAN)
::
::  ANTES DE EJECUTAR:
::    1. Haber ejecutado 1_ejecutar_pipeline.bat (necesita el parquet de features)
::    2. Tener instaladas las librerías:
::         pip install scikit-learn hdbscan
::
::  Output:
::    data\consolidado_features_ml.parquet   (parquet + columnas ML)
::    ml\output\ml_resumen_{COMERCIO}.xlsx   (resumen de clusters)
:: ─────────────────────────────────────────────────────────────────────────────

set PYTHON=python
set BASE=%~dp0
set ML_SCRIPT=%BASE%ml\clustering_fraude.py

echo.
echo ═══════════════════════════════════════════════════════════════════
echo   ML NO SUPERVISADO — SCOTIABANK PERU
echo ═══════════════════════════════════════════════════════════════════
echo   Script  : %ML_SCRIPT%
echo   Requiere: scikit-learn y hdbscan instalados
echo ═══════════════════════════════════════════════════════════════════
echo.

:: Verificar que el parquet de features exista
if not exist "%BASE%data\consolidado_features.parquet" (
    echo ❌  No se encontró data\consolidado_features.parquet
    echo     Ejecuta primero:  1_ejecutar_pipeline.bat
    pause
    exit /b 1
)

:: Verificar librerías
echo [CHECK] Verificando scikit-learn...
%PYTHON% -c "import sklearn" 2>nul
if %ERRORLEVEL% neq 0 (
    echo.
    echo ❌  scikit-learn no instalado.
    echo     Ejecuta en tu entorno:  pip install scikit-learn
    pause
    exit /b 1
)
echo ✅  scikit-learn OK

echo [CHECK] Verificando hdbscan...
%PYTHON% -c "import hdbscan" 2>nul
if %ERRORLEVEL% neq 0 (
    echo.
    echo ⚠   hdbscan no instalado — el clustering HDBSCAN se omitirá.
    echo     Para instalarlo:  pip install hdbscan
    echo     El Isolation Forest sí se ejecutará.
    echo.
)

:: ── EJECUTAR ML ──────────────────────────────────────────────────────────────
echo.
echo [ML]  Ejecutando Isolation Forest + HDBSCAN...
echo ─────────────────────────────────────────────────────────────────────────
%PYTHON% "%ML_SCRIPT%"
if %ERRORLEVEL% neq 0 (
    echo.
    echo ❌  ERROR en clustering_fraude.py
    pause
    exit /b 1
)

echo.
echo ═══════════════════════════════════════════════════════════════════
echo   ✅  ML COMPLETADO EXITOSAMENTE
echo ═══════════════════════════════════════════════════════════════════
echo.
echo   Parquet enriquecido:  data\consolidado_features_ml.parquet
echo   Excel resumen:        ml\output\
echo.
echo ═══════════════════════════════════════════════════════════════════

:: Abrir carpeta output de ML
explorer "%BASE%ml\output"

pause
