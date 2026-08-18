# Scripts

This directory contains Community deployment, model-installation, and maintenance scripts. Scripts use `GAMEKNIFE_*` environment variables.

- `build-images.sh`: Build the Community and standalone sound-service images defined by `docker/compose.community.yml`.
- `deploy.sh`: Build images, then start containers with `--no-build` to prevent implicit rebuilds during startup.
- `install-nvidia-container-toolkit-ubuntu.sh`: Install and verify NVIDIA Container Toolkit for Docker Engine on Ubuntu or WSL. It configures the Docker runtime only; the host still provides the GPU driver.
