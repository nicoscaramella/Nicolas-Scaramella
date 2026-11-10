"""Cliente mínimo para un LLM local servido por Ollama.

Es **opcional**: si está deshabilitado, si Ollama no responde o si el modelo no
está descargado, todos los métodos devuelven ``None``. Ningún camino crítico
(ASR, parser, detección, tablet) depende de este módulo.

Se habla HTTP directo con ``/api/chat`` para no sumar dependencias y para
controlar el timeout. ``trust_env=False`` es a propósito: el agente vive en
``planta-lan`` y tiene ``HTTP_PROXY=http://enlace:3128``; las llamadas al host
no pueden salir por el proxy de la planta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from .config import settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RespuestaLLM:
    texto: str
    tokens_entrada: int = 0
    tokens_salida: int = 0


class LLM:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
        habilitado: bool | None = None,
        permitidos: set[str] | None = None,
    ):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self.timeout_s = settings.llm_timeout_s if timeout_s is None else timeout_s
        self.habilitado = settings.llm_habilitado if habilitado is None else habilitado
        if permitidos is None:
            crudos = settings.llm_modelos_permitidos.split(",")
            permitidos = {m.strip() for m in crudos if m.strip()}
        self.permitidos = permitidos
        self.permitido = self.model in self.permitidos
        if not self.permitido:
            log.warning(
                "Modelo %s no está en LLM_MODELOS_PERMITIDOS (%s); no se usa",
                self.model,
                ", ".join(sorted(self.permitidos)) or "(vacío)",
            )

    def disponible(self) -> bool:
        """True solo si el modelo está permitido, descargado y responde."""
        if not self.habilitado or not self.permitido:
            return False
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=3, trust_env=False)
            r.raise_for_status()
            nombres = {m.get("name") for m in r.json().get("models", [])}
            return self.model in nombres
        except Exception as exc:
            log.info("LLM %s no disponible: %s", self.model, exc)
            return False

    def chat(
        self,
        mensaje: str,
        sistema: str | None = None,
        max_tokens: int | None = None,
    ) -> RespuestaLLM | None:
        """Una consulta sin streaming. Devuelve ``None`` ante cualquier falla."""
        if not self.habilitado or not self.permitido:
            return None
        mensajes = []
        if sistema:
            mensajes.append({"role": "system", "content": sistema})
        mensajes.append({"role": "user", "content": mensaje})
        payload = {
            "model": self.model,
            "messages": mensajes,
            "stream": False,
            # Los modelos de razonamiento (qwen3.5, ornith) mandan el texto a
            # "thinking" y dejan "content" vacío. Para una respuesta directa
            # se apaga el razonamiento; los modelos que no lo soportan lo
            # ignoran.
            "think": False,
            "keep_alive": "30m",
            "options": {
                "temperature": 0,
                "num_predict": max_tokens or settings.llm_max_tokens,
            },
        }
        try:
            r = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout_s,
                trust_env=False,
            )
            r.raise_for_status()
            datos = r.json()
            texto = ((datos.get("message") or {}).get("content") or "").strip()
            if not texto:
                log.warning(
                    "LLM %s devolvió contenido vacío (¿modelo de razonamiento?)", self.model
                )
                return None
            return RespuestaLLM(
                texto=texto,
                tokens_entrada=int(datos.get("prompt_eval_count") or 0),
                tokens_salida=int(datos.get("eval_count") or 0),
            )
        except Exception as exc:
            log.warning("Falló el LLM %s: %s", self.model, exc)
            return None
