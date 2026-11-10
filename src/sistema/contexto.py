"""Context builder para el análisis de anomalías (Entrega 2).

En la Entrega 1 queda diseñado y probado, pero el análisis completo de causas
probables y órdenes entra en la Entrega 2. Usa LangChain para componer el
contexto y conservar las citas.

El redactado final puede hacerlo un LLM local **opcional**. Si no está
disponible, se devuelve el texto determinista de la plantilla: el contexto
nunca queda vacío ni bloquea el flujo de la tablet.
"""

from __future__ import annotations

import json

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda

from .llm import LLM

SISTEMA = (
    "Sos el asistente de mantenimiento de la planta PIA-3. "
    "Respondé únicamente con la evidencia de los fragmentos recuperados. "
    "Usá solo los fragmentos que respondan directamente la pregunta; "
    "si un fragmento no es relevante, ignoralo y no lo cites. "
    "Citá cada afirmación con la cita entre corchetes, por ejemplo [MBP-4 §11.1]. "
    "No agregues conclusiones, valores ni procedimientos que no estén en el texto. "
    "Respondé la pregunta tal como la haría un operador de planta: no explores "
    "acepciones alternativas de las palabras ni temas que la evidencia no menciona. "
    "Si la evidencia no alcanza, decí exactamente qué falta."
)

PLANTILLA = PromptTemplate.from_template(
    """Sos el asistente de mantenimiento de la planta PIA-3.
Nota confirmada:
{nota}

Parte estructurado:
{filas}

Tendencia de sensores de las últimas horas:
{tendencia}

Fragmentos de manuales, contrato e historial recuperados:
{recuperados}

Devolvé un contexto compacto con la evidencia y la cita de cada fragmento.
No inventes secciones ni valores: si no hay evidencia, decilo.
"""
)


def _texto_recuperados(recuperados: list[dict]) -> str:
    if not recuperados:
        return "(sin fragmentos)"
    return "\n".join(
        f"- [{r.get('cita', '?')}] {r.get('texto', '')[:800]}" for r in recuperados
    )


def construir_contexto(
    nota: str,
    filas: list[dict],
    tendencia: list[dict],
    recuperados: list[dict],
) -> dict:
    cadena = PLANTILLA | RunnableLambda(lambda x: x.to_string())
    texto = cadena.invoke(
        {
            "nota": nota,
            "filas": json.dumps(filas, ensure_ascii=False, indent=2),
            "tendencia": json.dumps(tendencia, ensure_ascii=False, indent=2),
            "recuperados": _texto_recuperados(recuperados),
        }
    )
    return {
        "texto": texto,
        "citas": [r["cita"] for r in recuperados if r.get("cita")],
        "generado_por": "plantilla",
    }


def _con_llm(
    prompt: str,
    citas: list[str],
    base: str,
    llm: LLM | None,
    max_tokens: int | None = None,
) -> dict:
    """Intenta redactar con el LLM; si no está, devuelve el texto base."""
    cliente = llm or LLM()
    respuesta = cliente.chat(prompt, sistema=SISTEMA, max_tokens=max_tokens)
    if respuesta is None:
        return {"texto": base, "citas": citas, "generado_por": "plantilla"}
    return {
        "texto": respuesta.texto,
        "citas": citas,
        "generado_por": cliente.model,
        "tokens_entrada": respuesta.tokens_entrada,
        "tokens_salida": respuesta.tokens_salida,
    }


def redactar_contexto(
    nota: str,
    filas: list[dict],
    tendencia: list[dict],
    recuperados: list[dict],
    llm: LLM | None = None,
    max_tokens: int | None = None,
) -> dict:
    """Contexto para el análisis de una nota, redactado por el LLM si está."""
    base = construir_contexto(nota, filas, tendencia, recuperados)
    return _con_llm(base["texto"], base["citas"], base["texto"], llm, max_tokens)


def responder_consulta(
    pregunta: str,
    recuperados: list[dict],
    llm: LLM | None = None,
    max_tokens: int | None = None,
) -> dict:
    """Respuesta a una consulta del operador sobre el corpus, con citas."""
    evidencia = _texto_recuperados(recuperados)
    citas = [r["cita"] for r in recuperados if r.get("cita")]
    base = f"Pregunta: {pregunta}\n\nEvidencia recuperada:\n{evidencia}"
    prompt = (
        f"{base}\n\n"
        "Respondé en 2 o 3 oraciones. Usá solo los fragmentos relevantes: si "
        "uno no se relaciona con la pregunta, ignoralo y no lo cites. "
        "No explores otros significados de las palabras ni agregues datos que "
        "no estén en la evidencia. Si la pregunta ya quedó respondida, no "
        "agregues aclaraciones sobre lo que falta; decí qué falta solo si no "
        "se puede responder."
    )
    return _con_llm(prompt, citas, base, llm, max_tokens)
