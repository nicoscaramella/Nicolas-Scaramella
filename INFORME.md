# Informe técnico · modelos usados

## Entrega 1

| Tarea | Modelo | Proveedor | Versión | Parámetros | Hardware | Tokens | Costo |
|---|---|---|---|---|---|---|---|
| Transcripción de notas | `faster-whisper` `small` (CTranslate2) | OpenAI Whisper / SYSTRAN | faster-whisper 1.x, pesos Whisper small | ~244 M | CPU AMD Ryzen 5 5600, 4 CPU / 7 GB de contenedor, int8 | 0 (no es un LLM) | USD 0 |
| Embeddings del RAG | `intfloat/multilingual-e5-small` | Microsoft / Hugging Face | sentence-transformers 3.x | ~118 M | CPU, mismo contenedor | 0 | USD 0 |
| Extracción del parte | Parser determinista (`sistema/parser.py`) | — | — | — | CPU | 0 | USD 0 |
| Detección y seguridad | Reglas en código (`deteccion.py`, `seguridad.py`) | — | — | — | CPU | 0 | USD 0 |
| Contexto y consultas (opcional) | `ministral-3:3b` (GGUF, Ollama) | Mistral AI | ministral-3:3b | 3 B | CPU del host, fuera del contenedor | reales por consulta | USD 0 |

No se usan modelos en la nube en la Entrega 1. El sistema funciona con el
enlace caído: la transcripción, la detección, la alerta de seguridad y el parser
son locales.

El LLM es **opcional y fuera del camino crítico**: `LLM_HABILITADO=0` por
defecto. Si Ollama no está, el context builder y `scripts/preguntar.py` caen al
texto determinista con las citas. El parte nunca se arma ni se confirma con el
LLM.

### Consumo y latencia

- **Tokens de LLM**: 0 en el camino crítico. La transcripción y los embeddings
  no se facturan por token; se reporta 0 en `sistema/metricas` para que el visor
  muestre el modelo local sin inventar consumo. Cuando se usa el LLM opcional,
  el cliente devuelve `prompt_eval_count`/`eval_count` reales.
- **Costo**: USD 0 (todo local).
- **Latencia**: se mide en la corrida de corrección; el ASR de una nota de
  recorrida se procesa en CPU con `small` int8.

### Conclusión

Se eligió un pipeline local y determinista porque el anexo exige que la
transcripción sea local y porque el hardware de planta no tiene GPU (4 CPU,
8 GB). Un LLM chico en CPU agregaría latencia y variabilidad sin mejorar el
parte: las notas del operador siguen plantillas acotadas y un parser validado
contra `FilaParte` es más preciso y auditable. LangChain se usa en el context
builder y el RAG; el LLM local opcional (`ministral-3:3b`) redacta contexto y
consultas, y queda desactivado para la corrida oficial.
