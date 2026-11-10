import json

import httpx
import respx

from sistema.contexto import redactar_contexto, responder_consulta
from sistema.llm import LLM

BASE = "http://ollama:11434"


def cliente(habilitado: bool = True) -> LLM:
    return LLM(
        base_url=BASE,
        model="ministral-3:3b",
        timeout_s=5,
        habilitado=habilitado,
        permitidos={"ministral-3:3b"},
    )


def test_deshabilitado_no_llama(monkeypatch):
    def falla(*_a, **_k):
        raise AssertionError("no debería hacer HTTP")

    monkeypatch.setattr(httpx, "get", falla)
    monkeypatch.setattr(httpx, "post", falla)
    llm = cliente(habilitado=False)
    assert llm.disponible() is False
    assert llm.chat("hola") is None


def test_modelo_fuera_de_allowlist_no_llama(monkeypatch):
    def falla(*_a, **_k):
        raise AssertionError("no debería hacer HTTP")

    monkeypatch.setattr(httpx, "get", falla)
    monkeypatch.setattr(httpx, "post", falla)
    llm = LLM(
        base_url=BASE,
        model="qwen3.5:9b",
        habilitado=True,
        permitidos={"ministral-3:3b"},
    )
    assert llm.permitido is False
    assert llm.disponible() is False
    assert llm.chat("hola") is None


def test_modelo_en_allowlist_queda_habilitado():
    llm = LLM(
        base_url=BASE,
        model="ministral-3:3b",
        habilitado=True,
        permitidos={"ministral-3:3b"},
    )
    assert llm.permitido is True


@respx.mock
def test_disponible_lista_modelos():
    respx.get(f"{BASE}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "ministral-3:3b"}]})
    )
    assert cliente().disponible() is True


@respx.mock
def test_chat_devuelve_texto_y_tokens():
    ruta = respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {"content": "El límite es 7,1 mm/s [TX350-D §3.2]."},
                "prompt_eval_count": 120,
                "eval_count": 24,
            },
        )
    )
    r = cliente().chat("¿límite de vibración?", sistema="sos un asistente")
    assert r is not None
    assert "7,1" in r.texto
    assert (r.tokens_entrada, r.tokens_salida) == (120, 24)
    cuerpo = json.loads(ruta.calls[0].request.content)
    assert cuerpo["stream"] is False
    assert cuerpo["think"] is False
    assert cuerpo["options"]["temperature"] == 0
    assert cuerpo["model"] == "ministral-3:3b"


@respx.mock
def test_chat_falla_y_devuelve_none():
    respx.post(f"{BASE}/api/chat").mock(side_effect=httpx.ConnectError("sin ruta"))
    assert cliente().chat("hola") is None


@respx.mock
def test_chat_solo_thinking_devuelve_none():
    respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(
            200, json={"message": {"content": "", "thinking": "razonando..."}}
        )
    )
    assert cliente().chat("hola") is None


def test_contexto_sin_llm_usa_plantilla():
    recuperados = [{"cita": "MBP-4 §11.1", "texto": "Durante el corte se guarda en cola."}]
    salida = redactar_contexto("nota", [], [], recuperados, llm=cliente(habilitado=False))
    assert salida["generado_por"] == "plantilla"
    assert salida["citas"] == ["MBP-4 §11.1"]
    assert "cola" in salida["texto"]


@respx.mock
def test_contexto_con_llm_conserva_citas():
    respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={"message": {"content": "Se guarda en cola [MBP-4 §11.1]."},
                  "prompt_eval_count": 80, "eval_count": 12},
        )
    )
    recuperados = [{"cita": "MBP-4 §11.1", "texto": "Durante el corte se guarda en cola."}]
    salida = redactar_contexto("nota", [], [], recuperados, llm=cliente())
    assert salida["generado_por"] == "ministral-3:3b"
    assert salida["citas"] == ["MBP-4 §11.1"]
    assert salida["tokens_salida"] == 12
    assert "cola" in salida["texto"]


def test_consulta_sin_llm_muestra_evidencia():
    recuperados = [{"cita": "TX350-D §3.2", "texto": "Vibración máxima 7,1 mm/s."}]
    salida = responder_consulta("¿vibración?", recuperados, llm=cliente(habilitado=False))
    assert salida["generado_por"] == "plantilla"
    assert "7,1" in salida["texto"]
    assert salida["citas"] == ["TX350-D §3.2"]
