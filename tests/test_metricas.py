from datetime import datetime, timezone

from sistema.metricas import ConsumoTokens, modelos_metricas, payload_metricas


def test_metricas_incluyen_consumo_llm():
    modelos = modelos_metricas(
        [
            {
                "modelo": "ministral-3:3b",
                "tokens_entrada": 635,
                "tokens_salida": 137,
                "tokens_por_segundo": 70.0,
                "velocidad_estimada": False,
            }
        ],
        "small",
    )
    assert [m["modelo"] for m in modelos] == [
        "faster-whisper-small",
        "parser-determinista",
        "ministral-3:3b",
    ]
    llm = modelos[-1]
    assert llm["tokens_total"] == 772
    payload = payload_metricas(modelos, "Nicolas-Scaramella", datetime.now(timezone.utc))
    assert payload["tokens_total"] == 772
    assert payload["tokens_por_segundo"] == 70.0
    ConsumoTokens.model_validate(payload)


def test_metricas_sin_consumo():
    payload = payload_metricas(modelos_metricas([], "small"), "Nicolas-Scaramella")
    assert payload["tokens_total"] == 0
    assert payload["tokens_entrada"] == 0
    ConsumoTokens.model_validate(payload)
