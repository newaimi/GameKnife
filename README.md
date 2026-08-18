# GameKnife

GameKnife is a local toolbox for game-art asset processing. The Community edition provides a login-free local workspace built with SQLite, local file storage, FastAPI, React, TypeScript, and Vite.

Community Web, Community API, shared tool pages, the editor core, processors, and workflows live in one open source structure so contributors can run and understand each module independently.

## Features

| Module | Capability |
| --- | --- |
| Background removal | Upload JPG, PNG, or WebP files and generate transparent PNG output with BiRefNet. |
| Asset board | Detect regions, extract local cutouts, refine bounds, and export assets as ZIP. |
| Image upscaling | Use nearest-neighbor scaling for pixel art or Real-ESRGAN for AI super-resolution. |
| Sequences | Import, clean, compare, and export PNG or Spine packages. |
| AI video generation | Call an external video API after explicit user confirmation. |
| Video-to-sequence | Extract local video frames, remove backgrounds, and create sequence projects. |
| Manual editing | Edit with Canvas2D selections, brushes, erasers, eyedropper, restore, save, and export tools. |
| Sound effects | Generate WAV effects through the standalone Stable Audio SFX service. |
| Job history | Inspect status, download results, and delete jobs with their output assets. |
| Settings and help | Inspect model installation, system settings, video API configuration, and usage guidance. |

## Repository Layout

```text
GameKnife/
├── apps/
│   ├── community-api/        # Community FastAPI entry point
│   └── community-web/        # Community React shell
├── packages/
│   ├── api-client/           # Frontend API client
│   ├── app-context/          # Principal, Workspace, Permission, and Capability context
│   ├── editor-core/          # Manual editor core
│   ├── feature-registry/     # Tool route and menu registry
│   ├── image-workflows/      # Shared tool pages
│   ├── shared-types/         # Shared frontend types
│   └── ui-kit/               # Cross-tool UI components
├── services/
│   ├── api/                  # FastAPI routes, request context, and response assembly
│   ├── core/                 # Asset, Job, WorkflowRun, and other domain records
│   ├── jobs/                 # Local job queue and SQLite implementation
│   ├── processors/           # Model and image-processing adapters
│   ├── storage/              # Local file-storage interface and implementation
│   └── workflows/            # Backend workflow orchestration
├── services-extra/
│   └── stable-audio-sfx/     # Standalone sound-effect service
├── docker/                   # Community and sound-service images
├── docs/                     # Architecture and boundary documentation
├── package.json              # npm workspace
├── pyproject.toml            # Python packages
└── LICENSE
```

## Requirements

- Node.js 20.19 or later.
- Python 3.11 or later for the main Community service.
- Windows PowerShell, Linux shell, or macOS shell. Examples use PowerShell syntax unless stated otherwise.
- A compatible CUDA, PyTorch, and GPU-driver environment for hardware-accelerated model inference.
- NVIDIA drivers and NVIDIA Container Toolkit for Docker GPU deployment.
- Docker is optional.

## Quick Start

Install frontend and Python dependencies from the repository root:

```powershell
npm install
python -m pip install -e ".[dev]"
```

For local CUDA inference in the main service, install the same CUDA-enabled PyTorch versions used by its Docker image:

```powershell
python -m pip install --index-url https://download.pytorch.org/whl/cu124 "torch==2.5.1+cu124" "torchvision==0.20.1+cu124"
```

Verify the main-service PyTorch environment:

```powershell
python -m pip check
python -c "import torch, torchvision; print('torch', torch.__version__); print('torchvision', torchvision.__version__); print('cuda', torch.version.cuda); print('available', torch.cuda.is_available()); print('device', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO CUDA')"
```

Start Community API and Community Web in separate terminals:

```powershell
python -m uvicorn community_api.main:app --env-file .env --host 0.0.0.0 --port 8000
npm run dev:web
```

Open `http://127.0.0.1:5174`. During development, Vite proxies `/api` to `http://127.0.0.1:8000`. In production, FastAPI serves both the built frontend and `/api` from one port.

## Default Community Context

The Community edition has no login, registration, logout, or user-management entry points. The backend always injects this local context:

| Field | Default |
| --- | --- |
| `principal.id` | `anonymous` |
| `workspace.id` | `local` |
| `edition` | `community` |
| Database | `storage/gameknife.sqlite3` |
| File-storage root | `storage` |

Community API requires no Authorization header, login cookie, or localStorage token. Assets, jobs, and sequence projects are written to the local workspace.

## Configuration

The project uses `GAMEKNIFE_*` environment variables. Copy `.env.example` for local configuration:

```powershell
copy .env.example .env
```

