@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║   MONITOR COMPARADOR — Ejecución diaria             ║
echo ╚══════════════════════════════════════════════════════╝
echo.

python monitor_comparador.py

echo.
pause
