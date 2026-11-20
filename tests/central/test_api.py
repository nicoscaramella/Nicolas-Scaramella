"""M5 · Central de mantenimiento: roles, decisiones y API HTTP."""

import json
import threading
import urllib.error
import urllib.request
import uuid

import pytest

from sistema import db
from sistema.central import api, cli, servicio
from sistema.ordenes import estado


class PublicadorFalso:
    def __init__(self):
        self.mensajes = []

    def publicar(self, topico, payload):
        self.mensajes.append((topico, payload))


def _db_listo():
    try:
        db.init_db()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PostgreSQL no disponible: {exc}")


def _sufijo() -> str:
    return uuid.uuid4().hex[:4]


def _orden_pendiente(equipo: str | None = None) -> dict:
    orden = estado.armar_orden(
        equipo=equipo or f"B-1{_sufijo()}",
        tareas=["T-B-EMP"],
        evento_ids=["EV-CENTRAL"],
        repuestos=[{"codigo": "TX-EMP-KIT", "cantidad": 1}],
    )
    return estado.transicion(orden, estado.PENDIENTE, motivo="sin stock en el yacimiento")


def _orden_ejecutada(tareas=("T-B-ROD",), repuestos=()) -> dict:
    orden = estado.armar_orden(
        equipo=f"B-1{_sufijo()}", tareas=list(tareas), evento_ids=["EV-CENTRAL"],
        repuestos=list(repuestos), ejecutor="Servipat",
    )
    aprobada = estado.transicion(orden, estado.APROBADA)
    return estado.transicion(aprobada, estado.EJECUTADA)


def test_el_planificador_aprueba_una_pendiente():
    _db_listo()
    pub = PublicadorFalso()
    orden = _orden_pendiente()
    estado.publicar(pub, orden)
    nueva = servicio.decidir(pub, orden["id"], "aprobar", rol="planificador", quien="Rubén")
    assert nueva["estado"] == estado.APROBADA


def test_el_supervisor_no_puede_aprobar():
    _db_listo()
    pub = PublicadorFalso()
    orden = _orden_pendiente()
    estado.publicar(pub, orden)
    with pytest.raises(servicio.PermisoDenegado):
        servicio.decidir(pub, orden["id"], "aprobar", rol="supervisor")


def test_rechazar_exige_motivo():
    _db_listo()
    pub = PublicadorFalso()
    orden = _orden_pendiente()
    estado.publicar(pub, orden)
    with pytest.raises(ValueError):
        servicio.decidir(pub, orden["id"], "rechazar", rol="planificador", motivo="")


def test_no_se_certifica_un_cierre_con_diferencias():
    _db_listo()
    pub = PublicadorFalso()
    orden = _orden_ejecutada()
    estado.publicar(pub, orden)
    db.guardar_cierre_crudo({
        "id": f"CIERRE-{_sufijo()}", "ts": "2026-11-20T10:00:00-03:00",
        "orden_id": orden["id"], "tecnico": "Diego", "empresa": "Servipat",
        "audio_url": None, "fotos": [],
    })
    cierre_id = db.obtener_cierre_por_orden(orden["id"])["id"]
    db.actualizar_cierre_procesado(cierre_id, diferencias=["repuesto extra"])
    with pytest.raises(servicio.DecisionInvalida):
        servicio.decidir(pub, orden["id"], "certificar", rol="inspector")


def test_certificar_sin_diferencias_emite_habilita_y_monto():
    _db_listo()
    pub = PublicadorFalso()
    orden = _orden_ejecutada()
    estado.publicar(pub, orden)
    nueva = servicio.decidir(pub, orden["id"], "certificar", rol="inspector", quien="Inspector")
    assert nueva["estado"] == estado.CERTIFICADA
    assert nueva["habilita"].startswith("HAB-")
    assert nueva["monto_habilita_usd"] == 1150


def test_http_lista_y_aprueba():
    _db_listo()
    pub = PublicadorFalso()
    orden = _orden_pendiente()
    estado.publicar(pub, orden)

    servidor = api.crear_servidor(pub, host="127.0.0.1", puerto=0)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    base = f"http://127.0.0.1:{servidor.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/api/ordenes", timeout=10) as r:
            assert r.status == 200
            listado = json.loads(r.read())
        assert any(f["id"] == orden["id"] for f in listado)

        peticion = urllib.request.Request(
            f"{base}/api/ordenes/{orden['id']}/aprobar",
            data=json.dumps({"quien": "Rubén"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "X-Rol": "planificador"},
        )
        with urllib.request.urlopen(peticion, timeout=10) as r:
            assert r.status == 200
            assert json.loads(r.read())["estado"] == estado.APROBADA
    finally:
        servidor.shutdown()
        servidor.server_close()


def test_cli_mapea_acciones_a_roles():
    parser = cli.construir_parser()
    args = parser.parse_args(["aprobar", "ORD-1", "--quien", "Rubén"])
    assert args.comando == "aprobar"
    assert cli.ROLES["aprobar"] == "planificador"
    assert cli.ROLES["certificar"] == "inspector"
    assert cli.ROLES["cerrar"] == "supervisor"
