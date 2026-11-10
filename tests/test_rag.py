from sistema.rag.buscar import _aplica
from sistema.rag.evaluar import BM25, evaluar, rev_c_antes_que_d


def suite():
    return [
        {
            "id": "q1",
            "tipo": "limites",
            "pregunta": "vibración",
            "relevantes": ["TX350-D §3.2"],
            "distractores": ["TX350-C §3.2"],
        }
    ]


def test_metricas_hit_recall():
    def buscar(_q, _k):
        return ["TX350-D §3.2", "MBP-4 §5.1"]

    r = evaluar(buscar, suite())
    assert r["total"]["hit@5"] == 1.0
    assert r["total"]["recall@5"] == 1.0
    assert r["total"]["distractor@5"] == 0.0


def test_distractor_antes_que_relevante():
    def buscar(_q, _k):
        return ["TX350-C §3.2", "TX350-D §3.2"]

    r = evaluar(buscar, suite())
    assert r["total"]["distractor@5"] == 1.0


def test_rev_c_antes_que_d():
    assert rev_c_antes_que_d(suite(), lambda _q, _k: ["TX350-C §3.2", "TX350-D §3.2"], 5) == 1
    assert rev_c_antes_que_d(suite(), lambda _q, _k: ["TX350-D §3.2", "TX350-C §3.2"], 5) == 0


def test_asegurar_indice_completa_si_falta(monkeypatch):
    from sistema.rag import indexar as mod

    monkeypatch.setattr(mod.db, "rag_count", lambda: 349)
    monkeypatch.setattr(
        mod.PlantaAPI, "texto", lambda self, _ruta: "\n".join(["{}"] * 701)
    )
    llamado: list[int] = []
    monkeypatch.setattr(mod, "indexar", lambda rag=None: llamado.append(1))
    mod.asegurar_indice()
    assert llamado == [1]


def test_asegurar_indice_no_reindexa_si_esta_completo(monkeypatch):
    from sistema.rag import indexar as mod

    monkeypatch.setattr(mod.db, "rag_count", lambda: 701)
    monkeypatch.setattr(
        mod.PlantaAPI, "texto", lambda self, _ruta: "\n".join(["{}"] * 701)
    )
    llamado: list[int] = []
    monkeypatch.setattr(mod, "indexar", lambda rag=None: llamado.append(1))
    mod.asegurar_indice()
    assert llamado == []


def test_filtra_secciones_que_no_aplican_a_pia3():
    assert not _aplica({"titulo": "Límites de operación de otros modelos de la familia"})
    assert not _aplica({"titulo": "Límites de otras plantas"})
    assert not _aplica({"titulo": "PIA-1: bombas centrífugas multietapa"})
    assert _aplica({"titulo": "Límites de operación"})


def test_bm25_basico():
    frags = [
        {"id": "TX350-D §3.2", "texto": "límites de vibración y disparo por protección"},
        {"id": "FC48-3 §2", "texto": "cartuchos y presión diferencial del filtro"},
    ]
    assert BM25(frags).buscar("vibración", 1) == ["TX350-D §3.2"]
