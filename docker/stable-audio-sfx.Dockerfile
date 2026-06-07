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

# Stable Audio Open 当前依赖链对 Python 和音频系统库比较敏感。
# 声效服务单独使用 Python 3.10，可以避免把这些约束传递到 Community API 主进程。
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
