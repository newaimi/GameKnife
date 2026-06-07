#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "已创建 .env。请先按实际部署环境修改端口、模型 token 和代理配置。"
fi

# 这些信息会写入镜像和容器运行环境，方便设置页展示当前部署版本。
# 统一从构建入口生成，可以避免手动 docker build 得到不可追踪的镜像。
export GAMEKNIFE_GIT_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
export GAMEKNIFE_BUILD_NUMBER="$(git rev-list --count HEAD 2>/dev/null || echo local)"
export GAMEKNIFE_APP_VERSION="local-${GAMEKNIFE_BUILD_NUMBER}"
export GAMEKNIFE_BUILD_TIME="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

docker compose --env-file .env -f docker/compose.community.yml build "$@"
docker compose --env-file .env -f docker/compose.community.yml images
