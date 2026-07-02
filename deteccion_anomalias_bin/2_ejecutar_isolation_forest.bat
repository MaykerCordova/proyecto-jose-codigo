@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ═══════════════════════════════════════════════════════════════
echo   FASE 2 — Isolation Forest (capa multivariada)
echo ═══════════════════════════════════════════════════════════════
echo.
python ml\isolation_forest.py
if errorlevel 1 (
    echo.
    echo   ❌ Error — asegúrate de haber corrido antes 1_ejecutar_pipeline.bat
)
pause
