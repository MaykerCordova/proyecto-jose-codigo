@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ═══════════════════════════════════════════════════════════════
echo   DETECCIÓN DE ANOMALÍAS POR RANGO DE BIN — Pipeline completo
echo ═══════════════════════════════════════════════════════════════
echo.
echo   [1/4] Consolidando journals de Monitor...
python scripts\consolidar.py
if errorlevel 1 goto error

echo.
echo   [2/4] Agregando series diarias por rango de BIN (Polars)...
python scripts\agregacion.py
if errorlevel 1 goto error

echo.
echo   [3/4] Detección — z-score robusto (mediana + MAD)...
python scripts\deteccion.py
if errorlevel 1 goto error

echo.
echo   [4/4] Atribución — contribución + chi-cuadrado + calendario...
python scripts\atribucion.py
if errorlevel 1 goto error

echo.
echo ═══════════════════════════════════════════════════════════════
echo   ✅ PIPELINE COMPLETO — revisa la carpeta output\
echo   Fase 2 (opcional): 2_ejecutar_isolation_forest.bat
echo ═══════════════════════════════════════════════════════════════
pause
exit /b 0

:error
echo.
echo   ❌ El pipeline se detuvo por un error. Revisa el mensaje de arriba.
pause
exit /b 1
