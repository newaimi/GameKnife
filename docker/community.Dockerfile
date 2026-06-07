# syntax=docker/dockerfile:1.7

FROM node:20.19-slim AS community-web

ARG HTTP_PROXY=
ARG HTTPS_PROXY=
ARG NO_PROXY=
ARG http_proxy=
ARG https_proxy=
ARG no_proxy=

WORKDIR /app
COPY package.json package-lock.json ./
COPY tsconfig.base.json ./
COPY packages ./packages
COPY apps/community-web/package.json ./apps/community-web/package.json
# npm 的详细错误默认只留在构建容器内部。构建失败时直接输出日志，
# 能减少远程服务器排查前端依赖问题的来回成本。
RUN npm ci --no-audit --no-fund || (cat /root/.npm/_logs/*.log; exit 1)
COPY apps/community-web ./apps/community-web
RUN npm --workspace apps/community-web run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GAMEKNIFE_STORAGE_ROOT=/data/storage \
    GAMEKNIFE_DB_PATH=/data/storage/gameknife.sqlite3 \
    GAMEKNIFE_WEB_DIST=/app/apps/community-web/dist \
    HF_HOME=/data/huggingface \
    TRANSFORMERS_CACHE=/data/huggingface/transformers

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libglib2.0-0 libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY apps/community-api ./apps/community-api
COPY services ./services
COPY --from=community-web /app/apps/community-web/dist ./apps/community-web/dist

ARG TORCH_VERSION=2.5.1
ARG TORCHVISION_VERSION=0.20.1
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG GAMEKNIFE_APP_VERSION=dev
ARG GAMEKNIFE_BUILD_NUMBER=local
ARG GAMEKNIFE_GIT_SHA=unknown
ARG GAMEKNIFE_BUILD_TIME=unknown

# 先安装 PyTorch，可以固定 Docker 构建时使用的 torch/torchvision 版本。
# 默认使用 CPU wheel，部署方需要 CUDA wheel 时只要覆盖 TORCH_INDEX_URL。
RUN python -m pip install --upgrade pip \
    && python -m pip install "torch==${TORCH_VERSION}" "torchvision==${TORCHVISION_VERSION}" --index-url "${TORCH_INDEX_URL}" \
    && python -m pip install -e .

ENV GAMEKNIFE_APP_VERSION=${GAMEKNIFE_APP_VERSION} \
    GAMEKNIFE_BUILD_NUMBER=${GAMEKNIFE_BUILD_NUMBER} \
    GAMEKNIFE_GIT_SHA=${GAMEKNIFE_GIT_SHA} \
    GAMEKNIFE_BUILD_TIME=${GAMEKNIFE_BUILD_TIME}

EXPOSE 8000
VOLUME ["/data/storage", "/data/huggingface"]

CMD ["uvicorn", "community_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
