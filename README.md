# GameKnife

GameKnife 是面向游戏美术资源处理的本地工具箱。Community 版本采用无登录本地工作区，使用 SQLite、本地文件存储、FastAPI、React、TypeScript 和 Vite 组成完整的开源运行链路。

本仓库按前端 workspace 和 Python packages 拆分。Community Web、Community API、公共工具页面、编辑器核心、处理器和工作流都在同一套开源结构内维护，方便开发者按模块阅读、运行和贡献。

## 功能

| 模块 | 能力 |
| --- | --- |
| 去背景 | 上传 JPG、PNG、WebP 后生成透明 PNG，依赖 BiRefNet 模型。 |
| 素材板 | 区域识别、局部抠图、框刷新、素材导出 ZIP。 |
| 图片放大 | 像素风最近邻放大；AI 超分依赖 Real-ESRGAN 模型。 |
| 序列帧 | 导入、清洗、差异查看、导出 PNG 包和 Spine 包。 |
| AI 生成视频 | 独立外部视频 API 工具，调用前需要用户确认。 |
| 视频转序列帧 | 本地视频抽帧、抠图和序列帧项目生成。 |
| 手动编辑 | Canvas2D 单图层编辑、选区、画笔、橡皮、吸管、恢复、保存和导出。 |
| 声效生成 | 通过独立 Stable Audio SFX 服务生成 WAV 声效。 |
| 任务历史 | 查看任务状态、下载结果、删除任务及其输出资产。 |
| 设置与帮助 | 模型安装状态、系统设置、视频 API 配置和使用帮助。 |

## 仓库结构

```text
GameKnife/
├── apps/
│   ├── community-api/        # Community FastAPI 入口
│   └── community-web/        # Community React 外壳
├── packages/
│   ├── api-client/           # 前端 API 封装
│   ├── app-context/          # Principal、Workspace、Permission、Capability 上下文
│   ├── editor-core/          # 手动编辑器核心
│   ├── feature-registry/     # 工具路由和菜单注册
│   ├── image-workflows/      # 公共工具页面
│   ├── shared-types/         # 前端共享类型
│   └── ui-kit/               # 跨工具 UI 组件
├── services/
│   ├── api/                  # FastAPI 路由、请求上下文和响应组装
│   ├── core/                 # Asset、Job、WorkflowRun 等领域模型
│   ├── jobs/                 # 本地任务队列和 SQLite 实现
│   ├── processors/           # 模型和图像处理适配
│   ├── storage/              # 本地文件存储接口和实现
│   └── workflows/            # 后端工作流编排
├── services-extra/
│   └── stable-audio-sfx/     # 独立声效生成服务
├── docker/                   # Community 和声效服务镜像
├── docs/                     # 架构边界和迁移说明
├── package.json              # npm workspace
├── pyproject.toml            # Python packages
└── LICENSE
```

## 运行要求

- Node.js 20.19 或更高版本。
- Python 3.11 或更高版本。
- Windows PowerShell、Linux shell 或 macOS shell 均可运行；下方命令使用 PowerShell 写法。
- 使用真实模型推理时需要匹配本机 CUDA、PyTorch 和显卡驱动环境。
- Docker GPU 部署需要宿主机已安装 NVIDIA 驱动和 NVIDIA Container Toolkit。
- Docker 为可选运行方式。

## 快速开始

在 GameKnife 工程根目录安装前端和 Python 依赖：

```powershell
npm install
python -m pip install -e ".[dev]"
```

主服务本地需要使用 CUDA 推理时，安装项目依赖后再安装与 Docker 主服务一致的 CUDA 版 PyTorch：

```powershell
python -m pip install --index-url https://download.pytorch.org/whl/cu124 "torch==2.5.1+cu124" "torchvision==0.20.1+cu124"
```

验证主服务 PyTorch 环境：

```powershell
python -m pip check
python -c "import torch, torchvision; print('torch', torch.__version__); print('torchvision', torchvision.__version__); print('cuda', torch.version.cuda); print('available', torch.cuda.is_available()); print('device', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO CUDA')"
```

在 GameKnife 工程根目录启动 Community API：

```powershell
python -m uvicorn community_api.main:app --env-file .env --host 0.0.0.0 --port 8000
```

