from sistema.seguridad import detectar_seguridad, texto_alerta


def test_s1_agua_a_presion():
    texto = (
        "¡Atención! Se rompió algo en la descarga de la uno, sale agua a presión "
        "para todos lados, me alejé. Saqué foto desde lejos."
    )
    assert detectar_seguridad(texto) == "S1"


def test_s1_por_foto():
    assert detectar_seguridad("no se entiende el audio", ["/media/fotos/rotura_descarga/01.jpg"]) == "S1"


def test_s2_gas():
    assert detectar_seguridad("Hay olor a gas fuerte del lado del portón.") == "S2"


def test_s3_humo():
    assert detectar_seguridad("Sale humo del motor de la dos, hay olor a quemado.") == "S3"


def test_s4_lesion():
    assert detectar_seguridad("Mi compañero se golpeó la mano, está sangrando.") == "S4"


def test_goteo_normal_no_es_alerta():
    assert detectar_seguridad("La dos sigue goteando por la empaquetadura.") is None


def test_texto_alerta():
    assert "procedimiento de emergencia" in texto_alerta("S1")
