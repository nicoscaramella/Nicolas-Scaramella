# Spec · Flujo del parte de recorrida por voz

## Entradas

- `planta/recorridas` → `NotaRecorrida` con `id`, `ts`, `operador`, `audio_url`, `fotos`.
- `planta/respuestas` → `RespuestaOperador` con `mensaje_id`, `texto`, `audio_url`.
- `GET /api/planta` → equipos, nombres informales, sensores y límites.
- `GET /api/historian/{tag}/{variable}` → 45 días de historial.

## Salidas

- `sistema/tablet` → `MensajeTablet` con borrador, pregunta o aviso.
- `sistema/eventos` → `EventoSistema` (`SinNovedad`, `Escalado`, `AlertaSeguridad`).
- `sistema/estado` → `EstadoSistema` cada 30 s.
- `sistema/metricas` → `ConsumoTokens` (telemetría opcional).

## Estados del parte

```text
nueva
  ├─ (audio) → transcribiendo
  │      ├─ condición insegura → seguridad (AlertaSeguridad + aviso)
  │      ├─ ambigüedad de equipo → esperando_equipo
  │      ├─ ambigüedad de valor  → esperando_valor
  │      └─ borrador             → esperando_borrador
  └─ nota duplicada → se ignora
esperando_equipo → (respuesta) → borrador
esperando_valor  → (respuesta) → borrador
esperando_borrador
  ├─ confirmación → confirmado → eventos
  ├─ corrección   → esperando_borrador (intento + 1)
  └─ no entendí   → esperando_borrador (intento + 1, máx. 3)
sin valores numéricos → registrado (aviso sin respuesta) → eventos
```

Un parte cuyas filas quedan todas con `valor=null` no se manda como borrador:
el operador virtual no tendría nada que confirmar y respondería "¿Confirmar
qué?", entrando en un loop. Se registra con un aviso `espera_respuesta=false` y
se publican los eventos según las observaciones.

## Reglas

1. **Una fila por equipo y variable**. Si la nota mezcla equipos, se corta por
   mención de equipo y cada tramo se parsea por separado.
2. **Hora = `ts` de la nota**, no el reloj de la máquina.
3. **Nombres informales** contra `/api/planta`. Si el nombre no alcanza
   ("la bomba", "el filtro"), se manda una pregunta con opciones.
4. **Unidades**:
   - "kilos"/"kilogramos" → kg/cm²;
   - B-101 en kg/cm², B-102 en psi, B-103 en bar;
   - "libras" → psi; "bares" → bar; "grados" → °C; "metros" → m.
5. **Ambigüedad de valor**: un diferencial dicho "dieciocho" en lugar de
   "uno ocho" se pregunta y se interpreta como 1.8 (una décima).
6. **Rango histórico**: si un valor de presión queda fuera del rango de 45 días,
   se pide confirmación antes de guardar.
7. **Confirmación**: el borrador se manda con `espera_respuesta=true`; el
   operador confirma o corrige en lenguaje de campo. El parte pasa a confirmado
   solo con una confirmación explícita.
8. **Condición insegura**: S1 (agua a presión), S2 (gas), S3 (humo/fuego), S4
   (persona lesionada) se detectan en código, sin nube, y se publican en menos
   de 30 s reales con un aviso `espera_respuesta=false`.
9. **Detección**: por cada equipo de la nota confirmada, un evento. Una
   observación no vacía distinta de "parada, en reserva" o "parada por
   mantenimiento" es anomalía. También lo es una presión fuera de los límites de
   alarma del sensor.
10. **Notas `VIVO-…`**: no tienen parte esperado. Se registran con estado
    `vivo` y no se manda borrador, para no pedirle al operador una confirmación
    que no tiene verdad de campo.
11. **Idempotencia**: el id del evento es determinista
    (`EV-{nota_id}-{tag}`); publicar dos veces el mismo id no duplica.

## Criterios de aceptación

- [ ] Una nota de `martes-tranquilo` produce borrador, el operador confirma y se
      publica `SinNovedad` por equipo.
- [ ] Una nota ambigua genera una pregunta y no una pregunta de más en las notas
      claras.
- [ ] En `fuga-sin-enlace` sale `AlertaSeguridad` y aviso en tablet en < 30 s
      reales, aun con el enlace caído.
- [ ] Todos los mensajes publicados validan contra `planta_contrato`.
- [ ] El latido se publica cada 30 s.
