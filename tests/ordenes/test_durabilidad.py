"""M4 · Tests de durabilidad, reintentos, deadlines y loops."""

import uuid

import pytest

from sistema import db
from sistema.ordenes import estado, repositorio, workflow


class PublicadorFalso:
    def __init__(self):
        self.mensajes = []

    def publicar(self, topico, payload):
        self.mensajes.append((topico, payload))


def _orden(equipo="B-101", tareas=("T-B-EMP",)):
    return estado.armar_orden(
        equipo=equipo, tareas=list(tareas), evento_ids=["EV-1"],
        repuestos=[{"codigo": "TX-EMP-KIT", "cantidad": 1}],
    )


def test_recuperacion_republica_abiertas_con_el_mismo_estado():
    try:
        db.init_db()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PostgreSQL no disponible: {exc}")

    pub = PublicadorFalso()
    # Equipo único por test para no chocar con corridas anteriores.
    equipo = f"B-9{uuid.uuid4().int % 10}"
    orden = _orden(equipo=equipo)
    pendiente = estado.transicion(orden, estado.PENDIENTE, motivo="sin stock")
    estado.publicar(pub, pendiente, correlation_id="CORR-REC-1")

    recuperadas = repositorio.recuperar(pub)
    recientes = [
        (t, p) for t, p in pub.mensajes
        if t == "sistema/ordenes" and p.get("id") == pendiente["id"]
    ]
    assert recuperadas >= 1
    assert any(p["estado"] == estado.PENDIENTE for _, p in recientes)
    # Nunca se republica como Borrador.
    assert not any(p["estado"] == estado.BORRADOR for _, p in recientes)


# ---------------------------------------------------------------------- workflow


def test_reintenta_hasta_lograr():
    intentos = {"n": 0}

    def falla_dos_veces():
        intentos["n"] += 1
        if intentos["n"] < 3:
            raise ConnectionError("caído")
        return "ok"

    assert workflow.con_reintentos(falla_dos_veces, intentos=3, espera=0) == "ok"
    assert intentos["n"] == 3


def test_propaga_el_error_despues_de_los_intentos():
    with pytest.raises(ConnectionError):
        workflow.con_reintentos(
            lambda: (_ for _ in ()).throw(ConnectionError("siempre falla")),
            intentos=2, espera=0,
        )


def test_deadline_usa_el_reloj_inyectado():
    ahora = {"t": 0.0}
    d = workflow.Deadline(10, reloj=lambda: ahora["t"])
    ahora["t"] = 9.9
    d.verificar()
    ahora["t"] = 10.0
    with pytest.raises(workflow.TiempoAgotado):
        d.verificar()


def test_detector_de_loops_corta_al_cuarto_intento():
    ahora = {"t": 0.0}
    detector = workflow.DetectorDeLoops(maximo=3, ventana_s=3600, reloj=lambda: ahora["t"])
    for _ in range(3):
        detector.registrar("B-102|T-B-VAL")
        ahora["t"] += 10
    with pytest.raises(workflow.LoopDetectado):
        detector.registrar("B-102|T-B-VAL")


def test_detector_de_loops_se_limpia_al_pasar_la_ventana():
    ahora = {"t": 0.0}
    detector = workflow.DetectorDeLoops(maximo=2, ventana_s=60, reloj=lambda: ahora["t"])
    detector.registrar("B-102|T-B-VAL")
    detector.registrar("B-102|T-B-VAL")
    ahora["t"] = 61
    detector.registrar("B-102|T-B-VAL")  # la ventana anterior ya no cuenta
