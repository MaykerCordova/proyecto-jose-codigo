# Consolidado de Herramientas — Documentación del Pipeline

## ¿Qué hace este proceso?

Une 5 fuentes de datos de detección de fraude en un solo archivo Parquet maestro
(`MASTER_CONSOLIDADO.parquet`) con un esquema estándar de 12 columnas.

Las fuentes son:
| Fuente | Tipo | Herramienta de fraude |
|---|---|---|
| VCAS | Parquet (polars) | VCAS unitario |
| VRM | Parquet (polars) | VRM gold |
| RT_DEBITO | Parquet (polars) | Rechazos tarjeta débito |
| RT_CREDITO | Parquet (polars) | Rechazos tarjeta crédito |
| FRM | Access (.accdb, pandas) | FRM — solo declinaciones de39=63 |

---

## Estructura del repositorio

```
consolidado_declinaciones/
│
├── version_original/
│   └── consolidado_original.py   # Código funcional original (notebook → .py)
│
└── version_oop/
    ├── config.py                 # Rutas y constantes
    ├── transformaciones.py       # Funciones puras de limpieza
    ├── esquema.py                # Clase EsquemaMaster
    ├── fuentes.py                # Clases FuenteBase / FuenteParquet / FuenteAccess
    ├── consolidador.py           # Clase ConsolidadorHerramientas
    ├── main.py                   # Punto de entrada (ejecutar este)
    └── requirements.txt
```

---

## Cómo ejecutar

```bash
# Instalar dependencias
pip install -r version_oop/requirements.txt

# Ejecutar el pipeline
python version_oop/main.py
```

---

## Diagrama del flujo

```
main.py
  │
  ├── crea EsquemaMaster (columnas + sinónimos)
  │
  ├── crea lista de Fuentes:
  │     FuenteParquet("VCAS")
  │     FuenteAccess("FRM")
  │     FuenteParquet("VRM")
  │     FuenteParquet("RT_DEBITO")
  │     FuenteParquet("RT_CREDITO")
  │
  └── ConsolidadorHerramientas.ejecutar()
        │
        ├── 1. Validar archivos (FileNotFoundError si falta alguno)
        │
        ├── 2. Por cada fuente → fuente.procesar()
        │     │
        │     │  Pipeline polars (FuenteParquet):
        │     │    scan_parquet (lazy)
        │     │    → normalizar_columnas_pl
        │     │    → aplicar_sinonimos_pl
        │     │    → parsear_fecha_pl
        │     │    → agregar columna 'herramienta'
        │     │    → estandarizar_pl (selecciona COLUMNAS_MASTER)
        │     │
        │     │  Pipeline pandas + polars (FuenteAccess/FRM):
        │     │    leer_access (pandas)
        │     │    → normalizar_columnas_pd
        │     │    → aplicar_sinonimos_pd
        │     │    → parsear_fecha_pd
        │     │    → filtrar_declinaciones_validas (de39==63, sin NM/RD)
        │     │    → pandas_a_polars_con_fecha
        │     │    → agregar 'herramienta'
        │     │    → estandarizar_pl
        │     │
        ├── 3. pl.concat(todos, how="vertical_relaxed")
        │        .collect(streaming=True)   ← procesa en chunks, no carga todo en RAM
        │
        ├── 4. master.write_parquet(ruta_salida)
        │
        └── 5. Imprimir resumen (filas, fechas, % nulos, tiempo)
```

---

## Explicación de cada clase

### `EsquemaMaster` (esquema.py)

**¿Por qué existe?**
El master tiene 12 columnas estándar, pero cada fuente las llama diferente.
Por ejemplo, "fecha" se llama "ACF_Fecha_TRX" en VCAS y "RT-Fecha TRX" en los RT.
Esta clase centraliza esa lógica de mapeo para no repetirla en cada fuente.

**Responsabilidades:**
- Guardar la lista de columnas master (`COLUMNAS_MASTER`)
- Guardar el diccionario de sinónimos (`SINONIMOS_BRUTOS`)
- Pre-normalizar los sinónimos al inicializarse (una sola vez)
- `aplicar_sinonimos_pd(df)` → mapea sinónimos en pandas
- `aplicar_sinonimos_pl(df)` → mapea sinónimos en polars
- `estandarizar_pd(df)` → deja solo COLUMNAS_MASTER en pandas
- `estandarizar_pl(df)` → deja solo COLUMNAS_MASTER en polars

---

### `FuenteBase` (fuentes.py)

**¿Por qué existe?**
Las 4 fuentes parquet siguen exactamente el mismo pipeline de 6 pasos.
Sin esta clase, ese pipeline se repetiría 4 veces. Con `FuenteBase`,
el pipeline está escrito una sola vez en `procesar()` y cada subclase
solo implementa `_cargar_crudo()`.

**Responsabilidades:**
- Definir el contrato: toda fuente tiene `nombre`, `esquema`, y `procesar()`
- Implementar el pipeline estándar polars en `procesar()`
- Declarar `_cargar_crudo()` como abstracto (obliga a las subclases a implementarlo)

---

### `FuenteParquet` (fuentes.py)

