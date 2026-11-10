"""Métricas de retrieval: hit@k, recall@k, distractor@k y MRR.

Misma lógica y umbrales que `planta/corpus/evaluar.py` de la Academia
(`evaluar(buscar, suite, ks)`), copiada al repo para poder correr sin depender
del paquete del simulador.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Callable

_PARADA = set("""a al algo como con cual cuales cuando de del el ella en es esta este esto hay la las le lo los mas me
mi muy no o otra otras para pero por que se si sin sobre su sus un una uno y ya ante hace hacer tiene son fue ser
puede qué cuál cuáles cómo cuánto cuántos dónde""".split())


def tokens(texto: str) -> list[str]:
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return [
        t[:6]
        for t in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", texto)
        if t not in _PARADA
    ]


class BM25:
    def __init__(self, fragmentos: list[dict], k1: float = 1.4, b: float = 0.75):
        self.ids = [f["id"] for f in fragmentos]
        self.docs = [Counter(tokens(f["texto"])) for f in fragmentos]
        self.largos = [sum(d.values()) for d in self.docs]
        self.prom = sum(self.largos) / len(self.largos)
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.k1, self.b = k1, b

    def buscar(self, pregunta: str, k: int) -> list[str]:
        q = tokens(pregunta)
        puntajes = []
        for i, d in enumerate(self.docs):
            s = 0.0
            for t in q:
                if t in d:
                    tf = d[t]
                    s += self.idf[t] * tf * (self.k1 + 1) / (
                        tf + self.k1 * (1 - self.b + self.b * self.largos[i] / self.prom)
                    )
            if s > 0:
                puntajes.append((s, i))
        puntajes.sort(reverse=True)
        return [self.ids[i] for _, i in puntajes[:k]]


def evaluar(
    buscar: Callable[[str, int], list[str]], suite: list[dict], ks=(1, 3, 5, 10)
) -> dict:
    kmax = max(max(ks), 20)
    filas = []
    for q in suite:
        res = buscar(q["pregunta"], kmax)
        rel, dis = set(q["relevantes"]), set(q["distractores"])
        pos_rel = next((i for i, r in enumerate(res) if r in rel), None)
        fila = {
            "id": q["id"],
            "tipo": q["tipo"],
            "mrr": 1 / (pos_rel + 1) if pos_rel is not None else 0.0,
            "top": res[:5],
        }
        for k in ks:
            top = res[:k]
            fila[f"hit@{k}"] = float(any(r in rel for r in top))
            fila[f"recall@{k}"] = len(rel & set(top)) / len(rel)
            pos_dis = next((i for i, r in enumerate(top) if r in dis), None)
            fila[f"distractor@{k}"] = float(
                pos_dis is not None and (pos_rel is None or pos_dis < pos_rel)
            )
        filas.append(fila)
    metricas = [m for m in filas[0] if "@" in m or m == "mrr"]
    total = {
        m: round(sum(f[m] for f in filas) / len(filas), 3) for m in metricas
    }
    por_tipo = {}
    for tipo in sorted({f["tipo"] for f in filas}):
        sub = [f for f in filas if f["tipo"] == tipo]
        por_tipo[tipo] = {
            "n": len(sub),
            **{
                m: round(sum(f[m] for f in sub) / len(sub), 3)
                for m in metricas
                if m.startswith(("recall@", "hit@"))
            },
        }
    return {"n": len(filas), "total": total, "por_tipo": por_tipo, "preguntas": filas}


def rev_c_antes_que_d(suite: list[dict], buscar: Callable[[str, int], list[str]], k: int = 5) -> int:
    """Cuántas veces aparece la Rev. C antes que la D en el top-k."""
    casos = 0
    for q in suite:
        top = buscar(q["pregunta"], k)
        pos_c = next((i for i, c in enumerate(top) if c.startswith("TX350-C")), None)
        pos_d = next((i for i, c in enumerate(top) if c.startswith("TX350-D")), None)
        if pos_c is not None and (pos_d is None or pos_c < pos_d):
            casos += 1
    return casos
