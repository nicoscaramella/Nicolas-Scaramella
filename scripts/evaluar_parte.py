"""Primera evaluación del parte contra /api/verdad (solo en desarrollo).

Compara las filas confirmadas en Postgres con los ítems con valor de la verdad
de campo. En modo corrección /api/verdad está cerrada y el script lo avisa.
"""

from __future__ import annotations

import json

from sistema import db
from sistema.planta_api import PlantaAPI


def _cerca(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.051, abs(b) * 0.015)


def main() -> None:
    db.init_db()
    try:
        verdad = PlantaAPI().verdad()
    except Exception as exc:
        print(f"No se pudo leer /api/verdad (¿modo corrección?): {exc}")
        return
    notas = [v for v in verdad if v.get("recorrida_id") and v.get("tipo") != "vivo"]
    aciertos = total = 0
    sin_borrador = []
    preguntas_ok = []
    for nota in notas:
        parte = db.obtener_parte(nota["nota_id"])
        filas = (parte or {}).get("filas") or []
        esperado = [i for i in nota.get("items", []) if i.get("valor") is not None]
        for item in esperado:
            total += 1
            if any(
                f.get("tag") == item["tag"]
                and f.get("valor") is not None
                and _cerca(float(f["valor"]), float(item["valor"]))
                for f in filas
            ):
                aciertos += 1
        if not any((f.get("tag") and f.get("valor") is not None) for f in filas):
            sin_borrador.append(nota["nota_id"])
        if nota.get("ambiguedades"):
            # Las preguntas quedan registradas como mensajes de tablet.
            with db._pool().connection() as con:
                n = con.execute(
                    "SELECT count(*) AS n FROM mensajes_tablet WHERE nota_id = %s AND tipo LIKE 'pregunta%%'",
                    (nota["nota_id"],),
                ).fetchone()["n"]
            preguntas_ok.append((nota["nota_id"], n > 0))
    print(f"Notas: {len(notas)}")
    print(f"Aciertos por campo valor: {aciertos}/{total} = {aciertos/total if total else 0:.3f}")
    print(f"Notas sin borrador con valores: {len(sin_borrador)}")
    print(f"Notas ambiguas: {len(preguntas_ok)}; preguntó: {sum(1 for _, ok in preguntas_ok if ok)}")
    print(json.dumps({"sin_borrador": sin_borrador, "ambiguas": preguntas_ok}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
