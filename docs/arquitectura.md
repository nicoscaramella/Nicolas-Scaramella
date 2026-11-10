# Arquitectura

## Servicios

```text
planta-lan (red externa, sin internet)
├── broker        (planta)
├── sim           (planta)
├── enlace        (planta, proxy :3128)
├── postgres      (este sistema, pgvector)
└── agente        (este sistema)
```

El agente corre en la PC de planta: label `academia.planta: pc`, límite conjunto
de 4 CPU / 8 GB (3.5 + 0.5 y 7 + 1). Sale a internet solo por `enlace:3128`
cuando hace falta; el camino crítico no depende de internet.

## Componentes

| Módulo | Responsabilidad |
|---|---|
| `asr.py` | `faster-whisper` local, CPU, int8 |
| `numeros.py` | Números hablados y unidades |
| `parser.py` | Nota → `FilaParte[]`, nombres, variables y observaciones |
| `seguridad.py` | S1–S4 en código |
| `deteccion.py` | `SinNovedad`/`Escalado`, límites y sensores sostenidos |
| `tablet.py` | Borradores, preguntas y lectura de respuestas/correcciones |
| `db.py` | PostgreSQL: partes, tablet, eventos, outbox, RAG |
| `publicacion.py` | Validación Pydantic + outbox + MQTT |
| `tools.py` / `mcp_server.py` | Tools de solo lectura y MCP |
| `rag/` | Ingesta, búsqueda híbrida y evaluación |
| `contexto.py` | Context builder con LangChain |
| `main.py` | Orquestador y workers |

## Flujo

```text
NotaRecorrida
  → descargar audio
  → faster-whisper
  → detector de seguridad (código)
  → parser determinista
  → pregunta (si hay ambigüedad) / borrador en tablet
  → RespuestaOperador
  → confirmación / corrección
  → EventoSistema por equipo
```

## Persistencia

- `partes`: estado del parte por nota.
- `mensajes_tablet`: mensajes enviados y su intento.
- `eventos`: eventos idempotentes.
- `outbox`: publicaciones pendientes (para `pendientes_sincronizar`).
- `rag_chunks`: fragmentos + metadatos + `vector(384)`.

## Memoria

Se recuerda, por nota, el mensaje de tablet, el borrador, las ambigüedades y el
intento. La política es conservar el estado durante la corrida y 30 días para
auditoría; los datos de planta no salen de `planta-lan`. No se guardan audios
fuera del volumen de la planta.

## RAG vs API/SQL

- **API/SQL**: equipos, límites de alarma, stock, costos, historial de sensores,
  historial de órdenes y catálogo de tareas. Son datos estructurados y no deben
  salir del RAG.
- **RAG**: manuales, buenas prácticas y contrato, con cita de sección. La
  revisión vencida (TX350-C) se filtra con `vigente=false`.
