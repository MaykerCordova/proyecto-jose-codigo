@echo off
echo ============================================================
echo  DASHBOARD TARJETAS COMPROMETIDAS N7
echo  Iniciando Streamlit en http://localhost:8501
echo ============================================================
cd /d "%~dp0"
python -m streamlit run app.py --server.port 8501
pause