在 GameKnife 工程根目录启动 Community Web：

```powershell
npm run dev:web
```

打开：

```text
http://127.0.0.1:5174
```

开发环境下 Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。生产环境构建后，FastAPI 会在同一端口托管前端静态文件和 `/api`。

## Community 默认上下文

Community 版本没有登录、注册、退出和用户管理入口。后端固定注入本地上下文：

| 字段 | 默认值 |
| --- | --- |
| `principal.id` | `anonymous` |
| `workspace.id` | `local` |
| `edition` | `community` |
| 数据库 | `storage/gameknife.sqlite3` |
| 文件存储根目录 | `storage` |

Community API 不要求 Authorization header、登录 Cookie 或 localStorage token。所有资产、任务和序列帧项目都写入本地工作区。

## 配置

项目使用 `GAMEKNIFE_*` 环境变量。可以从 `.env.example` 复制一份本地配置：

```powershell
copy .env.example .env
```

常用配置：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `GAMEKNIFE_STORAGE_ROOT` | `storage` | 本地资产、输出和模型状态根目录。 |
| `GAMEKNIFE_DB_PATH` | `storage/gameknife.sqlite3` | Community SQLite 数据库路径。 |
| `GAMEKNIFE_WEB_DIST` | `apps/community-web/dist` | 生产环境前端构建产物目录。 |
| `GAMEKNIFE_CORS_ORIGINS` | `*` | API 允许的跨域来源。 |
| `GAMEKNIFE_MAX_UPLOAD_MB` | `50` | 上传文件大小上限。 |
| `GAMEKNIFE_MODEL_INPUT_SIZE` | `1024` | 模型预处理输入尺寸。 |
| `GAMEKNIFE_BIREFNET_MODEL_ROOT` | `storage/models/birefnet` | BiRefNet 模型目录。 |
| `GAMEKNIFE_UPSCALE_MODEL_ROOT` | `storage/models/upscale` | Real-ESRGAN 模型目录。 |
| `GAMEKNIFE_STABLE_AUDIO_BASE_URL` | `http://127.0.0.1:8090` | 独立声效服务地址。 |
| `GAMEKNIFE_STABLE_AUDIO_TOKEN` | `change-me` | Community API 调用声效服务的内部 token。 |
| `GAMEKNIFE_STABLE_AUDIO_TIMEOUT_SECONDS` | `900` | Community API 等待声效服务的超时时间。 |
| `GAMEKNIFE_VISIBLE_GPUS` | `all` | Docker 主服务可见 GPU；由 NVIDIA runtime 读取。 |
| `TORCH_VERSION` | `2.5.1` | 主服务 Docker 构建使用的 PyTorch 版本。 |
| `TORCHVISION_VERSION` | `0.20.1` | 主服务 Docker 构建使用的 torchvision 版本。 |
| `TORCH_INDEX_URL` | `https://download.pytorch.org/whl/cu124` | 主服务 Docker 构建使用的 PyTorch CUDA wheel 索引。 |

完整变量以 `.env.example` 为准。

## 模型安装策略

依赖模型的任务会在创建阶段检查安装状态，推理阶段只读取本地缓存。这样可以避免用户提交任务后才触发隐式下载，也方便在离线或内网环境里定位缺失模型。

| 功能 | 模型 | 安装入口 |
| --- | --- | --- |
| 去背景 | BiRefNet | 设置页或对应模型安装接口。 |
| AI 图片放大 | Real-ESRGAN | 设置页或对应模型安装接口。 |
| 声效生成 | Stable Audio Open | 独立声效服务 `/models/install`。 |

像素风图片放大使用最近邻算法，不要求安装 AI 模型。

## 独立声效服务

声效生成由 `services-extra/stable-audio-sfx` 提供独立 FastAPI 服务。Community API 只负责创建任务、调用内部服务和保存输出资产；模型下载、队列、worker、WAV 编码和推理错误都在声效服务内处理。

在 GameKnife 工程根目录启动服务：

```powershell
cd services-extra\stable-audio-sfx
python -m pip install --extra-index-url https://download.pytorch.org/whl/cu126 -e ".[dev]"
python -m uvicorn app.main:app --env-file ..\..\.env --host 0.0.0.0 --port 8090
```

