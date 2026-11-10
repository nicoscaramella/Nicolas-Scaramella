from types import SimpleNamespace

from sistema import asr


class ModeloFalso:
    def __init__(self):
        self.kwargs: dict = {}

    def transcribe(self, _nombre, **kwargs):
        self.kwargs = kwargs
        return iter([]), SimpleNamespace(duration=1.0)


def test_transcripcion_usa_prompt_de_dominio(monkeypatch):
    falso = ModeloFalso()
    monkeypatch.setattr(asr, "WhisperModel", lambda *_a, **_k: falso)
    texto = asr.ASR().transcribir(b"audio")
    assert texto == ""
    assert "PIA-3" in falso.kwargs["initial_prompt"]
    assert "B-101" in falso.kwargs["initial_prompt"]
    assert falso.kwargs["temperature"] == 0.0
    assert falso.kwargs["language"] == "es"
