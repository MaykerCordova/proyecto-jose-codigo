@echo off
chcp 65001 >nul
title Pipeline Condiciones Automatizadas — Scotiabank Peru

echo.
echo ============================================================
echo   CONDICIONES AUTOMATIZADAS — Scotiabank Peru
echo ============================================================
echo.

cd /d "%~dp0"

python automatizar.py

echo.
if %ERRORLEVEL% NEQ 0 (
    echo   [ERROR] El proceso terminó con errores. Revisar mensajes arriba.
) else (
    echo   [OK] Proceso completado correctamente.
)

echo.
pause
