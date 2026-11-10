"""Orquestador: MQTT, tablet, detección, latido y outbox."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
import paho.mqtt.client as mqtt
import yaml

from . import db, tablet
from .asr import ASR
from .config import settings
from .deteccion import SensorDetector, eventos_de_parte
from .historial import SENSOR, aviso_fuera_de_rango, resumen_tendencia
from .metricas import ConsumoTokens
from .parser import Parser
from .planta_api import PlantaAPI
from .publicacion import Publicador
from .rag.buscar import RAG
from .rag.indexar import asegurar_indice
from .seguridad import detectar_seguridad, texto_alerta

log = logging.getLogger(__name__)

COLA: queue.Queue = queue.Queue()
API = PlantaAPI()
EJECUTOR_NOTAS = ThreadPoolExecutor(max_workers=1)


def cargar_planta() -> dict:
    for intento in range(10):
        try:
            return API.planta()
        except Exception:
            log.warning("Esperando /api/planta (%s/10)", intento + 1)
            time.sleep(2)
    ruta = Path(__file__).resolve().parents[2] / "datos" / "planta.yaml"
    log.warning("Uso la copia local de planta.yaml: %s", ruta)
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


PLANTA = cargar_planta()
PARSER = Parser(PLANTA)
SENSORES = SensorDetector(PLANTA)
ASR_MODEL: ASR | None = None
PUBLICADOR: Publicador | None = None
RAG_MODEL = RAG()
ESTADO_BOMBAS: dict[str, str] = {}


def asr() -> ASR:
    global ASR_MODEL
    if ASR_MODEL is None:
        ASR_MODEL = ASR()
    return ASR_MODEL


def publicador() -> Publicador:
    assert PUBLICADOR is not None
    return PUBLICADOR


def actualizar_enlace() -> None:
    """Toma el estado del enlace de la planta antes de publicar.

    El latido solo mira cada 15 s; una nota puede llegar justo después del
    corte. Consultar ``/api/estado`` antes de publicar evita marcar como
    sincronizado algo que salió con el enlace caído.
    """
    if PUBLICADOR is None:
        return
    try:
        PUBLICADOR.enlace_ok = bool(API.estado().get("enlace_arriba", True))
    except Exception:
        log.warning("No se pudo leer enlace_arriba; se mantiene el último estado")


def publicar_estado() -> None:
    publicador().publicar(
        "sistema/estado",
        {
            "ts": datetime.now(timezone.utc),
            "sistema": settings.sistema,
            "enlace_ok": publicador().enlace_ok,
            "pendientes_sincronizar": db.pendientes_count(),
        },
    )


# --------------------------------------------------------------------------- tablet


def enviar_borrador(nota_id: str, filas: list[dict], intento: int) -> None:
    # Sin valores no hay nada que el operador pueda confirmar: se registra
    # directo para no entrar en el loop "¿Confirmar qué?".
    if not any(f.get("valor") is not None for f in filas):
        enviar_sin_valores(nota_id, filas)
        return
    aviso = None
    parte = db.obtener_parte(nota_id)
    if parte and parte.get("ts"):
        avisos = [
            a for fila in filas
            if (a := aviso_fuera_de_rango(API, fila, parte["ts"].isoformat()))
        ]
        aviso = " ".join(avisos) if avisos else None
    payload = tablet.payload_borrador(nota_id, filas, intento, aviso)
    db.guardar_mensaje(
        payload["id"], nota_id, "borrador", payload, filas, [], intento
    )
    db.actualizar_parte(nota_id, filas=filas, estado="esperando_borrador", intento=intento)
    publicador().publicar("sistema/tablet", payload)


def enviar_pregunta(
    nota_id: str, texto: str, opciones: list[str], filas: list[dict],
    ambiguedades: list[dict], intento: int, tipo: str,
) -> None:
    payload = tablet.payload_pregunta(nota_id, texto, opciones, intento, tipo)
    db.guardar_mensaje(payload["id"], nota_id, f"pregunta_{tipo}", payload, filas, ambiguedades, intento)
    db.actualizar_parte(
        nota_id, filas=filas, ambiguedades=ambiguedades, estado=f"esperando_{tipo}", intento=intento
    )
    publicador().publicar("sistema/tablet", payload)


def enviar_aviso(
    nota_id: str,
    texto: str,
    equipo: str | None,
    titulo: str = "Alerta de seguridad",
    variable: str = "condicion_insegura",
) -> None:
    payload = tablet.payload_aviso(nota_id, texto, equipo, titulo, variable)
    db.guardar_mensaje(payload["id"], nota_id, "aviso", payload, payload["pantalla"]["filas"], [], 0)
    publicador().publicar("sistema/tablet", payload)


def publicar_alerta(nota_id: str, codigo: str, texto: str, ts: str) -> None:
    equipo = PARSER.tag_en_texto(texto)
    evento = {
        "id": f"EV-{nota_id}-SEG",
        "ts": ts,
        "tipo": "AlertaSeguridad",
        "equipo": equipo,
        "origen": "parte",
        "nota_ids": [nota_id],
        "resumen": f"Condición insegura {codigo}",
    }
    if db.guardar_evento(evento):
        publicador().publicar("sistema/eventos", evento)
    enviar_aviso(nota_id, texto_alerta(codigo), equipo)
    db.actualizar_parte(
        nota_id,
        filas=[{"tag": equipo or "PLANTA", "variable": "condicion_insegura", "valor": None,
                "unidad": None, "observacion": texto_alerta(codigo)}],
        estado="seguridad",
    )
    log.info("Alerta %s publicada para %s", codigo, nota_id)


def tendencia_de(filas: list[dict], ts: datetime) -> str | None:
    """Tendencia de las últimas horas para el contexto del Escalado."""
    partes: list[str] = []
    vistos: set[tuple[str, str]] = set()
    for fila in filas:
        variable = fila.get("variable")
        if variable not in SENSOR or fila.get("valor") is None:
            continue
        clave = (fila.get("tag"), variable)
        if clave in vistos:
            continue
        vistos.add(clave)
        resumen = resumen_tendencia(API, fila["tag"], variable, ts.isoformat())
        if resumen:
            partes.append(f"{fila['tag']} {variable}: {resumen}")
    return "; ".join(partes) or None


def enviar_sin_valores(nota_id: str, filas: list[dict]) -> None:
    """Parte sin valores numéricos: se registra sin pedir confirmación.

    El operador virtual no puede confirmar un borrador que, después de filtrar
    los valores nulos, queda vacío. Si se lo manda igual, contesta "¿Confirmar
    qué?" y se entra en un loop. Se registra el parte con las observaciones y
    se publican los eventos directamente.
    """
    if not filas:
        filas = [{"tag": "PLANTA", "variable": "estado", "valor": None,
                  "unidad": None, "observacion": "sin novedad"}]
    payload = {
        "id": f"TAB-{nota_id}-SINVAL",
        "ts": tablet.ahora(),
        "nota_ids": [nota_id],
        "texto": "No hay valores numéricos para confirmar; registro el parte con las observaciones.",
        "pantalla": {
            "titulo": "Parte registrado",
            "filas": tablet.filas_para_tablet(filas),
            "opciones": [],
        },
        "espera_respuesta": False,
    }
    db.guardar_mensaje(payload["id"], nota_id, "sin_valores", payload, filas, [], 0)
    publicador().publicar("sistema/tablet", payload)
    db.actualizar_parte(nota_id, filas=filas, estado="confirmado")
    parte = db.obtener_parte(nota_id)
    ts = parte["ts"] if parte else datetime.now(timezone.utc)
    for evento in eventos_de_parte(nota_id, filas, PLANTA, ts, tendencia_de(filas, ts)):
        if db.guardar_evento(evento):
            publicador().publicar("sistema/eventos", evento)
    log.info("Parte %s registrado sin valores (solo observaciones)", nota_id)


# --------------------------------------------------------------------------- notas


def procesar_nota(nota: dict) -> None:
    nota_id = nota["id"]
    if not db.guardar_parte(nota):
        parte = db.obtener_parte(nota_id)
        log.info("Nota %s ya estaba (%s); no se reprocesa", nota_id, (parte or {}).get("estado"))
        return
    if nota_id.startswith("VIVO-"):
        # Nota grabada en vivo: no tiene parte esperado. No se manda borrador
        # porque el operador virtual no tiene verdad de campo para comparar.
        db.actualizar_parte(nota_id, estado="vivo")
        log.info("Nota VIVO %s: sin parte esperado; se registra y no se pide confirmación", nota_id)
        return
    # La foto de rotura de descarga es S1 aunque el ASR falle: el enlace puede
    # estar caído justo cuando llega la nota.
    codigo_foto = detectar_seguridad("", nota.get("fotos"))
    if codigo_foto:
        publicar_alerta(nota_id, codigo_foto, "", nota["ts"])
        return
    log.info("Nota %s de %s", nota_id, nota.get("operador"))
    actualizar_enlace()
    pasos = 0
    tokens = 0
    audio = b""
    if nota.get("audio_url"):
        try:
            audio = API.descargar(nota["audio_url"])
        except Exception:
            log.exception("No se pudo bajar el audio de %s", nota_id)
    for url in nota.get("fotos") or []:
        try:
            API.descargar(url)
        except Exception:
            log.warning("No se pudo bajar la foto %s de %s", url, nota_id)
    pasos += 1

    texto = ""
    if audio:
        try:
            texto = asr().transcribir(audio)
        except Exception:
            log.exception("Falló la transcripción de %s", nota_id)
    pasos += 1
    log.info("Transcripción: %s", texto)

    if not audio or not texto.strip():
        # Condición de corte: sin audio o sin transcripción no hay parte que
        # confirmar. No se registra como "sin valores" (eso es una nota válida
        # que no trae números).
        motivo = "No se pudo bajar el audio" if not audio else "No se pudo transcribir la nota"
        log.error("%s de %s; queda para revisión", motivo, nota_id)
        db.actualizar_parte(nota_id, estado="cortado")
        enviar_aviso(
            nota_id,
            f"{motivo}; queda para revisión.",
            None,
            titulo="Nota para revisión",
            variable="estado",
        )
        return

    # Presupuesto de pasos/tokens: en esta entrega no hay LLM, así que los
    # tokens son 0 y el presupuesto queda documentado para la Entrega 2.
    if pasos > settings.max_pasos or (
        settings.presupuesto_tokens and tokens > settings.presupuesto_tokens
    ):
        log.error("Presupuesto agotado en la nota %s (pasos=%s, tokens=%s)", nota_id, pasos, tokens)
        db.actualizar_parte(nota_id, estado="cortado")
        return

    codigo = detectar_seguridad(texto, nota.get("fotos"))
    if codigo:
        publicar_alerta(nota_id, codigo, texto, nota["ts"])
        return

    resultado = PARSER.parse(texto, nota.get("fotos"))
    pasos += 1
    if pasos > settings.max_pasos:
        log.error("Presupuesto de pasos agotado en la nota %s", nota_id)
        db.actualizar_parte(nota_id, estado="cortado")
        return
    amb = [asdict(a) for a in resultado.ambiguedades]
    equipo_amb = next((a for a in resultado.ambiguedades if a.tipo == "equipo"), None)
    valor_amb = next((a for a in resultado.ambiguedades if a.tipo == "valor"), None)

    if equipo_amb is not None:
        placeholder = "FILTRO" if "filtro" in (equipo_amb.dicho or "") else "BOMBA"
        opciones = tablet.opciones_equipo(PARSER, placeholder)
        texto_preg = "¿De qué equipo hablás? Elegí una opción."
        enviar_pregunta(nota_id, texto_preg, opciones, resultado.filas(), amb, 0, "equipo")
        return

    if valor_amb is not None:
        texto_preg = "¿El diferencial era uno coma ocho o dieciocho? Decime el valor."
        enviar_pregunta(nota_id, texto_preg, [], resultado.filas(), amb, 0, "valor")
        return

    filas = resultado.filas()
    if not filas:
        filas = [{"tag": "PLANTA", "variable": "estado", "valor": None,
                  "unidad": None, "observacion": "sin novedad"}]
    enviar_borrador(nota_id, filas, 1)


# --------------------------------------------------------------------------- respuestas


def procesar_respuesta(resp: dict) -> None:
    msg = db.obtener_mensaje(resp.get("mensaje_id", ""))
    if not msg:
        log.warning("Respuesta a un mensaje desconocido: %s", resp.get("mensaje_id"))
        return
    actualizar_enlace()
    nota_id = msg["nota_id"]
    filas = msg["filas"] or []
    amb = msg["ambiguedades"] or []
    intento = int(msg["intento"] or 0)
    tipo = msg["tipo"]
    texto = resp.get("texto") or ""
    log.info("Respuesta de %s a %s (%s): %s", nota_id, msg["id"], tipo, texto)

    if tipo == "pregunta_equipo":
        placeholder = "FILTRO" if any("filtro" in (a.get("dicho") or "") for a in amb) else "BOMBA"
        tag = tablet.resolver_equipo(texto, PARSER, placeholder)
        if not tag:
            if intento < settings.max_intentos:
                opciones = tablet.opciones_equipo(PARSER, placeholder)
                enviar_pregunta(nota_id, "No te entendí. ¿Cuál de estos es?", opciones, filas, amb, intento + 1, "equipo")
                return
            tag = tablet.opciones_equipo(PARSER, placeholder)[0].split(" · ")[0]
        filas = tablet.resolver_items(filas, tag, PARSER)
        enviar_borrador(nota_id, filas, max(intento + 1, 1))
        return

    if tipo == "pregunta_valor":
        # El valor ya se infirió (1.8); la pregunta existe para que el operador
        # confirme que no era 18. Si no entendió, seguimos con el borrador.
        enviar_borrador(nota_id, filas, max(intento + 1, 1))
        return

    if tipo == "borrador":
        if tablet.es_sin_borrador(texto):
            # El operador no vio filas con valor: no hay nada que confirmar.
            enviar_sin_valores(nota_id, filas)
            return
        if intento >= settings.max_intentos + 5:
            payload = {
                "id": f"TAB-{nota_id}-FIN-{intento}",
                "ts": tablet.ahora(),
                "nota_ids": [nota_id],
                "texto": "No pude confirmar el parte; queda pendiente para revisión.",
                "pantalla": {"titulo": "Pendiente", "filas": filas, "opciones": []},
                "espera_respuesta": False,
            }
            db.guardar_mensaje(payload["id"], nota_id, "sin_confirmar", payload, filas, [], intento)
            publicador().publicar("sistema/tablet", payload)
            db.actualizar_parte(nota_id, filas=filas, estado="sin_confirmar")
            log.error("Demasiados intentos en %s; queda sin confirmar", nota_id)
            return
        if (
            tablet.es_confirmacion(texto)
            and not tablet.es_correccion(texto)
            and not tablet.es_no_entendi(texto)
        ):
            db.actualizar_parte(nota_id, estado="confirmado")
            parte = db.obtener_parte(nota_id)
            ts = parte["ts"] if parte else datetime.now(timezone.utc)
            for evento in eventos_de_parte(nota_id, filas, PLANTA, ts, tendencia_de(filas, ts)):
                if db.guardar_evento(evento):
                    publicador().publicar("sistema/eventos", evento)
            payload = {
                "id": f"TAB-{nota_id}-ok",
                "ts": tablet.ahora(),
                "nota_ids": [nota_id],
                "texto": "Listo, guardé el parte. Gracias.",
                "pantalla": {"titulo": "Parte guardado", "filas": [], "opciones": []},
                "espera_respuesta": False,
            }
            publicador().publicar("sistema/tablet", payload)
            log.info("Parte %s confirmado", nota_id)
            return

        if tablet.es_no_entendi(texto) and intento < settings.max_intentos:
            enviar_borrador(nota_id, filas, intento + 1)
            return

        filas = tablet.aplicar_correcciones(filas, texto, PARSER)
        enviar_borrador(nota_id, filas, intento + 1)
        return


# --------------------------------------------------------------------------- workers


def worker() -> None:
    while True:
        item = COLA.get()
        try:
            if item[0] == "nota":
                futuro = EJECUTOR_NOTAS.submit(procesar_nota, item[1])
                try:
                    futuro.result(timeout=settings.timeout_nota_s)
                except FutureTimeout:
                    log.error(
                        "Timeout global de %ss en la nota %s",
                        settings.timeout_nota_s, item[1].get("id"),
                    )
                    db.actualizar_parte(item[1]["id"], estado="timeout")
            elif item[0] == "respuesta":
                procesar_respuesta(item[1])
        except Exception:
            log.exception("Error procesando %s", item[0])
        finally:
            COLA.task_done()


# --------------------------------------------------------------------------- MQTT


def on_connect(client, userdata, flags, reason_code, properties=None):
    log.info("MQTT conectado: %s", reason_code)
    client.subscribe([("planta/recorridas", 1), ("planta/respuestas", 1), ("planta/sensores/#", 1)])


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        log.exception("Payload inválido en %s", msg.topic)
        return
    if msg.topic == "planta/recorridas":
        COLA.put(("nota", payload))
    elif msg.topic == "planta/respuestas":
        COLA.put(("respuesta", payload))
    elif msg.topic.startswith("planta/sensores/"):
        try:
            evento = SENSORES.ingestar(payload, ESTADO_BOMBAS)
        except Exception:
            log.exception("Error en detector de sensores")
            return
        if evento and db.guardar_evento(evento):
            publicador().publicar("sistema/eventos", evento)


# --------------------------------------------------------------------------- latido y métricas


def probe_enlace() -> bool:
    try:
        r = httpx.get("https://www.google.com/generate_204", timeout=3, trust_env=True)
        return r.status_code < 500
    except Exception:
        return False


def metricas_payload() -> dict:
    modelos = [
        {"modelo": f"faster-whisper-{settings.asr_model}", "tokens_entrada": 0, "tokens_salida": 0,
         "tokens_total": 0, "tokens_por_segundo": None, "velocidad_estimada": False},
        {"modelo": "parser-determinista", "tokens_entrada": 0, "tokens_salida": 0,
         "tokens_total": 0, "tokens_por_segundo": None, "velocidad_estimada": False},
    ]
    return {
        "ts": datetime.now(timezone.utc),
        "sistema": settings.sistema,
        "tokens_entrada": 0,
        "tokens_salida": 0,
        "tokens_total": 0,
        "tokens_por_segundo": None,
        "velocidad_estimada": False,
        "modelos": modelos,
    }


def heartbeat_loop() -> None:
    global PUBLICADOR, ESTADO_BOMBAS
    while True:
        try:
            try:
                estado = API.estado()
                ESTADO_BOMBAS = {
                    b["tag"]: b.get("estado", "marcha") for b in estado.get("bombas", [])
                }
                # La planta es la fuente de verdad del enlace simulado.
                enlace = bool(estado.get("enlace_arriba", True))
            except Exception:
                log.warning("No se pudo leer /api/estado para el estado de bombas")
                enlace = probe_enlace()
            # Con el enlace caído lo publicado queda pendiente de sincronizar
            # y el latido lo muestra; al volver se reintenta en orden.
            publicador().enlace_ok = enlace
            publicar_estado()
            publicador().publicar("sistema/metricas", metricas_payload())
            publicador().reintentar()
        except Exception:
            log.exception("Error en el latido")
        time.sleep(settings.heartbeat_s)


# --------------------------------------------------------------------------- arranque


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    db.init_db()
    log.info("Sistema %s arrancando", settings.sistema)
    log.info("Planta: %s equipos", len(PLANTA.get("equipos", [])))
    # Preload del ASR: si la primera nota llega con el enlace caído, el modelo
    # ya tiene que estar en memoria y no intentar bajar nada de Hugging Face.
    try:
        asr()
        log.info("ASR %s cargado", settings.asr_model)
    except Exception:
        log.exception("No se pudo cargar el ASR al arranque")
    global ESTADO_BOMBAS
    try:
        ESTADO_BOMBAS = {
            b["tag"]: b.get("estado", "marcha")
            for b in API.estado().get("bombas", [])
        }
    except Exception:
        log.warning("No se pudo leer el estado inicial de bombas")

    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sistema-{settings.sistema}")
    cliente.on_connect = on_connect
    cliente.on_message = on_message
    cliente.reconnect_delay_set(1, 30)
    global PUBLICADOR
    PUBLICADOR = Publicador(cliente, al_quedar_pendiente=publicar_estado)
    for intento in range(30):
        try:
            cliente.connect(settings.mqtt_host, settings.mqtt_port, 60)
            break
        except Exception:
            log.warning("Esperando broker MQTT (%s/30)", intento + 1)
            time.sleep(2)
    cliente.loop_start()

    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    if settings.rag_autoindex:
        def autoindex() -> None:
            # La indexación compite por CPU con el ASR. Se retrasa para no
            # demorar la primera nota (y sobre todo la alerta de seguridad).
            time.sleep(settings.rag_autoindex_delay_s)
            asegurar_indice(RAG_MODEL)

        threading.Thread(target=autoindex, daemon=True).start()

    log.info("Listo. Escuchando planta/recorridas y planta/respuestas")
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        cliente.loop_stop()
        cliente.disconnect()


if __name__ == "__main__":
    main()
