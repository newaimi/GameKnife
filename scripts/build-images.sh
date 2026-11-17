#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env. Update the ports, model token, and proxy settings for this deployment before continuing."
fi

# These values are embedded in the image and container environment so the settings page can identify the deployment.
# Generating them at the build entry point keeps manually built images traceable.
export GAMEKNIFE_GIT_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
export GAMEKNIFE_BUILD_NUMBER="$(git rev-list --count HEAD 2>/dev/null || echo local)"
export GAMEKNIFE_APP_VERSION="local-${GAMEKNIFE_BUILD_NUMBER}"
export GAMEKNIFE_BUILD_TIME="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

docker compose --env-file .env -f docker/compose.community.yml build "$@"
docker compose --env-file .env -f docker/compose.community.yml images
