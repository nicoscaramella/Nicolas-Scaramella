# Informe técnico · modelos usados

## Entrega 1

| Tarea | Modelo | Proveedor | Versión | Parámetros | Hardware | Tokens | Costo |
|---|---|---|---|---|---|---|---|
| Transcripción de notas | `faster-whisper` `small` (CTranslate2) | OpenAI Whisper / SYSTRAN | faster-whisper 1.x, pesos Whisper small | ~244 M | Desktop Fedora, CPU AMD Ryzen 5 5600 (6C/12T), 3,5 vCPU / 7 GB del contenedor, int8; sin GPU | 0 (no es un LLM) | USD 0 |
| Embeddings del RAG | `intfloat/multilingual-e5-small` | Microsoft / Hugging Face | sentence-transformers 3.x | ~118 M | Mismo contenedor, CPU (3,5 vCPU / 7 GB) | 0 | USD 0 |
| Extracción del parte | Parser determinista (`sistema/parser.py`) | — | — | — | CPU del contenedor | 0 | USD 0 |
| Detección y seguridad | Reglas en código (`deteccion.py`, `seguridad.py`) | — | — | — | CPU del contenedor | 0 | USD 0 |
| Contexto y consultas (opcional) | `ministral-3:3b` (GGUF, Ollama) | Mistral AI | ministral-3:3b | 3 B | Desktop Fedora, **GPU AMD Radeon RX 6700 XT 12 GB** (Ollama/ROCm), CPU AMD Ryzen 5 5600, 15 GB RAM; 100 % GPU en las pruebas | 91–131 de salida por consulta | USD 0 |

No se usan modelos en la nube en la Entrega 1. El sistema funciona con el
enlace caído: la transcripción, la detección, la alerta de seguridad y el parser
son locales.

El LLM es **opcional y fuera del camino crítico**: el compose lo deja
habilitado para demos (`LLM_HABILITADO=1`). Si Ollama no está, el context builder
y `scripts/preguntar.py` caen al texto determinista con las citas. El parte nunca
se arma ni se confirma con el LLM.

### Hardware de pruebas

- **Desktop:** Fedora 44, CPU AMD Ryzen 5 5600 (6 núcleos / 12 hilos), 15 GB de
  RAM, GPU AMD Radeon RX 6700 XT con 12 GB de VRAM.
- **Contenedor del agente:** 3,5 vCPU / 7 GB; PostgreSQL: 0,5 vCPU / 1 GB.
- **ASR y embeddings:** CPU, dentro del contenedor.
- **LLM opcional:** GPU, servido por Ollama en el host.

### Consumo y latencia

- **Tokens de LLM:** 0 en el camino crítico. La transcripción y los embeddings
  no se facturan por token; se reporta 0 en `sistema/metricas`. Con el LLM
  opcional, el cliente devuelve `prompt_eval_count`/`eval_count` reales.
- **Costo:** USD 0 (todo local; no se usan modelos en la nube).
- **Latencia medida en desarrollo:**

| Tarea | Entrada | Tiempo | Tokens salida | Tok/s |
|---|---:|---:|---:|---:|
| ASR `small` int8 | nota de 7–16 s | 2,3–3,1 s | 0 | — |
| Parser determinista | texto de la nota | < 1 ms | 0 | — |
| `ministral-3:3b` (GPU) | consulta + 3 fragmentos | 1,2–1,9 s | 91–131 | 68–74 |
| `qwen3.5:9b` | misma consulta | ~38 s | 65 | 1,7 |
| `ornith-1.5:9b` | misma consulta | ~38 s | 84 | 2,2 |

La suite `scripts/evaluar_sistema.py` mide aciertos por campo, latencia por
etapa (descarga, ASR, parser, total) y costo sobre `/api/verdad`.

### Conclusión

Se eligió un pipeline local y determinista porque el anexo exige que la
transcripción sea local y porque el hardware disponible para la corrida no
garantiza GPU para todos los componentes. El ASR y los embeddings corren en CPU
dentro del contenedor; un LLM chico en ese camino agregaría latencia y
variabilidad sin mejorar el parte: las notas siguen plantillas acotadas y un
parser validado contra `FilaParte` es más preciso y auditable. LangChain se usa
en el context builder y el RAG; `ministral-3:3b` queda como LLM opcional para
contexto y consultas, y se ejecuta en la GPU del host, habilitado en el compose
para demos y fuera del camino crítico.