本地需要使用 CUDA 推理时，先确认当前 Python 环境是 3.10。Stable Audio Open 依赖链会锁定 `stable-audio-tools==0.0.20`，它要求 `torch==2.7.1` 和 `torchaudio==2.7.1`。因此不要使用无版本约束的 `pip install --upgrade torch torchvision torchaudio`，否则 pip 会安装最新版 PyTorch，导致声效服务依赖冲突。

在声效服务目录中安装 CUDA 版 PyTorch：

```powershell
python -m pip uninstall -y torch torchvision torchaudio torchtext torchdata stable-audio-tools pytorch-lightning
python -m pip install --upgrade pip
python -m pip install --index-url https://download.pytorch.org/whl/cu126 "torch==2.7.1+cu126" "torchaudio==2.7.1+cu126" "torchvision==0.22.1+cu126"
python -m pip install --extra-index-url https://download.pytorch.org/whl/cu126 -e ".[dev]"
```

安装后验证当前环境：

```powershell
python -m pip check
python -c "import torch, torchvision, torchaudio, stable_audio_tools; print('torch', torch.__version__); print('torchvision', torchvision.__version__); print('torchaudio', torchaudio.__version__); print('cuda', torch.version.cuda); print('available', torch.cuda.is_available()); print('device', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO CUDA')"
```

服务接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查。 |
| `GET` | `/models/status` | 查看 Stable Audio Open 安装状态和 worker 状态，需要 `X-Gameknife-Token`。 |
| `POST` | `/models/install` | 手动安装 Stable Audio Open 模型，需要 `X-Gameknife-Token`。 |
| `POST` | `/generate` | 生成 WAV 声效，需要 `X-Gameknife-Token`。 |

声效服务相关环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `GAMEKNIFE_STABLE_AUDIO_MODEL_ID` | `stabilityai/stable-audio-open-1.0` | Hugging Face 模型 ID。 |
| `GAMEKNIFE_STABLE_AUDIO_TOKEN` | 空字符串 | 内部调用 token；设置后请求必须携带 `X-Gameknife-Token`。 |
| `GAMEKNIFE_STABLE_AUDIO_QUEUE_SIZE` | `12` | 队列容量。 |
| `GAMEKNIFE_STABLE_AUDIO_GENERATION_TIMEOUT_SECONDS` | `900` | 单次生成等待上限。 |
| `GAMEKNIFE_STABLE_AUDIO_VISIBLE_GPUS` | `all` | Docker 声效服务可见 GPU；也可以写成 `0,1`。 |
| `GAMEKNIFE_STABLE_AUDIO_MODEL_HALF` | `1` | CUDA 环境下使用半精度模型。 |
| `STABLE_AUDIO_TORCH_EXTRA_INDEX_URL` | `https://download.pytorch.org/whl/cu126` | 声效服务 PyTorch CUDA wheel 附加索引。 |

Docker 声效镜像会安装 `stable-audio-tools`、`pytorch-lightning` 以及 CUDA 版 PyTorch 依赖。本地直接运行声效服务时，当前 Python 环境需要按上面的固定版本安装同等推理依赖。

## Docker

Community Docker 会构建前端，再由 FastAPI 同端口提供页面和 `/api`。声效服务作为独立容器运行。

在 GameKnife 工程根目录准备配置：

```powershell
copy .env.example .env
```

Linux、macOS 或 WSL 环境可以使用脚本构建并启动：

```bash
./scripts/build-images.sh
./scripts/deploy.sh
```

不使用脚本时，可以直接运行 Compose：

```powershell
docker compose --env-file .env -f docker\compose.community.yml config
docker compose --env-file .env -f docker\compose.community.yml build
docker compose --env-file .env -f docker\compose.community.yml up -d --no-build
```

默认访问地址：

```text
http://127.0.0.1:8000
```

Docker 运行数据会写入 `docker/gameknife-storage`、`docker/gameknife-huggingface` 和 `docker/gameknife-stable-audio-cache`。

默认 Docker 构建使用 CUDA 版 PyTorch，并通过 Compose 的 `gpus: all` 暴露 NVIDIA 设备。设置页显示 CPU 时，优先检查宿主机 `nvidia-smi`、NVIDIA Container Toolkit、`.env` 里的 `TORCH_INDEX_URL` 和 `GAMEKNIFE_VISIBLE_GPUS`。

