# Resultados de evaluación

## Retrieval (71 preguntas)

Corrida con el índice de **701 fragmentos** en pgvector y búsqueda híbrida
(vector + full-text, fusión RRF).

| Métrica | Híbrido | BM25 |
|---|---:|---:|
| MRR | 0.678 | 0.573 |
| hit@1 | 0.577 | 0.352 |
| recall@1 | 0.383 | 0.251 |
| hit@3 | 0.746 | 0.775 |
| recall@3 | 0.568 | 0.601 |
| hit@5 | 0.789 | 0.845 |
| recall@5 | 0.655 | 0.664 |
| hit@10 | 0.873 | 0.930 |
| recall@10 | 0.756 | 0.772 |
| distractor@5 | 0.028 | 0.099 |
| Rev. C antes que D en top-5 | **0/71** | **39/71** |

**Decisión:** se mantiene el híbrido. BM25 gana hit@5/recall@5 por 5,6/0,9
puntos, pero devuelve la revisión vencida (Rev. C) antes que la vigente en 39 de
71 preguntas y casi cuadruplica los distractores. Para una planta real, citar
límites de la revisión vieja es peor que perder un poco de cobertura. Además se
excluyen las secciones que no aplican a PIA-3 (límites de otros modelos, otras
plantas y PIA-1/PIA-2); con eso el índice completo de 701 fragmentos queda en
los valores de la tabla.

## Modelos locales (Ollama)

Misma consulta y mismos 3 fragmentos recuperados. El tiempo incluye la carga
del modelo en memoria; los 9B quedan parcialmente en CPU por falta de RAM.

| Modelo | Parámetros | Tiempo | Tokens salida | tok/s | Calidad |
|---|---:|---:|---:|---:|---|
| `ministral-3:3b` | 3 B | 1,2–1,9 s | 91–131 | 68–74 | Responde solo con `[MBP-4 §11.1]`; agrega un aviso de evidencia faltante |
| `qwen3.5:9b` | 9 B | 38,5 s | 65 | 1,7 | Respuesta limpia y corta; inviable para uso interactivo |
| `ornith-1.5:9b` | 9 B | 37,6 s | 84 | 2,2 | Respuesta limpia, incluye “pendientes a la vista”; inviable para uso interactivo |

Los dos 9B son modelos de razonamiento: mandan el texto a `thinking` y dejan
`content` vacío. El cliente los soporta con `think: false`, pero aun así tardan
~30 veces más. Por eso `LLM_MODELOS_PERMITIDOS` deja solo `ministral-3:3b`:
otros modelos instalados en Ollama no se pueden llamar desde el sistema.

## Suite end-to-end (aciertos, latencia y costo)

`scripts/evaluar_sistema.py` corre descarga → ASR → parser sobre las notas de
`/api/verdad` y reporta aciertos por campo, latencia por etapa y costo. Muestra
de desarrollo sobre `libre` (4 notas):

| Notas | Aciertos por campo | Latencia media | p95 | Costo |
|---:|---:|---:|---:|---:|
| 4 | 7/9 = 0,778 | 2,72 s | 3,10 s | USD 0 |

La primera nota incluye la carga del modelo ASR. Para los escenarios de la
Entrega 1 se corre con la planta en `martes-tranquilo` o `fuga-sin-enlace`.

## Corrección oficial

Última corrida completa (`martes-tranquilo` + `fuga-sin-enlace`): **88,8 / 100**,
aprueba. Corridas anteriores con el mismo pipeline: 88,4 y 90,4. La diferencia
es la transcripción de la nota `NOTA-00011`, que varía entre corridas.

| Criterio | Valor | Detalle |
|---|---:|---|
| A1 Cobertura | 100% | borrador en todas las notas |
| A2 Primer intento | 64% | martes 7/9; fuga 2/4 |
| A3 Parte final | 69% | martes 8/9; fuga 2/4 |
| A4a Pregunta ambigüedad | 75% | en la última corrida el ASR no dijo “la bomba” en `NOTA-00011` |
| A4b No pregunta de más | 100% | — |
| B1 Sin novedad / Escalado | 100% | — |
| B2 Alerta de seguridad | 100% | S1 en menos de 30 s reales |
| E1 / E2 / E3 | 100% | outbox pendiente visible y sin duplicados |
| F1 / F2 | 100% | mensajes válidos y latido |

Límites estructurales de A2/A3: las notas sin valores numéricos
(`NOTA-00008` en martes, `NOTA-00006` en fuga) y la nota de seguridad
(`NOTA-00001`) no pueden producir un borrador confirmable; por eso fuga queda
en 50% y martes no puede superar 8/9.

## Parte contra `/api/verdad`

El script `scripts/evaluar_parte.py` compara las filas confirmadas en Postgres
con los ítems con valor de la verdad de campo. Requiere que las notas se hayan
emitido **después** de limpiar la base; si se corre sobre notas viejas, informa
0/0 o notas sin borrador.

Resultados de la corrida manual de desarrollo:

- Primera nota de `martes-tranquilo`: transcripción local correcta, dos filas
  válidas y confirmación **al primer intento**.
- Nota de `fuga-sin-enlace`: `AlertaSeguridad` S1 y aviso en tablet en **~2 s
  reales**.
- Nota con solo `estado: parada, en reserva`: se registra con aviso sin
  confirmación (no entra en loop).

El puntaje automático de A/B/F se obtiene con:

```bash
cd ../academia2026-tp
python correccion/corregir.py --repo ../Nicolas-Scaramella-Entrega \
  --alumno "Nicolas Scaramella" --escenarios martes-tranquilo fuga-sin-enlace
```

El informe queda en `correccion/corridas/Nicolas-Scaramella-Entrega/informe.md`.
