from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import BackgroundTasks, Depends, Request

from gameknife_core import AllowAllPermissionChecker, CapabilitySet, Principal, RequestContext, Workspace
from gameknife_jobs import GameKnifeRepository, InProcessJobDispatcher, JobDispatcher, SQLiteGameKnifeRepository
from gameknife_storage import LocalStorageProvider
from gameknife_api.birefnet import BiRefNetService
from gameknife_api.job_dispatch import build_job_execution_handlers
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
        # Community reads GAMEKNIFE_DB_PATH so the renamed project uses one environment-variable convention.
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
    # Community model state belongs to local storage and must not read the machine-wide Hugging Face cache.
    # New workspaces, tests, and Docker volumes can then determine local installation independently.
    app.state.birefnet = BiRefNetService(model_input_size=settings.model_input_size, model_cache_dir=birefnet_model_root)
    # Upscaling weights are large, so startup stores only the service handle and defers loading until job execution.
    app.state.upscale_models = UpscaleModelService(upscale_model_root)
    # Community assembles every registered executor at startup. Handlers resolve model services from app state at
    # execution time so tests and explicit runtime replacements remain effective without capturing request objects.
    app.state.job_execution_handlers = build_job_execution_handlers(
        app.state.repository,
        lambda: _build_community_request_context(app),
        birefnet_resolver=lambda: app.state.birefnet,
        upscale_model_resolver=lambda: app.state.upscale_models,
        stable_audio_resolver=lambda: app.state.stable_audio,
    )


def recover_community_runtime(app) -> None:
    # BackgroundTasks has no durable continuation after process exit. Recovery closes those persisted executions
    # before the API accepts traffic, then removes only the objects whose Asset rows were atomically retired.
    cleanup_assets = app.state.repository.recover_incomplete_jobs(
        error_message="服务重启，未完成任务已终止。",
        updated_at=datetime.now(UTC).isoformat(),
    )
    for asset in cleanup_assets:
        try:
            app.state.storage.delete_object(asset.path)
        except Exception:  # noqa: BLE001
            # The database cleanup is authoritative. A failed local delete can be reclaimed by a later maintenance
            # pass without making the recovered Job or Sequence visible as delivered.
            continue


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
    return _build_community_request_context(request.app)


def get_job_dispatcher(
    request: Request,
    background_tasks: BackgroundTasks,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    birefnet: BiRefNetService = Depends(get_birefnet_service),
    upscale_models: UpscaleModelService = Depends(get_upscale_model_service),
    stable_audio: StableAudioService = Depends(get_stable_audio_service),
) -> JobDispatcher:
    handlers = getattr(request.app.state, "job_execution_handlers", None)
    if handlers is None:
        # Commercial currently injects a request-scoped project context and can override this dependency with its
        # durable dispatcher later. The fallback preserves the existing API while still scheduling stable IDs only.
        handlers = build_job_execution_handlers(
            repository,
            lambda: context,
            birefnet_resolver=lambda: birefnet,
            upscale_model_resolver=lambda: upscale_models,
            stable_audio_resolver=lambda: stable_audio,
        )
    return InProcessJobDispatcher(
        repository.get_job_for_workspace,
        handlers,
        scheduler=background_tasks.add_task,
    )


def _build_community_request_context(app) -> RequestContext:
    return RequestContext(
        principal=Principal(id="anonymous", kind="anonymous", display_name="本地用户"),
        workspace=Workspace(id="local", kind="local", name="本地工作区"),
        permissions=AllowAllPermissionChecker(),
        capabilities=CapabilitySet(edition="community", features=COMMUNITY_FEATURES),
        storage=app.state.storage,
    )