| Variable | Default | Description |
| --- | --- | --- |
| `GAMEKNIFE_STORAGE_ROOT` | `storage` | Root for local assets, outputs, and model state. |
| `GAMEKNIFE_DB_PATH` | `storage/gameknife.sqlite3` | Community SQLite database path. |
| `GAMEKNIFE_WEB_DIST` | `apps/community-web/dist` | Production frontend build directory. |
| `GAMEKNIFE_CORS_ORIGINS` | `*` | Origins allowed by the API. |
| `GAMEKNIFE_MAX_UPLOAD_MB` | `50` | Upload size limit. |
| `GAMEKNIFE_MODEL_INPUT_SIZE` | `1024` | Model preprocessing input size. |
| `GAMEKNIFE_BIREFNET_MODEL_ROOT` | `storage/models/birefnet` | BiRefNet model directory. |
| `GAMEKNIFE_UPSCALE_MODEL_ROOT` | `storage/models/upscale` | Real-ESRGAN model directory. |
| `GAMEKNIFE_STABLE_AUDIO_BASE_URL` | `http://127.0.0.1:8090` | Standalone sound-service URL. |
| `GAMEKNIFE_STABLE_AUDIO_TOKEN` | `change-me` | Internal token used by Community API to call the sound service. |
| `GAMEKNIFE_STABLE_AUDIO_TIMEOUT_SECONDS` | `900` | Community API wait timeout for sound generation. |
| `GAMEKNIFE_VISIBLE_GPUS` | `all` | GPUs exposed to the main Docker service by the NVIDIA runtime. |
| `TORCH_VERSION` | `2.5.1` | PyTorch version used by the main Docker build. |
| `TORCHVISION_VERSION` | `0.20.1` | torchvision version used by the main Docker build. |
| `TORCH_INDEX_URL` | `https://download.pytorch.org/whl/cu124` | CUDA wheel index used by the main Docker build. |

See `.env.example` for the complete set.

## Model Installation Policy

Model-dependent jobs check installation status before creation and read only local caches during inference. This prevents implicit downloads after submission and makes missing-model failures easier to diagnose in offline deployments.

| Feature | Model | Installation entry point |
| --- | --- | --- |
| Background removal | BiRefNet | Settings page or the matching model-install endpoint. |
| AI image upscaling | Real-ESRGAN | Settings page or the matching model-install endpoint. |
| Sound generation | Stable Audio Open | Standalone sound service `/models/install`. |

Pixel-art upscaling uses nearest-neighbor interpolation and requires no AI model.

## Standalone Sound Service

`services-extra/stable-audio-sfx` provides sound generation as an independent FastAPI service. Community API creates jobs, calls the internal service, and saves output assets. The sound service owns model download, queueing, workers, WAV encoding, and inference errors.

Start it from the repository root:

```powershell
cd services-extra\stable-audio-sfx
python -m pip install --extra-index-url https://download.pytorch.org/whl/cu126 -e ".[dev]"
python -m uvicorn app.main:app --env-file ..\..\.env --host 0.0.0.0 --port 8090
```

CUDA inference for Stable Audio currently uses Python 3.10. `stable-audio-tools==0.0.20` requires `torch==2.7.1` and `torchaudio==2.7.1`. Do not run an unpinned `pip install --upgrade torch torchvision torchaudio`, because a newer PyTorch release can break the pinned dependency set.

Install and verify the CUDA-enabled dependency set inside the sound-service environment:

```powershell
python -m pip uninstall -y torch torchvision torchaudio torchtext torchdata stable-audio-tools pytorch-lightning
python -m pip install --upgrade pip
python -m pip install --index-url https://download.pytorch.org/whl/cu126 "torch==2.7.1+cu126" "torchaudio==2.7.1+cu126" "torchvision==0.22.1+cu126"
python -m pip install --extra-index-url https://download.pytorch.org/whl/cu126 -e ".[dev]"
python -m pip check
python -c "import torch, torchvision, torchaudio, stable_audio_tools; print('torch', torch.__version__); print('torchvision', torchvision.__version__); print('torchaudio', torchaudio.__version__); print('cuda', torch.version.cuda); print('available', torch.cuda.is_available()); print('device', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO CUDA')"
```

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Health check. |
| `GET` | `/models/status` | Read model and worker status. Requires `X-Gameknife-Token`. |
| `POST` | `/models/install` | Install Stable Audio Open manually. Requires `X-Gameknife-Token`. |
| `POST` | `/generate` | Generate a WAV effect. Requires `X-Gameknife-Token`. |

