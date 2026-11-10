def por_clave(resultado):
    return {(i.tag, i.variable): i for i in resultado.items}


def test_nota_multiequipo(parser):
    texto = (
        "La uno está en ciento doce de descarga, ah, y el filtro B me dio uno ocho "
        "de diferencial. La tres sigue goteando por la empaquetadura, le saqué foto."
    )
    r = parser.parse(texto, ["/media/fotos/empaquetadura/01.jpg"])
    filas = por_clave(r)
    assert filas[("B-101", "presion_descarga_local")].valor == 112
    assert filas[("B-101", "presion_descarga_local")].unidad == "kg/cm2"
    assert filas[("F-201B", "presion_diferencial")].valor == 1.8
    assert filas[("B-103", "goteo_empaquetadura")].observacion == "goteo por empaquetadura"
    assert not r.ambiguedades


def test_diferencial_cero_nueve(parser):
    filas = por_clave(parser.parse("El filtro B me dio 09 de diferencial."))
    assert filas[("F-201B", "presion_diferencial")].valor == 0.9


def test_diferencial_0_a_9(parser):
    filas = por_clave(parser.parse("El filtro B me dio 0 a 9 de diferencial."))
    assert filas[("F-201B", "presion_diferencial")].valor == 0.9


def test_diferencial_1_a_3(parser):
    filas = por_clave(parser.parse("El filtro a medio, 1 a 3 de diferencial."))
    assert filas[("F-201A", "presion_diferencial")].valor == 1.3


def test_bomba_sin_articulo_no_pierde_el_valor(parser):
    texto = (
        "la uno, estar en 112 kilogramos de descarga, el rodamiento medió 59 grados "
        "con la pistola. Ambienta bomba Stein, el 600 PS y de descarga, "
        "el filtro Amedió 1,3 de diferencial."
    )
    r = parser.parse(texto)
    filas = por_clave(r)
    assert filas[("B-101", "presion_descarga_local")].valor == 112
    assert filas[("B-101", "temperatura_rodamiento_ir")].valor == 59
    # El valor de la bomba ya no desaparece: queda en el tramo ambiguo.
    assert filas[("BOMBA", "presion_descarga_local")].valor == 600
    assert any(a.tipo == "equipo" and a.dicho == "bomba" for a in r.ambiguedades)


def test_nota_fito_no_cuelga_el_diferencial_de_la_bomba(parser):
    texto = (
        "la 1 está en 112 kilogramos de descarga el rodamiento medió 59 grados "
        "con la pistola también la bomba está en 1600 pese y de descarga "
        "el fito a media 1.3 de diferencial"
    )
    filas = por_clave(parser.parse(texto))
    assert filas[("B-101", "presion_descarga_local")].valor == 112
    assert filas[("B-101", "temperatura_rodamiento_ir")].valor == 59
    assert filas[("BOMBA", "presion_descarga_local")].valor == 1600
    assert filas[("F-201A", "presion_diferencial")].valor == 1.3
    assert ("BOMBA", "presion_diferencial") not in filas


def test_unidades_por_bomba(parser):
    texto = (
        "La dos está en mil seiscientos cuarenta de descarga. "
        "La tres está en ciento diez bar de descarga."
    )
    filas = por_clave(parser.parse(texto))
    assert filas[("B-102", "presion_descarga_local")].valor == 1640
    assert filas[("B-102", "presion_descarga_local")].unidad == "psi"
    assert filas[("B-103", "presion_descarga_local")].valor == 110
    assert filas[("B-103", "presion_descarga_local")].unidad == "bar"


def test_presion_y_goteo_en_el_mismo_tramo(parser):
    filas = por_clave(
        parser.parse("La dos está en mil seiscientos cuarenta de descarga, gotea por la empaquetadura.")
    )
    assert filas[("B-102", "presion_descarga_local")].valor == 1640
    assert filas[("B-102", "goteo_empaquetadura")].observacion == "goteo por empaquetadura"


def test_goteo_y_temperatura(parser):
    texto = (
        "La dos gotea por la empaquetadura. "
        "En la dos, el rodamiento me dio ochenta y cinco grados con la pistola."
    )
    filas = por_clave(parser.parse(texto))
    assert filas[("B-102", "goteo_empaquetadura")].observacion == "goteo por empaquetadura"
    assert filas[("B-102", "temperatura_rodamiento_ir")].valor == 85
    assert filas[("B-102", "temperatura_rodamiento_ir")].observacion == "rodamiento caliente"


def test_presion_y_temperatura_juntas(parser):
    texto = (
        "La del medio está en 1630 de descarga, la uno está en 115 kilogramos "
        "de descarga, el rodamiento me dio 55 grados con la pistola."
    )
    filas = por_clave(parser.parse(texto))
    assert filas[("B-102", "presion_descarga_local")].valor == 1630
    assert filas[("B-102", "presion_descarga_local")].unidad == "psi"
    assert filas[("B-101", "presion_descarga_local")].valor == 115
    assert filas[("B-101", "temperatura_rodamiento_ir")].valor == 55
    assert filas[("B-101", "temperatura_rodamiento_ir")].observacion is None


def test_estado_normal(parser):
    filas = por_clave(parser.parse("La tres está parada, en reserva."))
    assert filas[("B-103", "estado")].observacion == "parada, en reserva"


def test_ambiguedad_equipo(parser):
    r = parser.parse("La bomba está en ciento doce de descarga.")
    assert any(a.tipo == "equipo" for a in r.ambiguedades)
    item = next(i for i in r.items if i.variable == "presion_descarga_local")
    assert item.tag == "BOMBA"
    assert item.unidad is None


def test_ambiguedad_valor(parser):
    r = parser.parse("El filtro A me dio dieciocho de diferencial.")
    item = next(i for i in r.items if i.variable == "presion_diferencial")
    assert item.valor == 1.8
    assert any(a.tipo == "valor" and a.real == 1.8 for a in r.ambiguedades)


def test_tanque_y_rebalse(parser):
    filas = por_clave(
        parser.parse("El pulmón está en cinco coma cero metros, está rebalsando a la pileta.")
    )
    assert filas[("TK-301", "nivel")].valor == 5.0
    assert filas[("TK-301", "nivel")].observacion == "rebalse a pileta"


def test_sin_novedad(parser):
    r = parser.parse("Recorrida sin novedad, todo normal.")
    assert not r.items
    assert not r.ambiguedades
