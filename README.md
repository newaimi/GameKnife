# GameKnife Community

GameKnife Community 是无登录的本地游戏素材处理工具箱。当前仓库承载开源核心、Community Web、Community API、公共前端包和公共后端包。

## 开发命令

```powershell
npm install
npm run build
```

```powershell
conda run -n codex python -m pip install -e ".[dev]"
conda run -n codex python -m uvicorn community_api.main:app --host 0.0.0.0 --port 8000
```

## 测试命令

```powershell
conda run -n codex python -m pytest -q apps\community-api\tests services-extra\stable-audio-sfx\tests
npm run build
```

## Community 默认上下文

- 主体：`anonymous`
- 工作区：`local`
- 数据库：`storage/gameknife.sqlite3`
- 文件存储：`storage/assets`

Community API 不读取 Authorization header、登录 Cookie 或本地 token。

## 模型安装

依赖模型的功能在创建任务阶段检查安装状态。BiRefNet、骨骼拆分模型和 Real-ESRGAN 通过设置页手动安装，推理阶段只从本地缓存读取模型文件。默认模型目录分别是 `storage/models/birefnet`、`storage/models/character-rig` 和 `storage/models/upscale`，可通过 `GAMEKNIFE_BIREFNET_MODEL_ROOT`、`GAMEKNIFE_CHARACTER_RIG_MODEL_ROOT`、`GAMEKNIFE_UPSCALE_MODEL_ROOT` 调整。像素风图片放大不要求模型安装。

## Stable Audio

声效生成走独立服务 `services-extra/stable-audio-sfx`。Community API 通过 `GAMEKNIFE_STABLE_AUDIO_BASE_URL` 和 `GAMEKNIFE_STABLE_AUDIO_TOKEN` 调用内部服务。模型通过 `/models/install` 手动安装，生成接口在模型未安装时返回中文错误。

## 视频 API 配置

AI 生成视频是独立工具。外部视频 API 的 provider、base_url 和 api_key 在设置页写入 `system_settings`，任务创建前必须确认外部付费调用。

## Docker

```powershell
copy .env.example .env
docker compose -f docker\compose.community.yml config
docker compose -f docker\compose.community.yml up --build
```

`gameknife-community` 镜像会先构建 Community Web，再由 FastAPI 在同一端口托管前端和 `/api`。`gameknife-stable-audio-sfx` 镜像独立运行声效队列。
