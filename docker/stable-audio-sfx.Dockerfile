# syntax=docker/dockerfile:1.7

FROM python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/data/huggingface

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

ARG STABLE_AUDIO_TORCH_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cu126

# Stable Audio Open has strict Python and system audio library requirements.
# Keeping the service on Python 3.10 prevents those constraints from affecting the Community API process.
RUN python -m pip install --upgrade pip \
    && python -m pip install --extra-index-url "${STABLE_AUDIO_TORCH_EXTRA_INDEX_URL}" \
        "fastapi" \
        "numpy<2" \
        "pytorch-lightning==2.5.5" \
        "stable-audio-tools==0.0.20" \
        "uvicorn[standard]"

COPY services-extra/stable-audio-sfx/app ./app

EXPOSE 8090
VOLUME ["/data/huggingface"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
