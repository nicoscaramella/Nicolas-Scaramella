from datetime import datetime, timezone

from sistema.deteccion import eventos_de_parte
from sistema.tablet import payload_borrador


def test_ids_de_eventos_estables(planta_def):
    filas = [
        {"tag": "B-101", "variable": "presion_descarga_local", "valor": 112,
         "unidad": "kg/cm2", "observacion": None},
        {"tag": "B-102", "variable": "goteo_empaquetadura", "valor": None,
         "unidad": "gotas/min", "observacion": "goteo por empaquetadura"},
    ]
    ts = datetime.now(timezone.utc)
    a = eventos_de_parte("NOTA-1", filas, planta_def, ts)
    b = eventos_de_parte("NOTA-1", filas, planta_def, ts)
    assert [e["id"] for e in a] == [e["id"] for e in b]
    assert len({e["id"] for e in a}) == 2


def test_ids_de_borrador_por_intento():
    filas = [{"tag": "B-101", "variable": "estado", "valor": None,
              "unidad": None, "observacion": "sin novedad"}]
    assert payload_borrador("NOTA-1", filas, 1)["id"] != payload_borrador("NOTA-1", filas, 2)["id"]
