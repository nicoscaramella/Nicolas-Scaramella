from sistema.contexto import responder_consulta
from sistema.llm import RespuestaLLM

FRAG = [{"cita": "MBP-4 §11.1", "texto": "Durante el corte se guarda en cola."}]


class LLMFalso:
    model = "ministral-3:3b"

    def __init__(self, texto: str):
        self.texto = texto
        self.kwargs: dict = {}

    def chat(self, *_args, **kwargs):
        self.kwargs = kwargs
        return RespuestaLLM(self.texto, 10, 5)


def test_respuesta_valida():
    texto = (
        '{"respuesta": "Se guarda en cola [MBP-4 §11.1].", '
        '"citas": ["MBP-4 §11.1"], "suficiente": true}'
    )
    r = responder_consulta("¿qué pasa con la cola?", FRAG, llm=LLMFalso(texto))
    assert r["generado_por"] == "ministral-3:3b"
    assert r["citas"] == ["MBP-4 §11.1"]
    assert r["fallback"] is None
    assert r["suficiente"] is True


def test_cita_inventada_cae_al_fallback():
    texto = (
        '{"respuesta": "Algo [TX350-C §3.2].", '
        '"citas": ["TX350-C §3.2"], "suficiente": true}'
    )
    r = responder_consulta("¿qué pasa con la cola?", FRAG, llm=LLMFalso(texto))
    assert r["generado_por"] == "plantilla"
    assert r["fallback"].startswith("cita_invalida")
    assert "TX350-C" in r["fallback"]


def test_sin_suficiente_cae_al_fallback():
    texto = '{"respuesta": "No sé.", "citas": [], "suficiente": false}'
    r = responder_consulta("¿qué pasa con la cola?", FRAG, llm=LLMFalso(texto))
    assert r["generado_por"] == "plantilla"
    assert r["fallback"] == "sin_evidencia"


def test_json_roto_cae_al_fallback():
    r = responder_consulta("¿qué pasa con la cola?", FRAG, llm=LLMFalso("no es json"))
    assert r["generado_por"] == "plantilla"
    assert r["fallback"] == "json_invalido"


def test_pide_formato_json():
    fake = LLMFalso('{"respuesta":"x","citas":["MBP-4 §11.1"],"suficiente":true}')
    responder_consulta("¿qué pasa con la cola?", FRAG, llm=fake)
    assert fake.kwargs.get("formato") == "json"
