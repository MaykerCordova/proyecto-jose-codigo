"""
Utilidad para buscar y eliminar registros puntuales del SQLite.
Primero muestra el registro encontrado para confirmar, luego elimina.
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


def eliminar_por_conversation_id(conv_id: str):
    with sqlite3.connect(RUTA_DB) as conn:
        conn.execute(
            "DELETE FROM Bitacora WHERE ConversationID = ?", (conv_id,)
        )
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

    confirmacion = input("  ¿Eliminar este registro? (s/n): ").strip().lower()
    if confirmacion == "s":
        eliminar_por_conversation_id(rows[0]["ConversationID"])
        print(f"\n  ✅ Registro eliminado. Corre el bat diario para regenerar el Excel.\n")
    else:
        print("\n  Cancelado. No se eliminó nada.\n")


if __name__ == "__main__":
    main()
