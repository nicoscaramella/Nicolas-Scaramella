"""T1.1 · Ruteo por tipo de mensaje.

El anexo pide rutear seguridad, parte, sensor, respuesta del operador y cierre.
La seguridad no tiene tópico propio: sale de una nota o lectura y la resuelve
el flujo de la nota; acá se fija el vocabulario y el ruteo por tópico.
"""

import pytest

from sistema import ruteo


@pytest.mark.parametrize(
    ("topico", "esperado"),
    [
        ("planta/recorridas", ruteo.PARTE),
        ("planta/respuestas", ruteo.RESPUESTA),
        ("planta/cierres", ruteo.CIERRE),
        ("planta/energia", ruteo.ENERGIA),
        ("planta/sensores/B-101/presion_descarga", ruteo.SENSOR),
        ("planta/sensores/F-201B/presion_diferencial", ruteo.SENSOR),
    ],
)
def test_clasifica_cada_topico(topico, esperado):
    assert ruteo.clasificar(topico) == esperado


@pytest.mark.parametrize(
    "topico",
    ["sistema/estado", "otro/topico", "planta/sensores", "", "planta/"],
)
def test_topico_desconocido_no_rutea(topico):
    assert ruteo.clasificar(topico) is None


def test_el_vocabulario_del_anexo_esta_completo():
    for tipo in (ruteo.SEGURIDAD, ruteo.PARTE, ruteo.SENSOR, ruteo.RESPUESTA, ruteo.CIERRE):
        assert isinstance(tipo, str) and tipo


# ---------------------------------------------------------------------- T1.2 energía


def test_energia_presente():
    assert ruteo.energia_disponible({"ts": "2026-11-06T15:30:00-03:00", "hay_energia": True}) is True


def test_energia_cortada():
    assert ruteo.energia_disponible({"ts": "2026-11-06T15:30:00-03:00", "hay_energia": False}) is False


def test_energia_sin_dato_asume_presente():
    # Sin campo, el sistema no inventa un corte: sigue operando.
    assert ruteo.energia_disponible({}) is True
