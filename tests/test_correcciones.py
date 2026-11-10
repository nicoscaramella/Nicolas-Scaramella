from sistema.tablet import (
    aplicar_correcciones,
    es_confirmacion,
    es_correccion,
    es_sin_borrador,
    resolver_equipo,
)

FILA_PRESION = {
    "tag": "B-102", "variable": "presion_descarga_local", "valor": 125.0,
    "unidad": "kg/cm2", "observacion": None,
}


def test_correccion_de_valor(parser):
    filas = [dict(FILA_PRESION)]
    texto = "No. La dos estaba en ciento quince kilos, no en ciento veinticinco. Corregilo y te confirmo."
    nuevas = aplicar_correcciones(filas, texto, parser)
    fila = next(f for f in nuevas if f["tag"] == "B-102" and f["variable"] == "presion_descarga_local")
    assert fila["valor"] == 115
    assert fila["unidad"] == "kg/cm2"


def test_goteo_con_valor_provisorio_se_corrige(parser):
    resultado = parser.parse("La dos gotea por la empaquetadura.")
    fila = next(f for f in resultado.filas() if f["variable"] == "goteo_empaquetadura")
    assert fila["valor"] == 1.0
    texto = "No. La dos estaba en ciento treinta y siete gotas por minuto, no en uno. Corregilo y te confirmo."
    nuevas = aplicar_correcciones(resultado.filas(), texto, parser)
    fila = next(f for f in nuevas if f["variable"] == "goteo_empaquetadura")
    assert fila["valor"] == 137
    assert fila["unidad"] == "gotas/min"


def test_correccion_falta_goteo(parser):
    filas = [dict(FILA_PRESION)]
    texto = "No. Te faltó la dos, que estaba en ciento treinta y siete gotas por minuto. Corregilo y te confirmo."
    nuevas = aplicar_correcciones(filas, texto, parser)
    fila = next(f for f in nuevas if f["variable"] == "goteo_empaquetadura")
    assert fila["valor"] == 137
    assert fila["unidad"] == "gotas/min"


def test_correccion_equipo(parser):
    filas = [{"tag": "B-101", "variable": "presion_descarga_local", "valor": 112.0,
              "unidad": "kg/cm2", "observacion": None}]
    texto = "No. Eso de ciento doce era de la dos, no de la uno. Corregilo y te confirmo."
    nuevas = aplicar_correcciones(filas, texto, parser)
    assert nuevas[0]["tag"] == "B-102"


def test_correccion_temperatura_limpia_observacion(parser):
    filas = [{"tag": "B-101", "variable": "temperatura_rodamiento_ir", "valor": 115.0,
              "unidad": "degC", "observacion": "rodamiento caliente"}]
    texto = "No. La uno estaba en cincuenta y cinco grados, no en ciento quince. Arreglá eso."
    nuevas = aplicar_correcciones(filas, texto, parser)
    fila = nuevas[0]
    assert fila["valor"] == 55
    assert fila["observacion"] is None


def test_correccion_diferencial_limpia_observacion(parser):
    filas = [{"tag": "F-201A", "variable": "presion_diferencial", "valor": 1.8,
              "unidad": "kg/cm2", "observacion": "diferencial alto"}]
    texto = "No. El filtro A estaba en uno con cuatro, no en uno con ocho. Arreglá eso."
    nuevas = aplicar_correcciones(filas, texto, parser)
    fila = nuevas[0]
    assert fila["valor"] == 1.4
    assert fila["observacion"] is None


def test_correccion_no_duplica_ni_pisa(parser):
    filas = [
        {"tag": "B-102", "variable": "presion_descarga_local", "valor": 112.0,
         "unidad": "kg/cm2", "observacion": None},
        {"tag": "B-101", "variable": "temperatura_rodamiento_ir", "valor": 59.0,
         "unidad": "degC", "observacion": None},
        {"tag": "B-102", "variable": "presion_descarga_local", "valor": 1600.0,
         "unidad": "psi", "observacion": None},
        {"tag": "F-201A", "variable": "presion_diferencial", "valor": 1.3,
         "unidad": "kg/cm2", "observacion": None},
    ]
    m1 = ("No. Eso de ciento doce era de la uno, no de la dos. Te faltó la uno, "
          "que estaba en cincuenta y nueve grados. Y hay más cosas, revisalo todo.")
    m2 = ("No. Eso de ciento doce era de la uno, no de la dos. La dos estaba en "
          "mil seiscientos psi, no en uno coma tres. Y hay más cosas, revisalo todo.")
    out = aplicar_correcciones(filas, m1, parser)
    out = aplicar_correcciones(out, m2, parser)
    b102 = [
        f for f in out
        if f["tag"] == "B-102" and f["variable"] == "presion_descarga_local"
    ]
    assert len(b102) == 1
    assert b102[0]["valor"] == 1600
    assert any(
        f["tag"] == "B-101" and f["variable"] == "presion_descarga_local"
        and f["valor"] == 112 for f in out
    )
    assert any(
        f["tag"] == "F-201A" and f["variable"] == "presion_diferencial"
        and f["valor"] == 1.3 for f in out
    )


def test_correccion_unidad(parser):
    filas = [{"tag": "B-102", "variable": "presion_descarga_local", "valor": 115.0,
              "unidad": "psi", "observacion": None}]
    texto = "No. Lo de la dos es en kilos, no en psi. Corregilo y te confirmo."
    nuevas = aplicar_correcciones(filas, texto, parser)
    assert nuevas[0]["unidad"] == "kg/cm2"


def test_correccion_sobra(parser):
    filas = [
        {"tag": "B-102", "variable": "presion_descarga_local", "valor": 115.0,
         "unidad": "kg/cm2", "observacion": None},
        {"tag": "B-102", "variable": "goteo_empaquetadura", "valor": None,
         "unidad": "gotas/min", "observacion": "goteo por empaquetadura"},
    ]
    texto = "No. Lo de la dos no lo dije. Corregilo y te confirmo."
    nuevas = aplicar_correcciones(filas, texto, parser)
    assert len(nuevas) == 1
    assert nuevas[0]["variable"] == "presion_descarga_local"


def test_confirmacion():
    assert es_confirmacion("Sí, confirmo.")
    assert es_confirmacion("Correcto, dale.")
    assert not es_confirmacion("No. La dos estaba en ciento quince kilos.")
    # La corrección termina con "y te confirmo": no debe tomarse como confirmación.
    assert es_correccion("No. La dos estaba en ciento quince kilos, no en ciento veinticinco. Corregilo y te confirmo.")
    assert not es_correccion("Sí, confirmo.")


def test_sin_borrador():
    assert es_sin_borrador("¿Confirmar qué? Mostrame lo que anotaste.")
    assert not es_sin_borrador("Sí, confirmo.")


def test_resolver_equipo(parser):
    assert resolver_equipo("La dos.", parser, "BOMBA") == "B-102"
    assert resolver_equipo("Era la de reserva.", parser, "BOMBA") == "B-103"
    assert resolver_equipo("F-201B.", parser, "FILTRO") == "F-201B"
