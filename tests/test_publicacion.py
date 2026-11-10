from types import SimpleNamespace

from sistema import publicacion
from sistema.publicacion import Publicador


class Cliente:
    def __init__(self):
        self.enviados: list[tuple[str, str]] = []

    def publish(self, topico, payload, qos=1):
        self.enviados.append((topico, payload))
        return SimpleNamespace(rc=0)


def _db_falso(monkeypatch, pendientes=None):
    marcados: list[int] = []
    monkeypatch.setattr(publicacion.db, "encolar", lambda _t, _p: 7)
    monkeypatch.setattr(publicacion.db, "marcar_publicado", lambda i: marcados.append(i))
    monkeypatch.setattr(
        publicacion.db, "pendientes", lambda limite=100: list(pendientes or [])
    )
    return marcados


def test_con_enlace_marca_publicado(monkeypatch):
    marcados = _db_falso(monkeypatch)
    cliente = Cliente()
    pub = Publicador(cliente)
    pub.publicar("prueba/x", {"a": 1})
    assert len(cliente.enviados) == 1
    assert marcados == [7]


def test_sin_enlace_publica_pero_queda_pendiente(monkeypatch):
    marcados = _db_falso(monkeypatch)
    cliente = Cliente()
    pub = Publicador(cliente)
    pub.enlace_ok = False
    pub.publicar("prueba/x", {"a": 1})
    # La tablet y la planta locales tienen que seguir recibiendo.
    assert len(cliente.enviados) == 1
    assert marcados == []


def test_sin_enlace_avisa_pendiente(monkeypatch):
    _db_falso(monkeypatch)
    avisos: list[int] = []
    cliente = Cliente()
    pub = Publicador(cliente, al_quedar_pendiente=lambda: avisos.append(1))
    pub.enlace_ok = False
    pub.publicar("prueba/x", {"a": 1})
    assert avisos == [1]


def test_reintentar_sin_enlace_no_reenvia(monkeypatch):
    _db_falso(
        monkeypatch,
        pendientes=[{"id": 1, "topico": "prueba/x", "payload": {"a": 1}}],
    )
    cliente = Cliente()
    pub = Publicador(cliente)
    pub.enlace_ok = False
    pub.reintentar()
    assert cliente.enviados == []


def test_reintentar_al_volver_envia_y_marca(monkeypatch):
    marcados = _db_falso(
        monkeypatch,
        pendientes=[{"id": 1, "topico": "prueba/x", "payload": {"a": 1}}],
    )
    cliente = Cliente()
    pub = Publicador(cliente)
    pub.enlace_ok = True
    pub.reintentar()
    assert len(cliente.enviados) == 1
    assert marcados == [1]
