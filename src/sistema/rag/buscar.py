"""Búsqueda híbrida (pgvector + full-text) con fusión RRF."""

from __future__ import annotations

import logging

from sentence_transformers import SentenceTransformer

from .. import db
from ..config import settings
from ..numeros import normalizar

log = logging.getLogger(__name__)

# Secciones del corpus que no aplican a PIA-3: límites de otros modelos de la
# familia y de otras plantas. Se excluyen salvo que el corpus no alcance.
NO_APLICA = ("otros modelos", "otras plantas", "pia-1:", "pia-2:")


def _aplica(fila: dict) -> bool:
    titulo = normalizar(fila.get("titulo") or "")
    return not any(p in titulo for p in NO_APLICA)


def filtrar_por_score(filas: list[dict], min_score: float | None) -> list[dict]:
    """Descarta fragmentos con evidencia semántica débil.

    Un fragmento que vino solo de full-text (sin ``vector_score``) se conserva
    si tuvo match; el umbral se aplica al score vectorial.
    """
    if not min_score:
        return filas
    return [
        f
        for f in filas
        if (
            f.get("vector_score") is not None
            and f["vector_score"] >= min_score
        )
        or (f.get("vector_score") is None and (f.get("fts_score") or 0) > 0)
    ]


class RAG:
    def __init__(self):
        self._modelo: SentenceTransformer | None = None

    @property
    def modelo(self) -> SentenceTransformer:
        if self._modelo is None:
            self._modelo = SentenceTransformer(
                settings.embedding_model, cache_folder="/models/st"
            )
        return self._modelo

    def embed(self, textos: list[str], tipo: str = "passage") -> list[list[float]]:
        prefijo = "passage: " if tipo == "passage" else "query: "
        return self.modelo.encode(
            [prefijo + t for t in textos],
            normalize_embeddings=True,
            batch_size=16,
            show_progress_bar=False,
        ).tolist()

    def buscar(
        self, query: str, k: int = 5, min_score: float | None = None
    ) -> list[dict]:
        if db.rag_count() == 0:
            return []
        emb = self.embed([query], "query")[0]
        vector = db.rag_vector(emb, k=max(k * 3, 20))
        fts = db.rag_fts(query, k=max(k * 3, 20))
        # Reciprocal Rank Fusion, conservando los scores de cada vía.
        puntajes: dict[str, float] = {}
        filas: dict[str, dict] = {}
        for lista, campo in ((vector, "vector_score"), (fts, "fts_score")):
            for r, fila in enumerate(lista):
                clave = fila["id"]
                actual = filas.setdefault(clave, dict(fila))
                actual.setdefault("vector_score", None)
                actual.setdefault("fts_score", None)
                actual[campo] = fila.get("score")
                puntajes[clave] = puntajes.get(clave, 0.0) + 1.0 / (60 + r + 1)
        orden = sorted(puntajes, key=puntajes.get, reverse=True)
        resultado = []
        for i in orden:
            fila = filas[i]
            fila["rrf"] = round(puntajes[i], 6)
            if _aplica(fila):
                resultado.append(fila)
        # Filtrar trampas, score débil y recién después cortar a k.
        return filtrar_por_score(resultado, min_score)[:k]

    def citas(self, query: str, k: int = 5) -> list[str]:
        return [f["cita"] for f in self.buscar(query, k)]
