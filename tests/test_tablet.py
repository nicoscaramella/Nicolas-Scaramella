from planta_contrato import MensajeTablet

from sistema import tablet


def test_borrador_quita_foto_y_valida_contrato():
    filas = [
        {
            "tag": "B-101",
            "variable": "presion_descarga_local",
            "valor": 112.0,
            "unidad": "kg/cm2",
            "observacion": None,
            "foto": "/media/fotos/descarga/01.jpg",
        }
    ]
    payload = tablet.payload_borrador("NOTA-1", filas, 1)
    assert "foto" not in payload["pantalla"]["filas"][0]
    MensajeTablet.model_validate(payload)


def test_aviso_con_titulo_generico():
    payload = tablet.payload_aviso(
        "NOTA-1", "No se pudo transcribir", None, titulo="Nota para revisión", variable="estado"
    )
    assert payload["pantalla"]["titulo"] == "Nota para revisión"
    assert payload["pantalla"]["filas"][0]["variable"] == "estado"
    assert payload["espera_respuesta"] is False
    MensajeTablet.model_validate(payload)
