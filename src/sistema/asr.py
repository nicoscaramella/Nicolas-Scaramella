"""Transcripción local de notas de voz con faster-whisper (CPU)."""

from __future__ import annotations

import logging
import tempfile

from faster_whisper import WhisperModel

from .config import settings

log = logging.getLogger(__name__)

# Sesgo de vocabulario: los nombres de equipo, unidades y formas de decir los
# números que usa el operador. Sin esto, "la uno" puede salir "aún no" y "psi"
# puede salir "pese".
PROMPT_DOMINIO = (
    "Nota de recorrida de la planta PIA-3. Bombas B-101, B-102 y B-103; "
    "filtros F-201A y F-201B; tanque TK-301. Presión de descarga en kg/cm2, "
    "psi o bar; diferencial en kg/cm2; temperatura del rodamiento en grados. "
    "La uno, la dos, la tres, el filtro A, el filtro B. Goteo por empaquetadura."
)


class ASR:
    def __init__(self, modelo: str | None = None, compute: str | None = None):
        self.modelo_nombre = modelo or settings.asr_model
        self.modelo = WhisperModel(
            self.modelo_nombre,
            device="cpu",
            compute_type=compute or settings.asr_compute,
            download_root="/models/whisper",
            cpu_threads=settings.asr_cpu_threads,
        )

    def transcribir(self, audio: bytes) -> str:
        if not audio:
            return ""
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(audio)
            tmp.flush()
            segmentos, info = self.modelo.transcribe(
                tmp.name,
                language="es",
                beam_size=5,
                # Sin fallback de temperatura: la misma nota da el mismo texto.
                temperature=0.0,
                vad_filter=True,
                condition_on_previous_text=False,
                initial_prompt=PROMPT_DOMINIO,
            )
            texto = " ".join(s.text.strip() for s in segmentos if s.text.strip())
        log.info("ASR %.1fs de audio: %s", getattr(info, "duration", 0), texto[:300])
        return texto
