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

echo [1/3] EDA Fraude vs No Fraude...
python scripts\eda_fraude.py
if %errorlevel% neq 0 ( echo ERROR en eda_fraude.py & pause & exit /b 1 )

echo.
echo [2/3] ML Scoring (Regresion Logistica / XGBoost)...
python scripts\ml_scoring.py
if %errorlevel% neq 0 ( echo ERROR en ml_scoring.py & pause & exit /b 1 )

echo.
echo [3/3] Analisis de Reglas para Monitor...
python scripts\reglas_monitor.py
if %errorlevel% neq 0 ( echo ERROR en reglas_monitor.py & pause & exit /b 1 )

echo.
echo ============================================================
echo  COMPLETADO - Abriendo carpeta output...
echo ============================================================
explorer output\
pause
