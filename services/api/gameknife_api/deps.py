from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from gameknife_core import AllowAllPermissionChecker, CapabilitySet, Principal, RequestContext, Workspace
from gameknife_jobs import GameKnifeRepository, SQLiteGameKnifeRepository
from gameknife_storage import LocalStorageProvider
from gameknife_api.birefnet import BiRefNetService
from gameknife_api.stable_audio import StableAudioService
from gameknife_api.upscale_model import UpscaleModelService

COMMUNITY_FEATURES = frozenset(
    {
        "background-remove",
        "asset-board",
        "upscale",
        "sequence",
        "video-generate",
        "video-to-sequence",
        "manual-edit",
        "sound-effect",
        "jobs",
        "settings",
        "help",
    }
)


@dataclass(frozen=True, slots=True)
class CommunitySettings:
    storage_root: Path
    database_path: Path
    cors_origins: list[str]
    web_dist: Path | None = None
    app_version: str = "dev"
    build_number: str = "local"
    git_sha: str = "unknown"
    build_time: str = "unknown"
    max_upload_mb: int = 50
    stable_audio_base_url: str = ""
    stable_audio_token: str = ""
    stable_audio_timeout_seconds: int = 900
    stable_audio_model_id: str = "stabilityai/stable-audio-open-1.0"
    model_input_size: int = 1024
    birefnet_model_root: Path | None = None
    upscale_model_root: Path | None = None

    @classmethod
    def from_env(cls) -> "CommunitySettings":
        storage_root = Path(os.getenv("GAMEKNIFE_STORAGE_ROOT", "storage")).resolve()
        # Community 数据库路径使用 GAMEKNIFE_DB_PATH，保持品牌迁移后的统一环境变量口径。
        database_path = Path(os.getenv("GAMEKNIFE_DB_PATH", storage_root / "gameknife.sqlite3")).resolve()
        web_dist = Path(os.getenv("GAMEKNIFE_WEB_DIST", "apps/community-web/dist")).resolve()
        cors_origins = [item.strip() for item in os.getenv("GAMEKNIFE_CORS_ORIGINS", "*").split(",") if item.strip()]
        max_upload_mb = int(os.getenv("GAMEKNIFE_MAX_UPLOAD_MB", "50"))
        stable_audio_timeout_seconds = int(os.getenv("GAMEKNIFE_STABLE_AUDIO_TIMEOUT_SECONDS", "900"))
        model_input_size = int(os.getenv("GAMEKNIFE_MODEL_INPUT_SIZE", "1024"))
        birefnet_model_root = Path(os.getenv("GAMEKNIFE_BIREFNET_MODEL_ROOT", storage_root / "models" / "birefnet")).resolve()
        upscale_model_root = Path(os.getenv("GAMEKNIFE_UPSCALE_MODEL_ROOT", storage_root / "models" / "upscale")).resolve()
        return cls(
            storage_root=storage_root,
            database_path=database_path,
            cors_origins=cors_origins or ["*"],
            web_dist=web_dist,
            app_version=os.getenv("GAMEKNIFE_APP_VERSION", "dev"),
            build_number=os.getenv("GAMEKNIFE_BUILD_NUMBER", "local"),
            git_sha=os.getenv("GAMEKNIFE_GIT_SHA", "unknown"),
            build_time=os.getenv("GAMEKNIFE_BUILD_TIME", "unknown"),
            max_upload_mb=max_upload_mb,
            stable_audio_base_url=os.getenv("GAMEKNIFE_STABLE_AUDIO_BASE_URL", "").strip(),
            stable_audio_token=os.getenv("GAMEKNIFE_STABLE_AUDIO_TOKEN", "").strip(),
            stable_audio_timeout_seconds=stable_audio_timeout_seconds,
            stable_audio_model_id=os.getenv("GAMEKNIFE_STABLE_AUDIO_MODEL_ID", "stabilityai/stable-audio-open-1.0"),
            model_input_size=model_input_size,
            birefnet_model_root=birefnet_model_root,
            upscale_model_root=upscale_model_root,
        )


def build_runtime_state(app, settings: CommunitySettings) -> None:
    app.state.settings = settings
    app.state.repository = SQLiteGameKnifeRepository(settings.database_path)
    app.state.storage = LocalStorageProvider(settings.storage_root)
    app.state.stable_audio = StableAudioService(
        settings.stable_audio_base_url,
        settings.stable_audio_token,
        settings.stable_audio_timeout_seconds,
    )
    birefnet_model_root = settings.birefnet_model_root or settings.storage_root / "models" / "birefnet"
    upscale_model_root = settings.upscale_model_root or settings.storage_root / "models" / "upscale"
    # Community 的模型安装状态必须跟本地 storage 绑定，不能读取用户机器上的全局 Hugging Face 缓存。
    # 这样新工作区、测试环境和 Docker 数据卷都能独立判断“是否已在本地安装模型”。
    app.state.birefnet = BiRefNetService(model_input_size=settings.model_input_size, model_cache_dir=birefnet_model_root)
    # 超分模型体积较大，运行时只保存服务句柄；真正加载发生在任务执行时，避免 Community 启动被模型初始化拖慢。
    app.state.upscale_models = UpscaleModelService(upscale_model_root)


def get_repository(request: Request) -> GameKnifeRepository:
    return request.app.state.repository


def get_stable_audio_service(request: Request) -> StableAudioService:
    return request.app.state.stable_audio


def get_birefnet_service(request: Request) -> BiRefNetService:
    return request.app.state.birefnet


def get_upscale_model_service(request: Request) -> UpscaleModelService:
    return request.app.state.upscale_models


def get_community_settings(request: Request) -> CommunitySettings:
    return request.app.state.settings


def get_request_context(request: Request) -> RequestContext:
    storage = request.app.state.storage
    return RequestContext(
        principal=Principal(id="anonymous", kind="anonymous", display_name="本地用户"),
        workspace=Workspace(id="local", kind="local", name="本地工作区"),
        permissions=AllowAllPermissionChecker(),
        capabilities=CapabilitySet(edition="community", features=COMMUNITY_FEATURES),
        storage=storage,
    )
