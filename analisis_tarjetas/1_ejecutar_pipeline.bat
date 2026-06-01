@echo off
echo ============================================================
echo  PIPELINE TARJETAS COMPROMETIDAS N7 DEBITO
echo  Scotiabank Peru - Prevencion de Fraude
echo ============================================================
echo.

cd /d "%~dp0"

echo [1/3] Consolidando journals...
python scripts\consolidar.py
if %errorlevel% neq 0 ( echo ERROR en consolidar.py & pause & exit /b 1 )

echo.
echo [2/3] Generando features...
python scripts\feature_engineering.py
if %errorlevel% neq 0 ( echo ERROR en feature_engineering.py & pause & exit /b 1 )

echo.
echo [3/3] Generando Excel de analisis...
python scripts\analisis.py
if %errorlevel% neq 0 ( echo ERROR en analisis.py & pause & exit /b 1 )

echo.
echo ============================================================
echo  PIPELINE COMPLETO - Abriendo carpeta output...
echo ============================================================
explorer output\
pause
