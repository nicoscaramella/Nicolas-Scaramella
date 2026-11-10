"""Detector local de condiciones inseguras S1–S4.

Corre en código, sin modelos ni nube. Se aplica apenas llega la nota para
publicar la alerta dentro de los 30 s reales que pide el anexo.
"""

from __future__ import annotations

import re
import unicodedata

TEXTOS = {
    "S1": (
        "Aplique el procedimiento de emergencia: aléjese de la zona, no se acerque "
        "y avise por radio al supervisor de turno."
    ),
    "S2": (
        "Aplique el procedimiento de emergencia: aleje al personal, no genere chispas "
        "y avise por radio al supervisor de turno."
    ),
    "S3": (
        "Aplique el procedimiento de emergencia: aléjese, use el extintor si es seguro "
        "y avise por radio al supervisor de turno."
    ),
    "S4": (
        "Aplique el procedimiento de emergencia: asegure la zona, no mueva al lesionado "
        "salvo peligro y avise por radio al supervisor de turno."
    ),
}


def _normal(texto: str) -> str:
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def detectar_seguridad(texto: str, fotos: list[str] | None = None) -> str | None:
    """Devuelve S1..S4 o None. Prioriza la condición más específica."""
    t = _normal(texto)
    fotos = fotos or []
    # La foto de rotura de descarga es una señal fuerte de S1.
    if any("rotura_descarga" in _normal(f) for f in fotos):
        return "S1"
    if re.search(r"(agua a presion|sale agua|se rompio|niple|chorro|para todos lados|me aleje)", t):
        return "S1"
    if re.search(r"(olor a gas|gas fuerte|fuga de gas)", t):
        return "S2"
    if re.search(r"(humo|fuego|incendio|olor a quemado|se quemo)", t):
        return "S3"
    if re.search(r"(se golpeo|sangrando|lesionad|herid|accidente|se corto)", t):
        return "S4"
    return None


def texto_alerta(codigo: str) -> str:
    return TEXTOS.get(codigo, TEXTOS["S1"])
