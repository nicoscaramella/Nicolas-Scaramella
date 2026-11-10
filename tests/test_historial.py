from sistema.historial import resumen_tendencia


class API:
    def historian(self, *_args, **_kwargs):
        return [{"valor": 100}, {"valor": 120}, {"valor": 110}]


def test_resumen_tendencia():
    assert (
        resumen_tendencia(
            API(), "B-101", "presion_descarga_local", "2026-11-09T10:00:00-03:00"
        )
        == "100.0–120.0, último 110.0"
    )


def test_resumen_tendencia_variable_sin_sensor():
    assert resumen_tendencia(API(), "B-101", "estado", "2026-11-09T10:00:00-03:00") is None
