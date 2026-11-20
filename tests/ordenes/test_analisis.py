"""T3.3/T3.4 · Análisis de la evidencia, borrador de orden y paso revisor."""

from sistema.ordenes import analisis, reglas
from sistema.ordenes.analisis import Evidencia

BOMBAS_OK = {"B-101": "marcha", "B-102": "marcha", "B-103": "parada"}


def test_golpeteo_en_la_dos_genera_orden_de_valvulas():
    a = analisis.analizar(Evidencia(equipo="B-102", observaciones=("hace un golpeteo metálico",)))
    assert a.falla == "F02"
    assert a.tareas == ("T-B-VAL",)
    assert a.cita == "MBP-4 §6.4"


def test_diferencial_del_filtro_b_genera_cambio_de_cartuchos_correctos():
    ev = Evidencia(equipo="F-201B", resumen="presión diferencial alta")
    a = analisis.analizar(ev)
    assert a.tareas == ("T-F-CAR",)
    orden = analisis.armar_orden(ev, a, bombas=BOMBAS_OK)
    assert orden["equipo"] == "F-201B"
    assert orden["repuestos"] == [{"codigo": "FC-CART-10", "cantidad": 48}]


def test_diferencial_del_filtro_a_usa_los_cartuchos_de_25():
    ev = Evidencia(equipo="F-201A", resumen="presión diferencial alta")
    orden = analisis.armar_orden(ev, analisis.analizar(ev), bombas=BOMBAS_OK)
    assert orden["repuestos"] == [{"codigo": "FC-CART-25", "cantidad": 48}]


def test_evidencia_insuficiente_es_una_inspeccion():
    a = analisis.analizar(Evidencia(equipo="B-101", resumen="vibración alta"))
    assert a.inspeccion
    assert a.tareas == ("I-VIB",)


def test_f10_no_exige_orden():
    a = analisis.analizar(Evidencia(equipo="B-101", observaciones=("el sensor tiene deriva",)))
    assert a.falla == "F10"
    assert a.sin_orden


def test_f09_senala_la_causa_raiz_en_otro_equipo():
    a = analisis.analizar(Evidencia(equipo="B-102", observaciones=("cavita, hace ruido a piedras",)))
    assert a.falla == "F09"
    assert a.tareas == ("I-VIB",)
    assert any("filtro primario" in c["causa"].lower() for c in a.causas)


def test_rodamiento_genera_orden_de_contratista_con_repuestos():
    ev = Evidencia(equipo="B-101", observaciones=("tiene un ruido raro de rodamiento",))
    a = analisis.analizar(ev)
    orden = analisis.armar_orden(ev, a, bombas=BOMBAS_OK)
    assert orden["tareas"] == ["T-B-ROD"]
    assert orden["ejecutor"] == "Servipat"
    codigos = {r["codigo"] for r in orden["repuestos"]}
    assert {"TX-ROD-CIG", "TX-SELLO-CAR"} <= codigos


def test_la_decision_usa_el_estado_real_de_las_bombas():
    # Tormenta: la orden de válvulas detiene la dos y la reserva está en
    # mantenimiento (no disponible) -> Pendiente con motivo.
    ev = Evidencia(equipo="B-102", observaciones=("golpeteo metálico",))
    a = analisis.analizar(ev)
    orden = analisis.armar_orden(ev, a, bombas={"B-101": "marcha", "B-102": "marcha", "B-103": "mantenimiento"})
    d = reglas.decidir(
        equipo=orden["equipo"], tareas=orden["tareas"], repuestos=orden["repuestos"],
        ejecutor=orden["ejecutor"], bombas={"B-101": "marcha", "B-102": "marcha", "B-103": "mantenimiento"},
    )
    assert d.estado == reglas.PENDIENTE
    assert any("inyección" in m for m in d.motivos)


def test_dano_estructural_siempre_pendiente_aunque_todo_lo_demas_pase():
    ev = Evidencia(equipo="B-101", observaciones=("pierde por la empaquetadura",), dano_estructural=True)
    a = analisis.analizar(ev)
    orden = analisis.armar_orden(ev, a, bombas=BOMBAS_OK)
    d = reglas.decidir(
        equipo=orden["equipo"], tareas=orden["tareas"], repuestos=orden["repuestos"],
        ejecutor=orden["ejecutor"], bombas=BOMBAS_OK, dano_estructural=True,
    )
    assert d.estado == reglas.PENDIENTE


# ---------------------------------------------------------------------- revisor


def test_revisor_acepta_citas_vigentes_y_repuestos_de_la_lista():
    ev = Evidencia(equipo="F-201B", resumen="diferencial alto")
    a = analisis.analizar(ev)
    orden = analisis.armar_orden(ev, a, bombas=BOMBAS_OK)
    problemas = analisis.revisar(orden, a, citas={"MBP-4 §6.9": True})
    assert problemas == []


def test_revisor_rechaza_cita_vencida():
    ev = Evidencia(equipo="B-101", observaciones=("goteo",))
    a = analisis.analizar(ev)
    orden = analisis.armar_orden(ev, a, bombas=BOMBAS_OK)
    problemas = analisis.revisar(orden, a, citas={"MBP-4 §6.3": False})
    assert any("vencida" in p for p in problemas)


def test_revisor_rechaza_cita_inexistente():
    ev = Evidencia(equipo="B-101", observaciones=("goteo",))
    a = analisis.analizar(ev)
    orden = analisis.armar_orden(ev, a, bombas=BOMBAS_OK)
    problemas = analisis.revisar(orden, a, citas={})
    assert any("no existe" in p for p in problemas)


def test_revisor_rechaza_repuesto_fuera_de_la_lista_de_materiales():
    ev = Evidencia(equipo="B-101", observaciones=("goteo",))
    a = analisis.analizar(ev)
    orden = analisis.armar_orden(ev, a, bombas=BOMBAS_OK)
    orden = dict(orden, repuestos=[{"codigo": "FC-CART-10", "cantidad": 1}])
    problemas = analisis.revisar(orden, a, citas={"MBP-4 §6.3": True})
    assert any("lista de materiales" in p for p in problemas)