`.env` 里的 `HTTP_PROXY`、`HTTPS_PROXY` 只作为镜像构建阶段的代理参数。运行中的容器默认不继承它们，因为容器内的 `127.0.0.1` 指向容器自身，不能代表 Windows 或 WSL 宿主机。模型下载需要显式代理时，使用 `GAMEKNIFE_CONTAINER_HTTP_PROXY` 和 `GAMEKNIFE_CONTAINER_HTTPS_PROXY`。

如果代理运行在 Docker Desktop 可访问的宿主机地址，可以使用：

```env
GAMEKNIFE_CONTAINER_HTTP_PROXY=http://host.docker.internal:7890
GAMEKNIFE_CONTAINER_HTTPS_PROXY=http://host.docker.internal:7890
```

如果代理只在 Windows Clash 中监听本机地址，需要先在 Clash 中允许局域网连接或监听可被 WSL/Docker 访问的地址，再把 `GAMEKNIFE_CONTAINER_*_PROXY` 指向该地址。不要把运行期容器代理设置成 `http://127.0.0.1:7890`。

启动时报 `could not select device driver "" with capabilities: [[gpu]]` 时，说明 Docker daemon 没有可用的 NVIDIA runtime。Ubuntu/WSL 中使用 Docker Engine 时，可以先执行：

```bash
./scripts/install-nvidia-container-toolkit-ubuntu.sh
```

如果当前 CLI 连接的是 Docker Desktop daemon，需要在 Docker Desktop 和 Windows NVIDIA 驱动侧完成 GPU 支持配置，再用下面命令验证：

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

Compose 中包含两个镜像：

| 服务 | 镜像名 | 端口 | 说明 |
| --- | --- | --- | --- |
| `gameknife-community` | `gameknife-community:local` | `8000` | Community Web 和 Community API。 |
| `gameknife-stable-audio-sfx` | `gameknife-stable-audio-sfx:local` | `8090` | 独立声效队列和 Stable Audio 接口。 |

## 测试

后端和声效服务测试：

```powershell
python -m pytest -q apps\community-api\tests services-extra\stable-audio-sfx\tests
```

前端构建：

```powershell
npm run build
```

## API 概览

Community API 统一挂载在 `/api` 下，主要入口包括：

```text
GET    /api/context
POST   /api/assets/images
POST   /api/assets/videos
GET    /api/assets/{asset_id}
GET    /api/jobs
GET    /api/jobs/history
GET    /api/jobs/{job_id}
DELETE /api/jobs/{job_id}
POST   /api/jobs/background-remove
POST   /api/jobs/upscale
POST   /api/jobs/sound-effect
POST   /api/jobs/asset-board/regions
POST   /api/jobs/asset-board/cutout
POST   /api/jobs/asset-board/refine
POST   /api/jobs/asset-board/export
POST   /api/manual-edits/save
```

序列帧、设置和模型安装接口继续由对应模块维护。接口返回中文错误信息，方便本地部署和内网使用场景排查。

## 模块边界

- `GameKnife` 保持 Apache-2.0 开源许可，Community 版本可独立运行。
- `apps/community-web` 负责 Community 外壳、路由、主题和本地上下文初始化。
- `packages/image-workflows` 承载工具页面、任务轮询、结果展示和保存流程。
- `packages/editor-core` 承载手动编辑画布、选区、画笔和 PNG 导出。
- `services/workflows` 承载后端编排，`services/processors` 承载模型和图像处理适配。
- `apps/community-api` 注入匿名主体、本地工作区、SQLite repository 和本地文件存储。

## 贡献

提交前请阅读 `CONTRIBUTING.md`。本项目使用 Conventional Commits。

常规提交前至少运行：

```powershell
python -m pytest -q apps\community-api\tests services-extra\stable-audio-sfx\tests
npm run build
```

新增功能前需要先检查现有 packages 和 services 中是否已有可复用实现。公共包内新增逻辑应保持输入、输出、状态和错误处理清晰，避免把具体页面流程隐藏在顺带参数或调用顺序里。

## 许可证

GameKnife Community 使用 Apache License 2.0。详见 `LICENSE`。
