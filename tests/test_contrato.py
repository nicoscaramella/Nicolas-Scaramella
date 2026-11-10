from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from planta_contrato import EstadoSistema, EventoSistema, MensajeTablet


def test_mensaje_tablet_valido():
    payload = {
        "id": "TAB-1-1",
        "ts": datetime.now(timezone.utc),
        "nota_ids": ["NOTA-1"],
        "texto": "¿Confirmás?",
        "pantalla": {
            "titulo": "Parte",
            "filas": [{"tag": "B-101", "variable": "presion_descarga_local",
                       "valor": 112.0, "unidad": "kg/cm2", "observacion": None}],
            "opciones": [],
        },
        "espera_respuesta": True,
    }
    MensajeTablet.model_validate(payload)


def test_evento_valido():
    EventoSistema.model_validate({
        "id": "EV-1-B-101", "ts": datetime.now(timezone.utc), "tipo": "Escalado",
        "equipo": "B-101", "origen": "parte", "nota_ids": ["NOTA-1"],
        "resumen": "pérdida",
    })


def test_estado_valido():
    EstadoSistema.model_validate({
        "ts": datetime.now(timezone.utc), "sistema": "Nicolas-Scaramella",
        "enlace_ok": True, "pendientes_sincronizar": 0,
    })


def test_extra_prohibido():
    with pytest.raises(ValidationError):
        MensajeTablet.model_validate({
            "id": "x", "ts": datetime.now(timezone.utc), "texto": "x",
            "extra": 1,
        })
