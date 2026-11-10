from sistema.auditoria import registro_consulta


def test_normaliza_y_trunca():
    r = registro_consulta(
        "¿qué pasa con la cola?",
        [{"cita": "MBP-4 §11.1", "texto": "x" * 600}],
        {
            "texto": "r" * 5000,
            "citas": ["MBP-4 §11.1"],
            "generado_por": "ministral-3:3b",
            "tokens_entrada": 10,
            "tokens_salida": 20,
            "suficiente": True,
            "fallback": None,
        },
    )
    assert r["pregunta"] == "¿qué pasa con la cola?"
    assert r["recuperados"][0]["texto"] == "x" * 500
    assert len(r["respuesta"]) == 4000
    assert r["citas_usadas"] == ["MBP-4 §11.1"]
    assert r["modelo"] == "ministral-3:3b"
    assert r["tokens_entrada"] == 10
    assert r["tokens_salida"] == 20
    assert r["suficiente"] is True
    assert r["fallback"] is None


def test_registro_de_fallback():
    r = registro_consulta(
        "¿capital de Francia?",
        [],
        {"texto": "No hay evidencia", "generado_por": "plantilla", "fallback": "sin_llm"},
    )
    assert r["suficiente"] is False
    assert r["fallback"] == "sin_llm"
    assert r["tokens_entrada"] == 0
