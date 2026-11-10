"""Evalúa el retriever híbrido contra la suite de 71 preguntas y BM25."""

from __future__ import annotations

import json
from pathlib import Path

from sistema import db
from sistema.planta_api import PlantaAPI
from sistema.rag.buscar import RAG
from sistema.rag.evaluar import BM25, evaluar, rev_c_antes_que_d
from sistema.rag.indexar import asegurar_indice


def main() -> None:
    db.init_db()
    suite = json.loads(Path("evaluacion/retrieval.json").read_text(encoding="utf-8"))
    rag = RAG()
    print(f"Suite: {len(suite)} preguntas")
    # También completa un índice parcial, no solo el vacío.
    asegurar_indice(rag)
    r = evaluar(rag.citas, suite)
    print("Híbrido (pgvector + full-text):")
    print(json.dumps(r["total"], indent=2, ensure_ascii=False))
    print("Por tipo:")
    for tipo, m in r["por_tipo"].items():
        print(f"  {tipo:14} n={m['n']:2}  " + "  ".join(f"{k}={v}" for k, v in m.items() if k != "n"))
    casos = rev_c_antes_que_d(suite, rag.citas, 5)
    print(f"Rev. C antes que D en top-5: {casos}/{len(suite)}")

    try:
        lineas = PlantaAPI().texto("/documentos/fragmentos.jsonl").splitlines()
        frags = [json.loads(l) for l in lineas if l.strip()]
        bm = evaluar(BM25(frags).buscar, suite)
        print("\nLínea de base BM25:")
        print(json.dumps(bm["total"], indent=2, ensure_ascii=False))
        print(f"Rev. C antes que D en top-5 (BM25): {rev_c_antes_que_d(suite, BM25(frags).buscar, 5)}/{len(suite)}")
    except Exception as exc:
        print(f"\nNo se pudo calcular BM25 en vivo: {exc}")
        print("Línea de base publicada: hit@5=0.85, recall@5=0.66")


if __name__ == "__main__":
    main()
