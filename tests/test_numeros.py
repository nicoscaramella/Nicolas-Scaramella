from sistema.numeros import (
    parse_decimal,
    parse_numero,
    parse_ultimo_numero,
    parse_unidad,
)


def test_enteros_hablados():
    assert parse_numero("ciento doce") == 112
    assert parse_numero("mil seiscientos cuarenta") == 1640
    assert parse_numero("ochenta y cinco") == 85
    assert parse_numero("ciento treinta y siete") == 137
    assert parse_numero("dieciocho") == 18


def test_decimales_hablados():
    assert parse_numero("uno ocho") == 1.8
    assert parse_numero("uno coma ocho") == 1.8
    assert parse_numero("uno con ocho") == 1.8
    assert parse_numero("uno y medio") == 1.5
    assert parse_numero("cinco coma cero") == 5.0


def test_digitos_del_asr():
    assert parse_numero("1.8 de diferencial") == 1.8
    assert parse_numero("1,640 de descarga") == 1640
    assert parse_numero("112 de descarga") == 112


def test_cero_nueve_del_asr():
    # Whisper transcribe "cero nueve" como "09": es 0,9, no 9.
    assert parse_numero("09 de diferencial") == 0.9
    assert parse_numero("cero nueve de diferencial") == 0.9


def test_decimal_con_a_del_asr():
    # Con voz humana el ASR escribe "0 a 9" por "0,9" y "1 a 3" por "1,3".
    assert parse_decimal("0 a 9") == 0.9
    assert parse_decimal("1 a 3") == 1.3
    assert parse_decimal("1 coma 3") == 1.3
    assert parse_decimal("1,3") is None


def test_ultimo_numero_del_tramo():
    # Cuando el tramo mezcla presión y diferencial, vale el último número.
    assert parse_ultimo_numero("1600 psi de descarga el fito a media 1.3") == 1.3
    assert parse_ultimo_numero("me dio uno coma tres") == 1.3
    assert parse_ultimo_numero("cero nueve") == 0.9


def test_unidades():
    assert parse_unidad("mil seiscientos cuarenta libras") == "psi"
    assert parse_unidad("ciento diez bar") == "bar"
    assert parse_unidad("ochenta y cinco grados") == "degC"
    assert parse_unidad("cinco metros") == "m"
    assert parse_unidad("ciento treinta y siete gotas por minuto") == "gotas/min"
