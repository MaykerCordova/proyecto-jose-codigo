"""
Utilidad para anular registros puntuales del SQLite.
Marca Conformidad = 'ANULADO' y guarda el motivo en Consideraciones.
No elimina nada — el correlativo se mantiene en la secuencia para auditoría.
"""

import os
import sqlite3

_BASE = os.path.join(
    os.path.expanduser("~"),
    "OneDrive - The Bank of Nova Scotia",
    "Bitacora_Reglas",
)
RUTA_DB = os.path.join(_BASE, "Respaldo_Blindado.db")

# ══════════════════════════════════════════════════════════════════
# ▶  EDITAR AQUÍ — criterios de búsqueda
#    Deja en None los campos que no quieras usar como filtro.
# ══════════════════════════════════════════════════════════════════
FILTRO = {
    "Fecha":  "16/02/2026",   # formato DD/MM/YYYY
    "Hora":   "16:31",        # formato HH:MM
    "Maker":  "César",        # basta con parte del nombre
}
# ══════════════════════════════════════════════════════════════════


def buscar(filtro: dict):
    condiciones = []
    valores     = []
    for col, val in filtro.items():
        if val is not None:
            condiciones.append(f"{col} LIKE ?")
            valores.append(f"%{val}%")
    where = " AND ".join(condiciones)
    with sqlite3.connect(RUTA_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM Bitacora WHERE {where}", valores
        ).fetchall()
    return rows


def anular(conv_id: str, motivo: str):
    with sqlite3.connect(RUTA_DB) as conn:
        conn.execute("""
            UPDATE Bitacora
            SET Conformidad     = 'ANULADO',
                Consideraciones = ?
            WHERE ConversationID = ?
        """, (motivo, conv_id))
        conn.commit()


def main():
    print(f"\n  🔍 Buscando registros con filtro: {FILTRO}\n")
    rows = buscar(FILTRO)

    if not rows:
        print("  ⚠️  No se encontró ningún registro con esos criterios.")
        return

    print(f"  Registros encontrados: {len(rows)}\n")
    for r in rows:
        print(f"  ─────────────────────────────────────────")
        print(f"  Correlativo  : {r['Nro_Correlativo']}")
        print(f"  Fecha / Hora : {r['Fecha']} {r['Hora']}")
        print(f"  Maker        : {r['Maker']}")
        print(f"  Herramienta  : {r['Herramienta']}")
        print(f"  Condicion    : {r['Codigo_Condicion']} — {r['Nombre_Condicion']}")
        print(f"  Conformidad  : {r['Conformidad']}")
        print(f"  ConversationID: {r['ConversationID'][:40]}...")
    print(f"  ─────────────────────────────────────────\n")

    if len(rows) > 1:
        print("  ⚠️  Se encontró más de un registro.")
        print("  Ajusta el FILTRO para ser más específico y vuelve a correr.\n")
        return

    motivo = input("  Motivo de anulación (escribe y presiona Enter):\n  > ").strip()
    if not motivo:
        print("\n  Cancelado. Se requiere un motivo para anular.\n")
        return

    confirmacion = input(f"\n  ¿Marcar correlativo {rows[0]['Nro_Correlativo']} como ANULADO? (s/n): ").strip().lower()
    if confirmacion == "s":
        anular(rows[0]["ConversationID"], motivo)
        print(f"\n  ✅ Registro anulado. Corre el bat diario para regenerar el Excel.\n")
    else:
        print("\n  Cancelado. No se modificó nada.\n")


if __name__ == "__main__":
    main()
