"""Máquina de estados de órdenes: **la ÚNICA escritura sobre órdenes**.

Cualquier cambio de estado (crear, aprobar, rechazar, ejecutar, cerrar,
certificar) pasa por este módulo: valida la transición, valida el contrato y
guarda el checkpoint en Postgres *antes* de publicar. Así, si el contenedor se
apaga de golpe (corte de luz de ``sin-luz``), la orden vuelve con el mismo id
y el mismo estado, sin duplicarse.

El id es idempotente y estable por equipo + tareas: un evento nuevo del mismo
trabajo se agrega a la orden abierta en vez de crear otra.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from planta_contrato import OrdenSistema

from .. import db

BORRADOR = "Borrador"
PENDIENTE = "PendienteAprobacion"
APROBADA = "Aprobada"
RECHAZADA = "Rechazada"
EJECUTADA = "Ejecutada"
OBSERVADA = "Observada"
CERRADA = "Cerrada"
CERTIFICADA = "Certificada"

INICIALES = {BORRADOR, PENDIENTE, APROBADA}
TERMINALES = {RECHAZADA, CERRADA, CERTIFICADA}
REQUIEREN_MOTIVO = {PENDIENTE, RECHAZADA, OBSERVADA}

TRANSICIONES: dict[str, set[str]] = {
    BORRADOR: {PENDIENTE, APROBADA},
    PENDIENTE: {APROBADA, RECHAZADA},
    APROBADA: {EJECUTADA},
    EJECUTADA: {CERRADA, OBSERVADA, CERTIFICADA},
    OBSERVADA: {CERTIFICADA},
    RECHAZADA: set(),
    CERRADA: set(),
    CERTIFICADA: set(),
}


class TransicionInvalida(ValueError):
    """La orden no puede pasar de un estado a otro."""


def validar_transicion(desde: str | None, hacia: str) -> None:
    if desde is None:
        if hacia not in INICIALES:
            raise TransicionInvalida(f"una orden no puede nacer en {hacia}")
        return
    if hacia not in TRANSICIONES.get(desde, set()):
        raise TransicionInvalida(f"{desde} → {hacia} no es una transición válida")


def validar_decision(hacia: str, motivo: str | None) -> None:
    """Pendiente, Rechazada y Observada siempre llevan motivo."""
    if hacia in REQUIEREN_MOTIVO and not (motivo or "").strip():
        raise ValueError(f"{hacia} exige un motivo")


def id_de_orden(equipo: str, tareas: list[str]) -> str:
    """Id idempotente: mismos equipo y tareas ⇒ misma orden."""
    base = f"{equipo}|{','.join(sorted(set(tareas)))}"
    return "ORD-" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


def _ts(ts: datetime | str | None) -> str:
    if ts is None:
        ts = datetime.now(timezone.utc)
    if isinstance(ts, datetime):
        return ts.isoformat()
    return str(ts)


def armar_orden(
    *,
    equipo: str,
    tareas: list[str],
    evento_ids: list[str] | tuple = (),
    detiene_equipo: bool = False,
    reduce_inyeccion: bool = False,
    repuestos: list[dict] | tuple = (),
    ejecutor: str = "propio",
    ts: datetime | str | None = None,
    estado_inicial: str = BORRADOR,
    motivo: str | None = None,
) -> dict:
    """Arma y valida una ``OrdenSistema`` nueva (estado Borrador por defecto)."""
    validar_transicion(None, estado_inicial)
    validar_decision(estado_inicial, motivo)
    orden = {
        "id": id_de_orden(equipo, tareas),
        "ts": _ts(ts),
        "estado": estado_inicial,
        "equipo": equipo,
        "evento_ids": list(evento_ids),
        "tareas": sorted(set(tareas)),
        "detiene_equipo": bool(detiene_equipo),
        "reduce_inyeccion": bool(reduce_inyeccion),
        "ejecutor": ejecutor,
        "repuestos": [dict(r) for r in repuestos],
        "motivo": motivo,
    }
    return OrdenSistema(**orden).model_dump(mode="json")


def transicion(
    orden: dict,
    hacia: str,
    motivo: str | None = None,
    **cambios,
) -> dict:
    """Devuelve la orden en el estado nuevo, conservando id y evidencia."""
    desde = orden.get("estado")
    validar_transicion(desde, hacia)
    validar_decision(hacia, motivo if motivo is not None else orden.get("motivo"))
    nuevo = dict(orden)
    nuevo.update(cambios)
    nuevo["estado"] = hacia
    if motivo is not None:
        nuevo["motivo"] = motivo
    nuevo["ts"] = _ts(None)
    return OrdenSistema(**nuevo).model_dump(mode="json")


def publicar(publicador, orden: dict, correlation_id: str | None = None) -> None:
    """Única vía de escritura: checkpoint en Postgres y publicación MQTT.

    El checkpoint va primero: si el contenedor se apaga entre el guardado y la
    publicación, la orden sigue en la base con el mismo id y estado.
    """
    OrdenSistema(**orden)
    db.guardar_orden(orden, correlation_id=correlation_id or orden["id"])
    publicador.publicar("sistema/ordenes", orden)
