"""Servidor MCP con las tools de solo lectura de la planta y el corpus."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import tools

mcp = FastMCP("planta-pia3")


@mcp.tool()
def equipos() -> list[dict]:
    """Equipos de la planta con TAG, nombres informales, sensores y límites."""
    return tools.equipos()


@mcp.tool()
def historial_sensores(
    tag: str, variable: str, desde: str | None = None, hasta: str | None = None
) -> list[dict]:
    """Historial de un sensor (una muestra por minuto, 45 días)."""
    return tools.historial_sensores(tag, variable, desde, hasta)


@mcp.tool()
def historial_ordenes(
    equipo: str | None = None, desde: str | None = None, hasta: str | None = None
) -> list[dict]:
    """Órdenes de trabajo del equipo: archivo de dos años más el simulador."""
    return tools.historial_ordenes(equipo, desde, hasta)


@mcp.tool()
def inventario() -> list[dict]:
    """Repuestos con stock por almacén y costo unitario."""
    return tools.inventario()


@mcp.tool()
def stock(codigo: str) -> dict:
    """Disponibilidad y costo de un repuesto."""
    return tools.stock(codigo)


@mcp.tool()
def lista_materiales(tag: str) -> dict:
    """Lista de materiales de un equipo."""
    return tools.lista_materiales(tag)


@mcp.tool()
def catalogo_tareas() -> dict:
    """Tareas estándar y no estándar del plan de mantenimiento."""
    return tools.catalogo_tareas()


@mcp.tool()
def buscar_manuales(query: str, k: int = 5) -> list[dict]:
    """Búsqueda semántica en manuales, contrato e historial, con cita."""
    return tools.buscar_manuales(query, k)


@mcp.tool()
def traducir_codigo_falla(codigo: str) -> dict:
    """Traduce un código del fabricante (TX-T03) al código de planta (F03)."""
    return tools.traducir_codigo_falla(codigo)


if __name__ == "__main__":
    mcp.run()
