"""T2.1 · Reglas de aprobación en código (función pura).

Casos límite congelados del Anexo Entrega 2 y un test diferencial contra el
corrector real (academia2026-tp/correccion/puntuar.py) cuando está disponible.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from sistema.ordenes import reglas


# ---------------------------------------------------------------------- helpers


def _catalogo_simple(**extra) -> reglas.Catalogo:
    """Catálogo mínimo para probar los bordes de costo sin tocar los datos."""
    repuestos = {
        "TEST-2499": {"codigo": "TEST-2499", "costo_usd": 2499, "stock": {"yacimiento": 5}},
        "TEST-2500": {"codigo": "TEST-2500", "costo_usd": 2500, "stock": {"yacimiento": 5}},
    }
    repuestos.update(extra.pop("repuestos", {}))
    return reglas.Catalogo(
        repuestos=repuestos,
        estandar={"B-101": {"T-TEST"}},
        detiene={"T-TEST": False},
        lista_materiales={"B-101": ["TEST-2499", "TEST-2500"]},
    )


def _bombas(marcha=("B-101", "B-102"), mantenimiento=(), parada=("B-103",)) -> dict:
    estado = {t: "marcha" for t in marcha}
    estado.update({t: "mantenimiento" for t in mantenimiento})
    estado.update({t: "parada" for t in parada})
    return estado


# ---------------------------------------------------------------------- casos del anexo


def test_orden_estandar_propia_con_stock_aprueba():
    d = reglas.decidir(
        equipo="B-101",
        tareas=["T-B-EMP"],
        repuestos=[{"codigo": "TX-EMP-KIT", "cantidad": 1}],
        ejecutor="propio",
        bombas=_bombas(),
    )
    assert d.estado == reglas.APROBADA
    assert d.motivos == ()


def test_costo_2499_aprueba_y_2500_queda_pendiente():
    cat = _catalogo_simple()
    abajo = reglas.decidir(
        equipo="B-101", tareas=["T-TEST"],
        repuestos=[{"codigo": "TEST-2499", "cantidad": 1}],
        ejecutor="propio", bombas=_bombas(), catalogo=cat,
    )
    borde = reglas.decidir(
        equipo="B-101", tareas=["T-TEST"],
        repuestos=[{"codigo": "TEST-2500", "cantidad": 1}],
        ejecutor="propio", bombas=_bombas(), catalogo=cat,
    )
    assert abajo.aprobada
    assert not borde.aprobada
    assert any("costo" in m for m in borde.motivos)


def test_t_b_val_1900_aprueba():
    # El kit de válvulas cuesta USD 1.900 y hay 1 en el yacimiento.
    d = reglas.decidir(
        equipo="B-102",
        tareas=["T-B-VAL"],
        repuestos=[{"codigo": "TX-VAL-KIT", "cantidad": 1}],
        ejecutor="propio",
        bombas=_bombas(),
    )
    assert d.aprobada


def test_tx_rod_cig_sin_stock_en_el_yacimiento_queda_pendiente():
    # Rodamientos: no estándar, contratista y sin stock en el yacimiento.
    d = reglas.decidir(
        equipo="B-101",
        tareas=["T-B-ROD"],
        repuestos=[{"codigo": "TX-ROD-CIG", "cantidad": 1}],
        ejecutor="Servipat",
        bombas=_bombas(),
    )
    assert not d.aprobada
    texto = " ".join(d.motivos)
    assert "no estándar" in texto
    assert "contratista" in texto or "personal propio" in texto
    assert "TX-ROD-CIG" in texto


def test_reserva_no_disponible_queda_pendiente():
    # La orden detiene la dos y la reserva (la tres) está en mantenimiento:
    # "mantenimiento" NO cuenta como reserva disponible (igual que el corrector).
    d = reglas.decidir(
        equipo="B-102",
        tareas=["T-B-VAL"],
        repuestos=[{"codigo": "TX-VAL-KIT", "cantidad": 1}],
        ejecutor="propio",
        bombas={"B-101": "marcha", "B-102": "marcha", "B-103": "mantenimiento"},
    )
    assert not d.aprobada
    assert any("inyección" in m for m in d.motivos)


def test_reserva_parada_habilita_la_aprobacion():
    d = reglas.decidir(
        equipo="B-102",
        tareas=["T-B-VAL"],
        repuestos=[{"codigo": "TX-VAL-KIT", "cantidad": 1}],
        ejecutor="propio",
        bombas={"B-101": "marcha", "B-102": "marcha", "B-103": "parada"},
    )
    assert d.aprobada


def test_repuesto_fuera_de_la_lista_de_materiales_queda_pendiente():
    # Un cartucho de filtro no corresponde a una bomba.
    d = reglas.decidir(
        equipo="B-101",
        tareas=["T-B-EMP"],
        repuestos=[{"codigo": "FC-CART-10", "cantidad": 1}],
        ejecutor="propio",
        bombas=_bombas(),
    )
    assert not d.aprobada
    assert any("lista de materiales" in m for m in d.motivos)


def test_dano_estructural_siempre_va_a_revision_humana():
    d = reglas.decidir(
        equipo="B-101",
        tareas=["T-B-EMP"],
        repuestos=[{"codigo": "TX-EMP-KIT", "cantidad": 1}],
        ejecutor="propio",
        bombas=_bombas(),
        dano_estructural=True,
    )
    assert not d.aprobada
    assert any("estructural" in m for m in d.motivos)


def test_sin_datos_de_bombas_es_conservador_solo_si_detiene():
    # Una tarea que no detiene no necesita el estado de las bombas.
    no_detiene = reglas.decidir(
        equipo="B-101", tareas=["T-B-ACE"],
        repuestos=[{"codigo": "ACE-ISO220", "cantidad": 8}],
        ejecutor="propio", bombas=None,
    )
    assert no_detiene.aprobada
    # Una que sí detiene, sin datos, va a Pendiente con motivo.
    detiene = reglas.decidir(
        equipo="B-101", tareas=["T-B-EMP"],
        repuestos=[{"codigo": "TX-EMP-KIT", "cantidad": 1}],
        ejecutor="propio", bombas=None,
    )
    assert not detiene.aprobada
    assert any("sin datos de planta" in m for m in detiene.motivos)


def test_sin_tareas_queda_pendiente():
    d = reglas.decidir(equipo="B-101", tareas=[], bombas=_bombas())
    assert not d.aprobada
    assert any("no estándar" in m for m in d.motivos)


# ---------------------------------------------------------------------- diferencial


def _corrector() -> Path | None:
    candidatos = [os.environ.get("CORRECTOR_DIR"), "/academia2026-tp",
                  str(Path(__file__).resolve().parents[3] / "academia2026-tp")]
    for c in candidatos:
        if c and (Path(c) / "correccion" / "puntuar.py").is_file():
            return Path(c)
    return None


@pytest.fixture(scope="module")
def puntuar():
    raiz = _corrector()
    if raiz is None:
        pytest.skip("corrector no disponible: montar academia2026-tp para el test diferencial")
    spec = importlib.util.spec_from_file_location("puntuar_ref", raiz / "correccion" / "puntuar.py")
    modulo = importlib.util.module_from_spec(spec)
    # dataclasses necesita el módulo en sys.modules para resolver anotaciones.
    import sys

    sys.modules["puntuar_ref"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _casos_diferenciales():
    return [
        dict(equipo="B-101", tareas=["T-B-EMP"], repuestos=[{"codigo": "TX-EMP-KIT", "cantidad": 1}],
             ejecutor="propio", bombas={"B-101": "marcha", "B-102": "marcha", "B-103": "parada"}),
        dict(equipo="B-102", tareas=["T-B-VAL"], repuestos=[{"codigo": "TX-VAL-KIT", "cantidad": 1}],
             ejecutor="propio", bombas={"B-101": "marcha", "B-102": "marcha", "B-103": "mantenimiento"}),
        dict(equipo="B-101", tareas=["T-B-ROD"], repuestos=[{"codigo": "TX-ROD-CIG", "cantidad": 1}],
             ejecutor="Servipat", bombas={"B-101": "marcha", "B-102": "marcha", "B-103": "parada"}),
        dict(equipo="B-101", tareas=["T-B-EMP"], repuestos=[{"codigo": "FC-CART-10", "cantidad": 1}],
             ejecutor="propio", bombas={"B-101": "marcha", "B-102": "marcha", "B-103": "parada"}),
        dict(equipo="F-201B", tareas=["T-F-CAR"], repuestos=[{"codigo": "FC-CART-10", "cantidad": 48}],
             ejecutor="propio", bombas={"B-101": "marcha", "B-102": "marcha", "B-103": "parada"}),
        dict(equipo="B-101", tareas=["T-B-ACE"], repuestos=[{"codigo": "ACE-ISO220", "cantidad": 8}],
             ejecutor="propio", bombas={}),
        dict(equipo="B-103", tareas=["I-VIB"], repuestos=[],
             ejecutor="propio", bombas={"B-101": "marcha", "B-102": "marcha", "B-103": "marcha"}),
    ]


def test_diferencial_las_reglas_coinciden_con_el_corrector(puntuar):
    p = {"costo_max_usd": 2500, "almacen": "yacimiento", "exigir_motivo": True, "siempre_pendiente": {}}
    for caso in _casos_diferenciales():
        payload = {
            "id": "ORD-TEST", "ts": "2026-11-20T10:00:00-03:00", "estado": "PendienteAprobacion",
            "equipo": caso["equipo"], "tareas": caso["tareas"], "repuestos": caso["repuestos"],
            "ejecutor": caso["ejecutor"], "detiene_equipo": True, "reduce_inyeccion": False,
        }
        ours = reglas.decidir(**caso)
        fallan = puntuar.reglas({"payload": payload, "planta": {"bombas": caso["bombas"]}}, "test", p)
        assert (not ours.motivos) == (not fallan), f"{caso}: nuestras={ours.motivos} corrector={fallan}"


def test_nuestro_catalogo_es_el_mismo_del_corrector(puntuar):
    cat = reglas.catalogo_por_defecto()
    assert set(cat.repuestos) == set(puntuar.REPUESTOS)
    for codigo, info in cat.repuestos.items():
        assert info["costo_usd"] == puntuar.REPUESTOS[codigo]["costo_usd"]
        assert info["stock"] == puntuar.REPUESTOS[codigo]["stock"]
    for equipo, tareas in puntuar.ESTANDAR.items():
        assert set(tareas) <= cat.estandar.get(equipo, set())
    assert cat.detiene == puntuar.DETIENE
    assert cat.lista_materiales == puntuar.MATERIALES["lista_materiales"]
