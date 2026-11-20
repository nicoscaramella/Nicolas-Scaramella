"""M4 · Durabilidad de las órdenes: recuperación tras el corte de luz.

El estado vive en Postgres, no en memoria: cuando el corte de ``sin-luz`` apaga
los contenedores ``academia.planta: pc``, la orden pendiente vuelve con el
mismo id y el mismo estado. Al arrancar se re-publican las órdenes abiertas
(re-publicar el mismo id es idempotente para el contrato).
"""

from __future__ import annotations

from .. import db
from . import estado


def recuperar(publicador, limite: int = 200) -> int:
    """Re-publica las órdenes abiertas tal como quedaron (nunca a Borrador)."""
    recuperadas = 0
    for fila in db.ordenes_abiertas(limite):
        payload = dict(fila["payload"])
        # Una orden que se cortó antes de decidirse no se degrada ni se
        # inventa: se dejar para que el flujo la retome.
        if payload.get("estado") == estado.BORRADOR:
            continue
        publicador.publicar("sistema/ordenes", payload)
        recuperadas += 1
    return recuperadas
