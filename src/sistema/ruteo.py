"""Ruteo por tipo de mensaje entre la planta y el agente.

La planta publica todo por MQTT y el agente recibe un solo callback. Este
módulo decide a qué flujo va cada mensaje, sin tocar red ni base.

Los cinco tipos del anexo:

- ``SEGURIDAD``: derivado de una nota o lectura (no tiene tópico propio);
- ``PARTE``: ``NotaRecorrida`` (``planta/recorridas``);
- ``SENSOR``: ``LecturaSensor`` (``planta/sensores/{tag}/{variable}``);
- ``RESPUESTA``: ``RespuestaOperador`` a la tablet (``planta/respuestas``);
- ``CIERRE``: ``NotaCierre`` del técnico (``planta/cierres``).

Además, ``ENERGIA`` (``EstadoEnergia``): el corte de luz mata la PC de planta
y el sistema tiene que saberlo para sobrevivir sin duplicar.
"""

from __future__ import annotations

SEGURIDAD = "seguridad"
PARTE = "parte"
SENSOR = "sensor"
RESPUESTA = "respuesta"
CIERRE = "cierre"
ENERGIA = "energia"

_TOPICOS = {
    "planta/recorridas": PARTE,
    "planta/respuestas": RESPUESTA,
    "planta/cierres": CIERRE,
    "planta/energia": ENERGIA,
}

_PREFIJO_SENSORES = "planta/sensores/"


def clasificar(topico: str) -> str | None:
    """Devuelve el tipo de mensaje del tópico, o ``None`` si no es nuestro."""
    if topico in _TOPICOS:
        return _TOPICOS[topico]
    if topico.startswith(_PREFIJO_SENSORES) and len(topico) > len(_PREFIJO_SENSORES):
        return SENSOR
    return None


def energia_disponible(payload: dict) -> bool:
    """Interpreta un ``EstadoEnergia``: ``True`` si la planta tiene energía.

    Sin el campo se asume que hay energía: el sistema no inventa un corte.
    """
    return bool(payload.get("hay_energia", True))
