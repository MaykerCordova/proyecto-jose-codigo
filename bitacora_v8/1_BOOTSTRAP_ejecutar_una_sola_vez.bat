@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║   BOOTSTRAP HISTÓRICO V8 — Solo correr UNA vez      ║
echo ╚══════════════════════════════════════════════════════╝
echo.
echo  Este script reconstruye la base SQLite desde Outlook.
echo  Asegúrate de que Outlook esté abierto antes de continuar.
echo.
pause

python bootstrap_historico_v8.py

echo.
pause
