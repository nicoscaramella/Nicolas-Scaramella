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

    def buscar(self, query: str, k: int = 5) -> list[dict]:
        if db.rag_count() == 0:
            return []
        emb = self.embed([query], "query")[0]
        vector = db.rag_vector(emb, k=max(k * 3, 20))
        fts = db.rag_fts(query, k=max(k * 3, 20))
        # Reciprocal Rank Fusion.
        puntajes: dict[str, float] = {}
        filas: dict[str, dict] = {}
        for lista in (vector, fts):
            for r, fila in enumerate(lista):
                clave = fila["id"]
                filas[clave] = fila
                puntajes[clave] = puntajes.get(clave, 0.0) + 1.0 / (60 + r + 1)
        orden = sorted(puntajes, key=puntajes.get, reverse=True)
        # Filtrar trampas del corpus y recién después cortar a k, para que el
        # hueco lo ocupe el siguiente candidato y no se pierda cobertura.
        return [filas[i] for i in orden if _aplica(filas[i])][:k]

    def citas(self, query: str, k: int = 5) -> list[str]:
        return [f["cita"] for f in self.buscar(query, k)]
