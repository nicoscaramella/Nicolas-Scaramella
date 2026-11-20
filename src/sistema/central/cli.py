"""CLI de la Central de mantenimiento.

Habla con la API HTTP del agente (``:8200``) para que el planificador, el
supervisor y el inspector puedan decidir sin abrir el navegador.

    python -m sistema.central.cli pendientes
    python -m sistema.central.cli aprobar ORD-123 --quien "Planificador" --motivo "..."
    python -m sistema.central.cli certificar ORD-123 --quien "Inspector"
    python -m sistema.central.cli observar ORD-123 --quien "Inspector" --motivo "..."
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ROLES = {
    "aprobar": "planificador",
    "rechazar": "planificador",
    "cerrar": "supervisor",
    "certificar": "inspector",
    "observar": "inspector",
}


def llamar(base: str, metodo: str, ruta: str, cuerpo: dict | None = None, rol: str | None = None):
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    peticion = urllib.request.Request(base.rstrip("/") + ruta, data=datos, method=metodo)
    peticion.add_header("Content-Type", "application/json")
    if rol:
        peticion.add_header("X-Rol", rol)
    with urllib.request.urlopen(peticion, timeout=30) as respuesta:
        return json.loads(respuesta.read())


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Central de mantenimiento PIA-3")
    parser.add_argument("--base", default=os.getenv("CENTRAL_URL", "http://localhost:8200"))
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("pendientes", help="órdenes pendientes de aprobación")
    sub.add_parser("listar", help="todas las órdenes")
    for accion in ROLES:
        cmd = sub.add_parser(accion)
        cmd.add_argument("orden")
        cmd.add_argument("--quien", default=None)
        cmd.add_argument("--motivo", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    base = args.base
    try:
        if args.comando == "pendientes":
            datos = llamar(base, "GET", "/api/ordenes?estado=PendienteAprobacion")
        elif args.comando == "listar":
            datos = llamar(base, "GET", "/api/ordenes")
        else:
            cuerpo = {"quien": args.quien, "motivo": args.motivo}
            datos = llamar(
                base,
                "POST",
                f"/api/ordenes/{args.orden}/{args.comando}",
                cuerpo,
                rol=ROLES[args.comando],
            )
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    print(json.dumps(datos, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
