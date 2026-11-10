"""Compara modelos locales de Ollama con la misma consulta y el mismo contexto.

    docker compose run --rm -e LLM_HABILITADO=1 agente \
        python scripts/comparar_llm.py "¿Qué se hace con la cola cuando se corta el enlace?" \
        --modelos ministral-3:3b qwen3.5:9b ornith-1.5:9b --verboso

La recuperación se hace una sola vez; cada modelo recibe los mismos fragmentos.
El tiempo incluye la carga del modelo en memoria (la primera consulta de cada
uno es la más lenta).
"""

from __future__ import annotations

import argparse
import time

from sistema import db
from sistema.config import settings
from sistema.contexto import responder_consulta
from sistema.llm import LLM
from sistema.rag.buscar import RAG
from sistema.rag.indexar import asegurar_indice


def main() -> int:
    ap = argparse.ArgumentParser(description="Compara modelos locales de Ollama")
    ap.add_argument("pregunta", nargs="+", help="Pregunta en lenguaje natural")
    ap.add_argument(
        "--modelos",
        nargs="+",
        default=["ministral-3:3b", "qwen3.5:9b", "ornith-1.5:9b"],
        help="Modelos de Ollama a comparar",
    )
    ap.add_argument("-k", type=int, default=3, help="Fragmentos a usar (default 3)")
    ap.add_argument("--timeout", type=float, default=180, help="Timeout por modelo")
    ap.add_argument("--max-tokens", type=int, default=200, help="Máximo de tokens de salida")
    ap.add_argument(
        "--verboso", action="store_true", help="Imprime la respuesta completa de cada modelo"
    )
    args = ap.parse_args()
    pregunta = " ".join(args.pregunta)

    # La allowlist manda: no se prueba un modelo que el sistema no puede usar.
    permitidos = {m.strip() for m in settings.llm_modelos_permitidos.split(",") if m.strip()}
    omitidos = [m for m in args.modelos if m not in permitidos]
    args.modelos = [m for m in args.modelos if m in permitidos]
    if omitidos:
        print(f"Omitidos por LLM_MODELOS_PERMITIDOS: {', '.join(omitidos)}")
    if not args.modelos:
        print(
            "Ningún modelo permitido. Agregalos a LLM_MODELOS_PERMITIDOS "
            "si querés compararlos."
        )
        return 1

    db.init_db()
    rag = RAG()
    if db.rag_count() == 0:
        print("Índice vacío: indexando el corpus desde la planta...")
        asegurar_indice(rag)
    recuperados = rag.buscar(pregunta, k=args.k)
    if not recuperados:
        print("No hay fragmentos para esa consulta.")
        return 1

    print(f"Pregunta: {pregunta}")
    print(f"Fragmentos: {', '.join(r.get('cita', '?') for r in recuperados)}\n")
    print(f"{'modelo':22} {'seg':>7} {'in':>6} {'out':>6} {'tok/s':>7}  resultado")
    for modelo in args.modelos:
        inicio = time.perf_counter()
        salida = responder_consulta(
            pregunta,
            recuperados,
            llm=LLM(model=modelo, habilitado=True, timeout_s=args.timeout),
            max_tokens=args.max_tokens,
        )
        segundos = time.perf_counter() - inicio
        salida_tokens = salida.get("tokens_salida", 0)
        tps = salida_tokens / segundos if segundos else 0.0
        print(
            f"{modelo:22} {segundos:7.1f} {salida.get('tokens_entrada', 0):6} "
            f"{salida_tokens:6} {tps:7.1f}  {salida['generado_por']}"
        )
        if args.verboso:
            print(f"\n--- {modelo} ---\n{salida['texto']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
