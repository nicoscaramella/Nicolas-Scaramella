"""Parser determinista de notas de recorrida.

Las notas del operador virtual salen de plantillas acotadas (ver
`planta/sim/planta_sim/operador.py`). Un parser determinista es más rápido y
más predecible que un LLM chico en CPU, y permite validar cada fila como
`FilaParte`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .numeros import (
    normalizar,
    parse_decimal,
    parse_numero,
    parse_ultimo_numero,
    parse_unidad,
)
from .seguridad import detectar_seguridad

NORMALES = {"parada, en reserva", "parada por mantenimiento"}


@dataclass
class ItemParte:
    tag: str
    variable: str
    valor: float | None
    unidad: str | None
    observacion: str | None = None
    foto: str | None = None


@dataclass
class Ambiguedad:
    tipo: str                      # "equipo" | "valor"
    tag: str | None = None
    dicho: str | None = None
    real: float | None = None
    segmento: int = 0


@dataclass
class Resultado:
    items: list[ItemParte] = field(default_factory=list)
    ambiguedades: list[Ambiguedad] = field(default_factory=list)
    seguridad: str | None = None

    def filas(self) -> list[dict]:
        return [
            {
                "tag": i.tag,
                "variable": i.variable,
                "valor": i.valor,
                "unidad": i.unidad,
                "observacion": i.observacion,
            }
            for i in self.items
        ]


class Parser:
    def __init__(self, planta_def: dict):
        self.planta = planta_def
        self.equipos = {e["tag"]: e for e in planta_def.get("equipos", [])}
        self.aliases: list[tuple[str, str | None, bool]] = []
        for e in planta_def.get("equipos", []):
            for nombre in e.get("nombres", []):
                self.aliases.append((normalizar(nombre), e["tag"], False))
            self.aliases.append((normalizar(e["tag"]), e["tag"], False))
        # Alias que no siempre están en planta.yaml.
        self.aliases.extend([
            ("la de reserva", self._tag_reserva(), False),
            ("la bomba", None, True),
            ("el filtro", None, True),
            ("filtro a", "F-201A", False),
            ("filtro b", "F-201B", False),
            # El ASR suele comerse la "l" y la "r": "el fito a media 1.3".
            ("el fito a", "F-201A", False),
            ("el fito b", "F-201B", False),
            ("fito a", "F-201A", False),
            ("fito b", "F-201B", False),
            ("el fito", None, True),
            ("fito", None, True),
            # "bomba"/"filtro" sueltos también son ambiguos: si el ASR escribe
            # "bomba Stein" en vez de "la bomba", el valor no puede quedar
            # pegado al equipo anterior en silencio.
            ("bomba", None, True),
            ("filtro", None, True),
        ])
        self.aliases = [a for a in self.aliases if a[0]]
        self.aliases.sort(key=lambda a: len(a[0]), reverse=True)
        self._regex = re.compile(
            "|".join(
                rf"(?P<a{i}>{re.escape(alias)})"
                for i, (alias, _, _) in enumerate(self.aliases)
            )
        )

    def _tag_reserva(self) -> str | None:
        for e in self.planta.get("equipos", []):
            if e.get("rol_inicial") == "reserva":
                return e["tag"]
        return None

    def tag_en_texto(self, texto: str) -> str | None:
        """Primer equipo concreto mencionado (para la alerta de seguridad)."""
        t = normalizar(texto)
        for alias, tag, ambiguo in self.aliases:
            if tag and not ambiguo and re.search(rf"\b{re.escape(alias)}\b", t):
                return tag
        return None

    def _manometro(self, tag: str) -> str:
        eq = self.equipos.get(tag, {})
        return (eq.get("manometro_local") or {}).get("unidad", "kg/cm2")

    def _tipo(self, tag: str) -> str | None:
        return self.equipos.get(tag, {}).get("tipo")

    def _segmentos(self, texto: str):
        """Corta el texto en tramos, uno por equipo mencionado."""
        matches = []
        for m in self._regex.finditer(texto):
            if m.lastgroup is None:
                continue
            idx = int(m.lastgroup[1:])
            alias, tag, ambiguo = self.aliases[idx]
            matches.append((m.start(), m.end(), tag, ambiguo, alias))
        if not matches:
            tag = self._inferir_tag(texto)
            if tag is None:
                return []
            return [("", texto, tag, tag in ("BOMBA", "FILTRO"))]
        # Sin solapamientos: el alias más largo gana.
        matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        elegidos = []
        fin = -1
        for m in matches:
            if m[0] >= fin:
                elegidos.append(m)
                fin = m[1]
        salida = []
        for i, (ini, f, tag, ambiguo, alias) in enumerate(elegidos):
            siguiente = elegidos[i + 1][0] if i + 1 < len(elegidos) else len(texto)
            tramo = texto[ini:siguiente]
            sin_alias = (texto[ini:f] + texto[f:siguiente])
            # Quita la primera aparición del alias para no confundir "la dos" con el número 2.
            sin_alias = re.sub(rf"\b{re.escape(alias)}\b", " ", sin_alias, count=1)
            salida.append((alias, sin_alias, tag, ambiguo))
        return salida

    def _inferir_tag(self, texto: str) -> str | None:
        if re.search(r"pulmon|tanque|nivel", texto):
            return "TK-301"
        if "diferencial" in texto or "filtro" in texto:
            return "FILTRO"
        if re.search(r"bomba|descarga|rodamiento|aceite|correa|gotea|chorrea|ruido|cavita", texto):
            return "BOMBA"
        return None

    def parse(self, texto: str, fotos: list[str] | None = None) -> Resultado:
        original = normalizar(texto)
        seguridad = detectar_seguridad(original, fotos)
        if seguridad:
            return Resultado(seguridad=seguridad)

        resultado = Resultado()
        foto_idx = 0
        for idx, (alias, tramo, tag, ambiguo) in enumerate(self._segmentos(original)):
            if tag is None or ambiguo or tag in ("BOMBA", "FILTRO"):
                # "la bomba" o "el filtro" sin especificar: hay que preguntar.
                if tag == "FILTRO":
                    resultado.ambiguedades.append(
                        Ambiguedad(tipo="equipo", dicho="el filtro", segmento=idx)
                    )
                else:
                    resultado.ambiguedades.append(
                        Ambiguedad(tipo="equipo", dicho=alias or "la bomba", segmento=idx)
                    )
                    tag = "BOMBA"
            items, amb = self._parse_tramo(tramo, tag, idx)
            if amb:
                resultado.ambiguedades.extend(amb)
            for item in items:
                if "foto" in tramo and item.foto is None and foto_idx < len(fotos or []):
                    item.foto = (fotos or [])[foto_idx]
                    foto_idx += 1
            resultado.items.extend(items)
        resultado.items = self._deduplicar(resultado.items)
        return resultado

    def _parse_tramo(self, t: str, tag: str, idx: int) -> tuple[list[ItemParte], list[Ambiguedad]]:
        items: list[ItemParte] = []
        amb: list[Ambiguedad] = []
        eq = self.equipos.get(tag, {})
        manometro = self._manometro(tag) if tag != "BOMBA" else "kg/cm2"

        # Estado de la bomba.
        if re.search(r"parada,? en reserva", t):
            items.append(ItemParte(tag, "estado", None, None, "parada, en reserva"))
        elif re.search(r"parada por mantenimiento", t):
            items.append(ItemParte(tag, "estado", None, None, "parada por mantenimiento"))
        elif re.search(r"disparada,? no arranca", t):
            items.append(ItemParte(tag, "estado", None, None, "disparada, no arranca"))

        # Presión de descarga local.
        if "descarga" in t:
            pre = t.split("descarga", 1)[0]
            pre = re.sub(r"^\s*(?:esta|está)?\s*(?:en)?\s*", "", pre)
            valor = parse_numero(pre)
            if valor is not None:
                unidad = parse_unidad(pre)
                if unidad is None and tag != "BOMBA":
                    unidad = manometro
                # Con "la bomba" ambiguo la unidad se completa al resolver el equipo.
                items.append(ItemParte(tag, "presion_descarga_local", valor, unidad))

        # Presión diferencial de filtros.
        if "diferencial" in t:
            pre = t.split("diferencial", 1)[0]
            # El tramo puede traer una presión antes ("la bomba en 1600 psi de
            # descarga ... el filtro A media 1.3 de diferencial"). El valor del
            # diferencial es el último número cercano, no el primero.
            # El tokenizador conserva los decimales ("1.3") enteros.
            ventana = " ".join(re.findall(r"[a-z0-9]+(?:[.,][0-9]+)*", pre)[-8:])
            # El ASR con voz humana escribe "0 a 9" por "0,9" y "1 a 3" por
            # "1,3". Se interpreta como decimal antes de buscar el último número.
            valor = parse_decimal(ventana)
            if valor is None:
                valor = parse_ultimo_numero(ventana)
            if valor is not None:
                unidad = parse_unidad(ventana) or "kg/cm2"
                # "dieciocho" por "uno ocho": el valor real es una décima.
                if valor >= 10 and float(valor).is_integer() and re.search(r"\bdieci\w+|\bveinti\w+|\b(?:treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa)\b", ventana):
                    real = valor / 10.0
                    amb.append(Ambiguedad(tipo="valor", tag=tag, dicho=str(int(valor)), real=real, segmento=idx))
                    valor = real
                obs = "diferencial alto" if valor >= 1.5 else None
                items.append(ItemParte(tag, "presion_diferencial", valor, unidad, obs))

        # Temperatura de rodamiento con pistola infrarroja.
        if "rodamiento" in t and "grados" in t:
            # Tomar el número que está entre "rodamiento" y "grados": si el
            # tramo trae antes una presión, no confundirla con la temperatura.
            cola = t.split("rodamiento", 1)[1]
            pre = cola.split("grados", 1)[0]
            valor = parse_numero(pre)
            if valor is not None:
                obs = "rodamiento caliente" if valor > 75 else None
                items.append(ItemParte(tag, "temperatura_rodamiento_ir", valor, "degC", obs))

        # Nivel del tanque pulmón.
        if tag == "TK-301" and re.search(r"metro|nivel", t):
            pre = t.split("metro", 1)[0]
            valor = parse_numero(pre)
            if valor is not None:
                obs = "rebalse a pileta" if re.search(r"rebals|rebalse", t) else None
                items.append(ItemParte(tag, "nivel", valor, "m", obs))
        elif re.search(r"rebals|rebalse", t):
            items.append(ItemParte(tag, "nivel", None, "m", "rebalse a pileta"))

        # Goteo por empaquetadura: el valor no se dice en la nota.
        if "empaquetadura" in t and re.search(r"gotea|goteando|chorrea|pierde", t):
            obs = "pérdida importante por empaquetadura" if re.search(r"pierde bastante|chorrea", t) else "goteo por empaquetadura"
            # El operador dice que gotea, pero no dicta la tasa. Se manda un
            # valor provisorio para que el borrador sea un borrador de verdad
            # y el operador lo corrija con "estaba en ... gotas por minuto".
            items.append(ItemParte(tag, "goteo_empaquetadura", 1.0, "gotas/min", obs))

        # Visor de aceite.
        if "aceite" in t and re.search(r"bajo|casi no tiene|visor", t):
            items.append(ItemParte(tag, "nivel_aceite_visor", None, None, "nivel de aceite bajo"))

        # Correas.
        if "correa" in t:
            estado = "flojas" if "flojas" in t else "rotas" if "rotas" in t else "gastadas" if "gastadas" in t else "mal"
            items.append(ItemParte(tag, "estado_correas", None, None, f"correas {estado}"))

        # Ruidos.
        if "golpeteo" in t:
            items.append(ItemParte(tag, "ruido", None, None, "hace un golpeteo metálico"))
        elif re.search(r"piedras|cavita", t):
            items.append(ItemParte(tag, "ruido", None, None, "suena como si tuviera piedras adentro"))
        elif "ruido raro de rodamiento" in t:
            items.append(ItemParte(tag, "ruido", None, None, "tiene un ruido raro de rodamiento"))

        return items, amb

    @staticmethod
    def _deduplicar(items: list[ItemParte]) -> list[ItemParte]:
        vistos = set()
        salida = []
        for item in items:
            clave = (item.tag, item.variable, item.observacion)
            if clave in vistos:
                continue
            vistos.add(clave)
            salida.append(item)
        return salida
