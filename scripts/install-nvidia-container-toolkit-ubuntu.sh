#!/usr/bin/env bash
set -euo pipefail

if [ -x /usr/lib/wsl/lib/nvidia-smi ]; then
  # WSL exposes the Windows driver's nvidia-smi binary from this directory.
  # An interactive PATH often includes it while sudo's secure_path may not.
  export PATH="/usr/lib/wsl/lib:${PATH}"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker was not detected. Install Docker Engine before continuing."
  exit 1
fi

docker_server_os="$(docker info --format '{{.OperatingSystem}}' 2>/dev/null || true)"
if echo "$docker_server_os" | grep -qi "docker desktop"; then
  cat <<'TEXT'
The Docker CLI is connected to the Docker Desktop daemon.
This script cannot modify Docker Desktop's internal runtime. Update Docker Desktop, the Windows NVIDIA driver, and WSL integration first.
Then verify that Docker Desktop exposes the GPU with:

docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
TEXT
  exit 1
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  cat <<'TEXT'
The current WSL environment cannot find nvidia-smi.
Install an NVIDIA driver with WSL support on Windows and confirm that nvidia-smi runs inside WSL.
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

# This only configures Docker to use the NVIDIA runtime; the host must still provide the GPU driver.
# The Compose `gpus: all` setting also depends on this Docker daemon configuration.
sudo nvidia-ctk runtime configure --runtime=docker

if command -v systemctl >/dev/null 2>&1 && systemctl is-active docker >/dev/null 2>&1; then
  sudo systemctl restart docker
elif command -v service >/dev/null 2>&1; then
  sudo service docker restart
else
  sudo /etc/init.d/docker restart
fi

docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
