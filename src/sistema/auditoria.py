"""Normaliza una consulta del RAG para auditarla en PostgreSQL."""

from __future__ import annotations


def registro_consulta(
    pregunta: str, recuperados: list[dict], salida: dict
) -> dict:
    return {
        "pregunta": pregunta,
        "recuperados": [
            {
                "cita": r.get("cita"),
                "texto": (r.get("texto") or "")[:500],
            }
            for r in recuperados
        ],
        "respuesta": (salida.get("texto") or "")[:4000],
        "citas_usadas": list(salida.get("citas") or []),
        "modelo": salida.get("generado_por"),
        "tokens_entrada": int(salida.get("tokens_entrada") or 0),
        "tokens_salida": int(salida.get("tokens_salida") or 0),
        "suficiente": bool(salida.get("suficiente")),
        "fallback": salida.get("fallback"),
    }
