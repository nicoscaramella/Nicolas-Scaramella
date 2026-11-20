"""Publica la Central fuera de ``planta-lan``.

La red de la planta es ``internal: true``: los servicios de planta (agente y
base) no pueden publicar puertos al host. La Central es la **interfaz humana**,
no un servicio de planta: corre en este proceso aparte, escucha en el puerto
publicado y reenvía al agente por la red interna. Es un proxy TCP transparente
(HTTP incluido).
"""

from __future__ import annotations

import logging
import os
import socket
import threading

log = logging.getLogger("central.proxy")

ESCUCHA = int(os.getenv("CENTRAL_PORT", "8200"))
DESTINO_HOST = os.getenv("CENTRAL_DESTINO_HOST", "agente")
DESTINO_PUERTO = int(os.getenv("CENTRAL_DESTINO_PUERTO", "8200"))


def _bombear(origen: socket.socket, destino: socket.socket) -> None:
    try:
        while datos := origen.recv(65536):
            destino.sendall(datos)
    except OSError:
        pass
    finally:
        try:
            destino.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _atender(cliente: socket.socket) -> None:
    try:
        servidor = socket.create_connection((DESTINO_HOST, DESTINO_PUERTO), timeout=15)
    except OSError as exc:
        log.warning("No se pudo conectar con %s:%s (%s)", DESTINO_HOST, DESTINO_PUERTO, exc)
        cliente.close()
        return
    ida = threading.Thread(target=_bombear, args=(cliente, servidor), daemon=True)
    vuelta = threading.Thread(target=_bombear, args=(servidor, cliente), daemon=True)
    ida.start()
    vuelta.start()
    ida.join()
    vuelta.join()
    cliente.close()
    servidor.close()


def servir(sock: socket.socket) -> None:
    while True:
        try:
            cliente, _ = sock.accept()
        except OSError:
            return
        threading.Thread(target=_atender, args=(cliente,), daemon=True).start()


def crear_socket(puerto: int = ESCUCHA) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", puerto))
    sock.listen(64)
    return sock


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    sock = crear_socket()
    log.info("Central publicada en :%s → %s:%s", ESCUCHA, DESTINO_HOST, DESTINO_PUERTO)
    servir(sock)


if __name__ == "__main__":
    main()
