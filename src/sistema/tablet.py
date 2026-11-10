"""Mensajes de tablet y lectura de las respuestas del operador."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .numeros import normalizar, parse_decimal, parse_numero, parse_unidad
from .parser import Parser

CONFIRMA = (
    "confirmo", "correcto", "asi es", "esta bien", "perfecto", "dale",
    "si,", "si.", "confirmado",
)
NO_ENTENDI = ("no te entendi", "como?", "repetime", "no te sigo")


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def filas_para_tablet(filas: list[dict]) -> list[dict]:
    """Quita ``foto``: el contrato ``FilaParte`` no tiene ese campo.

    La foto se guarda en el parte interno (``partes.filas``) y se usa en el
    contexto del Escalado; la tablet solo muestra los campos del contrato.
    """
    return [{k: v for k, v in f.items() if k != "foto"} for f in filas]


def payload_borrador(
    nota_id: str, filas: list[dict], intento: int, aviso: str | None = None
) -> dict:
    texto = "Te leo lo que entendí. ¿Confirmás el parte?"
    if aviso:
        texto = f"{aviso} ¿Confirmás el parte?"
    return {
        "id": f"TAB-{nota_id}-{intento}",
        "ts": ahora(),
        "nota_ids": [nota_id],
        "texto": texto,
        "pantalla": {
            "titulo": "Parte de recorrida · borrador",
            "filas": filas_para_tablet(filas),
            "opciones": [],
        },
        "espera_respuesta": True,
    }


def payload_pregunta(
    nota_id: str, texto: str, opciones: list[str], intento: int, tipo: str
) -> dict:
    return {
        "id": f"TAB-{nota_id}-Q{tipo}-{intento}",
        "ts": ahora(),
        "nota_ids": [nota_id],
        "texto": texto,
        "pantalla": {
            "titulo": "Necesito confirmar",
            "filas": [],
            "opciones": opciones,
        },
        "espera_respuesta": True,
    }


def payload_aviso(
    nota_id: str,
    texto: str,
    equipo: str | None,
    titulo: str = "Alerta de seguridad",
    variable: str = "condicion_insegura",
) -> dict:
    return {
        "id": f"TAB-{nota_id}-SEG",
        "ts": ahora(),
        "nota_ids": [nota_id],
        "texto": texto,
        "pantalla": {
            "titulo": titulo,
            "filas": [
                {
                    "tag": equipo or "PLANTA",
                    "variable": variable,
                    "valor": None,
                    "unidad": None,
                    "observacion": texto,
                }
            ],
            "opciones": [],
        },
        "espera_respuesta": False,
    }


def es_confirmacion(texto: str) -> bool:
    t = normalizar(texto)
    return any(c in t for c in CONFIRMA)


def es_no_entendi(texto: str) -> bool:
    t = normalizar(texto)
    return any(c in t for c in NO_ENTENDI)


def es_sin_borrador(texto: str) -> bool:
    """El operador no ve ninguna fila con valor para confirmar."""
    t = normalizar(texto)
    return "confirmar que" in t or "mostrame lo que anotaste" in t


def es_correccion(texto: str) -> bool:
    """El operador corrige: "No. ...", "Te faltó...", "Corregilo...".

    Ojo: la corrección termina con "y te confirmo", así que no alcanza con
    buscar la palabra "confirmo".
    """
    t = normalizar(texto)
    if re.match(r"^no\b", t):
        return True
    return any(
        p in t
        for p in (" no en ", "te falto", "no lo dije", "corregilo", "arregla", "no, ")
    )


def opciones_equipo(parser: Parser, placeholder: str) -> list[str]:
    tipo = "bomba" if placeholder == "BOMBA" else "filtro"
    return [
        f"{e['tag']} · {e['nombres'][0]}"
        for e in parser.planta.get("equipos", [])
        if e.get("tipo") == tipo
    ]


def resolver_equipo(respuesta: str, parser: Parser, placeholder: str) -> str | None:
    t = normalizar(respuesta)
    tipo = "bomba" if placeholder == "BOMBA" else "filtro"
    candidatos = [
        (normalizar(nombre), e["tag"])
        for e in parser.planta.get("equipos", [])
        if e.get("tipo") == tipo
        for nombre in e.get("nombres", []) + [e["tag"]]
    ]
    candidatos.sort(key=lambda x: len(x[0]), reverse=True)
    for nombre, tag in candidatos:
        if re.search(rf"\b{re.escape(nombre)}\b", t):
            return tag
    return None


def resolver_items(items: list[dict], tag: str, parser: Parser) -> list[dict]:
    """Reemplaza el tag provisorio y completa la unidad de presión si faltaba."""
    eq = parser.equipos.get(tag, {})
    manometro = (eq.get("manometro_local") or {}).get("unidad", "kg/cm2")
    salida = []
    for item in items:
        nuevo = dict(item)
        if nuevo.get("tag") in ("BOMBA", "FILTRO"):
            nuevo["tag"] = tag
            if nuevo.get("variable") == "presion_descarga_local" and not nuevo.get("unidad"):
                nuevo["unidad"] = manometro
        salida.append(nuevo)
    return salida


def _variable_por_unidad(tag: str, unidad: str | None, parser: Parser) -> str | None:
    tipo = parser.equipos.get(tag, {}).get("tipo")
    if unidad in ("kg/cm2", "psi", "bar"):
        return "presion_descarga_local" if tipo == "bomba" else "presion_diferencial"
    if unidad == "degC":
        return "temperatura_rodamiento_ir"
    if unidad == "m":
        return "nivel"
    if unidad == "gotas/min":
        return "goteo_empaquetadura"
    if unidad is None:
        # El operador a veces no repite la unidad al corregir: se infiere por
        # el tipo de equipo (un filtro corrige diferencial, una bomba presión).
        if tipo == "filtro":
            return "presion_diferencial"
        if tipo == "bomba":
            return "presion_descarga_local"
        if tag == "TK-301":
            return "nivel"
    return None


def _tag_de(nombre: str, parser: Parser) -> str | None:
    t = normalizar(nombre)
    candidatos = [
        (normalizar(n), e["tag"])
        for e in parser.planta.get("equipos", [])
        for n in e.get("nombres", []) + [e["tag"]]
    ]
    candidatos.sort(key=lambda x: len(x[0]), reverse=True)
    for n, tag in candidatos:
        if re.search(rf"\b{re.escape(n)}\b", t):
            return tag
    return None


def _observacion(variable: str, valor: float | None, actual: str | None) -> str | None:
    """Recalcula la observación cuando una corrección cambia el valor."""
    if variable == "temperatura_rodamiento_ir":
        return "rodamiento caliente" if valor is not None and valor > 75 else None
    if variable == "presion_diferencial":
        return "diferencial alto" if valor is not None and valor >= 1.5 else None
    if variable == "presion_descarga_local":
        return None
    if variable == "goteo_empaquetadura":
        return actual or "goteo por empaquetadura"
    return actual


def _set(filas: list[dict], tag: str, variable: str, valor: float | None, unidad: str | None) -> None:
    for fila in filas:
        if fila.get("tag") == tag and fila.get("variable") == variable:
            fila["valor"] = valor
            fila["unidad"] = unidad
            fila["observacion"] = _observacion(variable, valor, fila.get("observacion"))
            return
    filas.append({
        "tag": tag, "variable": variable, "valor": valor, "unidad": unidad,
        "observacion": _observacion(variable, valor, None),
    })


def _mismo_valor(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= max(0.011, abs(float(b)) * 0.005)


def _numero_de(texto: str) -> float | None:
    """Número dicho por el operador, incluyendo "1 a 3" por "1,3"."""
    valor = parse_decimal(texto)
    return valor if valor is not None else parse_numero(texto)


def aplicar_correcciones(filas: list[dict], respuesta: str, parser: Parser) -> list[dict]:
    """Aplica las correcciones que dicta el operador, en lenguaje de campo.

    El orden importa: primero se reasigna el valor al equipo correcto y recién
    después se cambia el valor. Si se hace al revés, "La dos estaba en 1600, no
    en 1.3" puede pisar la fila del 112 y duplicar el 1600.
    """
    filas = [dict(f) for f in filas]
    t = normalizar(respuesta)

    # "Eso de ciento doce era de la uno, no de la dos." Reasignar por valor.
    for m in re.finditer(r"eso de (?P<valor>.+?) era de (?P<bueno>[a-z ]+?),? no de (?P<malo>[a-z ]+?)(?:\.|$)", t):
        valor = _numero_de(m.group("valor"))
        bueno = _tag_de(m.group("bueno"), parser)
        if valor is None or not bueno:
            continue
        for fila in filas:
            if _mismo_valor(fila.get("valor"), valor):
                fila["tag"] = bueno

    # "La dos estaba en ciento sesenta psi, no en uno coma tres."
    for m in re.finditer(r"(?P<nombre>[a-z ]+?) estaba en (?P<nuevo>.+?),? no en (?P<viejo>.+?)(?:\.|$)", t):
        tag = _tag_de(m.group("nombre"), parser)
        if not tag:
            continue
        nuevo_txt = m.group("nuevo")
        nuevo = _numero_de(nuevo_txt)
        unidad = parse_unidad(nuevo_txt) or parse_unidad(m.group("viejo"))
        variable = _variable_por_unidad(tag, unidad, parser)
        if nuevo is None or not variable:
            continue
        # Si el valor nuevo ya está en ese equipo, la corrección ya se cumplió:
        # no hay que tocar otra fila (ni duplicar).
        if any(
            f.get("tag") == tag and f.get("variable") == variable
            and _mismo_valor(f.get("valor"), nuevo)
            for f in filas
        ):
            continue
        candidatas = [f for f in filas if f.get("tag") == tag]
        viejo = _numero_de(m.group("viejo"))
        fila = next((f for f in candidatas if _mismo_valor(f.get("valor"), viejo)), None)
        if fila is None:
            fila = next((f for f in candidatas if f.get("variable") == variable), None)
        if fila is None:
            continue
        fila["valor"] = nuevo
        fila["unidad"] = unidad or fila.get("unidad")
        fila["observacion"] = _observacion(variable, nuevo, fila.get("observacion"))

    # "Lo de la dos es en kilos, no en psi."
    for m in re.finditer(r"lo de (?P<nombre>[a-z ]+?) es en (?P<unidad>[a-z/]+),? no en (?P<vieja>[a-z/]+?)(?:\.|$)", t):
        tag = _tag_de(m.group("nombre"), parser)
        unidad = parse_unidad(m.group("unidad"))
        if tag and unidad:
            for fila in filas:
                if fila.get("tag") == tag and fila.get("variable") == "presion_descarga_local":
                    fila["unidad"] = unidad

    # "Te faltó la dos, que estaba en ciento treinta y siete gotas por minuto."
    for m in re.finditer(r"te falto (?P<nombre>[a-z ]+?),? que estaba en (?P<valor>.+?)(?:\.|$)", t):
        tag = _tag_de(m.group("nombre"), parser)
        if not tag:
            continue
        valor = _numero_de(m.group("valor"))
        unidad = parse_unidad(m.group("valor"))
        variable = _variable_por_unidad(tag, unidad, parser)
        if variable:
            _set(filas, tag, variable, valor, unidad)

    # "Lo de la dos no lo dije." Se quita la última fila de ese equipo
    # (la que sobró en el borrador), no todas.
    for m in re.finditer(r"lo de (?P<nombre>[a-z ]+?) no lo dije", t):
        tag = _tag_de(m.group("nombre"), parser)
        if tag:
            for i in range(len(filas) - 1, -1, -1):
                if filas[i].get("tag") == tag:
                    filas.pop(i)
                    break

    return filas
