"""Pregunta al corpus indexado y redacta la respuesta con el LLM local.

    docker compose run --rm agente python scripts/preguntar.py \
        "¿Cuál es el límite de vibración de la bomba B-101?"

Recupera fragmentos con la búsqueda híbrida (pgvector + full-text) y deja que
Ollama redacte con citas. Si el LLM no está disponible, imprime la evidencia
recuperada: el script nunca falla por culpa del modelo.
"""

from __future__ import annotations

import argparse
import sys
import time

from sistema import db
from sistema.contexto import responder_consulta
from sistema.llm import LLM
from sistema.rag.buscar import RAG
from sistema.rag.indexar import asegurar_indice


def main() -> int:
    ap = argparse.ArgumentParser(description="Consulta al RAG con LLM local opcional")
    ap.add_argument("pregunta", nargs="+", help="Pregunta en lenguaje natural")
    # Menos fragmentos = menos ruido para un modelo chico. El retrieval sigue
    # siendo híbrido; solo se le pasa al LLM lo mejor rankeado.
    ap.add_argument("-k", type=int, default=3, help="Fragmentos a usar (default 3)")
    args = ap.parse_args()
    pregunta = " ".join(args.pregunta)

    db.init_db()
    rag = RAG()
    if db.rag_count() == 0:
        print("Índice vacío: indexando el corpus desde la planta...")
        asegurar_indice(rag)

    recuperados = rag.buscar(pregunta, k=args.k)
    if not recuperados:
        print("No hay fragmentos para esa consulta.")
        return 1

    inicio = time.perf_counter()
    salida = responder_consulta(pregunta, recuperados)
    segundos = time.perf_counter() - inicio
    print(salida["texto"])
    print()
    print("Fuentes:", ", ".join(salida["citas"]) or "(sin citas)")
    print(f"Generado por: {salida['generado_por']}")
    if salida.get("tokens_salida"):
        print(
            f"Tokens: entrada={salida.get('tokens_entrada', 0)} "
            f"salida={salida['tokens_salida']}"
        )
        # Dejar el consumo en Postgres para que el latido del agente lo
        # publique en sistema/metricas y se vea en el visor.
        try:
            db.registrar_consumo(
                salida["generado_por"],
                salida.get("tokens_entrada", 0),
                salida["tokens_salida"],
                salida["tokens_salida"] / segundos if segundos else None,
            )
        except Exception as exc:
            print(f"No se pudo registrar el consumo: {exc}", file=sys.stderr)
    if salida["generado_por"] == "plantilla":
        print(
            "Nota: el LLM no está disponible; se muestra la evidencia sin redactar.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
