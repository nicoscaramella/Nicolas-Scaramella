"""Telemetría de consumo de tokens (`sistema/metricas`).

El contrato operativo no incluye este modelo; la planta lo valida con
`planta_sim.metricas.ConsumoTokens`. Replicamos el esquema para no depender del
paquete del simulador.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConsumoModelo(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    modelo: str = Field(min_length=1)
    tokens_entrada: int = Field(ge=0)
    tokens_salida: int = Field(ge=0)
    tokens_total: int = Field(ge=0)
    tokens_por_segundo: float | None = Field(default=None, ge=0)
    velocidad_estimada: bool = False

    @model_validator(mode="after")
    def comprobar_total(self):
        if self.tokens_total != self.tokens_entrada + self.tokens_salida:
            raise ValueError("El total debe ser entrada + salida")
        return self


def modelos_metricas(consumo: list[dict], asr_model: str) -> list[dict]:
    """Modelos del latido: ASR/parser fijos + consumo acumulado del LLM."""
    modelos = [
        {
            "modelo": f"faster-whisper-{asr_model}",
            "tokens_entrada": 0,
            "tokens_salida": 0,
            "tokens_total": 0,
            "tokens_por_segundo": None,
            "velocidad_estimada": False,
        },
        {
            "modelo": "parser-determinista",
            "tokens_entrada": 0,
            "tokens_salida": 0,
            "tokens_total": 0,
            "tokens_por_segundo": None,
            "velocidad_estimada": False,
        },
    ]
    for fila in consumo:
        entrada = int(fila.get("tokens_entrada") or 0)
        salida = int(fila.get("tokens_salida") or 0)
        modelos.append(
            {
                "modelo": fila["modelo"],
                "tokens_entrada": entrada,
                "tokens_salida": salida,
                "tokens_total": entrada + salida,
                "tokens_por_segundo": fila.get("tokens_por_segundo"),
                "velocidad_estimada": bool(fila.get("velocidad_estimada")),
            }
        )
    return modelos


def payload_metricas(
    modelos: list[dict], sistema: str, ts: datetime | None = None
) -> dict:
    return {
        "ts": ts or datetime.now(timezone.utc),
        "sistema": sistema,
        "tokens_entrada": sum(m["tokens_entrada"] for m in modelos),
        "tokens_salida": sum(m["tokens_salida"] for m in modelos),
        "tokens_total": sum(m["tokens_total"] for m in modelos),
        "tokens_por_segundo": next(
            (m["tokens_por_segundo"] for m in modelos if m["tokens_por_segundo"] is not None),
            None,
        ),
        "velocidad_estimada": any(m["velocidad_estimada"] for m in modelos),
        "modelos": modelos,
    }


class ConsumoTokens(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    ts: datetime
    sistema: str
    tokens_entrada: int = Field(ge=0)
    tokens_salida: int = Field(ge=0)
    tokens_total: int = Field(ge=0)
    tokens_por_segundo: float | None = Field(default=None, ge=0)
    velocidad_estimada: bool = False
    modelos: list[ConsumoModelo]

    @model_validator(mode="after")
    def comprobar_totales(self):
        for campo in ("tokens_entrada", "tokens_salida", "tokens_total"):
            if getattr(self, campo) != sum(getattr(m, campo) for m in self.modelos):
                raise ValueError("El total debe coincidir con el desglose por modelo")
        if len({m.modelo for m in self.modelos}) != len(self.modelos):
            raise ValueError("Cada modelo debe aparecer una sola vez")
        if self.ts.utcoffset() is None:
            raise ValueError("La fecha debe incluir la zona horaria")
        return self
