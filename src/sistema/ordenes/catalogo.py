"""Catálogo de repuestos, tareas y lista de materiales (``datos/materiales.yaml``).

Es la misma información que usa la planta y el corrector. Los límites de
aprobación y el stock salen de acá, nunca del RAG.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[3]
RUTA_MATERIALES = RAIZ / "datos" / "materiales.yaml"


@lru_cache
def materiales() -> dict:
    return yaml.safe_load(RUTA_MATERIALES.read_text(encoding="utf-8"))


@lru_cache
def repuestos() -> dict[str, dict]:
    return {r["codigo"]: r for r in materiales()["repuestos"]}


@lru_cache
def estandar() -> dict[str, set[str]]:
    """Equipo -> tareas estándar que le corresponden."""
    salida: dict[str, set[str]] = {}
    for tarea in materiales()["tareas_estandar"]:
        for equipo in tarea["equipos"]:
            salida.setdefault(equipo, set()).add(tarea["codigo"])
    return salida


@lru_cache
def detiene() -> dict[str, bool]:
    """Tarea -> si detiene el equipo."""
    tareas = materiales()["tareas_estandar"] + materiales()["tareas_no_estandar"]
    return {t["codigo"]: bool(t.get("detiene", True)) for t in tareas}


@lru_cache
def lista_materiales() -> dict[str, list[str]]:
    return materiales()["lista_materiales"]


@lru_cache
def tareas_definidas() -> list[dict]:
    """Todas las tareas tal como están en el YAML (T-F-CAR aparece una por filtro)."""
    return list(materiales()["tareas_estandar"] + materiales()["tareas_no_estandar"])


@lru_cache
def tareas_por_codigo() -> dict[str, dict]:
    return {t["codigo"]: t for t in tareas_definidas()}


def tarea_para(codigo: str, equipo: str | None = None) -> dict | None:
    """La definición de la tarea que corresponde a ese equipo.

    ``T-F-CAR`` existe dos veces (cartuchos de 25 µm para F-201A y de 10 µm
    para F-201B): se elige la que incluye al equipo.
    """
    candidatas = [t for t in tareas_definidas() if t["codigo"] == codigo]
    if equipo:
        for t in candidatas:
            if equipo in (t.get("equipos") or []):
                return t
    return candidatas[0] if candidatas else None


def repuestos_de_la_tarea(codigo: str, equipo: str | None = None) -> list[dict]:
    """Repuestos que pide una tarea del catálogo (vacío si no está)."""
    tarea = tarea_para(codigo, equipo)
    return list((tarea or {}).get("repuestos") or [])

