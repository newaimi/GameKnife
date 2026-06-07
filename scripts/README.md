# Scripts

本目录用于放置 Community 部署、模型安装和维护脚本。脚本使用 `GAMEKNIFE_*` 环境变量。

- `build-images.sh`：按 `docker/compose.community.yml` 构建 Community 和独立声效服务镜像。
- `deploy.sh`：先构建镜像，再使用 `--no-build` 启动容器，避免启动阶段隐式重建。
