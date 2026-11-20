"""G · Cierre: de la nota del técnico al parte de cierre y la orden Ejecutada.

El texto del cierre lo dicta el técnico ("probé a ciento diez kilos, sin
pérdida"). Se transcribe con el mismo ASR local y se arma el parte: tareas
hechas, repuestos usados, horas y resultado de la prueba. Después se compara
contra la orden y se marcan las diferencias. La decisión final (certificar u
observar) es del inspector, por la Central.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .. import db
from ..numeros import normalizar, parse_numero, UNIDADES
from . import catalogo, estado


@dataclass(frozen=True)
class ParteCierre:
    tareas: tuple[str, ...] = ()
    repuestos: tuple[dict, ...] = ()
    horas: float | None = None
    prueba: str | None = None
    texto: str = ""


def _tareas_en(texto: str) -> tuple[str, ...]:
    t = normalizar(texto)
    encontradas: dict[str, int] = {}
    for tarea in catalogo.tareas_definidas():
        nombre = normalizar(tarea["nombre"])
        if nombre and nombre in t:
            codigo = tarea["codigo"]
            encontradas[codigo] = max(encontradas.get(codigo, 0), len(nombre))
    return tuple(sorted(encontradas))


def _cantidad_antes(texto: str, posicion: int) -> float:
    """Cantidad dicha antes del repuesto ("un kit", "dos elastómeros")."""
    previo = normalizar(texto[:posicion])
    for token in reversed(previo.split()[-4:]):
        if token.isdigit():
            return float(token)
        if token in UNIDADES:
            return float(UNIDADES[token])
    return 1.0


def _repuestos_en(texto: str, equipo: str | None) -> tuple[dict, ...]:
    t = normalizar(texto)
    encontrados: dict[str, float] = {}

    for codigo, info in catalogo.repuestos().items():
        nombre = normalizar((info.get("nombre") or "").split(" (")[0])
        if not nombre:
            continue
        # Los cartuchos se distinguen por la micra; el resto por el nombre.
        if codigo.startswith("FC-CART"):
            micra = "25" if codigo.endswith("25") else "10"
            m = re.search(rf"cartuchos? filtrantes? {micra}", t)
        else:
            m = re.search(re.escape(nombre), t)
        if m:
            encontrados[codigo] = _cantidad_antes(texto, m.start())

    # "cartuchos" a secas: se resuelve con el equipo de la orden.
    if not any(c.startswith("FC-CART") for c in encontrados) and re.search(r"\bcartuchos?\b", t):
        if equipo == "F-201A":
            encontrados["FC-CART-25"] = 1.0
        elif equipo == "F-201B":
            encontrados["FC-CART-10"] = 1.0

    return tuple({"codigo": c, "cantidad": cant} for c, cant in encontrados.items())


def parsear_cierre(texto: str, equipo: str | None = None) -> ParteCierre:
    horas = None
    m = re.search(r"fueron\s+(.+?)\s+horas", normalizar(texto))
    if m:
        horas = parse_numero(m.group(1))

    prueba = None
    m = re.search(r"(prob[eé][^.]*|qued[oó] en servicio[^.]*)", texto, re.IGNORECASE)
    if m:
        prueba = m.group(1).strip()

    return ParteCierre(
        tareas=_tareas_en(texto),
        repuestos=_repuestos_en(texto, equipo),
        horas=horas,
        prueba=prueba,
        texto=texto,
    )


def comparar(
    orden: dict,
    parte: ParteCierre,
    *,
    horas_registro: float | None = None,
) -> list[str]:
    """Diferencias entre lo pedido y lo informado (tareas, repuestos, horas)."""
    problemas: list[str] = []

    pedidas = set(orden.get("tareas") or [])
    hechas = set(parte.tareas)
    for tarea in sorted(pedidas - hechas):
        problemas.append(f"tarea pedida no informada: {tarea}")
    for tarea in sorted(hechas - pedidas):
        problemas.append(f"tarea informada que no estaba en la orden: {tarea}")

    reservados = {r["codigo"]: float(r["cantidad"]) for r in orden.get("repuestos") or []}
    usados = {r["codigo"]: float(r["cantidad"]) for r in parte.repuestos}
    for codigo in sorted(set(usados) - set(reservados)):
        problemas.append(f"repuesto {codigo} no estaba en la orden")
    for codigo in sorted(set(reservados) - set(usados)):
        problemas.append(f"repuesto {codigo} reservado y no usado")
    for codigo in sorted(set(reservados) & set(usados)):
        if reservados[codigo] != usados[codigo]:
            problemas.append(
                f"cantidad de {codigo}: orden {reservados[codigo]:g}, cierre {usados[codigo]:g}"
            )

    if horas_registro is not None and parte.horas is not None:
        if parte.horas > float(horas_registro) + 0.1:
            problemas.append(
                f"declara {parte.horas:g} horas y el registro de ingreso da {horas_registro:g} horas"
            )

    return problemas


def procesar(publicador, *, nota: dict, texto: str) -> tuple[dict | None, ParteCierre, list[str]]:
    """Procesa una ``NotaCierre``: parte de cierre, diferencias y Ejecutada."""
    orden_id = nota.get("orden_id")
    parte = parsear_cierre(texto, None)
    if not orden_id:
        return None, parte, ["el cierre no trae orden"]

    fila = db.obtener_orden(orden_id)
    if not fila:
        return None, parte, [f"no existe la orden {orden_id}"]
    orden = dict(fila["payload"])
    parte = parsear_cierre(texto, orden.get("equipo"))
    diferencias = comparar(orden, parte)

    if orden.get("estado") == estado.APROBADA:
        ejecutada = estado.transicion(orden, estado.EJECUTADA)
        estado.publicar(publicador, ejecutada, correlation_id=fila.get("correlation_id"))
        orden = ejecutada
    elif orden.get("estado") != estado.EJECUTADA:
        diferencias.append(
            f"la orden estaba en {orden.get('estado')}, no aprobada: no se puede ejecutar"
        )

    db.actualizar_cierre_procesado(
        nota["id"],
        parte={
            "tareas": list(parte.tareas),
            "repuestos": list(parte.repuestos),
            "horas": parte.horas,
            "prueba": parte.prueba,
        },
        diferencias=diferencias,
    )
    return orden, parte, diferencias
