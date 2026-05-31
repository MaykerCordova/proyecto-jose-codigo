"""
consolidador.py — Orquestador del pipeline completo.

¿Por qué una clase aquí?
    ConsolidadorHerramientas es el "director de orquesta": no sabe cómo
    funciona cada fuente, solo sabe que todas tienen un método `procesar()`
    y que hay que unirlas. Separar esto de main.py permite testear la
    lógica de unión y escritura sin depender de archivos reales.
"""
from __future__ import annotations

import time
from pathlib import Path

import polars as pl

from fuentes import FuenteBase, FuenteParquet


class ConsolidadorHerramientas:
    """
    Orquesta el pipeline completo:
    1. Valida que los archivos fuente existan
    2. Procesa cada fuente en su pipeline correspondiente
    3. Une todos los resultados en un solo DataFrame master
    4. Guarda el resultado como Parquet
    5. Imprime un resumen de validación
    """

    def __init__(self, fuentes: list[FuenteBase], ruta_salida: Path) -> None:
        self.fuentes = fuentes
        self.ruta_salida = ruta_salida

    def ejecutar(self) -> pl.DataFrame:
        """Punto de entrada principal. Retorna el DataFrame master generado."""
        t0 = time.time()

        self._validar_fuentes()
        dataframes = self._procesar_fuentes()
        master = self._unir_y_colectar(dataframes)

        self.ruta_salida.parent.mkdir(parents=True, exist_ok=True)
        master.write_parquet(self.ruta_salida)

        self._imprimir_resumen(master, tiempo_segundos=time.time() - t0)
        return master

    # ------------------------------------------------------------------
    # Pasos internos
    # ------------------------------------------------------------------

    def _validar_fuentes(self) -> None:
        """Verifica la existencia de archivos antes de iniciar el proceso."""
        for fuente in self.fuentes:
            if isinstance(fuente, FuenteParquet):
                fuente.validar()

    def _procesar_fuentes(self) -> list[pl.LazyFrame]:
        """Llama a procesar() en cada fuente y retorna la lista de LazyFrames."""
        resultados = []
        for fuente in self.fuentes:
            print(f"  Procesando fuente: {fuente.nombre}...")
            resultados.append(fuente.procesar())
        return resultados

    def _unir_y_colectar(self, dataframes: list[pl.LazyFrame]) -> pl.DataFrame:
        """
        Une todos los LazyFrames verticalmente y ejecuta el plan lazy.

        - how="vertical_relaxed": permite diferencias de tipo entre columnas
          (ej: una fuente tiene fecha como Date, otra como Datetime).
        - streaming=True: procesa en chunks, crucial para 9M+ registros.
          Evita cargar todo en RAM de una sola vez.
        """
        master_lazy = pl.concat(dataframes, how="vertical_relaxed")
        print("  Ejecutando plan lazy (collect streaming)...")
        return master_lazy.collect(streaming=True)

    def _imprimir_resumen(self, master: pl.DataFrame, tiempo_segundos: float) -> None:
        """Imprime estadísticas de validación del master generado."""
        fecha     = master["fecha"]
        pct_nulos = round(fecha.null_count() / master.height * 100, 2)

        print("\n✅ MASTER CONSOLIDADO GENERADO")
        print(f"   Filas totales  : {master.height:,}")
        print(f"   Columnas       : {master.width}")
        print(f"   Tipo de fecha  : {master.schema['fecha']}")
        print(f"   Fecha mínima   : {fecha.min()}")
        print(f"   Fecha máxima   : {fecha.max()}")
        print(f"   % Nulos fecha  : {pct_nulos}%")
        print(f"   Tiempo total   : {tiempo_segundos:.2f} segundos")
        print(f"   Guardado en    : {self.ruta_salida}")
