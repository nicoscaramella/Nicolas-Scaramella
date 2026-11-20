"""Central de mantenimiento: las decisiones humanas del circuito.

- **Planificador**: aprueba o rechaza una orden pendiente.
- **Supervisor**: cierra el trabajo propio terminado.
- **Inspector**: certifica (con habilita y monto del contrato) u observa el
  trabajo de la contratista.

El contrato MQTT no trae canal para estas decisiones: esta es la interfaz
propia que pide el anexo. Toda escritura pasa por ``ordenes.estado``.
"""

from __future__ import annotations

from .. import db
from ..ordenes import certificacion, estado

ROLES = {
    "planificador": {"aprobar", "rechazar"},
    "supervisor": {"cerrar"},
    "inspector": {"certificar", "observar"},
}

ACCIONES = {
    "aprobar": estado.APROBADA,
    "rechazar": estado.RECHAZADA,
    "cerrar": estado.CERRADA,
    "certificar": estado.CERTIFICADA,
    "observar": estado.OBSERVADA,
}


class ErrorCentral(Exception):
    """Error de negocio de la Central."""


class PermisoDenegado(ErrorCentral):
    pass


class OrdenNoEncontrada(ErrorCentral):
    pass


class DecisionInvalida(ErrorCentral):
    pass


def listar(estado_filtro: str | None = None, limite: int = 200) -> list[dict]:
    return [dict(fila) for fila in db.listar_ordenes(estado_filtro, limite)]


def obtener(orden_id: str) -> dict:
    fila = db.obtener_orden(orden_id)
    if not fila:
        raise OrdenNoEncontrada(orden_id)
    datos = dict(fila)
    cierre = db.obtener_cierre_por_orden(orden_id)
    datos["cierre"] = dict(cierre) if cierre else None
    return datos


def decidir(
    publicador,
    orden_id: str,
    accion: str,
    *,
    rol: str,
    quien: str | None = None,
    motivo: str | None = None,
) -> dict:
    """Aplica la decisión humana con la transición y el motivo correctos."""
    if accion not in ROLES.get(rol, set()):
        raise PermisoDenegado(f"el rol {rol or '(sin rol)'} no puede {accion}")

    fila = db.obtener_orden(orden_id)
    if not fila:
        raise OrdenNoEncontrada(orden_id)
    orden = dict(fila["payload"])
    destino = ACCIONES[accion]

    cambios: dict = {}
    if accion == "certificar":
        cierre = db.obtener_cierre_por_orden(orden_id)
        diferencias = (cierre or {}).get("diferencias") or []
        if diferencias:
            raise DecisionInvalida(
                "el cierre tiene diferencias respecto de la orden: corresponde Observar"
            )
        resultado = certificacion.evaluar(
            orden, None, diferencias=[], fecha_inicio=orden.get("ts")
        )
        cambios = {
            "habilita": resultado["habilita"],
            "monto_habilita_usd": resultado["monto"],
        }

    nueva = estado.transicion(orden, destino, motivo=motivo, **cambios)
    if quien:
        db.registrar_decision(orden_id, accion, rol, quien, motivo)
    estado.publicar(publicador, nueva, correlation_id=fila.get("correlation_id"))
    return nueva
