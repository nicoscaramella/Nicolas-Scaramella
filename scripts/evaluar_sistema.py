"""Evaluación end-to-end sobre los datos de la planta: aciertos, costo y latencia.

Corre el mismo camino que el sistema (descarga de audio → ASR local → parser)
sobre las notas de `/api/verdad`, sin depender de la base ni del flujo MQTT.
Sirve para desarrollo: en modo corrección `/api/verdad` está cerrada.

    docker compose run --rm agente python scripts/evaluar_sistema.py
    docker compose run --rm agente python scripts/evaluar_sistema.py --limite 3
"""

from __future__ import annotations

import argparse
import json
import statistics
import time

from sistema.asr import ASR
from sistema.parser import Parser
from sistema.planta_api import PlantaAPI


def _cerca(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) <= max(0.051, abs(float(b)) * 0.015)


def _p95(valores: list[float]) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, round(0.95 * (len(ordenados) - 1)))]


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluación de aciertos, costo y latencia")
    ap.add_argument("--limite", type=int, help="máximo de notas a evaluar")
    ap.add_argument("--json", action="store_true", help="salida JSON además de la tabla")
    args = ap.parse_args()

    api = PlantaAPI()
    try:
        verdad = api.verdad()
        planta = api.planta()
    except Exception as exc:
        print(f"No se pudo leer /api/verdad o /api/planta (¿modo corrección?): {exc}")
        return 1

    notas = [v for v in verdad if v.get("recorrida_id") and v.get("tipo") != "vivo"]
    if args.limite:
        notas = notas[: args.limite]
    if not notas:
        print("No hay notas para evaluar.")
        return 1

    parser = Parser(planta)
    asr = ASR()
    filas_salida: list[dict] = []
    latencias: list[float] = []
    aciertos = esperados_total = 0
    completas = 0
    sin_borrador: list[str] = []

    print(
        f"{'nota':13} {'desc_s':>7} {'asr_s':>7} "
        f"{'parse_s':>8} {'total_s':>8} {'aciertos':>9}"
    )
    for nota in notas:
        t0 = time.perf_counter()
        audio = b""
        if nota.get("audio_url"):
            audio = api.descargar(nota["audio_url"])
        t1 = time.perf_counter()
        texto = asr.transcribir(audio) if audio else ""
        t2 = time.perf_counter()
        resultado = parser.parse(texto, nota.get("fotos"))
        filas = resultado.filas()
        t3 = time.perf_counter()

        esperados = [i for i in nota.get("items", []) if i.get("valor") is not None]
        ok = sum(
            1
            for item in esperados
            if any(
                f.get("tag") == item["tag"]
                and f.get("valor") is not None
                and _cerca(f["valor"], item["valor"])
                for f in filas
            )
        )
        aciertos += ok
        esperados_total += len(esperados)
        if esperados and ok == len(esperados):
            completas += 1
        if not any(f.get("valor") is not None for f in filas):
            sin_borrador.append(nota["nota_id"])

        total = t3 - t0
        latencias.append(total)
        filas_salida.append(
            {
                "nota": nota["nota_id"],
                "descarga_s": round(t1 - t0, 3),
                "asr_s": round(t2 - t1, 3),
                "parse_s": round(t3 - t2, 3),
                "total_s": round(total, 3),
                "aciertos": f"{ok}/{len(esperados)}",
            }
        )
        print(
            f"{nota['nota_id']:13} {t1 - t0:7.3f} {t2 - t1:7.3f} "
            f"{t3 - t2:8.3f} {total:8.3f} {ok:>4}/{len(esperados):<4}"
        )

    media = statistics.mean(latencias) if latencias else 0.0
    resumen = {
        "notas": len(notas),
        "aciertos_por_campo": aciertos,
        "campos_esperados": esperados_total,
        "precision_campos": round(aciertos / esperados_total, 3) if esperados_total else 0.0,
        "notas_completas": completas,
        "notas_sin_borrador": sin_borrador,
        "latencia_media_s": round(media, 3),
        "latencia_p95_s": round(_p95(latencias), 3),
        "costo_usd": 0.0,
        "modelos": "ASR local (faster-whisper small) + parser determinista",
        "nota": "La primera nota incluye la carga del modelo ASR en memoria.",
    }
    print()
    print(f"Notas: {resumen['notas']}")
    print(
        f"Aciertos por campo: {aciertos}/{esperados_total} = "
        f"{resumen['precision_campos']:.3f}"
    )
    print(f"Notas completas: {completas}/{len(notas)}")
    print(f"Notas sin borrador: {len(sin_borrador)} {sin_borrador}")
    print(
        f"Latencia: media {resumen['latencia_media_s']:.3f} s, "
        f"p95 {resumen['latencia_p95_s']:.3f} s"
    )
    print("Costo: USD 0 (modelos locales, sin nube)")
    if args.json:
        print(json.dumps({"resumen": resumen, "notas": filas_salida}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
