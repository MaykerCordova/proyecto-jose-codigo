"""
main.py — Punto de entrada del pipeline.

Este archivo es el único que "sabe" qué fuentes existen y dónde están.
Si mañana se agrega una fuente nueva (ej: RT_PREPAGO), solo hay que
agregar una línea aquí, sin tocar ninguna otra clase.

Ejecución:
    python main.py
"""
import config
from consolidador import ConsolidadorHerramientas
from esquema import EsquemaMaster
from fuentes import FuenteAccess, FuenteParquet


def main() -> None:
    esquema = EsquemaMaster()

    fuentes = [
        FuenteParquet("VCAS",       config.RUTA_VCAS,       esquema),
        FuenteAccess( "FRM",        config.RUTA_BD_FRM,     "SELECT * FROM BBDD_FRM", esquema),
        FuenteParquet("VRM",        config.RUTA_VRM,        esquema),
        FuenteParquet("RT_DEBITO",  config.RUTA_RT_DEBITO,  esquema),
        FuenteParquet("RT_CREDITO", config.RUTA_RT_CREDITO, esquema),
    ]

    consolidador = ConsolidadorHerramientas(
        fuentes=fuentes,
        ruta_salida=config.RUTA_PARQUET_SALIDA,
    )
    consolidador.ejecutar()


if __name__ == "__main__":
    main()
