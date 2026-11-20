"""D · Reglas de aprobación en código: **la única puerta de aprobación**.

``decidir`` es una función pura: no habla con MQTT, con la base ni con la
planta. Recibe la orden y el estado de las bombas del momento y devuelve
``Aprobada`` o ``PendienteAprobacion`` con los motivos.

Semántica acordada con la rúbrica (``correccion/puntuar.py::reglas``):

- tarea estándar para ese equipo;
- la inyección se mantiene: si la tarea detiene el equipo y no hay **otra**
  bomba ``parada`` (una en ``mantenimiento`` no es reserva disponible);
- repuesto en la lista de materiales del equipo y con stock en el **yacimiento**;
- costo de repuestos **menor** a USD 2.500 (2.500 ya queda pendiente);
- personal propio;
- daño estructural visible en las fotos: revisión humana siempre.

Ante la duda (sin datos de planta) la decisión es conservadora: Pendiente.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import catalogo as cat

APROBADA = "Aprobada"
PENDIENTE = "PendienteAprobacion"

COSTO_MAX_USD = 2500.0
ALMACEN = "yacimiento"


@dataclass(frozen=True)
class Catalogo:
    """Datos necesarios para decidir (se inyectan en los tests)."""

    repuestos: dict[str, dict] = field(default_factory=dict)
    estandar: dict[str, set[str]] = field(default_factory=dict)
    detiene: dict[str, bool] = field(default_factory=dict)
    lista_materiales: dict[str, list[str]] = field(default_factory=dict)


def catalogo_por_defecto() -> Catalogo:
    return Catalogo(
        repuestos=cat.repuestos(),
        estandar=cat.estandar(),
        detiene=cat.detiene(),
        lista_materiales=cat.lista_materiales(),
    )


@dataclass(frozen=True)
class Decision:
    estado: str
    motivos: tuple[str, ...] = ()

    @property
    def aprobada(self) -> bool:
        return self.estado == APROBADA


def reduce_inyeccion(
    equipo: str,
    tareas: list[str],
    bombas: dict[str, str] | None,
    catalogo: Catalogo,
) -> bool | None:
    """``True`` si detener el equipo deja la planta sin reserva disponible.

    Devuelve ``None`` si la tarea detiene y no hay datos de bombas: el que
    decide tiene que ser conservador. ``mantenimiento`` no cuenta como reserva:
    solo una bomba ``parada`` está disponible.
    """
    if not any(catalogo.detiene.get(t, True) for t in tareas):
        return False
    if bombas is None:
        return None
    if bombas.get(equipo) != "marcha":
        return False
    return not any(estado == "parada" for tag, estado in bombas.items() if tag != equipo)


def costo_orden(repuestos: list[dict], catalogo: Catalogo) -> float:
    """Costo de los repuestos de la orden (los desconocidos no suman)."""
    total = 0.0
    for rep in repuestos:
        info = catalogo.repuestos.get(rep.get("codigo"))
        if info:
            total += float(info.get("costo_usd", 0)) * float(rep.get("cantidad", 0))
    return total


def decidir(
    *,
    equipo: str,
    tareas: list[str],
    repuestos: list[dict] | tuple = (),
    ejecutor: str = "propio",
    bombas: dict[str, str] | None = None,
    dano_estructural: bool = False,
    catalogo: Catalogo | None = None,
    almacen: str = ALMACEN,
    costo_max_usd: float = COSTO_MAX_USD,
) -> Decision:
    cat_ = catalogo or catalogo_por_defecto()
    motivos: list[str] = []

    if not tareas or any(t not in cat_.estandar.get(equipo, set()) for t in tareas):
        motivos.append("tarea no estándar")

    reduce = reduce_inyeccion(equipo, tareas, bombas, cat_)
    if reduce is None:
        motivos.append("sin datos de planta para verificar la inyección")
    elif reduce:
        motivos.append("reduce la inyección (no hay reserva disponible)")

    permitidos = set(cat_.lista_materiales.get(equipo, []))
    for rep in repuestos:
        codigo = rep.get("codigo")
        info = cat_.repuestos.get(codigo)
        if info is None or codigo not in permitidos:
            motivos.append(f"repuesto {codigo} fuera de la lista de materiales")
        elif float(rep.get("cantidad", 0)) > float(info.get("stock", {}).get(almacen, 0)):
            motivos.append(f"sin stock de {codigo} en el {almacen}")

    costo = costo_orden(list(repuestos), cat_)
    if costo >= costo_max_usd:
        motivos.append(f"costo USD {costo:.0f} no es menor a {costo_max_usd:.0f}")

    if ejecutor != "propio":
        motivos.append(f"ejecutor {ejecutor}: no es personal propio")

    if dano_estructural:
        motivos.append("posible daño estructural en las fotos: revisión humana")

    estado = APROBADA if not motivos else PENDIENTE
    return Decision(estado=estado, motivos=tuple(motivos))
