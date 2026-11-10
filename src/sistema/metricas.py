"""Telemetría de consumo de tokens (`sistema/metricas`).

El contrato operativo no incluye este modelo; la planta lo valida con
`planta_sim.metricas.ConsumoTokens`. Replicamos el esquema para no depender del
paquete del simulador.
"""

from __future__ import annotations

from datetime import datetime

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