| Variable | Default | Description |
| --- | --- | --- |
| `GAMEKNIFE_STABLE_AUDIO_MODEL_ID` | `stabilityai/stable-audio-open-1.0` | Hugging Face model ID. |
| `GAMEKNIFE_STABLE_AUDIO_TOKEN` | Empty string | Internal token required by requests when configured. |
| `GAMEKNIFE_STABLE_AUDIO_QUEUE_SIZE` | `12` | Queue capacity. |
| `GAMEKNIFE_STABLE_AUDIO_GENERATION_TIMEOUT_SECONDS` | `900` | Maximum wait for one generation. |
| `GAMEKNIFE_STABLE_AUDIO_VISIBLE_GPUS` | `all` | GPUs exposed to the Docker sound service; values such as `0,1` are accepted. |
| `GAMEKNIFE_STABLE_AUDIO_MODEL_HALF` | `1` | Use half precision on CUDA. |
| `STABLE_AUDIO_TORCH_EXTRA_INDEX_URL` | `https://download.pytorch.org/whl/cu126` | Additional CUDA wheel index for the sound service. |

The Docker image installs `stable-audio-tools`, `pytorch-lightning`, and CUDA-enabled PyTorch. A local environment must use the same pinned inference dependencies.

## Docker

The Community image builds the frontend and serves it with `/api` from FastAPI. The sound service runs in a separate container.

```powershell
copy .env.example .env
```

On Linux, macOS, or WSL, use the deployment scripts:

```bash
./scripts/build-images.sh
./scripts/deploy.sh
```

Or run Compose directly:

```powershell
docker compose --env-file .env -f docker\compose.community.yml config
docker compose --env-file .env -f docker\compose.community.yml build
docker compose --env-file .env -f docker\compose.community.yml up -d --no-build
```

Open `http://127.0.0.1:8000` after startup. Runtime data is written to `docker/gameknife-storage`, `docker/gameknife-huggingface`, and `docker/gameknife-stable-audio-cache`.

The default build uses CUDA-enabled PyTorch and exposes NVIDIA devices through `gpus: all`. If Settings reports CPU, check host `nvidia-smi`, NVIDIA Container Toolkit, `TORCH_INDEX_URL`, and `GAMEKNIFE_VISIBLE_GPUS`.

`HTTP_PROXY` and `HTTPS_PROXY` in `.env` are build-time proxy arguments only. Running containers do not inherit them because `127.0.0.1` inside a container does not refer to the host. Use `GAMEKNIFE_CONTAINER_HTTP_PROXY` and `GAMEKNIFE_CONTAINER_HTTPS_PROXY` for model downloads that need a runtime proxy:

```env
GAMEKNIFE_CONTAINER_HTTP_PROXY=http://host.docker.internal:7890
GAMEKNIFE_CONTAINER_HTTPS_PROXY=http://host.docker.internal:7890
```

If a Windows proxy listens only on localhost, enable LAN access or bind it to an address reachable from WSL and Docker. Never configure a runtime container proxy as `http://127.0.0.1:7890`.

The error `could not select device driver "" with capabilities: [[gpu]]` means the Docker daemon has no NVIDIA runtime. For Docker Engine on Ubuntu or WSL, run:

```bash
./scripts/install-nvidia-container-toolkit-ubuntu.sh
```

When the CLI targets Docker Desktop, configure GPU support in Docker Desktop and the Windows NVIDIA driver, then verify it with:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

| Service | Image | Port | Description |
| --- | --- | --- | --- |
| `gameknife-community` | `gameknife-community:local` | `8000` | Community Web and Community API. |
| `gameknife-stable-audio-sfx` | `gameknife-stable-audio-sfx:local` | `8090` | Standalone sound queue and Stable Audio API. |

## Testing

```powershell
python -m pytest -q apps\community-api\tests services-extra\stable-audio-sfx\tests
npm run build
```

## API Overview

Community API is mounted under `/api`. Main endpoints include:

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

Sequence, settings, and model-installation endpoints remain in their corresponding modules. Runtime API errors currently use Chinese product copy for local and private-network deployments.

## Module Boundaries

- `GameKnife` is licensed under Apache-2.0, and the Community edition runs independently.
- `apps/community-web` owns the Community shell, routes, theme, and local-context initialization.
- `packages/image-workflows` owns tool pages, job polling, result presentation, and save flows.
- `packages/editor-core` owns the manual-edit canvas, selections, brushes, and PNG export.
- `services/workflows` owns backend orchestration, while `services/processors` owns model and image-processing adapters.
- `apps/community-api` injects the anonymous principal, local workspace, SQLite repository, and local file storage.

## Contributing

Read `CONTRIBUTING.md` before submitting changes. The project uses English Conventional Commit messages.

Before adding a feature, search existing packages and services for a reusable implementation. New public-package logic should expose clear inputs, outputs, state, and error behavior without relying on hidden parameters or call order.

## License

GameKnife Community is available under the Apache License 2.0. See `LICENSE`.
