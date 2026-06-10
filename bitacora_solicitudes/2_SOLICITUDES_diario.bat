@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║   ROBOT Solicitudes Clientes — Ejecución diaria     ║
echo ╚══════════════════════════════════════════════════════╝
echo.

python bitacora_solicitudes.py

echo.
pause
