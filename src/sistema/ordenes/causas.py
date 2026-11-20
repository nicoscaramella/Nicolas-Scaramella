"""C · Catálogo de fallas con cita y causas probables según el historial.

La tabla sale del MBP-4 §6 (catálogo de fallas de equipo) y del catálogo de
tareas. El historial es texto libre de campo: se buscan los cinco patrones que
el anexo pide (MBP-4 §6.14: "el historial cambia la causa probable").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class Falla:
    codigo: str
    nombre: str
    cita: str
    tareas: tuple[str, ...]
    sintomas: tuple[str, ...]
    tipo: str                       # "bomba" | "filtro" | "sensor"
    raiz_en_otro_equipo: bool = False
    sin_orden: bool = False


FALLAS: dict[str, Falla] = {
    "F01": Falla(
        "F01", "Pérdida por empaquetadura", "MBP-4 §6.3", ("T-B-EMP",),
        ("goteo", "empaquetadura", "perdida", "pierde", "fuga", "agua a presion", "se rompio"),
        "bomba",
    ),
    "F02": Falla(
        "F02", "Válvulas de succión/descarga gastadas", "MBP-4 §6.4", ("T-B-VAL",),
        ("golpeteo", "golpetea", "valvula", "pulsacion", "martilleo"),
        "bomba",
    ),
    "F03": Falla(
        "F03", "Rodamiento de cigüeñal dañado", "MBP-4 §6.5", ("T-B-ROD",),
        ("rodamiento", "ruido raro", "zumbido"),
        "bomba",
    ),
    "F04": Falla(
        "F04", "Bajo nivel de aceite del cárter", "MBP-4 §6.6", ("T-B-ACE",),
        ("nivel de aceite", "visor de aceite", "aceite bajo", "sin aceite"),
        "bomba",
    ),
    "F05": Falla(
        "F05", "Correas flojas o gastadas", "MBP-4 §6.7", ("T-B-COR",),
        ("correa", "chirrido", "polea"),
        "bomba",
    ),
    "F06": Falla(
        "F06", "Acople desalineado / elastómero gastado", "MBP-4 §6.8", ("T-B-ALI",),
        ("acople", "elastomero", "desalineado"),
        "bomba",
    ),
    "F07": Falla(
        "F07", "Cartuchos colmatados", "MBP-4 §6.9", ("T-F-CAR",),
        ("diferencial alto", "colmatado", "diferencial subiendo"),
        "filtro",
    ),
    "F08": Falla(
        "F08", "Cartucho roto (agua sin filtrar)", "MBP-4 §6.10", ("T-F-CAR",),
        ("cartucho roto", "diferencial cae"),
        "filtro",
    ),
    "F09": Falla(
        "F09", "Cavitación por baja succión", "MBP-4 §6.11", ("I-VIB",),
        ("cavita", "cavitacion", "a piedras", "baja succion"),
        "bomba", raiz_en_otro_equipo=True,
    ),
    "F10": Falla(
        "F10", "Sensor congelado o con deriva", "MBP-4 §6.12", ("T-I-CAL",),
        ("deriva", "sensor congelado", "no coincide"),
        "sensor", sin_orden=True,
    ),
}

# Orden de prioridad al clasificar un texto (más específico primero).
_PRIORIDAD = ("F10", "F03", "F02", "F01", "F05", "F06", "F04", "F09")


def _normal(texto: str) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def tipo_de_equipo(equipo: str) -> str:
    if equipo.startswith("F-"):
        return "filtro"
    if equipo.startswith("B-"):
        return "bomba"
    return "sensor"


def clasificar(equipo: str, texto: str) -> str | None:
    """Código de falla más probable para el texto de la recorrida, o ``None``."""
    t = _normal(texto)
    if not t:
        return None
    # La deriva del sensor se detecta en cualquier equipo (el manómetro local
    # no coincide con el sensor conectado).
    if any(s in t for s in FALLAS["F10"].sintomas):
        return "F10"
    tipo = tipo_de_equipo(equipo)
    if tipo == "filtro":
        # En un filtro el síntoma es el diferencial: alto = colmatado.
        if "diferencial" in t or "colmatad" in t or "cartucho" in t:
            return "F08" if "roto" in t else "F07"
        return None
    for codigo in _PRIORIDAD:
        falla = FALLAS[codigo]
        if falla.tipo == "sensor" and tipo != "sensor":
            continue
        if any(s in t for s in falla.sintomas):
            return codigo
    return None


# ---------------------------------------------------------------------- historial

DIAS_RECIENTE = 45
DIAS_VALVULAS = 30


def _fecha(orden: dict) -> datetime | None:
    valor = orden.get("fecha") or orden.get("fecha_aviso") or orden.get("fecha_inicio")
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


def _texto_de(orden: dict) -> str:
    return _normal(f"{orden.get('aviso') or ''} {orden.get('trabajo_realizado') or ''}")


def _recientes(ordenes: list[dict], dias: int, ahora: datetime | None = None) -> list[dict]:
    ahora = ahora or datetime.now(timezone.utc)
    salida = []
    for o in ordenes:
        f = _fecha(o)
        if f is None:
            salida.append(o)
            continue
        if f.tzinfo is None:
            f = f.replace(tzinfo=timezone.utc)
        if ahora - f <= timedelta(days=dias):
            salida.append(o)
    return salida


def _patron(equipo: str, texto: str, historial: list[dict], causas: list[dict]) -> None:
    ordenes = [o for o in historial if o.get("equipo") == equipo]
    recientes = _recientes(ordenes, DIAS_RECIENTE)
    t = _normal(texto)

    # 1) Vibración que no se fue cambiando válvulas: era el acople (F06).
    if tipo_de_equipo(equipo) == "bomba" and ("vibra" in t or any("vibra" in _texto_de(o) for o in recientes)):
        valvulas = [o for o in recientes if "T-B-VAL" in (o.get("tareas") or [])]
        if len(valvulas) >= 2:
            causas.append({
                "falla": "F06", "causa": "Acople desalineado / elastómero gastado (la vibración siguió tras cambiar válvulas)",
                "cita": "MBP-4 §6.8", "evidencia": f"{len(valvulas)} cambios de válvulas recientes y vibración persistente",
                "falta": "medir alineación con láser para confirmar",
            })

    # 2) Empaquetadura que dura semanas: émbolo rayado.
    empaquetaduras = [o for o in recientes if "T-B-EMP" in (o.get("tareas") or [])]
    if tipo_de_equipo(equipo) == "bomba" and len(empaquetaduras) >= 2:
        causas.append({
            "falla": "F01", "causa": "Émbolo rayado (la empaquetadura no dura semanas: revisar extremo hidráulico)",
            "cita": "MBP-4 §6.3", "evidencia": f"{len(empaquetaduras)} cambios de empaquetadura en menos de {DIAS_RECIENTE} días",
            "falta": "inspeccionar los émbolos y el estado del extremo hidráulico",
        })

    # 3) Válvulas gastadas en dos bombas en pocos días: cartucho roto en F-201B.
    valvulas_bombas = {
        o["equipo"] for o in _recientes(
            [o for o in historial if "T-B-VAL" in (o.get("tareas") or []) and tipo_de_equipo(o.get("equipo", "")) == "bomba"],
            DIAS_VALVULAS,
        )
    }
    if tipo_de_equipo(equipo) == "bomba" and len(valvulas_bombas) >= 2:
        causas.append({
            "falla": "F08", "causa": "Cartucho roto en F-201B (agua sin filtrar gasta las válvulas de varias bombas)",
            "cita": "MBP-4 §6.10", "evidencia": f"cambios de válvulas en {', '.join(sorted(valvulas_bombas))} en menos de {DIAS_VALVULAS} días",
            "falta": "inspeccionar los cartuchos del filtro secundario",
        })

    # 4) La dos que cavita: filtro primario colmatado (la causa raíz es otro equipo).
    if equipo == "B-102" and ("cavita" in t or "piedras" in t):
        causas.append({
            "falla": "F07", "causa": "Filtro primario F-201A colmatado (baja succión de la B-102)",
            "cita": "MBP-4 §6.11", "evidencia": "cavitación en la bomba del medio",
            "falta": "medir el diferencial del filtro primario",
        })

    # 5) Consumo de aceite de la B-102: retén del piñón.
    if equipo == "B-102" and ("aceite" in t or any("aceite" in _texto_de(o) for o in recientes)):
        consumos = [o for o in recientes if "T-B-ACE" in (o.get("tareas") or [])]
        if consumos:
            causas.append({
                "falla": "F04", "causa": "Retén del piñón (consumo de aceite persistente)",
                "cita": "MBP-4 §6.6", "evidencia": f"{len(consumos)} reposiciones de aceite recientes",
                "falta": "revisar pérdidas por el retén del piñón",
            })


def patrones_de_historial(equipo: str, texto: str, historial: list[dict]) -> list[dict]:
    """Causas probables que agrega el historial, en orden de evidencia."""
    causas: list[dict] = []
    _patron(equipo, texto, historial or [], causas)
    return causas


# Repuestos que el catálogo de tareas no lista pero la falla necesita.
# F03: rodamientos + sellos de cárter (como el cierre OT-24-0015 del corpus).
REPUESTOS_POR_FALLA: dict[str, tuple[dict, ...]] = {
    "F03": (
        {"codigo": "TX-ROD-CIG", "cantidad": 1},
        {"codigo": "TX-SELLO-CAR", "cantidad": 1},
    ),
    "F06": ({"codigo": "ACO-ELAST-90", "cantidad": 1},),
}


def repuestos_sugeridos(codigo: str | None) -> list[dict]:
    return [dict(r) for r in REPUESTOS_POR_FALLA.get(codigo or "", ())]

