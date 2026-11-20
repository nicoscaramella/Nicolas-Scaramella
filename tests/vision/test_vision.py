"""M6 · Visión NVIDIA: conector, respuesta dorada y cola sin enlace."""

import httpx
import pytest
import respx

from sistema.vision import nvidia, proveedor


RESPUESTA_DORADA = {
    "choices": [
        {
            "message": {
                "content": '{"componente": "descarga", "dano_estructural": true, '
                '"descripcion": "Rotura en línea de descarga", "confianza": 0.8}'
            }
        }
    ]
}


def test_lee_la_respuesta_dorada_de_la_foto_de_fuga():
    with respx.mock:
        respx.post(nvidia.BASE).mock(return_value=httpx.Response(200, json=RESPUESTA_DORADA))
        analisis = nvidia.analizar_foto(b"jpeg", api_key="nvapi-test")
    assert analisis.componente == "descarga"
    assert analisis.dano_estructural is True
    assert analisis.confianza == 0.8


def test_sin_api_key_no_llama(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(nvidia.VisionNoDisponible):
        nvidia.analizar_foto(b"jpeg", api_key=None)


def test_http_no_200_es_no_disponible():
    with respx.mock:
        respx.post(nvidia.BASE).mock(return_value=httpx.Response(410, text="gone"))
        with pytest.raises(nvidia.VisionNoDisponible):
            nvidia.analizar_foto(b"jpeg", api_key="nvapi-test")


def test_content_none_es_respuesta_invalida():
    with respx.mock:
        respx.post(nvidia.BASE).mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": None}}]})
        )
        with pytest.raises(nvidia.VisionNoDisponible):
            nvidia.analizar_foto(b"jpeg", api_key="nvapi-test")


def test_json_con_bloque_de_codigo_se_acepta():
    with respx.mock:
        respx.post(nvidia.BASE).mock(
            return_value=httpx.Response(
                200,
                json={"choices": [{"message": {"content": '```json\n{"dano_estructural": true}\n```'}}]},
            )
        )
        assert nvidia.analizar_foto(b"jpeg", api_key="nvapi-test").dano_estructural


class ApiFalsa:
    def descargar(self, url):
        return b"jpeg"


def test_proveedor_encola_sin_enlace_y_usa_la_heuristica_local(monkeypatch):
    encoladas = []
    monkeypatch.setattr(
        proveedor.nvidia, "analizar_foto",
        lambda *a, **k: (_ for _ in ()).throw(nvidia.VisionNoDisponible("sin enlace")),
    )
    monkeypatch.setattr(proveedor.db, "encolar_vision", lambda n, f, m: encoladas.append((n, f)))

    analisis = proveedor.Proveedor(ApiFalsa(), habilitado=True).analizar(
        {"id": "NOTA-1", "fotos": ["/media/fotos/rotura_descarga/04.jpg"]}
    )
    assert analisis is not None and analisis.dano_estructural
    assert encoladas == [("NOTA-1", "/media/fotos/rotura_descarga/04.jpg")]


def test_proveedor_sin_fotos_no_hace_nada():
    assert proveedor.Proveedor(ApiFalsa(), habilitado=True).analizar({"id": "N", "fotos": []}) is None
