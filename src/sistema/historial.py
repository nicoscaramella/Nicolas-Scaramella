"""Rango histórico de 45 días para confirmar valores de presión."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from .planta_api import PlantaAPI

log = logging.getLogger(__name__)

A_KG = {"kg/cm2": 1.0, "psi": 1 / 14.2233, "bar": 1.01972}
SENSOR = {
    "presion_descarga_local": "presion_descarga",
    "presion_diferencial": "presion_diferencial",
}

_CACHE: dict[tuple[str, str], tuple[float, tuple[float, float] | None]] = {}
_TTL = 300.0


def rango_historico(
    api: PlantaAPI, tag: str, variable: str, ts: str
) -> tuple[float, float] | None:
    sensor = SENSOR.get(variable)
    if sensor is None:
        return None
    clave = (tag, sensor)
    ahora = time.monotonic()
    if clave in _CACHE and ahora - _CACHE[clave][0] < _TTL:
        return _CACHE[clave][1]
    try:
        hasta = datetime.fromisoformat(ts)
        desde = hasta - timedelta(days=45)
        datos = api.historian(tag, sensor, desde.isoformat(), hasta.isoformat())
        valores = [float(d["valor"]) for d in datos if d.get("valor") is not None]
        rango = (min(valores), max(valores)) if valores else None
    except Exception:
        log.exception("No se pudo leer el historian de %s/%s", tag, sensor)
        rango = None
    _CACHE[clave] = (ahora, rango)
    return rango


def aviso_fuera_de_rango(api: PlantaAPI, fila: dict, ts: str) -> str | None:
    variable = fila.get("variable")
    valor = fila.get("valor")
    if variable not in SENSOR or valor is None:
        return None
    rango = rango_historico(api, fila["tag"], variable, ts)
    if not rango:
        return None
    en_kg = float(valor) * A_KG.get(fila.get("unidad") or "kg/cm2", 1.0)
    minimo, maximo = rango
    # Margen amplio: no convertir una variación normal en una pregunta de más.
    if en_kg < minimo * 0.8 or en_kg > maximo * 1.2:
        return (
            f"{fila['tag']} {variable} = {valor} {fila.get('unidad') or ''} "
            f"está fuera del rango histórico ({minimo:.1f} a {maximo:.1f} kg/cm2). "
            "Confirmá si el valor es correcto."
        )
    return None
