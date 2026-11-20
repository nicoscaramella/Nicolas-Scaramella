"""T3.1/T3.2 · Catálogo de fallas con cita y causas probables por historial.

Las citas salen del MBP-4 §6 (catálogo de fallas) y §6.14 (el historial cambia
la causa probable). Los patrones del historial son los cinco del anexo.
"""

from sistema.ordenes import causas


def test_cada_falla_tiene_tarea_y_cita_vigente_del_manual():
    for codigo, falla in causas.FALLAS.items():
        assert falla.tareas, codigo
        assert falla.cita.startswith("MBP-4 §6."), codigo


def test_clasifica_golpeteo_como_f02():
    assert causas.clasificar("B-102", "hace un golpeteo metálico") == "F02"


def test_clasifica_ruido_de_rodamiento_como_f03():
    assert causas.clasificar("B-101", "tiene un ruido raro de rodamiento") == "F03"


def test_clasifica_goteo_como_f01():
    assert causas.clasificar("B-101", "pierde por la empaquetadura, hay goteo") == "F01"


def test_clasifica_diferencial_alto_en_filtro_como_f07():
    assert causas.clasificar("F-201B", "presión diferencial alta, cartuchos colmatados") == "F07"


def test_clasifica_cavitacion_como_f09():
    assert causas.clasificar("B-102", "cavita, hace ruido a piedras") == "F09"


def test_clasifica_deriva_de_sensor_como_f10():
    assert causas.clasificar("B-101", "el sensor tiene deriva, no coincide con el manómetro") == "F10"


def test_texto_desconocido_no_inventa_falla():
    assert causas.clasificar("B-101", "todo normal") is None


def test_f09_senala_causa_raiz_en_otro_equipo():
    falla = causas.FALLAS["F09"]
    assert falla.raiz_en_otro_equipo
    assert "I-VIB" in falla.tareas


def test_f10_no_exige_orden():
    assert causas.FALLAS["F10"].sin_orden


# ---------------------------------------------------------------------- historial


def _orden(equipo, tareas, dias, aviso="", trabajo=""):
    from datetime import datetime, timedelta, timezone

    base = datetime.now(timezone.utc) - timedelta(days=dias)
    return {
        "id": f"OT-{equipo}-{dias}", "equipo": equipo, "tareas": tareas,
        "fecha": base.isoformat(), "aviso": aviso, "trabajo_realizado": trabajo,
    }


def test_historial_vibracion_que_sigue_tras_cambiar_valvulas_sugiere_acople():
    historial = [
        _orden("B-101", ["T-B-VAL"], 40, aviso="vibración alta en B1"),
        _orden("B-101", ["T-B-VAL"], 15, aviso="B1 vibración subiendo"),
    ]
    patrones = causas.patrones_de_historial("B-101", "sigue con vibración", historial)
    assert any("acople" in p["causa"].lower() for p in patrones)
    assert any(p["falla"] == "F06" for p in patrones)


def test_historial_empaquetadura_repetida_sugiere_embolo_rayado():
    historial = [
        _orden("B-103", ["T-B-EMP"], 35, aviso="pierde por empaquetadura"),
        _orden("B-103", ["T-B-EMP"], 5, aviso="vuelve a perder por empaquetadura"),
    ]
    patrones = causas.patrones_de_historial("B-103", "goteo otra vez", historial)
    assert any("émbolo" in p["causa"].lower() or "embolo" in p["causa"].lower() for p in patrones)


def test_historial_valvulas_en_dos_bombas_sugiere_cartucho_roto_del_filtro():
    historial = [
        _orden("B-101", ["T-B-VAL"], 10),
        _orden("B-102", ["T-B-VAL"], 6),
    ]
    patrones = causas.patrones_de_historial("B-101", "", historial)
    assert any("cartucho" in p["causa"].lower() and "F-201" in p["causa"] for p in patrones)


def test_historial_cavitacion_de_la_dos_sugiere_filtro_primario():
    patrones = causas.patrones_de_historial("B-102", "la dos cavita y hace ruido a piedras", [])
    assert any("filtro primario" in p["causa"].lower() for p in patrones)
    assert any(p["falla"] == "F07" and "F-201A" in p["causa"] for p in patrones)


def test_historial_consumo_de_aceite_sugiere_reten_del_pinon():
    historial = [
        _orden("B-102", ["T-B-ACE"], 20, aviso="consumo de aceite alto"),
        _orden("B-102", ["T-B-ACE"], 4, aviso="otra vez bajo el aceite"),
    ]
    patrones = causas.patrones_de_historial("B-102", "consume aceite", historial)
    assert any("retén" in p["causa"].lower() or "reten" in p["causa"].lower() for p in patrones)
