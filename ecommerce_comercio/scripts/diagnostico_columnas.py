"""
diagnostico_columnas.py
───────────────────────
Muestra todas las columnas del primer Excel en data/journals/
para comparar con los nombres definidos en config.py

Ejecutar: python scripts/diagnostico_columnas.py
"""
import sys
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import COLS, FOLDER_JOURNALS, SKIPROWS

archivos = sorted(FOLDER_JOURNALS.glob("*.xlsx"))
if not archivos:
    archivos = sorted(FOLDER_JOURNALS.glob("*.xls"))
if not archivos:
    print("❌ No hay archivos Excel en data/journals/"); sys.exit(1)

ruta = archivos[0]
print(f"\nLeyendo: {ruta.name}")
df = pd.read_excel(ruta, skiprows=SKIPROWS, dtype=str, header=0, nrows=3)
df.columns = df.columns.str.strip()

cols_excel = list(df.columns)
cols_config = {k: v for k, v in COLS.items() if v}

print("\n" + "═"*65)
print("COLUMNAS EN EL EXCEL (primeras 60):")
print("═"*65)
for i, c in enumerate(cols_excel[:60], 1):
    print(f"  {i:>3}. {c}")

print("\n" + "═"*65)
print("VERIFICACIÓN vs CONFIG.PY:")
print("═"*65)
ok, mal = [], []
for clave, valor in cols_config.items():
    if valor in cols_excel:
        ok.append((clave, valor))
    else:
        mal.append((clave, valor))

print(f"\n✅ ENCONTRADAS ({len(ok)}):")
for k, v in ok:
    print(f"   {k:25s} → '{v}'")

print(f"\n❌ NO ENCONTRADAS ({len(mal)}) — HAY QUE CORREGIR EN config.py:")
for k, v in mal:
    print(f"   {k:25s} → '{v}'")

print("\n" + "═"*65)
