"""Abstracción del análisis de fotos: NVIDIA y cola cuando no hay enlace.

La decisión de la orden nunca se bloquea esperando la foto: si el enlace está
caído, el análisis queda en cola y se usa la heurística local (la alerta de
seguridad tampoco depende de la visión).
"""
from __future__ import annotations

import logging

from .. import db
from . import nvidia
from .nvidia import AnalisisFoto

log = logging.getLogger(__name__)


def _heuristica_local(fotos) -> AnalisisFoto | None:
    """Señal local que no depende de la nube (foto de rotura de descarga)."""
    for foto in fotos or ():
        if "rotura_descarga" in (foto or "").lower():
            return AnalisisFoto(
                componente="descarga",
                dano_estructural=True,
                descripcion="rotura en la línea de descarga (heurística local)",
                confianza=0.9,
            )
    return None


class Proveedor:
    def __init__(self, api, *, habilitado: bool = True, modelo: str | None = None):
        self.api = api
        self.habilitado = habilitado
        self.modelo = modelo

    def analizar(self, nota: dict) -> AnalisisFoto | None:
        fotos = list(nota.get("fotos") or ())
        if not fotos:
            return None
        local = _heuristica_local(fotos)
        if not self.habilitado:
            return local
        try:
            imagen = self.api.descargar(fotos[0])
            return nvidia.analizar_foto(imagen, modelo=self.modelo)
        except nvidia.VisionNoDisponible as exc:
            try:
                db.encolar_vision(nota.get("id"), fotos[0], str(exc))
            except Exception:
                log.warning("No se pudo encolar la foto de %s", nota.get("id"))
            log.info("Análisis de foto de %s en cola: %s", nota.get("id"), exc)
        except Exception as exc:
            log.warning("No se pudo bajar la foto de %s: %s", nota.get("id"), exc)
        return local
