@echo off
echo ============================================================
echo  ML SCORING + EDA — TARJETAS COMPROMETIDAS N7 DEBITO
echo  Scotiabank Peru - Prevencion de Fraude
echo ============================================================
echo.
echo Requiere que el pipeline principal ya se haya ejecutado:
echo   1_ejecutar_pipeline.bat
echo.

cd /d "%~dp0"

echo [1/4] EDA Fraude vs No Fraude...
python scripts\eda_fraude.py
if %errorlevel% neq 0 ( echo ERROR en eda_fraude.py & pause & exit /b 1 )

echo.
echo [2/4] ML Scoring (Regresion Logistica)...
python scripts\ml_scoring.py
if %errorlevel% neq 0 ( echo ERROR en ml_scoring.py & pause & exit /b 1 )

echo.
echo [3/4] Analisis de Reglas para Monitor (simples + combinadas)...
python scripts\reglas_monitor.py
if %errorlevel% neq 0 ( echo ERROR en reglas_monitor.py & pause & exit /b 1 )

echo.
echo [4/4] Generando informe HTML (sin instalacion de paquetes extra)...
python scripts\generar_informe_html.py
if %errorlevel% neq 0 ( echo ERROR en generar_informe_html.py & pause & exit /b 1 )

echo.
echo ============================================================
echo  COMPLETADO - Abriendo carpeta output...
echo ============================================================
explorer output\
pause
