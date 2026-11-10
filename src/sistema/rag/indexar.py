"""Indexación del corpus en pgvector.

El corpus se baja de la API de la planta (`/documentos/...`), no se copia a
mano. Cada fragmento conserva su cita, documento, sección y metadatos.
"""

from __future__ import annotations

import json
import logging

from .. import db
from ..planta_api import PlantaAPI
from .buscar import RAG

log = logging.getLogger(__name__)


def _documentos_meta(api: PlantaAPI) -> dict[str, dict]:
    indice = json.loads(api.texto("/documentos/indice.json"))
    return {d["id"]: d for d in indice.get("documentos", [])}


def indexar(rag: RAG | None = None) -> int:
    api = PlantaAPI()
    meta = _documentos_meta(api)
    lineas = [l for l in api.texto("/documentos/fragmentos.jsonl").splitlines() if l.strip()]
    log.info("Indexando %s fragmentos", len(lineas))
    rag = rag or RAG()
    chunks: list[dict] = []
    for linea in lineas:
        f = json.loads(linea)
        d = meta.get(f.get("doc"), {})
        chunks.append(
            {
                "id": f["id"],
                "doc": f.get("doc"),
                "cita": f.get("id"),
                "numero": f.get("numero"),
                "titulo": f.get("titulo"),
                "clave": f.get("clave"),
                "pagina": f.get("pagina"),
                "vigente": f.get("vigente", d.get("vigente")),
                "equipos": d.get("equipos"),
                "fabricante": d.get("emisor"),
                "tipo": d.get("tipo"),
                "texto": f.get("texto", ""),
            }
        )
    for i in range(0, len(chunks), 32):
        lote = chunks[i:i + 32]
        embeddings = rag.embed([c["texto"] for c in lote], "passage")
        for c, emb in zip(lote, embeddings):
            c["embedding"] = emb
        db.rag_insertar(lote)
        log.info("Indexados %s/%s", min(i + 32, len(chunks)), len(chunks))
    return len(chunks)


def _fragmentos_esperados(api: PlantaAPI) -> int:
    lineas = api.texto("/documentos/fragmentos.jsonl").splitlines()
    return sum(1 for linea in lineas if linea.strip())


def asegurar_indice(rag: RAG | None = None) -> None:
    """Indexa el corpus o completa un índice que quedó a medias.

    Un indexado interrumpido (corte de enlace, reinicio del contenedor) deja
    menos fragmentos que el corpus. Antes se detectaba solo ``count == 0`` y el
    índice quedaba incompleto para siempre; ahora se compara con el corpus.
    """
    try:
        actual = db.rag_count()
        try:
            esperados = _fragmentos_esperados(PlantaAPI())
        except Exception:
            log.warning("No se pudo verificar el corpus; se usa el índice actual")
            if actual > 0:
                log.info("RAG ya indexado (%s fragmentos)", actual)
                return
            esperados = 0
        if esperados and actual >= esperados:
            log.info("RAG ya indexado (%s fragmentos)", actual)
            return
        if actual and esperados:
            log.warning(
                "RAG incompleto (%s/%s): indexando lo que falta", actual, esperados
            )
        # rag_insertar es ON CONFLICT DO NOTHING: completar no duplica.
        indexar(rag)
    except Exception:
        log.exception("No se pudo indexar el corpus; el RAG queda vacío")
