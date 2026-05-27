"""
diagnostico_columnas.py
───────────────────────
Muestra las columnas REALES del Excel y cuáles faltan en config.py.
Prueba automáticamente distintos SKIPROWS para detectar dónde está el header.

Ejecutar: python scripts/diagnostico_columnas.py
"""
import sys
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import COLS, FOLDER_JOURNALS

archivos = sorted(FOLDER_JOURNALS.glob("*.xlsx"))
if not archivos:
    archivos = sorted(FOLDER_JOURNALS.glob("*.xls"))
if not archivos:
    print("❌ No hay archivos Excel en data/journals/"); sys.exit(1)

ruta = archivos[0]
print(f"\nArchivo: {ruta.name}")

# ── Detectar SKIPROWS correcto ──────────────────────────────────────────────
print("\n" + "═"*65)
print("DETECTANDO FILA DEL HEADER (probando skiprows 0 a 5)...")
print("═"*65)

cols_config_vals = [v for v in COLS.values() if v and v != "FECHA_HORA"]
mejor_skip = 3
mejor_matches = 0

for skip in range(6):
    try:
        df_test = pd.read_excel(ruta, skiprows=skip, dtype=str, header=0, nrows=2)
        df_test.columns = df_test.columns.str.strip()
        matches = sum(1 for v in cols_config_vals if v in df_test.columns)
        print(f"  skiprows={skip}  →  {matches} columnas coinciden con config.py  | "
              f"Total cols: {len(df_test.columns)}")
        if matches > mejor_matches:
            mejor_matches = matches
            mejor_skip = skip
    except Exception as e:
        print(f"  skiprows={skip}  →  Error: {e}")

print(f"\n  ✅ Mejor opción: SKIPROWS = {mejor_skip} ({mejor_matches} coincidencias)")
print(f"     Si es distinto al valor actual en config.py, actualízalo.")

# ── Leer con el mejor SKIPROWS ──────────────────────────────────────────────
df = pd.read_excel(ruta, skiprows=mejor_skip, dtype=str, header=0, nrows=3)
df.columns = df.columns.str.strip()
cols_excel = list(df.columns)

# ── Mostrar columnas reales ──────────────────────────────────────────────────
print("\n" + "═"*65)
print(f"COLUMNAS REALES EN EL EXCEL (skiprows={mejor_skip}) — Total: {len(cols_excel)}")
print("═"*65)
for i, c in enumerate(cols_excel, 1):
    print(f"  {i:>3}. {c}")

# ── Verificar vs config.py ───────────────────────────────────────────────────
print("\n" + "═"*65)
print("COLUMNAS DE CONFIG.PY — ESTADO:")
print("═"*65)

ok, mal = [], []
for clave, valor in COLS.items():
    if not valor or valor == "FECHA_HORA":
        continue
    if valor in cols_excel:
        ok.append((clave, valor))
    else:
        mal.append((clave, valor))

print(f"\n✅ ENCONTRADAS ({len(ok)}):")
for k, v in ok:
    print(f"   {k:30s} → '{v}'")

if mal:
    print(f"\n❌ NO ENCONTRADAS ({len(mal)}) — buscar nombre similar abajo:")
    for k, v in mal:
        # Buscar la columna más parecida en el Excel
        similar = [c for c in cols_excel
                   if any(p.upper() in c.upper() for p in v.replace("ACF-","").split()[:2])]
        print(f"\n   config  → '{v}'")
        if similar:
            print(f"   Excel   → posibles: {similar[:3]}")
        else:
            print(f"   Excel   → sin similares visibles")

print("\n" + "═"*65)
print("ACCION: copia los nombres de la columna 'Excel →' al valor")
print("correspondiente en scripts/config.py y vuelve a ejecutar el pipeline.")
print("═"*65)
