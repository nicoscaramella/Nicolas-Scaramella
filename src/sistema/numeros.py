"""Números hablados en las notas de campo.

El operador dicta "ciento doce", "mil seiscientos cuarenta", "uno ocho" o
"dieciocho". El ASR puede devolver palabras o dígitos. Este módulo normaliza
ambos formatos.
"""

from __future__ import annotations

import re
import unicodedata

UNIDADES = {
    "cero": 0, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11,
    "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16,
    "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20,
    "veintiuno": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24,
    "veinticinco": 25, "veintiseis": 26, "veintisiete": 27, "veintiocho": 28,
    "veintinueve": 29,
}
DECENAS = {
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90,
}
CENTENAS = {
    "cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300,
    "cuatrocientos": 400, "quinientos": 500, "seiscientos": 600,
    "setecientos": 700, "ochocientos": 800, "novecientos": 900,
}
NUM_WORDS = set(UNIDADES) | set(DECENAS) | set(CENTENAS) | {"mil"}
SEPARADORES_DECIMALES = {"coma", "punto"}


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y con espacios simples."""
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = texto.replace("veintiun", "veintiuno").replace("veintiun ", "veintiuno ")
    return re.sub(r"\s+", " ", texto).strip()


def _digito(valor: str) -> float:
    """Convierte un número escrito con dígitos, incluyendo 1,640 y 1.8."""
    valor = valor.strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", valor):
        return float(re.sub(r"[.,]", "", valor))
    if re.fullmatch(r"0\d", valor):
        # El ASR transcribe "cero nueve" como "09". En campo eso es 0,9, no 9.
        return int(valor) / 10
    return float(valor.replace(",", "."))


def _entero(tokens: list[str]) -> int:
    total = 0
    actual = 0
    for token in tokens:
        if token == "y":
            continue
        if token in CENTENAS:
            actual += CENTENAS[token]
        elif token in DECENAS:
            actual += DECENAS[token]
        elif token in UNIDADES:
            actual += UNIDADES[token]
        elif token == "mil":
            actual = actual or 1
            total += actual * 1000
            actual = 0
        elif token.isdigit():
            actual += int(token)
        else:
            break
    return total + actual


def _decimal_dicho(tokens: list[str]) -> float | None:
    """1.8 dicho "uno ocho" / "uno coma ocho" / "uno con ocho" / "uno y medio"."""
    if not tokens:
        return None
    if "y" in tokens and tokens[-1] == "medio":
        base = _entero([t for t in tokens if t not in ("y", "medio")])
        return float(base) + 0.5
    for sep in SEPARADORES_DECIMALES | {"con"}:
        if sep in tokens:
            i = tokens.index(sep)
            # "con la pistola" no es decimal: hace falta un número de cada lado.
            if sep == "con":
                antes = tokens[i - 1] if i > 0 else ""
                despues = tokens[i + 1] if i + 1 < len(tokens) else ""
                if antes not in UNIDADES or despues not in UNIDADES:
                    continue
            entero = _entero(tokens[:i])
            decimales = [t for t in tokens[i + 1:] if t in UNIDADES]
            if decimales:
                return float(f"{entero}.{''.join(str(UNIDADES[t]) for t in decimales)}")
    # "uno ocho": dos unidades seguidas, sin decenas ni centenas.
    if len(tokens) == 2 and all(t in UNIDADES and UNIDADES[t] <= 9 for t in tokens):
        return float(f"{UNIDADES[tokens[0]]}.{UNIDADES[tokens[1]]}")
    return None


def _grupo_numerico(tokens: list[str], inicio: int) -> list[str]:
    """Toma desde `inicio` los tokens que forman un número."""
    grupo: list[str] = []
    i = inicio
    while i < len(tokens):
        t = tokens[i]
        if t in NUM_WORDS or t.isdigit() or t in SEPARADORES_DECIMALES:
            grupo.append(t)
            i += 1
            continue
        if t == "y":
            siguiente = tokens[i + 1] if i + 1 < len(tokens) else ""
            if siguiente in NUM_WORDS or siguiente == "medio":
                grupo.append(t)
                i += 1
                continue
        if t == "medio" and grupo and grupo[-1] == "y":
            grupo.append(t)
            i += 1
            continue
        if t == "con":
            # "uno con ocho" es decimal; "grados con la pistola" no.
            anterior = grupo[-1] if grupo else ""
            siguiente = tokens[i + 1] if i + 1 < len(tokens) else ""
            if anterior in UNIDADES and siguiente in UNIDADES:
                grupo.append(t)
                i += 1
                continue
        break
    return grupo


def parse_numero(texto: str) -> float | None:
    """Devuelve el primer número que aparece en el texto, o None."""
    texto = normalizar(texto)
    # Primero, números con dígitos (el ASR suele devolverlos así).
    m = re.search(r"\d+(?:[.,]\d+)*", texto)
    if m:
        return _digito(m.group(0))
    tokens = re.findall(r"[a-z0-9]+", texto)
    for i, token in enumerate(tokens):
        if token in NUM_WORDS or token.isdigit() or token in SEPARADORES_DECIMALES:
            grupo = _grupo_numerico(tokens, i)
            if not grupo:
                continue
            decimal = _decimal_dicho(grupo)
            if decimal is not None:
                return decimal
            return float(_entero(grupo))
    return None


def parse_decimal(texto: str) -> float | None:
    """Decimal que el ASR escribe raro: "0 a 9" o "1 a 3" por "0,9"/"1,3".

    También acepta "1 coma 3" con dígitos. No reemplaza a ``parse_numero``:
    devuelve ``None`` si no encuentra ese patrón, y ahí se usa el parser normal.
    """
    t = normalizar(texto)
    patrones = (
        r"\b(\d)\s+a\s+(\d)\b",
        r"\b(\d)\s+(?:coma|punto)\s+(\d)\b",
    )
    for patron in patrones:
        matches = list(re.finditer(patron, t))
        if matches:
            entero, decimal = matches[-1].groups()
            return float(f"{entero}.{decimal}")
    return None


def parse_ultimo_numero(texto: str) -> float | None:
    """Devuelve el último número del texto, no el primero.

    Sirve cuando un tramo mezcla dos lecturas: "1600 psi de descarga ... el
    filtro A media 1,3 de diferencial". El valor del diferencial es el último.
    """
    texto = normalizar(texto)
    matches = list(re.finditer(r"\d+(?:[.,]\d+)*", texto))
    if matches:
        return _digito(matches[-1].group(0))
    tokens = re.findall(r"[a-z0-9]+", texto)
    ultimo = None
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in NUM_WORDS or token.isdigit() or token in SEPARADORES_DECIMALES:
            grupo = _grupo_numerico(tokens, i)
            if grupo:
                decimal = _decimal_dicho(grupo)
                ultimo = decimal if decimal is not None else float(_entero(grupo))
                i += len(grupo)
                continue
        i += 1
    return ultimo


def parse_unidad(texto: str) -> str | None:
    """Unidad dicha en la nota."""
    t = normalizar(texto)
    if re.search(r"\b(kilos?|kilogramos?|kg)\b", t):
        return "kg/cm2"
    if re.search(r"\b(psi|libras?|lb)\b", t):
        return "psi"
    if re.search(r"\b(bares?|bar)\b", t):
        return "bar"
    if re.search(r"\b(grados?|°c|degc)\b", t):
        return "degC"
    if re.search(r"\b(metros?|m)\b", t):
        return "m"
    if re.search(r"gotas?(?: por minuto)?", t):
        return "gotas/min"
    return None
