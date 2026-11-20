"""M7 · Cierre y certificación.

- El cierre se transcribe, se arma el parte (tareas, repuestos, horas, prueba)
  y la orden pasa a Ejecutada.
- El monto del habilita sale de la orden y de CT-SVP-2025, nunca del cierre.
- Regresión con ``cierres_ejemplo.json``: cada caso real del contrato.
"""

import json
from pathlib import Path

import pytest

from sistema.ordenes import certificacion, cierre


TEXTO = (
    "Cierro la orden OT 25 0026. Hice cambio de válvulas de succión y descarga. "
    "Usé un kit de válvulas de succión y descarga TX-350. "
    "Probé a ciento diez kilos, sin pérdida. Fueron 6,5 horas."
)


def _orden(**cambios):
    base = {
        "id": "ORD-TEST", "equipo": "B-102", "tareas": ["T-B-VAL"],
        "repuestos": [{"codigo": "TX-VAL-KIT", "cantidad": 1}],
        "ejecutor": "propio", "estado": "Aprobada",
    }
    base.update(cambios)
    return base


def test_parsea_tareas_repuestos_horas_y_prueba():
    parte = cierre.parsear_cierre(TEXTO, "B-102")
    assert parte.tareas == ("T-B-VAL",)
    assert parte.repuestos == ({"codigo": "TX-VAL-KIT", "cantidad": 1},)
    assert parte.horas == 6.5
    assert "ciento diez kilos" in (parte.prueba or "")


def test_compara_y_marca_repuesto_extra():
    parte = cierre.ParteCierre(
        tareas=("T-B-VAL",),
        repuestos=({"codigo": "TX-VAL-KIT", "cantidad": 1}, {"codigo": "TX-SELLO-CAR", "cantidad": 1}),
        horas=6.0, prueba=None, texto="",
    )
    problemas = cierre.comparar(_orden(), parte)
    assert any("TX-SELLO-CAR" in p and "no estaba en la orden" in p for p in problemas)


def test_compara_y_marca_doble_cantidad():
    parte = cierre.ParteCierre(
        tareas=("T-B-VAL",),
        repuestos=({"codigo": "TX-VAL-KIT", "cantidad": 2},),
        horas=6.0, prueba=None, texto="",
    )
    problemas = cierre.comparar(_orden(), parte)
    assert any("cantidad de TX-VAL-KIT" in p for p in problemas)


def test_compara_y_marca_tarea_faltante():
    parte = cierre.ParteCierre(tareas=(), repuestos=(), horas=6.0, prueba=None, texto="")
    problemas = cierre.comparar(_orden(), parte)
    assert any("T-B-VAL" in p and "no informada" in p for p in problemas)


def test_compara_horas_contra_el_registro_de_ingreso():
    parte = cierre.ParteCierre(tareas=("T-B-VAL",), repuestos=(),
                               horas=26.5, prueba=None, texto="")
    problemas = cierre.comparar(_orden(), parte, horas_registro=17.5)
    assert any("horas" in p.lower() for p in problemas)


# ---------------------------------------------------------------------- certificación


def test_monto_usa_la_lista_vigente_por_fecha_de_inicio():
    assert certificacion.monto_contrato(["I-VIB"], fecha_inicio="2026-01-01", equipos=3) == 960
    assert certificacion.monto_contrato(["I-VIB"], fecha_inicio="2024-11-05", equipos=3) == 840
    assert certificacion.monto_contrato(["T-B-ROD"], fecha_inicio="2024-11-21") == 980
    assert certificacion.monto_contrato(["T-B-ROD"], fecha_inicio="2026-01-01") == 1150
    assert certificacion.monto_contrato(["T-B-ALI"], fecha_inicio="2025-03-11") == 780


def test_sin_diferencias_certifica_con_habilita_y_monto():
    resultado = certificacion.evaluar(
        _orden(tareas=["T-B-ROD"], repuestos=[{"codigo": "TX-ROD-CIG", "cantidad": 1}]),
        cierre.ParteCierre(tareas=("T-B-ROD",), repuestos=({"codigo": "TX-ROD-CIG", "cantidad": 1},),
                          horas=16.0, prueba=None, texto=""),
        diferencias=[], fecha_inicio="2026-01-01",
    )
    assert resultado["estado"] == "Certificada"
    assert resultado["habilita"].startswith("HAB-")
    assert resultado["monto"] == 1150


def test_con_diferencias_observa_con_motivo():
    resultado = certificacion.evaluar(
        _orden(), cierre.ParteCierre(tareas=("T-B-VAL",), repuestos=(),
                                    horas=6.0, prueba=None, texto=""),
        diferencias=["repuesto TX-SELLO-CAR no estaba en la orden"],
        fecha_inicio="2026-01-01",
    )
    assert resultado["estado"] == "Observada"
    assert "TX-SELLO-CAR" in resultado["motivo"]
    assert resultado.get("habilita") is None


def test_monto_declarado_mayor_es_una_diferencia():
    resultado = certificacion.evaluar(
        _orden(tareas=["T-B-ALI"], repuestos=[]),
        cierre.ParteCierre(tareas=("T-B-ALI",), repuestos=(), horas=5, prueba=None, texto=""),
        diferencias=[], fecha_inicio="2026-01-01", monto_declarado=1245,
    )
    assert resultado["estado"] == "Observada"


# ---------------------------------------------------------------------- regresión


def _ruta_ejemplos() -> Path | None:
    for raiz in (Path("/academia2026-tp"), Path(__file__).resolve().parents[3] / "academia2026-tp"):
        ruta = raiz / "datos" / "documentos" / "contrato" / "cierres_ejemplo.json"
        if ruta.is_file():
            return ruta
    return None


def test_regresion_cierres_de_ejemplo():
    ruta = _ruta_ejemplos()
    if ruta is None:
        pytest.skip("cierres_ejemplo.json no disponible")
    ejemplos = json.loads(ruta.read_text(encoding="utf-8"))

    for ejemplo in ejemplos:
        orden = {
            "id": f"ORD-{ejemplo['orden_id']}", "equipo": ejemplo["equipo"],
            "tareas": ejemplo["tareas"], "repuestos": ejemplo["repuestos_orden"],
            "ejecutor": "Servipat", "estado": "Ejecutada",
        }
        parte = cierre.parsear_cierre(ejemplo["cierre_texto"], ejemplo["equipo"])
        equipos = 3 if "I-VIB" in ejemplo["tareas"] else 1
        monto = certificacion.monto_contrato(
            ejemplo["tareas"], fecha_inicio=ejemplo["fecha_inicio"], equipos=equipos
        )
        assert monto == pytest.approx(ejemplo["monto_habilita_usd"], abs=1), ejemplo["orden_id"]

        diferencias = cierre.comparar(
            orden, parte, horas_registro=ejemplo["horas_registro_ingreso"]
        )
        resultado = certificacion.evaluar(
            orden, parte, diferencias=diferencias,
            fecha_inicio=ejemplo["fecha_inicio"], equipos=equipos,
            monto_declarado=ejemplo["monto_declarado_usd"],
        )
        tiene_diferencias = bool(ejemplo["diferencias"])
        assert (resultado["estado"] == "Observada") == tiene_diferencias, (
            ejemplo["orden_id"], resultado, ejemplo["diferencias"]
        )
