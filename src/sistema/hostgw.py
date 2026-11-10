"""Resuelve ``host.docker.internal`` al gateway real de la red interna.

La red ``planta-lan`` es ``internal:true`` y su subred cambia cuando se recrea
la planta; además puede no tener ruta por defecto. En vez de hardcodear una IP,
se lee la ruta por defecto si existe y, si no, se calcula el gateway a partir de
la IP y la máscara del contenedor (red + 1). Así Ollama en el host sigue siendo
alcanzable sin abrir otra red.
"""

from __future__ import annotations

import fcntl
import socket
import struct

SIOCGIFADDR = 0x8915
SIOCGIFNETMASK = 0x891B


def gateway_desde_rutas(lineas: list[str]) -> str | None:
    """Primera ruta por defecto (Destination 00000000) como IP."""
    for linea in lineas:
        partes = linea.split()
        if len(partes) >= 3 and partes[1] == "00000000":
            try:
                return socket.inet_ntoa(struct.pack("<L", int(partes[2], 16)))
            except (ValueError, OSError):
                continue
    return None


def gateway_desde_ip(ip: str, mascara: str) -> str | None:
    """Gateway de una red de bridge: dirección de red + 1."""
    try:
        ip_i = struct.unpack("!I", socket.inet_aton(ip))[0]
        mask_i = struct.unpack("!I", socket.inet_aton(mascara))[0]
        return socket.inet_ntoa(struct.pack("!I", (ip_i & mask_i) + 1))
    except OSError:
        return None


def _ip_y_mascara(interfaz: str) -> tuple[str, str] | None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        peticion = struct.pack("256s", interfaz.encode()[:15])
        ip = socket.inet_ntoa(fcntl.ioctl(s.fileno(), SIOCGIFADDR, peticion)[20:24])
        mascara = socket.inet_ntoa(
            fcntl.ioctl(s.fileno(), SIOCGIFNETMASK, peticion)[20:24]
        )
        return ip, mascara
    except OSError:
        return None
    finally:
        s.close()


def _gateway() -> str | None:
    try:
        with open("/proc/net/route", encoding="utf-8") as f:
            ip = gateway_desde_rutas(f.readlines()[1:])
        if ip:
            return ip
    except OSError:
        pass
    for _, nombre in socket.if_nameindex():
        if nombre == "lo":
            continue
        datos = _ip_y_mascara(nombre)
        if datos:
            return gateway_desde_ip(*datos)
    return None


def main() -> None:
    try:
        ip = _gateway()
        if not ip:
            return
        with open("/etc/hosts", encoding="utf-8") as f:
            if "host.docker.internal" in f.read():
                return
        with open("/etc/hosts", "a", encoding="utf-8") as f:
            f.write(f"{ip}\thost.docker.internal\n")
    except Exception:
        # Nunca impedir el arranque del agente por esto.
        return


if __name__ == "__main__":
    main()
