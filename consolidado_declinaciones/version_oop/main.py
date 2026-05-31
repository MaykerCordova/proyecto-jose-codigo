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
from detector_anomalias import DetectorAnomalias
from esquema import EsquemaMaster
from fuentes import FuenteAccess, FuenteParquet
from post_procesamiento import PostProcesadorMaster
from reporte_correo import ReporteCorreo


def main() -> None:
    esquema = EsquemaMaster()

    fuentes = [
        FuenteParquet("VCAS",       config.RUTA_VCAS,       esquema),
        FuenteAccess( "FRM",        config.RUTA_BD_FRM,     "SELECT * FROM BBDD_FRM", esquema),
        FuenteParquet("VRM",        config.RUTA_VRM,        esquema),
        FuenteParquet("RT_DEBITO",  config.RUTA_RT_DEBITO,  esquema),
        FuenteParquet("RT_CREDITO", config.RUTA_RT_CREDITO, esquema),
    ]

    # Paso 1: consolidar todas las fuentes en un master crudo
    consolidador = ConsolidadorHerramientas(
        fuentes=fuentes,
        ruta_salida=config.RUTA_PARQUET_SALIDA,
    )
    consolidador.ejecutar()

    # Paso 2: filtros de negocio + columnas calculadas → parquet para Power BI
    post = PostProcesadorMaster(
        ruta_entrada=config.RUTA_PARQUET_SALIDA,
        ruta_salida=config.RUTA_PARQUET_POWERBI,
    )
    post.ejecutar()

    # Paso 3: detectar anomalías y enviar reporte por correo
    detector = DetectorAnomalias(
        ruta_parquet=config.RUTA_PARQUET_POWERBI,
        ventana_dias=config.VENTANA_DIAS_ZSCORE,
        umbral_zscore=config.UMBRAL_ZSCORE,
        top_n=config.TOP_N_ALERTAS,
    )
    resultado = detector.analizar()

    reporte = ReporteCorreo(
        resultado_detector=resultado,
        destinatarios=config.DESTINATARIOS_CORREO,
    )
    reporte.enviar()


if __name__ == "__main__":
    main()
