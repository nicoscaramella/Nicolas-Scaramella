"""Configuración del sistema, leída de variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    sistema: str = os.getenv("SISTEMA_NOMBRE", "Nicolas-Scaramella")
    mqtt_host: str = os.getenv("MQTT_HOST", "broker")
    mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
    planta_url: str = os.getenv("PLANTA_URL", "http://sim:8100")
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://sistema:sistema@postgres:5432/sistema"
    )
    asr_model: str = os.getenv("ASR_MODEL", "small")
    asr_compute: str = os.getenv("ASR_COMPUTE", "int8")
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL", "intfloat/multilingual-e5-small"
    )
    heartbeat_s: int = int(os.getenv("HEARTBEAT_S", "30"))
    max_intentos: int = int(os.getenv("MAX_INTENTOS", "3"))
    timeout_nota_s: int = int(os.getenv("TIMEOUT_NOTA_S", "120"))
    max_pasos: int = int(os.getenv("MAX_PASOS", "8"))
    presupuesto_tokens: int = int(os.getenv("PRESUPUESTO_TOKENS", "0"))
    rag_autoindex: bool = os.getenv("RAG_AUTOINDEX", "1") not in ("0", "false", "no")
    rag_autoindex_delay_s: int = int(os.getenv("RAG_AUTOINDEX_DELAY_S", "60"))
    asr_cpu_threads: int = int(os.getenv("ASR_CPU_THREADS", "2"))
    proxy: str | None = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")

    # LLM local opcional (Ollama). Deshabilitado por defecto: el camino crítico
    # (ASR, parser, detección, tablet) sigue siendo determinista y no lo espera.
    llm_habilitado: bool = os.getenv("LLM_HABILITADO", "0") not in ("0", "false", "no")
    llm_model: str = os.getenv("LLM_MODEL", "ministral-3:3b")
    # Allowlist: solo estos modelos pueden usarse, aunque Ollama tenga otros.
    llm_modelos_permitidos: str = os.getenv(
        "LLM_MODELOS_PERMITIDOS", "ministral-3:3b"
    )
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://host.docker.internal:11434")
    llm_timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "60"))
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "200"))


settings = Settings()
