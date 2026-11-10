"""Detección en planta, en código y sin LLM.

Replica las reglas que usa la corrección:
- una observación no vacía que no sea "parada, en reserva" o
  "parada por mantenimiento" es anomalía;
- una presión local fuera de los límites de alarma del sensor también lo es;
- se publica un evento por equipo de la nota.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime

NORMALES = {"parada, en reserva", "parada por mantenimiento"}

# Mismas conversiones que correccion/puntuar.py.
A_KG = {"kg/cm2": 1.0, "psi": 1 / 14.2233, "bar": 1.01972}

VARIABLES_CON_LIMITE = {
    "presion_descarga_local": "presion_descarga",
    "presion_diferencial": "presion_diferencial",
}


def _limites(planta_def: dict) -> dict[tuple[str, str], dict]:
    return {(s["tag"], s["variable"]): s for s in planta_def.get("sensores", [])}


def fuera_de_limite(item: dict, limites: dict) -> bool:
    sensor = VARIABLES_CON_LIMITE.get(item.get("variable"))
    if sensor is None or item.get("valor") is None:
        return False
    lim = limites.get((item.get("tag"), sensor))
    if not lim:
        return False
    valor = item["valor"] * A_KG.get(item.get("unidad") or "kg/cm2", 1.0)
    return (
        lim.get("alarma_alta") is not None and valor >= lim["alarma_alta"]
    ) or (
        lim.get("alarma_baja") is not None and valor <= lim["alarma_baja"]
    )


def es_anomalia(item: dict, limites: dict) -> bool:
    obs = item.get("observacion")
    if obs is not None and obs not in NORMALES:
        return True
    return fuera_de_limite(item, limites)


def eventos_de_parte(
    nota_id: str,
    filas: list[dict],
    planta_def: dict,
    ts: datetime,
    tendencia: str | None = None,
) -> list[dict]:
    """Un EventoSistema por equipo de la nota (o uno sin equipo si no hay filas)."""
    limites = _limites(planta_def)
    por_tag: dict[str, list[dict]] = defaultdict(list)
    for fila in filas:
        if fila.get("tag") in (None, "", "BOMBA", "FILTRO", "PLANTA"):
            continue
        por_tag[fila["tag"]].append(fila)

    if not por_tag:
        return [
            {
                "id": f"EV-{nota_id}-NA",
                "ts": ts,
                "tipo": "SinNovedad",
                "equipo": None,
                "origen": "parte",
                "nota_ids": [nota_id],
                "resumen": "Recorrida sin novedad",
            }
        ]

    salida = []
    for tag, filas_tag in por_tag.items():
        anomalo = any(es_anomalia(f, limites) for f in filas_tag)
        tipo = "Escalado" if anomalo else "SinNovedad"
        if anomalo:
            detalles = [f.get("observacion") or "presión fuera de límite" for f in filas_tag if es_anomalia(f, limites)]
            resumen = f"Anomalía en {tag}: " + "; ".join(dict.fromkeys(d for d in detalles if d))
            extras = []
            fotos = [f["foto"] for f in filas_tag if f.get("foto")]
            if fotos:
                extras.append("fotos: " + ", ".join(fotos))
            if tendencia:
                extras.append("tendencia: " + tendencia)
            if extras:
                resumen += "; " + "; ".join(extras)
        else:
            resumen = f"{tag} sin novedad"
        salida.append(
            {
                "id": f"EV-{nota_id}-{tag}",
                "ts": ts,
                "tipo": tipo,
                "equipo": tag,
                "origen": "parte",
                "nota_ids": [nota_id],
                "resumen": resumen,
            }
        )
    return salida


class SensorDetector:
    """Anomalía sostenida: 5 muestras consecutivas fuera de límite."""

    def __init__(self, planta_def: dict, muestras: int = 5):
        self.limites = _limites(planta_def)
        self.muestras = muestras
        self.hist: dict[tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=muestras + 3))
        self.activos: dict[tuple[str, str], str] = {}

    def ingestar(self, lectura: dict, estado_bombas: dict[str, str] | None = None) -> dict | None:
        tag = lectura.get("tag")
        variable = lectura.get("variable")
        valor = lectura.get("valor")
        if not tag or not variable or valor is None or lectura.get("calidad") == "sin_dato":
            return None
        # Una bomba parada o en reserva no tiene descarga, vibración ni aceite
        # caliente: no es una anomalía del proceso.
        if (
            estado_bombas
            and tag in estado_bombas
            and variable in ("presion_descarga", "vibracion", "temperatura_aceite")
            and estado_bombas[tag] != "marcha"
        ):
            self.hist.pop((tag, variable), None)
            self.activos.pop((tag, variable), None)
            return None
        lim = self.limites.get((tag, variable))
        if not lim:
            return None
        clave = (tag, variable)
        self.hist[clave].append((lectura.get("ts"), valor))
        valores = list(self.hist[clave])
        if len(valores) < self.muestras:
            return None
        ultimos = valores[-self.muestras:]
        alto, bajo = lim.get("alarma_alta"), lim.get("alarma_baja")
        condicion = None
        limite = None
        if alto is not None and all(v >= alto for _, v in ultimos):
            condicion, limite = "alta", alto
        elif bajo is not None and all(v <= bajo for _, v in ultimos):
            condicion, limite = "baja", bajo
        if condicion is None:
            self.activos.pop(clave, None)
            return None
        if clave in self.activos:
            return None
        primero = ultimos[0][0]
        self.activos[clave] = primero
        return {
            "id": f"EV-SENSOR-{tag}-{variable}-{primero}",
            "ts": primero,
            "tipo": "Escalado",
            "equipo": tag,
            "origen": "sensor",
            "nota_ids": [],
            "resumen": f"{tag} {variable} sostenidamente fuera de límite ({condicion}, límite {limite})",
        }
