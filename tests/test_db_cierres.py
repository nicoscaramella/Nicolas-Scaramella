"""T1.2 · Persistencia cruda de cierres y estado de energía.

El cierre se guarda tal como llega (idempotente por id) apenas se recibe: si
el contenedor se apaga de golpe, el cierre no se pierde. Su procesamiento
(armar el parte, comparar con la orden) es de M7.
"""

import uuid

import pytest

from sistema import db


def _cierre(cid: str) -> dict:
    return {
        "id": cid,
        "ts": "2026-11-09T10:00:00-03:00",
        "orden_id": "OT-TEST-0001",
        "tecnico": "Diego Barría",
        "empresa": "Servipat",
        "audio_url": None,
        "fotos": [],
    }


def test_cierre_crudo_es_idempotente():
    try:
        db.init_db()
    except Exception as exc:  # pragma: no cover - depende del arranque de Postgres
        pytest.skip(f"PostgreSQL no disponible: {exc}")

    cid = f"CIERRE-TEST-{uuid.uuid4().hex[:8]}"
    payload = _cierre(cid)

    assert db.guardar_cierre_crudo(payload) is True
    # El mismo id no se duplica ni se reprocesa.
    assert db.guardar_cierre_crudo(payload) is False

    crudo = db.obtener_cierre_crudo(cid)
    assert crudo is not None
    assert crudo["payload"]["orden_id"] == "OT-TEST-0001"
    assert crudo["procesado"] is False
