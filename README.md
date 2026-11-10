# Nicolas-Scaramella-Entrega · PIA-3

Sistema de **parte de recorrida por voz** y **detección en planta** para la planta
simulada PIA-3 de la Academia Novit 2026.

Se levanta al lado de la planta, en la red `planta-lan`, y habla por MQTT usando
el contrato `planta_contrato`.

## Cómo levantarlo

```bash
# 1. La planta tiene que estar arriba (desde el repo academia2026-tp)
cd ../academia2026-tp
docker compose up -d --build

# 2. Este sistema
cd ../Nicolas-Scaramella-Entrega
docker compose up -d --build
```

Visores: <http://localhost:8080> (3D) y <http://localhost:8081> (2D).
Ahí se ve el latido de este sistema y los eventos que publica.

### Postgres y el corrector: no los corras juntos

La planta y tu sistema comparten la red `planta-lan`. El corrector levanta su
propio proyecto (`alumno-nicolas-scaramella-entrega`) con un servicio `postgres`
que tiene el mismo nombre que el de tu `docker compose up`. Si dejás tu stack
arriba mientras corre el corrector, el agente puede resolver `postgres` a la
base equivocada y fallar con `relation "outbox" does not exist` o quedar mudo.

Antes de correr el corrector:

```bash
cd /home/nscaramella/AcademiaNovit/Nicolas-Scaramella-Entrega
docker compose down
docker ps --format '{{.Names}}' | grep -E 'entrega|alumno' || true
```

Tiene que quedar vacío (o solo el `alumno` si el corrector ya lo levantó). Al
terminar el corrector podés volver a levantar tu stack con `docker compose up -d`.

## Qué hace

- Escucha `planta/recorridas`, baja el audio y las fotos, y transcribe el audio
  **localmente** con `faster-whisper`.
- La foto queda asociada a la fila del parte interno (`partes.filas`); el
  `Escalado` incluye en su resumen las fotos y la tendencia de las últimas horas.
- Arma el parte con `FilaParte` (equipo, variable, valor, unidad, observación),
  resuelve nombres informales, unidades y rangos históricos, y lo manda a la
  tablet del operador para confirmar o corregir.
- Genera `EventoSistema` (`SinNovedad` / `Escalado`) por equipo y por nota
  confirmada, y eventos por desvíos sostenidos de sensores.
