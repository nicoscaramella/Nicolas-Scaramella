"""Conector de visión NVIDIA (build.nvidia.com).

El modelo elegido es ``nvidia/nemotron-3-nano-omni-30b-a3b-reasoning``: es el
VLM conversacional vigente del catálogo (verificado con la foto real de
``fuga-sin-enlace``). Es un modelo *reasoning*: necesita ``max_tokens`` alto
(2000) y ``reasoning_effort: low``, o devuelve ``content: null``.

La foto viaja como data URL base64 (la planta no es alcanzable desde la nube).
"""
from __future__ import annotations

import base64
import json
import os

import httpx
from pydantic import BaseModel, ConfigDict

MODELO_POR_DEFECTO = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
BASE = "https://integrate.api.nvidia.com/v1/chat/completions"

PROMPT = (
    "Sos inspector de mantenimiento de una planta de inyección de agua. "
    "Mirá la foto y respondé SOLO un JSON válido, sin texto extra, con esta forma: "
    '{"componente": "empaquetadura|correas|acople|manometro|filtro|descarga|otro", '
    '"dano_estructural": true o false, "descripcion": "breve", '
    '"confianza": numero entre 0 y 1}. '
    "La foto fue sacada desde lejos por seguridad: puede mostrar una rotura en la "
    "descarga de una bomba."
)


class VisionNoDisponible(Exception):
    """Sin clave, sin enlace o respuesta inválida: la foto queda en cola."""


class AnalisisFoto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    componente: str = "otro"
    dano_estructural: bool = False
    descripcion: str = ""
    confianza: float = 0.0


def _extraer_json(texto: str) -> dict:
    limpio = (texto or "").strip()
    if limpio.startswith("```"):
        limpio = limpio.strip("`")
        if limpio.startswith("json"):
            limpio = limpio[4:]
    inicio, fin = limpio.find("{"), limpio.rfind("}")
    if inicio < 0 or fin < inicio:
        raise VisionNoDisponible("la respuesta no trae JSON")
    return json.loads(limpio[inicio : fin + 1])


def analizar_foto(
    imagen: bytes,
    *,
    modelo: str | None = None,
    api_key: str | None = None,
    timeout: float = 60,
    cliente=None,
) -> AnalisisFoto:
    clave = api_key or os.getenv("NVIDIA_API_KEY")
    if not clave:
        raise VisionNoDisponible("sin NVIDIA_API_KEY configurada")
    modelo = modelo or os.getenv("VISION_MODELO") or MODELO_POR_DEFECTO
    b64 = base64.b64encode(imagen).decode("ascii")
    cuerpo = {
        "model": modelo,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": 2000,
        "reasoning_effort": "low",
    }
    try:
        respuesta = (cliente or httpx).post(
            BASE,
            headers={"Authorization": f"Bearer {clave}", "Accept": "application/json"},
            json=cuerpo,
            timeout=timeout,
        )
    except Exception as exc:  # conexión cortada por el enlace caído
        raise VisionNoDisponible(f"sin enlace: {exc}") from exc
    if respuesta.status_code != 200:
        raise VisionNoDisponible(f"HTTP {respuesta.status_code}: {respuesta.text[:200]}")
    try:
        contenido = respuesta.json()["choices"][0]["message"].get("content") or ""
        return AnalisisFoto(**_extraer_json(contenido))
    except VisionNoDisponible:
        raise
    except Exception as exc:
        raise VisionNoDisponible(f"respuesta inválida: {exc}") from exc
