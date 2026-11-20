"""T2.2 · Máquina de estados y ÚNICA escritura sobre órdenes.

Reglas del anexo que se prueban acá:
- id idempotente y estable por equipo + tareas (una sola orden abierta);
- transiciones válidas, con motivo obligatorio para Pendiente/Rechazada/Observada;
- toda escritura pasa por este módulo y valida contra el contrato.
"""

from datetime import datetime, timezone

import pytest

from sistema.ordenes import estado


def _orden(**cambios) -> dict:
    base = dict(
        equipo="B-102",
        tareas=["T-B-VAL"],
        evento_ids=["EV-NOTA-1"],
        detiene_equipo=True,
        reduce_inyeccion=True,
        repuestos=[{"codigo": "TX-VAL-KIT", "cantidad": 1}],
        ejecutor="propio",
    )
    base.update(cambios)
    return estado.armar_orden(**base)


def test_id_estable_por_equipo_y_tareas():
    a = estado.id_de_orden("B-102", ["T-B-VAL"])
    assert a == estado.id_de_orden("B-102", ["T-B-VAL"])
    assert a == estado.id_de_orden("B-102", ["T-B-VAL", "T-B-VAL"])
    assert a.startswith("ORD-")
    assert a != estado.id_de_orden("B-101", ["T-B-VAL"])
    assert a != estado.id_de_orden("B-102", ["T-B-VAL", "I-VIB"])


def test_id_no_depende_del_orden_de_las_tareas():
    assert estado.id_de_orden("B-102", ["I-VIB", "T-B-VAL"]) == estado.id_de_orden(
        "B-102", ["T-B-VAL", "I-VIB"]
    )


def test_transiciones_validas():
    for desde, hacia in [
        (None, estado.BORRADOR),
        (None, estado.PENDIENTE),
        (None, estado.APROBADA),
        (estado.BORRADOR, estado.PENDIENTE),
        (estado.BORRADOR, estado.APROBADA),
        (estado.PENDIENTE, estado.APROBADA),
        (estado.PENDIENTE, estado.RECHAZADA),
        (estado.APROBADA, estado.EJECUTADA),
        (estado.EJECUTADA, estado.CERRADA),
        (estado.EJECUTADA, estado.OBSERVADA),
        (estado.EJECUTADA, estado.CERTIFICADA),
        (estado.OBSERVADA, estado.CERTIFICADA),
    ]:
        estado.validar_transicion(desde, hacia)


@pytest.mark.parametrize(
    ("desde", "hacia"),
    [
        (None, estado.EJECUTADA),
        (estado.EJECUTADA, estado.BORRADOR),
        (estado.RECHAZADA, estado.APROBADA),
        (estado.CERTIFICADA, estado.EJECUTADA),
        (estado.APROBADA, estado.PENDIENTE),
        (estado.CERRADA, estado.OBSERVADA),
    ],
)
def test_transiciones_invalidas(desde, hacia):
    with pytest.raises(estado.TransicionInvalida):
        estado.validar_transicion(desde, hacia)


def test_pendiente_sin_motivo_es_invalida():
    with pytest.raises(ValueError):
        estado.validar_decision(estado.PENDIENTE, "")


def test_rechazo_sin_motivo_es_invalido():
    with pytest.raises(ValueError):
        estado.validar_decision(estado.RECHAZADA, None)


def test_observacion_sin_motivo_es_invalida():
    with pytest.raises(ValueError):
        estado.validar_decision(estado.OBSERVADA, "  ")


def test_orden_nueva_valida_contra_el_contrato():
    orden = _orden()
    assert orden["id"].startswith("ORD-")
    assert orden["estado"] == estado.BORRADOR
    assert orden["equipo"] == "B-102"
    assert orden["repuestos"] == [{"codigo": "TX-VAL-KIT", "cantidad": 1}]
    # El contrato no acepta campos de más (extra="forbid").
    assert "correlation_id" not in orden


def test_transicion_conserva_id_y_registra_motivo():
    orden = _orden()
    pendiente = estado.transicion(orden, estado.PENDIENTE, motivo="reduce la inyección")
    assert pendiente["id"] == orden["id"]
    assert pendiente["estado"] == estado.PENDIENTE
    assert pendiente["motivo"] == "reduce la inyección"
    aprobada = estado.transicion(pendiente, estado.APROBADA, motivo=None)
    assert aprobada["estado"] == estado.APROBADA
    assert aprobada["id"] == orden["id"]


def test_ts_es_iso_y_usa_el_reloj_simulado_si_se_pasa():
    ts = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
    orden = _orden(ts=ts)
    assert orden["ts"].startswith("2026-11-09T10:00")


# ---------------------------------------------------------------------- persistencia


def test_guarda_y_publica_pasa_por_el_modulo():
    class PublicadorFalso:
        def __init__(self):
            self.mensajes = []

        def publicar(self, topico, payload):
            self.mensajes.append((topico, payload))

    try:
        estado.db.init_db()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PostgreSQL no disponible: {exc}")

    pub = PublicadorFalso()
    orden = _orden(equipo="B-101", tareas=["T-B-EMP"],
                   repuestos=[{"codigo": "TX-EMP-KIT", "cantidad": 1}])
    estado.publicar(pub, orden, correlation_id="CORR-TEST-1")

    assert pub.mensajes == [("sistema/ordenes", orden)]
    guardada = estado.db.obtener_orden(orden["id"])
    assert guardada is not None
    assert guardada["correlation_id"] == "CORR-TEST-1"
    assert guardada["estado"] == estado.BORRADOR


def test_una_sola_orden_abierta_por_equipo_y_tareas():
    try:
        estado.db.init_db()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PostgreSQL no disponible: {exc}")

    class Pub:
        def publicar(self, topico, payload):
            pass

    orden = _orden(equipo="B-103", tareas=["T-B-COR"],
                   repuestos=[{"codigo": "COR-5V-1800", "cantidad": 4}])
    estado.publicar(Pub(), orden)

    abierta = estado.db.existe_orden_abierta("B-103", ["T-B-COR"])
    assert abierta is not None
    assert abierta["id"] == orden["id"]

    cerrada = estado.transicion(orden, estado.APROBADA)
    cerrada = estado.transicion(cerrada, estado.EJECUTADA)
    cerrada = estado.transicion(cerrada, estado.CERRADA)
    estado.publicar(Pub(), cerrada)
    assert estado.db.existe_orden_abierta("B-103", ["T-B-COR"]) is None
