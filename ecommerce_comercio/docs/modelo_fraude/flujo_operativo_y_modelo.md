# Flujo Operativo de Fraude — Scotiabank Peru
# Modelo de Detección: Contexto, Proceso y Próximos Pasos

**Última actualización:** junio 2026  
**Estado:** En diseño / pendiente de implementación

---

## 1. Las dos bases del sistema

### 8750 — Monitor (motor transaccional)
- Aquí pasan **todas las transacciones en tiempo real**
- Las reglas de fraude se evalúan aquí
- El analista descarga data filtrando por: comercio, BIN, rango de fechas, aprobadas/denegadas
- **Limitante importante:** máximo 50,000 registros por descarga
  - Un comercio como Apple puede tener 50–60k transacciones en un solo día
- Las marcas (F/G/N/P/D) se **actualizan retroactivamente** desde la 8850
  - Si hoy descargo y veo todo N, mañana algunos de esos N ya serán F o G

### 8850 — Base de calificación
- Concentra **todo lo revisado y calificado**
- Tiene dos fuentes de input:
  1. Alertas calificadas por el analista de detección (marcas G/F/P/D)
  2. Reclamos del cliente → proceso llamado **"carga masiva"** (chargebacks)
- La 8850 retroalimenta la 8750, actualizando las marcas

---

## 2. Flujo completo de una transacción

```
Transacción en tiempo real
         │
         ▼
    [8750 — Motor]
    Evaluación de reglas
         │
    ┌────┴────┐
    │         │
Regla       Regla
fuerte      alerta
    │         │
    ▼         ▼
Declina   Va al VISOR
automático  del analista
(código 59) de detección
    │         │
    │    Analista llama
    │    al tarjetahabiente
    │         │
    │    ┌────┼────┬────┐
    │    G    F    P    D
    │    │    │    │    │
    │  Buena Fra  Pend  Des-
    │  conf. conf iente carte
    │         │
    ▼         ▼
         [8850 — Calificación]
              │
         Carga masiva
         (reclamos /
         chargebacks)
              │
              ▼
         Retroalimenta 8750
         (actualiza marcas)
```

### Significado de cada marca
| Marca | Nombre | Descripción |
|---|---|---|
| **F** | Fraude | Confirmado fraude — regla fuerte OR cliente confirmó |
| **G** | Buena | Cliente confirmó que la transacción es legítima |
| **N** | Normal | Pasó sin ser alertada por ninguna regla |
| **P** | Pendiente | Se intentó contactar al cliente pero no respondió |
| **D** | Descarte | Analista evaluó el patrón y determinó que es legítima |

---

## 3. El problema del label N (el "dolor de cabeza")

- **N NO significa necesariamente legítimo**
- N = "la regla no lo detectó" — puede ser fraude silencioso
- Los N fraudulentos aparecen **semanas después** como reclamos (carga masiva)
- Mientras no llegue el reclamo, ese N figura como si fuera bueno
- Se ha observado: transacciones N con BIN12 repetido, diferencia de milisegundos → patrón claramente sospechoso → luego llegan como reclamo
- **Conclusión:** los N están contaminados — una fracción son fraudes no detectados aún

---

## 4. Proceso correcto para el modelo

### Paso 1 — Esperar madurez del label
No usar data reciente. Los chargebacks llegan con 15–45 días de retraso.  
**Usar data de hace 60+ días** para que los N ya hayan tenido tiempo de convertirse en F por reclamo.

### Paso 2 — Estrategia de label objetivo
```
F  → fraude = 1   (confirmado fraude)
G  → fraude = 0   (el label más limpio — confirmado legítimo)
N  → fraude = 0   (asumido, con sesgo conocido)
D  → fraude = 0   (analista lo descartó = patrón habitual)
P  → EXCLUIR      (pendiente = label incierto, ensucia el modelo)
```

### Paso 3 — Balanceo de clases
Con ~6% de fraude no es tan extremo como el 0.5% de datasets públicos.  
Probar primero con `class_weight='balanced'` antes de usar SMOTE.  
Razón: generar datos sintéticos sobre labels ya contaminados amplifica el sesgo.

### Paso 4 — El output real no es el modelo, son las reglas
El modelo identifica variables importantes → se traducen a reglas Monitor (lógica if-then).  
Monitor soporta: acumulados de días/horas, montos acumulados, vínculos de cliente.

```
Modelo dice:  GAP_MINUTOS < 120       →  peso 0.32
              BIN12_REPETIDO           →  peso 0.28
              HORA entre 0–3am         →  peso 0.15

Lo traduces:  SI GAP < 120 Y BIN12_REPETIDO Y HORA < 3 → ALERTA
```

### Paso 5 — Reentrenamiento (retroalimentación)
- Cada mes (o trimestre) descargar data con marcas actualizadas
- Los N de hace 60 días ya tienen sus F definitivos por carga masiva
- Reentrenar el modelo con el dataset ampliado
- No es automático pero sí sistemático

---

## 5. Limitantes actuales

| Limitante | Detalle |
|---|---|
| No deploy en tiempo real | Monitor maneja el scoring en producción |
| 50k registros por descarga | Comercios grandes requieren múltiples descargas o filtros |
| N contaminado | No se sabe qué % de N son fraude hasta que lleguen reclamos |
| Labels tardíos | Reclamos llegan 15–45 días después |

---

## 6. El pitch al jefe / director

> *"Asumiendo N como no fraude (con sesgo conocido por el proceso de carga masiva),  
> el modelo identifica estas variables como las más discriminantes.  
> Con esta combinación capturaría X% del fraude afectando solo Y% de clientes legítimos.  
> La regla propuesta para Monitor sería: [if-then concreto]."*

Presentar siempre con:
- Importancia de variables (modelo)
- Matriz de confusión
- Curva ROC / AUC
- Captura % de fraude vs afectación % de buenos

---

## 7. ¿Dónde nos quedamos?

**Hasta aquí hemos definido:**
- [x] El flujo operativo completo (8750 → 8850 → retroalimentación)
- [x] El problema del label N y por qué está contaminado
- [x] La estrategia de label para el modelo (F=1, N/G/D=0, excluir P)
- [x] El proceso de 5 pasos para construir y retroalimentar el modelo
- [x] Las limitantes actuales del entorno

**Próximo paso a retomar:**
- **Comercio piloto definido: SMART FIT**
- Interpretar resultados del análisis ya corrido (imágenes / Excel)
- Establecer recomendación concreta de regla para Monitor
- Construir el pitch: variables discriminantes + captura% + afectación% + regla if-then propuesta
