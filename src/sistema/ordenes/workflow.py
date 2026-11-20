"""M4 · Reintentos, deadlines y detección de loops del flujo de órdenes."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone


class TiempoAgotado(Exception):
    """Se venció el plazo de un paso del workflow."""


class LoopDetectado(Exception):
    """El mismo caso se repitió demasiadas veces: se corta para no loopear."""


class Deadline:
    """Plazo para un paso (por ejemplo, el análisis de una foto)."""

    def __init__(self, segundos: float, reloj=time.monotonic):
        self._reloj = reloj
        self._limite = reloj() + segundos

    def vencido(self) -> bool:
        return self._reloj() >= self._limite

    def verificar(self) -> None:
        if self.vencido():
            raise TiempoAgotado("se agotó el tiempo del paso")


def con_reintentos(
    fn,
    *,
    intentos: int = 3,
    espera: float = 0.0,
    dormir=time.sleep,
    excepciones: tuple[type[BaseException], ...] = (Exception,),
):
    """Ejecuta ``fn`` con backoff exponencial; propaga el último error."""
    ultimo: BaseException | None = None
    for i in range(max(1, intentos)):
        try:
            return fn()
        except excepciones as exc:
            ultimo = exc
            if i + 1 < intentos and espera:
                dormir(espera * (2**i))
    assert ultimo is not None
    raise ultimo


class DetectorDeLoops:
    """Corta si la misma clave (equipo + tareas) se repite en la ventana."""

    def __init__(self, maximo: int = 3, ventana_s: float = 3600, reloj=None):
        self.maximo = maximo
        self.ventana = float(ventana_s)
        self._reloj = reloj or (lambda: datetime.now(timezone.utc))
        self._vistos: dict[str, list] = defaultdict(list)

    def _segundos(self, desde, hasta) -> float:
        diferencia = hasta - desde
        if hasattr(diferencia, "total_seconds"):
            return float(diferencia.total_seconds())
        return float(diferencia)

    def registrar(self, clave: str) -> None:
        ahora = self._reloj()
        recientes = [t for t in self._vistos[clave] if self._segundos(t, ahora) <= self.ventana]
        if len(recientes) >= self.maximo:
            raise LoopDetectado(f"{clave} se repitió {len(recientes)} veces en la ventana")
        recientes.append(ahora)
        self._vistos[clave] = recientes
