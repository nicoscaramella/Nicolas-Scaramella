"""Tools de solo lectura con validación estricta de entrada."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .planta_api import PlantaAPI
from .rag.buscar import RAG

log = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parents[2]
DATOS = RAIZ / "datos"


class _Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EquiposIn(_Entrada):
    pass


class HistorianIn(_Entrada):
    tag: str = Field(min_length=1)
    variable: str = Field(min_length=1)
    desde: str | None = None
    hasta: str | None = None


class HistorialIn(_Entrada):
    equipo: str | None = None
    desde: str | None = None
    hasta: str | None = None


class InventarioIn(_Entrada):
    pass


class StockIn(_Entrada):
    codigo: str = Field(min_length=1)


class MaterialesIn(_Entrada):
    tag: str = Field(min_length=1)


class TareasIn(_Entrada):
    pass


class ManualesIn(_Entrada):
    query: str = Field(min_length=2)
    k: int = Field(default=5, ge=1, le=20)


class CodigoIn(_Entrada):
    codigo: str = Field(min_length=2)


class ToolError(RuntimeError):
    pass


def _materiales() -> dict:
    with open(DATOS / "materiales.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _planta_local() -> dict:
    with open(DATOS / "planta.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def equipos() -> list[dict]:
    EquiposIn()
    return PlantaAPI().planta().get("equipos", [])


def historial_sensores(tag: str, variable: str, desde: str | None = None, hasta: str | None = None) -> list[dict]:
    HistorianIn(tag=tag, variable=variable, desde=desde, hasta=hasta)
    try:
        return PlantaAPI().historian(tag, variable, desde, hasta)
    except Exception as exc:
        raise ToolError(f"No se pudo leer el historian de {tag}/{variable}: {exc}") from exc


def historial_ordenes(equipo: str | None = None, desde: str | None = None, hasta: str | None = None) -> list[dict]:
    HistorialIn(equipo=equipo, desde=desde, hasta=hasta)
    try:
        return PlantaAPI().historial_ordenes(equipo, desde, hasta)
    except Exception as exc:
        raise ToolError(f"No se pudo leer el historial de órdenes: {exc}") from exc


def inventario() -> list[dict]:
    InventarioIn()
    return _materiales().get("repuestos", [])


def stock(codigo: str) -> dict:
    StockIn(codigo=codigo)
    for repuesto in _materiales().get("repuestos", []):
        if repuesto["codigo"] == codigo:
            return repuesto
    raise ToolError(f"No existe el repuesto {codigo}")


def lista_materiales(tag: str) -> dict:
    MaterialesIn(tag=tag)
    materiales = _materiales()
    codigos = materiales.get("lista_materiales", {}).get(tag, [])
    por_codigo = {r["codigo"]: r for r in materiales.get("repuestos", [])}
    return {"equipo": tag, "repuestos": [por_codigo[c] for c in codigos if c in por_codigo]}


def catalogo_tareas() -> dict:
    TareasIn()
    materiales = _materiales()
    return {
        "estandar": materiales.get("tareas_estandar", []),
        "no_estandar": materiales.get("tareas_no_estandar", []),
    }


def buscar_manuales(query: str, k: int = 5) -> list[dict]:
    ManualesIn(query=query, k=k)
    return [
        {
            "cita": f["cita"],
            "texto": f["texto"][:1200],
            "doc": f.get("doc"),
            "vigente": f.get("vigente"),
        }
        for f in RAG().buscar(query, k)
    ]


def traducir_codigo_falla(codigo: str) -> dict:
    """Código del fabricante (TX-T03) → código de la planta (F03)."""
    from .rag.codigos import DESCRIPCIONES, traducir

    entrada = CodigoIn(codigo=codigo)
    planta = traducir(entrada.codigo)
    return {
        "codigo_fabricante": entrada.codigo.strip().upper(),
        "codigo_planta": planta,
        "descripcion": DESCRIPCIONES.get(planta) if planta else None,
    }
