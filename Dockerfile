FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/hf \
    TRANSFORMERS_CACHE=/models/st \
    SENTENCE_TRANSFORMERS_HOME=/models/st

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        git libgomp1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY datos ./datos
COPY scripts ./scripts
COPY evaluacion ./evaluacion
COPY tests ./tests

RUN pip install --upgrade pip \
    && pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -e ".[dev]"

# Los modelos se bajan en el build: en planta-lan no hay internet en runtime.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8', download_root='/models/whisper')"
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small', cache_folder='/models/st')"

CMD ["python", "-m", "sistema.main"]
