"""Publicación de la Central fuera de planta-lan (proxy TCP)."""

import socket
import threading

from sistema.central import proxy


def test_el_proxy_reenvia_tcp(monkeypatch):
    eco = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    eco.bind(("127.0.0.1", 0))
    eco.listen(1)
    puerto_eco = eco.getsockname()[1]

    def atender_eco():
        cliente, _ = eco.accept()
        datos = cliente.recv(1024)
        cliente.sendall(b"ECO:" + datos)
        cliente.close()

    threading.Thread(target=atender_eco, daemon=True).start()

    monkeypatch.setattr(proxy, "DESTINO_HOST", "127.0.0.1")
    monkeypatch.setattr(proxy, "DESTINO_PUERTO", puerto_eco)

    servidor = proxy.crear_socket(0)
    threading.Thread(target=proxy.servir, args=(servidor,), daemon=True).start()

    cliente = socket.create_connection(("127.0.0.1", servidor.getsockname()[1]), timeout=5)
    cliente.sendall(b"hola")
    assert cliente.recv(1024) == b"ECO:hola"

    cliente.close()
    servidor.close()
    eco.close()
