#!/usr/bin/env bash
set -euo pipefail

if [ -x /usr/lib/wsl/lib/nvidia-smi ]; then
  # WSL 会把 Windows 驱动提供的 nvidia-smi 放在这个目录。
  # 用户直接运行时通常能从 PATH 找到它，但 sudo 的 secure_path 可能会漏掉该目录。
  export PATH="/usr/lib/wsl/lib:${PATH}"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "未检测到 Docker，请先安装 Docker Engine。"
  exit 1
fi

docker_server_os="$(docker info --format '{{.OperatingSystem}}' 2>/dev/null || true)"
if echo "$docker_server_os" | grep -qi "docker desktop"; then
  cat <<'TEXT'
当前 docker CLI 连接的是 Docker Desktop daemon。
这个脚本无法修改 Docker Desktop 内部 runtime，请先确认 Docker Desktop、Windows NVIDIA 驱动和 WSL 集成均已更新。
随后用下面命令验证 Docker Desktop 是否已经暴露 GPU：

docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
TEXT
  exit 1
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  cat <<'TEXT'
当前 WSL 环境未检测到 nvidia-smi。
请先在 Windows 安装支持 WSL 的 NVIDIA 驱动，并确认 WSL 内可以直接运行 nvidia-smi。
TEXT
  exit 1
fi

sudo apt-get update
sudo apt-get install -y curl ca-certificates gnupg

sudo install -m 0755 -d /usr/share/keyrings
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 这里只配置 Docker 调用 NVIDIA runtime，显卡驱动仍必须由 Windows/宿主机提供。
# Compose 里的 gpus: all 最终也依赖这一步写入 Docker daemon 配置。
sudo nvidia-ctk runtime configure --runtime=docker

if command -v systemctl >/dev/null 2>&1 && systemctl is-active docker >/dev/null 2>&1; then
  sudo systemctl restart docker
elif command -v service >/dev/null 2>&1; then
  sudo service docker restart
else
  sudo /etc/init.d/docker restart
fi

docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
