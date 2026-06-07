# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/data/huggingface

WORKDIR /app
COPY services-extra/stable-audio-sfx/pyproject.toml ./pyproject.toml
COPY services-extra/stable-audio-sfx/app ./app
RUN python -m pip install --upgrade pip \
    && python -m pip install -e .

EXPOSE 8090
VOLUME ["/data/huggingface"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