- Si una nota no trae valores numéricos (por ejemplo, solo "parada, en
  reserva"), no se pide una confirmación imposible: se registra con un aviso y
  se publican los eventos según las observaciones.
- Si falta el audio o la transcripción falla, la nota queda en estado `cortado`
  y se avisa en la tablet; no se confunde con una nota válida sin valores.
- Las notas `VIVO-…` (grabadas en vivo) se registran como `vivo` y no piden
  borrador, porque no tienen parte esperado.
- Detecta condiciones inseguras S1–S4 en código, sin nube, y publica
  `AlertaSeguridad` y el aviso en la tablet.
- Publica el latido `sistema/estado` cada 30 s y telemetría en `sistema/metricas`.
- Con el enlace caído sigue publicando en la red local, pero deja la outbox
  **pendiente de sincronizar** y la informa en el latido; al volver el enlace
  reintenta en orden y sin duplicar (los ids del contrato son idempotentes).
- Expone tools de solo lectura por MCP y un RAG sobre el corpus en pgvector.

## Conexión con el visor

El visor no se conecta a un modelo: muestra lo que publica este sistema.

- **“Sistema del cursante · en vivo”**: sale del latido `sistema/estado` cada
  30 s. Si no hay latido, el visor dice “sin conexión”. El latido informa
  `pendientes_sincronizar` mientras el enlace está caído.
- **Tabla “Modelo / Entrada / Salida / tok/s”**: sale de `sistema/metricas`.
  Incluye el ASR/parser y el consumo acumulado del LLM (`ministral-3:3b`) que
  dejan `scripts/preguntar.py` y `scripts/comparar_llm.py` en PostgreSQL. Si
  nunca se usó el LLM, la tabla muestra los modelos locales con 0 tokens.

No hace falta NVIDIA ni `build.nvidia.com`: la transcripción y los embeddings
corren en CPU dentro de este contenedor.

## Memoria y retención

Por cada nota se persiste en PostgreSQL:

- el mensaje de tablet enviado (`mensajes_tablet`),
- el borrador y las ambigüedades (`partes`),
- el intento y el estado del parte,
- los eventos publicados (`eventos`).

Se conserva durante la corrida y hasta 30 días para auditoría. La política es
no guardar audios fuera del volumen de la planta y no sacar datos de
`planta-lan`. El estado pendiente sobrevive a un reinicio porque está en
PostgreSQL, no en memoria.

## Control y presupuesto

- **Timeout global por nota**: `TIMEOUT_NOTA_S` (120 s). Si se agota, el parte
  queda en estado `timeout` y el worker sigue con la próxima nota.
- **Presupuesto de pasos**: `MAX_PASOS` (8). En esta entrega el pipeline tiene
  3 pasos (audio, ASR, parser).
- **Presupuesto de tokens**: `PRESUPUESTO_TOKENS` (0 = sin límite). El camino
  crítico (ASR, parser, detección, tablet) no usa LLM: los tokens son 0. Un LLM
  local opcional puede redactar contexto y consultas del RAG, e informa sus
  tokens reales.
- **Condiciones de corte**: sin audio, sin transcripción o con error de
  contrato, el parte no se confirma y se registra el motivo.

## RAG vs API/SQL

- **API/SQL**: equipos, límites de alarma, stock, costos, historial de sensores,
  historial de órdenes y catálogo de tareas. Son datos estructurados y
  deterministas.
- **RAG**: manuales, buenas prácticas y contrato, con cita de sección. La
  revisión vencida (TX350-C) se filtra por `vigente=false` y se excluyen las
  secciones de otros modelos/plantas (TX-250, TX-500, FC-24, FC-96, PIA-1,
  PIA-2). Se usa búsqueda híbrida: BM25 gana hit@5, pero el híbrido evita la
  revisión vencida y baja los distractores (ver `evaluacion/resultados.md`).

## Seguridad del RAG

El RAG es asesor: no arma ni confirma el parte. Para que no invente:

- **Guardia de citas:** el LLM devuelve JSON con `respuesta`, `citas` y
  `suficiente`. Si una cita no está entre los fragmentos recuperados, si no hay
  citas o si `suficiente=false`, se descarta la respuesta y se muestra la
  evidencia.
- **Umbral de evidencia:** `RAG_MIN_SCORE=0.82`. Si la consulta no tiene un
  fragmento con score vectorial suficiente, no se llama al LLM y se responde
  “No encontré evidencia suficiente en el corpus”.
  Medido con las 71 preguntas: 0 quedan sin evidencia; 4 de 4 consultas fuera
  del corpus (capital de Francia, pizza, mundial, MQTT) se rechazan.
- **Formato JSON** en Ollama (`format: "json"`), temperatura 0.
- **La pregunta y los fragmentos son datos, no instrucciones**: el system prompt
  no cambia por lo que digan.

Prueba:

```bash
docker compose run --rm agente python scripts/preguntar.py \
  "¿Qué se hace con la cola cuando se corta el enlace?"   # responde con cita

docker compose run --rm agente python scripts/preguntar.py \
  "¿Cuál es la capital de Francia?"                       # no hay evidencia
```

La guardia verifica que las citas existan, no que la interpretación sea
correcta. Para los valores y las decisiones sigue mandando el parser
determinista, no el LLM.

## Estructura

```text
src/sistema/
├── main.py            orquestador MQTT/tablet/worker
├── asr.py             faster-whisper local
├── numeros.py         números hablados
├── parser.py          nota → FilaParte
├── seguridad.py       S1–S4 en código
├── deteccion.py       SinNovedad / Escalado
├── tablet.py          borradores, preguntas y correcciones
├── db.py              PostgreSQL + pgvector
├── publicacion.py     validación + outbox
├── tools.py           tools de solo lectura
├── mcp_server.py      servidor MCP
├── contexto.py        context builder (LangChain + LLM opcional)
├── llm.py             cliente Ollama opcional
└── rag/               ingesta, búsqueda híbrida y evaluación
```

## LLM local opcional

El sistema no necesita un LLM para funcionar: el parser, la detección y la
tablet son deterministas. Opcionalmente, un modelo local servido por Ollama
redacta el contexto de una anomalía o responde consultas sobre el corpus:

```bash
# En el host, una sola vez: que Ollama escuche a Docker.
sudo systemctl edit ollama   # OLLAMA_HOST=0.0.0.0:11434

# El entrypoint resuelve host.docker.internal al gateway real de planta-lan
# (la subred cambia si se recrea la red). Solo hace falta que Ollama escuche
# en 0.0.0.0:11434. Variables: LLM_HABILITADO=1, LLM_MODEL=ministral-3:3b,
# LLM_BASE_URL=http://host.docker.internal:11434.

docker compose run --rm agente python scripts/preguntar.py \
  "¿Qué se hace con la cola cuando se corta el enlace?"

# Comparar modelos con la misma consulta y los mismos fragmentos
docker compose run --rm -e LLM_HABILITADO=1 agente \
  python scripts/comparar_llm.py "¿Qué se hace con la cola cuando se corta el enlace?" \
  --modelos ministral-3:3b qwen3.5:9b ornith-1.5:9b --verboso
```

Se pasan solo los **3 fragmentos mejor rankeados** y se le pide al modelo que
cite únicamente los que usa. `LLM_MODELOS_PERMITIDOS` es una allowlist: si
Ollama tiene otros modelos instalados, el sistema igual **solo** puede llamar a
los que estén ahí (`ministral-3:3b` por defecto). Si Ollama no está, el modelo
no está descargado o la llamada falla, el script muestra la evidencia recuperada
y el flujo normal sigue igual. El compose lo deja habilitado
(`LLM_HABILITADO=1`) para demos, pero el flujo del parte no lo usa: si Ollama no
está, los scripts caen al texto determinista.

Medición local: `ministral-3:3b` responde en ~1–2 s (~70 tok/s), mientras que
los 9B instalados tardan ~38 s (~2 tok/s) por falta de RAM/GPU. Por eso la
allowlist deja solo `ministral-3:3b`. La tabla completa está en
`evaluacion/resultados.md`.

### Cómo ver el consumo del LLM en el visor

1. Levantá la planta y el agente:

   ```bash
   docker compose up -d
   ```

2. Corré una consulta con el LLM:

   ```bash
   docker compose run --rm -e LLM_HABILITADO=1 agente \
     python scripts/preguntar.py "¿Qué se hace con la cola cuando se corta el enlace?"
   ```

   Al final tiene que decir `Generado por: ministral-3:3b` y los tokens.

3. El script guarda los tokens en PostgreSQL. En el próximo latido (30 s), el
   agente publica `sistema/metricas` con la fila `ministral-3:3b`.

4. Abrí el visor en <http://localhost:8081> (o `:8080`) y mirá la tabla de
   consumo. Si todavía no aparece, esperá un latido más.

Para verificarlo sin el visor:

```bash
docker compose exec -T postgres psql -U sistema -d sistema -c \
  "select modelo, sum(tokens_entrada) as entrada, sum(tokens_salida) as salida,
          round(avg(tokens_por_segundo)::numeric,1) as tok_s
   from consumo group by modelo order by modelo;"

docker exec planta-broker-1 mosquitto_sub -t sistema/metricas -C 1
```

El consumo se acumula: cada consulta suma una llamada y actualiza el promedio
de tok/s.

## Variables

Ver `.env.example`. Las principales:

| Variable | Default | Qué es |
|---|---|---|
| `SISTEMA_NOMBRE` | `Nicolas-Scaramella` | Nombre que aparece en el latido |
| `ASR_MODEL` | `small` | Modelo local de transcripción |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Embeddings del RAG |
| `TIMEOUT_NOTA_S` | `120` | Timeout global por nota |
| `MAX_INTENTOS` | `3` | Intentos de borrador/pregunta |
| `LLM_HABILITADO` | `1` en compose (`0` en config) | Habilita el LLM local opcional para consultas; no participa del parte |
| `LLM_MODEL` | `ministral-3:3b` | Modelo de Ollama |
| `LLM_MODELOS_PERMITIDOS` | `ministral-3:3b` | Allowlist separada por comas; el resto se rechaza |
| `LLM_BASE_URL` | `http://host.docker.internal:11434` | Ollama visto desde el contenedor |
| `LLM_TIMEOUT_S` | `60` | Timeout de la llamada al LLM |
| `LLM_MAX_TOKENS` | `200` | Máximo de tokens de salida |

## Tests

```bash
docker compose run --rm agente pytest
```

## Evaluación

```bash
# RAG: hit@k, recall@k y comparación con BM25
docker compose run --rm agente python scripts/evaluar_rag.py

# Parte: aciertos por campo contra /api/verdad (planta en modo desarrollo)
docker compose run --rm agente python scripts/evaluar_parte.py

# Suite end-to-end: aciertos por campo, latencia por etapa y costo
docker compose run --rm agente python scripts/evaluar_sistema.py
```

`evaluar_sistema.py` corre descarga → ASR → parser sobre las notas de
`/api/verdad` y reporta aciertos, latencia media/p95 por etapa y costo
(USD 0 para los modelos locales). Es la suite que se usa para comparar
cambios de ASR o de parser sin depender del flujo MQTT.

Antes de correr el corrector, bajá este stack con `docker compose down`: el
corrector levanta su propio `postgres` en `planta-lan` y dos servicios con el
mismo nombre se pisan (el agente puede terminar conectado a la base equivocada).

## Planta vs nube

Todo el camino crítico corre en la PC de planta (`planta-lan`, 4 CPU / 8 GB):

- transcripción local con `faster-whisper` `small` (ASR; no es un LLM y no
  usa la nube);
- detector de anomalías y de condiciones inseguras en código;
- parser determinista del parte;
- PostgreSQL + pgvector para estado, memoria y RAG.

`ministral-3:3b` **no transcribe audio**: se usa para consultas y contexto
(texto y fotos) en el host, con Ollama, y queda fuera de la transcripción y del
camino crítico del parte.

No hay componentes en la nube en la Entrega 1. Los modelos locales se descargan
durante el build de la imagen; en runtime la red de planta no tiene internet. El
enlace solo se usa para el latido informativo (`enlace_ok`) y para la
sincronización diferida de la cola.

El LLM opcional (`ministral-3:3b`) corre en la GPU del host vía Ollama. El
compose lo deja habilitado para demos (`LLM_HABILITADO=1`), pero no participa del
camino crítico: se usa para consultas al RAG y contexto, nunca para armar o
confirmar el parte. Por eso la entrega funciona igual sin GPU y sin Ollama.
