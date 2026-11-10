import httpx
import pytest
import respx

from sistema import tools
from sistema.tools import HistorianIn, ToolError


@respx.mock
def test_equipos():
    respx.get("http://sim:8100/api/planta").mock(
        return_value=httpx.Response(200, json={"equipos": [{"tag": "B-101"}]})
    )
    assert tools.equipos() == [{"tag": "B-101"}]


@respx.mock
def test_historial_sensores():
    respx.get("http://sim:8100/api/historian/B-101/vibracion").mock(
        return_value=httpx.Response(200, json=[{"valor": 2.1}])
    )
    assert tools.historial_sensores("B-101", "vibracion") == [{"valor": 2.1}]


@respx.mock
def test_historial_sensores_error():
    respx.get("http://sim:8100/api/historian/B-101/vibracion").mock(
        return_value=httpx.Response(500)
    )
    with pytest.raises(ToolError):
        tools.historial_sensores("B-101", "vibracion")


def test_inventario_y_stock():
    inv = tools.inventario()
    assert any(r["codigo"] == "TX-EMP-KIT" for r in inv)
    assert tools.stock("TX-EMP-KIT")["costo_usd"] == 420
    assert tools.lista_materiales("B-101")["equipo"] == "B-101"
    assert tools.catalogo_tareas()["estandar"]


def test_entrada_estricta():
    with pytest.raises(Exception):
        HistorianIn(tag="B-101", variable="vibracion", otro=1)


@respx.mock
def test_historial_ordenes():
    respx.get("http://sim:8100/api/historial-ordenes").mock(
        return_value=httpx.Response(
            200, json=[{"id": "OT-25-0026", "equipo": "B-101"}]
        )
    )
    assert tools.historial_ordenes() == [{"id": "OT-25-0026", "equipo": "B-101"}]


def test_buscar_manuales(monkeypatch):
    class RAGFalso:
        def buscar(self, query, k):
            assert query == "vibracion"
            assert k == 1
            return [
                {
                    "cita": "TX350-D §3.2",
                    "texto": "x" * 2000,
                    "doc": "TX350-D",
                    "vigente": True,
                }
            ]

    monkeypatch.setattr(tools, "RAG", RAGFalso)
    salida = tools.buscar_manuales("vibracion", 1)
    assert salida[0]["cita"] == "TX350-D §3.2"
    assert len(salida[0]["texto"]) == 1200


def test_traducir_codigo_falla():
    r = tools.traducir_codigo_falla("tx-t03")
    assert r["codigo_fabricante"] == "TX-T03"
    assert r["codigo_planta"] == "F03"
    assert "Rodamiento" in r["descripcion"]
    assert tools.traducir_codigo_falla("XX-9")["codigo_planta"] is None
