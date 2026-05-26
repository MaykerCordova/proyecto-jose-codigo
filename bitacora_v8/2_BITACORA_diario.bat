@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║   ROBOT BITÁCORA V8 — Ejecución diaria              ║
echo ╚══════════════════════════════════════════════════════╝
echo.

python bitacoraV8.py

echo.
pause
