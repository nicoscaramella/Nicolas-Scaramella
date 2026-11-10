from datetime import datetime, timezone

from sistema.deteccion import SensorDetector, eventos_de_parte


def evento_unico(filas, planta_def):
    return eventos_de_parte("NOTA-1", filas, planta_def, datetime.now(timezone.utc))


def test_presion_normal_es_sin_novedad(planta_def):
    filas = [
        {"tag": "B-101", "variable": "presion_descarga_local", "valor": 112,
         "unidad": "kg/cm2", "observacion": None}
    ]
    [evento] = evento_unico(filas, planta_def)
    assert evento["tipo"] == "SinNovedad"
    assert evento["equipo"] == "B-101"


def test_goteo_es_escalado(planta_def):
    filas = [
        {"tag": "B-102", "variable": "goteo_empaquetadura", "valor": None,
         "unidad": "gotas/min", "observacion": "goteo por empaquetadura"}
    ]
    [evento] = evento_unico(filas, planta_def)
    assert evento["tipo"] == "Escalado"


def test_parada_en_reserva_no_es_anomalia(planta_def):
    filas = [
        {"tag": "B-103", "variable": "estado", "valor": None,
         "unidad": None, "observacion": "parada, en reserva"}
    ]
    [evento] = evento_unico(filas, planta_def)
    assert evento["tipo"] == "SinNovedad"


def test_presion_fuera_de_limite_es_escalado(planta_def):
    filas = [
        {"tag": "B-101", "variable": "presion_descarga_local", "valor": 130,
         "unidad": "kg/cm2", "observacion": None}
    ]
    [evento] = evento_unico(filas, planta_def)
    assert evento["tipo"] == "Escalado"


def test_escalado_incluye_foto_y_tendencia(planta_def):
    filas = [
        {"tag": "B-101", "variable": "presion_descarga_local", "valor": 130,
         "unidad": "kg/cm2", "observacion": "presión alta",
         "foto": "/media/fotos/descarga/01.jpg"}
    ]
    [evento] = eventos_de_parte(
        "NOTA-1",
        filas,
        planta_def,
        datetime.now(timezone.utc),
        tendencia="100–120, último 118",
    )
    assert evento["tipo"] == "Escalado"
    assert "/media/fotos/descarga/01.jpg" in evento["resumen"]
    assert "tendencia: 100–120, último 118" in evento["resumen"]


def test_un_evento_por_equipo(planta_def):
    filas = [
        {"tag": "B-101", "variable": "presion_descarga_local", "valor": 112,
         "unidad": "kg/cm2", "observacion": None},
        {"tag": "B-102", "variable": "goteo_empaquetadura", "valor": None,
         "unidad": "gotas/min", "observacion": "goteo por empaquetadura"},
    ]
    eventos = evento_unico(filas, planta_def)
    assert {e["equipo"] for e in eventos} == {"B-101", "B-102"}
    assert {e["tipo"] for e in eventos} == {"SinNovedad", "Escalado"}


def test_sin_filas_es_sin_novedad_sin_equipo(planta_def):
    [evento] = evento_unico([], planta_def)
    assert evento["tipo"] == "SinNovedad"
    assert evento["equipo"] is None


def test_placeholder_planta_no_genera_escalado(planta_def):
    filas = [{"tag": "PLANTA", "variable": "estado", "valor": None,
              "unidad": None, "observacion": "sin novedad"}]
    [evento] = evento_unico(filas, planta_def)
    assert evento["tipo"] == "SinNovedad"
    assert evento["equipo"] is None


def test_sensor_sostenido(planta_def):
    detector = SensorDetector(planta_def, muestras=5)
    evento = None
    for i in range(5):
        evento = detector.ingestar(
            {"tag": "B-101", "variable": "vibracion", "valor": 12.0,
             "unidad": "mm/s", "ts": f"2026-11-09T10:0{i}:00-03:00"}
        )
    assert evento is not None
    assert evento["tipo"] == "Escalado"
    assert evento["origen"] == "sensor"


def test_sensor_normal_no_dispara(planta_def):
    detector = SensorDetector(planta_def, muestras=5)
    for i in range(8):
        evento = detector.ingestar(
            {"tag": "B-101", "variable": "vibracion", "valor": 2.0,
             "unidad": "mm/s", "ts": f"2026-11-09T10:0{i}:00-03:00"}
        )
        assert evento is None
