"""C · Análisis de la evidencia: causas ordenadas y borrador de orden.

Entrada: el parte confirmado, las fotos y la tendencia del historian. Con eso
se elige la falla más probable (con su cita del MBP-4), se enriquecen las
causas con el historial de órdenes y se arma la ``OrdenSistema`` completa.

La decisión de aprobarla o dejarla pendiente NO se toma acá: la toma
``reglas.decidir`` (función pura) y la escribe ``estado.publicar``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .. import db
from . import catalogo, causas, estado, reglas

INSPECCIONES = {"I-VIB", "I-VAL"}
EQUIPOS_VALIDOS = ("B-", "F-")
CONTRATISTA = "Servipat"


@dataclass(frozen=True)
class Evidencia:
    """Todo lo que el análisis puede mirar de un caso."""

    equipo: str
    resumen: str = ""
    observaciones: tuple[str, ...] = ()
    variables: dict[str, float] = field(default_factory=dict)
    tendencia: str | None = None
    dano_estructural: bool = False
    fotos: tuple[str, ...] = ()
    evento_ids: tuple[str, ...] = ()
    historial: tuple[dict, ...] = ()


@dataclass(frozen=True)
class Analisis:
    falla: str | None
    tareas: tuple[str, ...]
    causas: tuple[dict, ...]
    cita: str | None
    inspeccion: bool
    sin_orden: bool = False


def _texto(ev: Evidencia) -> str:
    return " ".join(x for x in (ev.resumen, *ev.observaciones) if x).strip()


def _por_variables(ev: Evidencia) -> str | None:
    tipo = causas.tipo_de_equipo(ev.equipo)
    if tipo == "filtro" and "presion_diferencial" in ev.variables:
        return "F07"
    if tipo == "bomba":
        if "temperatura_aceite" in ev.variables and "vibracion" in ev.variables:
            return "F03"
        if "presion_succion" in ev.variables:
            return "F09"
    return None


def analizar(ev: Evidencia) -> Analisis:
    """Elige la falla y ordena las causas por evidencia."""
    texto = _texto(ev)
    codigo = causas.clasificar(ev.equipo, texto)
    if codigo is None and ev.variables:
        codigo = _por_variables(ev)

    if codigo is None:
        # La evidencia no alcanza para una causa: se inspecciona.
        return Analisis(
            falla=None, tareas=("I-VIB",), causas=(), cita=None, inspeccion=True
        )

    falla = causas.FALLAS[codigo]
    ordenadas: list[dict] = [
        {
            "falla": codigo,
            "causa": falla.nombre,
            "cita": falla.cita,
            "evidencia": (texto or ev.equipo)[:240],
            "falta": (
                "identificar el equipo de origen"
                if falla.raiz_en_otro_equipo
                else "confirmar con la prueba en marcha"
            ),
        }
    ]
    ordenadas.extend(causas.patrones_de_historial(ev.equipo, texto, list(ev.historial)))

    vistas: set[tuple] = set()
    unicas: list[dict] = []
    for causa in ordenadas:
        clave = (causa.get("falla"), causa.get("causa"))
        if clave in vistas:
            continue
        vistas.add(clave)
        unicas.append(causa)

    return Analisis(
        falla=codigo,
        tareas=falla.tareas,
        causas=tuple(unicas),
        cita=falla.cita,
        inspeccion=falla.raiz_en_otro_equipo
        or all(t in INSPECCIONES for t in falla.tareas),
        sin_orden=falla.sin_orden,
    )


def _repuestos(equipo: str, tareas: list[str], falla: str | None) -> list[dict]:
    crudos: list[dict] = []
    for tarea in tareas:
        crudos.extend(catalogo.repuestos_de_la_tarea(tarea, equipo))
    crudos.extend(causas.repuestos_sugeridos(falla))
    por_codigo: dict[str, float] = {}
    for rep in crudos:
        codigo = rep["codigo"]
        por_codigo[codigo] = max(por_codigo.get(codigo, 0), float(rep["cantidad"]))
    return [{"codigo": c, "cantidad": cant} for c, cant in por_codigo.items()]


def _ejecutor(equipo: str, tareas: list[str]) -> str:
    for tarea in tareas:
        definicion = catalogo.tarea_para(tarea, equipo) or {}
        if definicion.get("ejecutor") == "contratista":
            return CONTRATISTA
    return "propio"


def armar_orden(
    ev: Evidencia,
    analisis_: Analisis,
    *,
    bombas: dict[str, str] | None,
    cat: reglas.Catalogo | None = None,
    ts: datetime | str | None = None,
) -> dict:
    """Arma la ``OrdenSistema`` completa con repuestos, ejecutor e inyección."""
    cat_ = cat or reglas.catalogo_por_defecto()
    tareas = list(analisis_.tareas)
    repuestos = _repuestos(ev.equipo, tareas, analisis_.falla)
    reduce = reglas.reduce_inyeccion(ev.equipo, tareas, bombas, cat_)
    return estado.armar_orden(
        equipo=ev.equipo,
        tareas=tareas,
        evento_ids=list(ev.evento_ids),
        detiene_equipo=any(cat_.detiene.get(t, True) for t in tareas),
        reduce_inyeccion=True if reduce is None else bool(reduce),
        repuestos=repuestos,
        ejecutor=_ejecutor(ev.equipo, tareas),
        ts=ts,
    )


def procesar(
    ev: Evidencia,
    publicador,
    *,
    bombas: dict[str, str] | None,
    cat: reglas.Catalogo | None = None,
) -> dict | None:
    """De la evidencia a la orden publicada (Borrador → Aprobada/Pendiente).

    Si ya hay una orden abierta del mismo equipo con las mismas tareas, no se
    duplica: se devuelve la existente (la evidencia nueva se agrega a esa).
    """
    if not ev.equipo or not ev.equipo.startswith(EQUIPOS_VALIDOS):
        return None
    analisis_ = analizar(ev)
    if analisis_.sin_orden or not analisis_.tareas:
        return None
    existente = db.existe_orden_abierta(ev.equipo, list(analisis_.tareas))
    if existente:
        return dict(existente["payload"])

    borrador = armar_orden(ev, analisis_, bombas=bombas, cat=cat)
    correlacion = f"CORR-{borrador['id']}"
    estado.publicar(publicador, borrador, correlation_id=correlacion)

    decision = reglas.decidir(
        equipo=borrador["equipo"],
        tareas=borrador["tareas"],
        repuestos=borrador["repuestos"],
        ejecutor=borrador["ejecutor"],
        bombas=bombas,
        dano_estructural=ev.dano_estructural,
        catalogo=cat,
    )
    final = estado.transicion(
        borrador,
        decision.estado,
        motivo="; ".join(decision.motivos) if decision.motivos else None,
    )
    estado.publicar(publicador, final, correlation_id=correlacion)
    return final


def revisar(
    orden: dict,
    analisis_: Analisis,
    *,
    citas: dict[str, bool] | None = None,
) -> list[str]:
    """Paso revisor: cada cita existe y está vigente; cada repuesto es de la lista.

    Devuelve la lista de problemas (vacía = el análisis pasa la revisión).
    """
    disponibles = citas if citas is not None else db.citas_del_corpus()
    problemas: list[str] = []
    usadas = {analisis_.cita} if analisis_.cita else set()
    usadas |= {c.get("cita") for c in analisis_.causas if c.get("cita")}
    for cita in sorted(usadas):
        if cita not in disponibles:
            problemas.append(f"cita {cita} no existe en el corpus")
        elif not disponibles[cita]:
            problemas.append(f"cita {cita} está vencida")
    permitidos = set(catalogo.lista_materiales().get(orden.get("equipo"), []))
    for rep in orden.get("repuestos", []):
        if rep.get("codigo") not in permitidos:
            problemas.append(
                f"repuesto {rep.get('codigo')} fuera de la lista de materiales de "
                f"{orden.get('equipo')}"
            )
    return problemas
