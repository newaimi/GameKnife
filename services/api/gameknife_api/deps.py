from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from gameknife_core import AllowAllPermissionChecker, CapabilitySet, Principal, RequestContext, Workspace
from gameknife_jobs import SQLiteGameKnifeRepository
from gameknife_storage import LocalStorageProvider
from gameknife_api.birefnet import BiRefNetService
from gameknife_api.character_rig_models import CharacterRigModelService
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
        "character-rig",
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
    stable_audio_base_url: str = ""
    stable_audio_token: str = ""
    stable_audio_timeout_seconds: int = 900
    model_input_size: int = 1024
    upscale_model_root: Path | None = None

    @classmethod
    def from_env(cls) -> "CommunitySettings":
        storage_root = Path(os.getenv("GAMEKNIFE_STORAGE_ROOT", "storage")).resolve()
        # Community 数据库路径使用 GAMEKNIFE_DB_PATH，保持品牌迁移后的统一环境变量口径。
        database_path = Path(os.getenv("GAMEKNIFE_DB_PATH", storage_root / "gameknife.sqlite3")).resolve()
        cors_origins = [item.strip() for item in os.getenv("GAMEKNIFE_CORS_ORIGINS", "*").split(",") if item.strip()]
        stable_audio_timeout_seconds = int(os.getenv("GAMEKNIFE_STABLE_AUDIO_TIMEOUT_SECONDS", "900"))
        model_input_size = int(os.getenv("GAMEKNIFE_MODEL_INPUT_SIZE", "1024"))
        upscale_model_root = Path(os.getenv("GAMEKNIFE_UPSCALE_MODEL_ROOT", storage_root / "models" / "upscale")).resolve()
        return cls(
            storage_root=storage_root,
            database_path=database_path,
            cors_origins=cors_origins or ["*"],
            stable_audio_base_url=os.getenv("GAMEKNIFE_STABLE_AUDIO_BASE_URL", "").strip(),
            stable_audio_token=os.getenv("GAMEKNIFE_STABLE_AUDIO_TOKEN", "").strip(),
            stable_audio_timeout_seconds=stable_audio_timeout_seconds,
            model_input_size=model_input_size,
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
    app.state.birefnet = BiRefNetService(model_input_size=settings.model_input_size)
    app.state.character_rig_models = CharacterRigModelService()
    # 超分模型体积较大，运行时只保存服务句柄；真正加载发生在任务执行时，避免 Community 启动被模型初始化拖慢。
    app.state.upscale_models = UpscaleModelService(settings.upscale_model_root or settings.storage_root / "models" / "upscale")


def get_repository(request: Request) -> SQLiteGameKnifeRepository:
    return request.app.state.repository


def get_stable_audio_service(request: Request) -> StableAudioService:
    return request.app.state.stable_audio


def get_birefnet_service(request: Request) -> BiRefNetService:
    return request.app.state.birefnet


def get_character_rig_model_service(request: Request) -> CharacterRigModelService:
    return request.app.state.character_rig_models


def get_upscale_model_service(request: Request) -> UpscaleModelService:
    return request.app.state.upscale_models


def get_request_context(request: Request) -> RequestContext:
    storage = request.app.state.storage
    return RequestContext(
        principal=Principal(id="anonymous", kind="anonymous", display_name="本地用户"),
        workspace=Workspace(id="local", kind="local", name="本地工作区"),
        permissions=AllowAllPermissionChecker(),
        capabilities=CapabilitySet(edition="community", features=COMMUNITY_FEATURES),
        storage=storage,
    )
