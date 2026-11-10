"""Validación contra el contrato, outbox y publicación MQTT."""

from __future__ import annotations

import json
import logging

import paho.mqtt.client as mqtt
from planta_contrato import EstadoSistema, EventoSistema, MensajeTablet, OrdenSistema

from . import db
from .metricas import ConsumoTokens

log = logging.getLogger(__name__)

MODELOS = {
    "sistema/eventos": EventoSistema,
    "sistema/ordenes": OrdenSistema,
    "sistema/estado": EstadoSistema,
    "sistema/tablet": MensajeTablet,
    "sistema/metricas": ConsumoTokens,
}


class Publicador:
    def __init__(self, cliente: mqtt.Client, al_quedar_pendiente=None):
        self.cliente = cliente
        # Mientras el enlace está caído se publica igual en la red local (la
        # tablet y la planta tienen que seguir andando), pero la fila queda
        # pendiente de sincronizar hasta que vuelva el enlace.
        self.enlace_ok = True
        # Se avisa enseguida cuando aparece un pendiente, para que el visor no
        # tenga que esperar al próximo latido.
        self.al_quedar_pendiente = al_quedar_pendiente
        self._avisando = False

    def publicar(self, topico: str, payload: dict) -> None:
        modelo = MODELOS.get(topico)
        if modelo is not None:
            payload = modelo.model_validate(payload).model_dump(mode="json")
        fila_id = db.encolar(topico, payload)
        self._intentar(fila_id, topico, payload)

    def _intentar(self, fila_id: int, topico: str, payload: dict) -> None:
        info = self.cliente.publish(topico, json.dumps(payload, ensure_ascii=False), qos=1)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            log.warning("No se pudo publicar en %s (rc=%s); queda en outbox", topico, info.rc)
            return
        if self.enlace_ok:
            db.marcar_publicado(fila_id)
            return
        # Quedó pendiente de sincronizar. El latido y la métrica no disparan
        # otro latido para no entrar en recursión.
        if (
            self.al_quedar_pendiente
            and not self._avisando
            and topico not in ("sistema/estado", "sistema/metricas")
        ):
            self._avisando = True
            try:
                self.al_quedar_pendiente()
            finally:
                self._avisando = False

    def reintentar(self) -> None:
        # Sin enlace no se reintenta: se acumula en la cola y el latido lo
        # muestra. Al volver el enlace se envía en orden (los ids del contrato
        # son idempotentes, así que reenviar no duplica).
        if not self.enlace_ok:
            return
        for fila in db.pendientes():
            self._intentar(int(fila["id"]), fila["topico"], fila["payload"])
