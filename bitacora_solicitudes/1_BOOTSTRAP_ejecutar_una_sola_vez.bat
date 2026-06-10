@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║   BOOTSTRAP Solicitudes Clientes — correr UNA vez   ║
echo ╚══════════════════════════════════════════════════════╝
echo.
echo  Este script reconstruye la base SQLite desde Outlook.
echo  Asegúrate de que Outlook esté abierto antes de continuar.
echo.
pause

python bootstrap_historico_solicitudes.py

echo.
pause
