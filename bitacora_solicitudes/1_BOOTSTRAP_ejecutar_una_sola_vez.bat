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
echo  Fecha desde la cual procesar (formato AAAA-MM-DD).
echo  Deja vacío y presiona Enter para usar la fecha por defecto del código.
set /p FECHA_DESDE="  Desde (ej. 2026-07-05): "
pause

if "%FECHA_DESDE%"=="" (
    python bootstrap_historico_solicitudes.py
) else (
    python bootstrap_historico_solicitudes.py --desde %FECHA_DESDE%
)

echo.
pause
