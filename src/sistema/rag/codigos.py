"""Traducción de códigos de falla del fabricante a F01–F10 (MBP-4 §6)."""

from __future__ import annotations

CODIGOS = {
    "TX-T01": "F01",
    "TX-T02": "F02",
    "TX-T03": "F03",
    "TX-T04": "F04",
    "TX-T05": "F05",
    "TX-T06": "F06",
    "TX-T07": "F09",
    "TX-T08": "F10",
    "FC-T01": "F07",
    "FC-T02": "F08",
    "FC-T04": "F10",
}

DESCRIPCIONES = {
    "F01": "Pérdida por empaquetadura",
    "F02": "Válvulas de succión/descarga gastadas",
    "F03": "Rodamiento de cigüeñal dañado",
    "F04": "Bajo nivel de aceite del cárter",
    "F05": "Correas flojas o gastadas",
    "F06": "Acople desalineado / elastómero gastado",
    "F07": "Cartuchos colmatados",
    "F08": "Cartucho roto (agua sin filtrar)",
    "F09": "Cavitación por baja succión",
    "F10": "Sensor congelado o con deriva",
}


def traducir(codigo: str) -> str | None:
    return CODIGOS.get((codigo or "").strip().upper())
