# Arquitectura

## Servicios

```text
planta-lan (red externa, internal: sin internet)
├── broker        (planta)
├── sim           (planta)
├── enlace        (planta, proxy :3128)
├── db            (este sistema, PostgreSQL + pgvector)
└── agente        (este sistema)

interfaz (red bridge normal, fuera de planta-lan)
└── central       (publica el 8200 → agente:8200)
```

Los servicios de planta (`db` y `agente`) corren en la PC de planta: label
`academia.planta: pc` y límite conjunto de 4 CPU / 8 GB (0.5 + 3.5 y 1 + 7).
Salen a internet solo por `enlace:3128`. Como `planta-lan` es `internal: true`
no se pueden publicar puertos desde ahí: la **Central** (interfaz humana) es un
servicio aparte (`central`), también en `planta-lan` para llegar al agente, y
en una red normal para publicar el panel en el host. No lleva el label `pc`
porque no vive en la PC de planta.

## Componentes

| Módulo | Responsabilidad |
|---|---|
| `asr.py` | `faster-whisper` local, CPU, int8 |
| `numeros.py` | Números hablados y unidades |
| `parser.py` | Nota → `FilaParte[]`, nombres, variables y observaciones |
| `seguridad.py` | S1–S4 en código |
| `deteccion.py` | `SinNovedad`/`Escalado`, límites, sensores sostenidos y colmatación lenta de filtros |
| `ruteo.py` | Dispatcher: seguridad, parte, sensor, respuesta, cierre, energía |
| `tablet.py` | Borradores, preguntas y lectura de respuestas/correcciones |
| `db.py` | PostgreSQL: partes, tablet, eventos, órdenes, cierres, decisiones, outbox, visión y RAG |
| `publicacion.py` | Validación Pydantic + outbox + MQTT |
| `ordenes/reglas.py` | **Función pura** con las 5 reglas de aprobación |
| `ordenes/estado.py` | Máquina de estados y **única escritura** de órdenes |
| `ordenes/causas.py` | Catálogo MBP-4 §6 con citas y patrones del historial |
| `ordenes/analisis.py` | Evidencia → causas → borrador de `OrdenSistema` |
| `ordenes/repositorio.py` | Recuperación de órdenes tras el corte de luz |
| `ordenes/workflow.py` | Reintentos, deadlines y detección de loops |
| `ordenes/cierre.py` | `NotaCierre` → parte de cierre y comparación con la orden |
| `ordenes/certificacion.py` | Habilita y monto con CT-SVP-2025 |
| `vision/nvidia.py` | Conector de visión de build.nvidia.com |
| `vision/proveedor.py` | Heurística local + cola cuando no hay enlace |
| `central/servicio.py` | Decisiones del planificador, supervisor e inspector |
| `central/api.py` | Panel y API HTTP `:8200` (solo biblioteca estándar) |
| `central/cli.py` | CLI de la Central |
| `central/proxy.py` | Publica el `:8200` fuera de `planta-lan` |
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

Entrega 2, del evento a la orden:

```text
Escalado (parte o sensor)
  → evidencia: parte confirmado + fotos + tendencia del historian
  → causas ordenadas (MBP-4 §6 + historial §6.14) y paso revisor
  → borrador de OrdenSistema
  → reglas.decidir() (pura)
      ├─ Aprobada            → cuadrilla → cierre
      └─ PendienteAprobacion → Central (planificador)
  → NotaCierre → parte de cierre → comparación → Ejecutada
      ├─ propio      → supervisor → Cerrada
      └─ contratista → inspector → Certificada (habilita + monto) u Observada
```

La aprobación es **solo humana** cuando las reglas no alcanzan. `estado.py` es
la única vía de escritura: valida la transición, guarda el checkpoint en
Postgres y publica; el id es idempotente por equipo + tareas.

## Persistencia

- `partes`: estado del parte por nota.
- `mensajes_tablet`: mensajes enviados y su intento.
- `eventos`: eventos idempotentes.
- `ordenes`: estado, payload y `correlation_id` de cada orden (checkpoint).
- `cierres`: `NotaCierre` cruda, parte de cierre y diferencias.
- `decisiones`: auditoría de la Central (quién decidió y por qué).
- `vision_pendientes`: fotos cuyo análisis espera el enlace.
- `outbox`: publicaciones pendientes (para `pendientes_sincronizar`).
- `rag_chunks`: fragmentos + metadatos + `vector(384)`.

## Memoria

Se recuerda, por nota, el mensaje de tablet, el borrador, las ambigüedades y el
intento. Para las órdenes se conserva el estado, el `correlation_id`, el cierre
y las decisiones humanas. La política es conservar el estado durante la corrida
y 30 días para auditoría; los datos de planta no salen de `planta-lan`. No se
guardan audios fuera del volumen de la planta.

## RAG vs API/SQL

- **API/SQL**: equipos, límites de alarma, stock, costos, historial de sensores,
  historial de órdenes y catálogo de tareas. Son datos estructurados y no deben
  salir del RAG.
- **RAG**: manuales, buenas prácticas y contrato, con cita de sección. La
  revisión vencida (TX350-C) se filtra con `vigente=false`.