**¿Por qué existe?**
Implementa `_cargar_crudo()` para archivos `.parquet` usando `pl.scan_parquet`.
`scan_parquet` es **lazy**: polars construye un plan de ejecución pero no
lee datos hasta que se llama `.collect()`. Esto es lo que permite manejar
9M+ registros sin llenar la RAM.

**Responsabilidades:**
- Guardar la ruta del archivo parquet
- `validar()` → verifica que el archivo existe antes de empezar
- `_cargar_crudo()` → abre el parquet en modo lazy

---

### `FuenteAccess` (fuentes.py)

**¿Por qué es una clase separada y no usa el mismo pipeline?**
Access no tiene soporte nativo en polars: requiere `pyodbc` + `pandas`.
Además, FRM tiene un filtro de negocio propio (solo `de39 == "63"`) que
no aplica a ninguna otra fuente.

**Responsabilidades:**
- Leer desde `.accdb` usando pyodbc
- Aplicar el pipeline en pandas (normalizar, sinónimos, fecha)
- `_filtrar_declinaciones_validas(df)` → aplica las reglas de negocio de FRM:
  - `de39 == "63"` → código ISO de declinación por VCAS
  - `condicion` no es "NM" (no match) ni "RD" (reverso/duplicado)
- Convertir a polars LazyFrame al final con `pandas_a_polars_con_fecha()`

---

### `ConsolidadorHerramientas` (consolidador.py)

**¿Por qué existe?**
Es el orquestador. No sabe cómo funciona cada fuente internamente;
solo sabe que todas tienen `procesar()` y que el resultado se puede
unir con `pl.concat`. Separar la orquestación de las fuentes permite
agregar o quitar fuentes modificando solo `main.py`.

**Responsabilidades:**
- `_validar_fuentes()` → FileNotFoundError temprano si falta un parquet
- `_procesar_fuentes()` → llama `procesar()` en cada fuente
- `_unir_y_colectar()` → `pl.concat + collect(streaming=True)`
- Escribir el parquet de salida
- `_imprimir_resumen()` → estadísticas de validación

---

## Funciones puras (transformaciones.py)

Son funciones, no métodos de clase, porque **no guardan estado**.
Solo reciben datos y devuelven datos transformados:

| Función | Qué hace |
|---|---|
| `normalizar_nombre_columna(col)` | minúsculas, sin tildes, sin espacios dobles |
| `normalizar_columnas_pd(df)` | aplica la anterior a todas las columnas pandas |
| `normalizar_columnas_pl(df)` | ídem para polars LazyFrame |
| `parsear_fecha_pd(df)` | convierte fecha a datetime pandas (dayfirst=True) |
| `parsear_fecha_pl(df)` | convierte fecha a Datetime("ms") polars (detecta DD/MM/YYYY) |
| `pandas_a_polars_con_fecha(df)` | convierte pandas → polars LazyFrame, asegura tipo fecha |
| `leer_access(ruta, sql)` | lee una consulta desde .accdb con pyodbc |

---

## Mejoras de rendimiento respecto a la versión original

| Mejora | Detalle |
|---|---|
| `collect(streaming=True)` | Polars procesa los 9M registros en chunks en lugar de cargarlos todos en RAM de golpe. La versión original usaba `.collect()` sin streaming. |
| `collect_schema()` en `apply_synonyms_pl` | La versión original accedía a `.schema` directamente en el LazyFrame, lo que puede ser impreciso. La versión OOP usa `.collect_schema()` que es el método correcto. |
| Validación temprana con `FileNotFoundError` | El error aparece antes de hacer cualquier carga de datos, no a mitad del proceso. |
| Código sin repetición | El pipeline polars está escrito una sola vez en `FuenteBase.procesar()`. Menos código = menos bugs posibles. |
| `pd.to_datetime` sin `infer_datetime_format` | `infer_datetime_format=True` está deprecado en pandas 2.x. La versión OOP lo elimina. |

### Mejora adicional opcional (para datasets muy grandes)

Si los 9M registros siguen siendo lentos, se puede reemplazar:
```python
# En ConsolidadorHerramientas._unir_y_colectar()
# Cambiar collect + write_parquet por sink_parquet (escribe directo sin materializar):
master_lazy.sink_parquet(self.ruta_salida)
```
El trade-off es que `sink_parquet` no permite calcular estadísticas de validación
(min/max fecha, % nulos) porque no hay DataFrame en memoria.

---

## Agregar una nueva fuente

Si mañana aparece una nueva fuente, por ejemplo `RT_PREPAGO`:

1. En `config.py` agrega la ruta:
   ```python
   RUTA_RT_PREPAGO = DIRECTORIO_DATOS / "rt_prepago_gold.parquet"
   ```

2. En `main.py` agrega una línea:
   ```python
   FuenteParquet("RT_PREPAGO", config.RUTA_RT_PREPAGO, esquema),
   ```

3. Si la nueva fuente tiene columnas con nombres distintos, agrega sus sinónimos
   en `SINONIMOS_BRUTOS` dentro de `esquema.py`.

No hay que tocar `consolidador.py`, `fuentes.py` ni `transformaciones.py`.
