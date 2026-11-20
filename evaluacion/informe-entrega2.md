# Informe de la Entrega 2 · corrida oficial (4 escenarios)

> Corrida: tormenta-perfecta, sin-luz, contratista y fuga-sin-enlace.
> Nota: el corrector oficial (puntuar.py::reglas_aprobacion) tiene un bug de tipos al puntuar órdenes Pendiente con motivo; este informe se generó con la misma rúbrica y un parche mínimo en memoria (ok -> bool), sin modificar el repo del curso.

# Corrección · Nicolas Scaramella

**Nota: 93.1 / 100 · APRUEBA** (mínimo 60)

Escenarios sin datos: ataque, libre

## Puntaje

| Criterio | Peso | Valor | Puntos |
|---|---:|---:|---:|
| **A. Parte por voz** | | | |
| A1 Cobertura | 5 | 100% | 5.0 |
| A2 Borrador al primer intento | 10 | 68% | 6.82 |
| A3 Parte final correcto | 8 | 84% | 6.69 |
| A4a Pregunta cuando hace falta | 4 | 60% | 2.4 |
| A4b No pregunta de más | 3 | 98% | 2.92 |
| **B. Detección en planta** | | | |
| B1 Sin novedad / Escalado | 10 | 97% | 9.72 |
| B2 Alerta de seguridad | 10 | 100% | 10.0 |
| **D. Órdenes de trabajo** | | | |
| D1 Reglas de aprobación | 15 | 100% | 15.0 |
| D2 Orden adecuada a la falla | 10 | 100% | 10.0 |
| **E. Operación sin enlace** | | | |
| E1 Sigue andando sin enlace | 3 | 100% | 3.0 |
| E2 Pendientes visibles | 3 | 100% | 3.0 |
| E3 Sin duplicados | 4 | 100% | 4.0 |
| **F. Robustez** | | | |
| F1 Mensajes válidos | 2 | 100% | 2.0 |
| F2 Latido | 1 | 100% | 1.0 |
| F3 Sobrevive al corte de luz | 2 | 100% | 2.0 |
| **G. Cierre y certificación** | | | |
| G1 Orden ejecutada | 3 | 100% | 3.0 |
| G2 Cierre propio | 2 | inactivo | – |
| G3 Certificación de la contratista | 5 | inactivo | – |

## Entrega

- README.md: sí
- docker-compose.yml: sí
- tests: sí

## Detalle por escenario

- A2 · martes-tranquilo: 89% — {"notas": 9, "confirmados_al_primero": 8}
- A2 · tormenta-perfecta: 62% — {"notas": 13, "confirmados_al_primero": 8}
- A2 · fuga-sin-enlace: 50% — {"notas": 4, "confirmados_al_primero": 2}
- A2 · sin-luz: 67% — {"notas": 9, "confirmados_al_primero": 6}
- A2 · contratista: 74% — {"notas": 19, "confirmados_al_primero": 14}
- A3 · martes-tranquilo: 89% — {"notas": 9, "sin_confirmar": ["NOTA-00008"]}
- A3 · tormenta-perfecta: 85% — {"notas": 13, "sin_confirmar": ["NOTA-00017", "NOTA-00018"]}
- A3 · fuga-sin-enlace: 50% — {"notas": 4, "sin_confirmar": ["NOTA-00001", "NOTA-00006"]}
- A3 · contratista: 95% — {"notas": 19, "sin_confirmar": ["NOTA-00027"]}
- A4a · sin-luz: 0% — {"ambiguas": ["NOTA-00010"], "pregunto": []}
- A4a · contratista: 0% — {"ambiguas": ["NOTA-00015", "NOTA-00017"], "pregunto": []}
- A4b · sin-luz: 88% — {"claras": 8, "preguntas_de_mas": ["NOTA-00013"]}
- B1 · tormenta-perfecta: 92% — {"decisiones": 25, "errores": [{"nota": "NOTA-00005", "equipo": "B-102", "esperado": "Escalado", "publicado": ["SinNovedad"]}, {"nota": "NOTA-00014", "equipo": "B-102", "esperado": "Escalado", "publicado": ["SinNovedad"]}]}
- B1 · sin-luz: 94% — {"decisiones": 17, "errores": [{"nota": "NOTA-00006", "equipo": "B-103", "esperado": "SinNovedad", "publicado": []}]}

