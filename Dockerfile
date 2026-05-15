FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIPER_HOST=0.0.0.0 \
    PIPER_PORT=8000 \
    PIPER_ENABLE_GUI=true \
    PIPER_MODELS_DIR=/app/models/piper

WORKDIR /app

COPY pyproject.toml README.md ./
COPY piper_sandbox ./piper_sandbox

RUN pip install --upgrade pip && pip install '.[tts]'

EXPOSE 8000

CMD ["python", "-m", "piper_sandbox.api"]
