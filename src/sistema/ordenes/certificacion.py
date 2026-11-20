"""G · Certificación de trabajos de contratista (CT-SVP-2025).

El monto del habilita sale de la orden y de la lista de precios vigente a la
fecha de inicio, NUNCA de lo que declara el cierre. Si el cierre declara algo
distinto de la orden, la orden queda Observada con el motivo.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime

# Anexo II del contrato: precios cerrados por tarea y por equipo.
PRECIOS = {
    "2025": {"T-B-ROD": 1150.0, "T-B-ALI": 780.0, "I-VIB": 320.0},
    "2022": {"T-B-ROD": 980.0, "T-B-ALI": 650.0, "I-VIB": 280.0},
}
POR_EQUIPO = {"I-VIB"}
CAMBIO_DE_LISTA = date(2025, 1, 1)


def lista_por_fecha(fecha_inicio: str | date | datetime | None) -> str:
    """Lista aplicable: CT-SVP-2022 para trabajos iniciados antes de 2025."""
    if not fecha_inicio:
        return "2025"
    if isinstance(fecha_inicio, str):
        fecha_inicio = datetime.fromisoformat(fecha_inicio).date()
    elif isinstance(fecha_inicio, datetime):
        fecha_inicio = fecha_inicio.date()
    return "2022" if fecha_inicio < CAMBIO_DE_LISTA else "2025"


def monto_contrato(
    tareas: list[str],
    *,
    fecha_inicio: str | date | datetime | None = None,
    equipos: int = 1,
) -> float:
    """Precio del contrato para las tareas de la orden, según la lista vigente."""
    precios = PRECIOS[lista_por_fecha(fecha_inicio)]
    total = 0.0
    for tarea in tareas:
        precio = precios.get(tarea, 0.0)
        total += precio * (equipos if tarea in POR_EQUIPO else 1)
    return total


def habilita(orden_id: str, anio: int | None = None) -> str:
    """Número de habilita HAB-AAAA-NNNN, estable por orden."""
    anio = anio or date.today().year
    sufijo = hashlib.sha1(orden_id.encode("utf-8")).hexdigest()[:4].upper()
    return f"HAB-{anio}-{sufijo}"


def evaluar(
    orden: dict,
    parte,
    *,
    diferencias: list[str] | None = None,
    fecha_inicio: str | date | datetime | None = None,
    equipos: int = 1,
    monto_declarado: float | None = None,
) -> dict:
    """Resultado del inspector: Certificada con habilita o Observada con motivo."""
    motivos = list(diferencias or [])
    monto = monto_contrato(orden.get("tareas") or [], fecha_inicio=fecha_inicio, equipos=equipos)
    if monto_declarado is not None and float(monto_declarado) > monto + 1:
        motivos.append(
            f"el cierre declara USD {float(monto_declarado):.0f} y la orden vale USD {monto:.0f}"
        )
    if motivos:
        return {
            "estado": "Observada",
            "motivo": "; ".join(motivos),
            "diferencias": motivos,
            "monto": monto,
            "habilita": None,
        }
    return {
        "estado": "Certificada",
        "motivo": None,
        "diferencias": [],
        "monto": monto,
        "habilita": habilita(orden["id"]),
    }
