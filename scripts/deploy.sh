#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "已创建 .env。请先按实际部署环境修改端口、模型 token 和代理配置。"
fi

# 部署脚本先统一构建，再使用 --no-build 启动，避免启动阶段隐式重建镜像。
export GAMEKNIFE_GIT_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
export GAMEKNIFE_BUILD_NUMBER="$(git rev-list --count HEAD 2>/dev/null || echo local)"
export GAMEKNIFE_APP_VERSION="local-${GAMEKNIFE_BUILD_NUMBER}"
export GAMEKNIFE_BUILD_TIME="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

docker compose --env-file .env -f docker/compose.community.yml build
docker compose --env-file .env -f docker/compose.community.yml up -d --no-build
docker compose --env-file .env -f docker/compose.community.yml ps
