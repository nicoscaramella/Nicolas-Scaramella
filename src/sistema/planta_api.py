"""Cliente de la API HTTP de la planta (`http://sim:8100`)."""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from .config import settings

log = logging.getLogger(__name__)


class PlantaAPI:
    def __init__(self, base: str | None = None):
        self.base = (base or settings.planta_url).rstrip("/")
        self.http = httpx.Client(base_url=self.base, timeout=30, trust_env=True)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _get(self, ruta: str, params: dict | None = None):
        r = self.http.get(ruta, params=params)
        r.raise_for_status()
        return r

    def planta(self) -> dict:
        return self._get("/api/planta").json()

    def historian(
        self, tag: str, variable: str, desde: str | None = None, hasta: str | None = None
    ) -> list[dict]:
        params = {k: v for k, v in (("desde", desde), ("hasta", hasta)) if v}
        return self._get(f"/api/historian/{tag}/{variable}", params=params).json()

    def historial_ordenes(
        self, equipo: str | None = None, desde: str | None = None, hasta: str | None = None
    ) -> list[dict]:
        params = {k: v for k, v in (("equipo", equipo), ("desde", desde), ("hasta", hasta)) if v}
        return self._get("/api/historial-ordenes", params=params).json()

    def documentos(self) -> dict:
        return self._get("/api/documentos").json()

    def documento(self, doc_id: str) -> dict:
        return self._get(f"/api/documentos/{doc_id}").json()

    def secciones(self, doc_id: str, numero: str | None = None) -> list[dict]:
        params = {"numero": numero} if numero else None
        return self._get(f"/api/documentos/{doc_id}/secciones", params=params).json()

    def verdad(self) -> list[dict]:
        return self._get("/api/verdad").json()

    def registro(self) -> list[dict]:
        return self._get("/api/registro").json()

    def estado(self) -> dict:
        return self._get("/api/estado").json()

    def descargar(self, url: str) -> bytes:
        absoluta = url if url.startswith("http") else urljoin(self.base + "/", url.lstrip("/"))
        r = self.http.get(absoluta)
        r.raise_for_status()
        return r.content

    def texto(self, ruta: str) -> str:
        r = self.http.get(ruta)
        r.raise_for_status()
        return r.text
