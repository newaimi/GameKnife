from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from gameknife_core import AllowAllPermissionChecker, CapabilitySet, Principal, RequestContext, Workspace
from gameknife_jobs import SQLiteGameKnifeRepository
from gameknife_storage import LocalStorageProvider

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

    @classmethod
    def from_env(cls) -> "CommunitySettings":
        storage_root = Path(os.getenv("GAMEKNIFE_STORAGE_ROOT", "storage")).resolve()
        database_path = Path(os.getenv("GAMEKNIFE_SQLITE_PATH", storage_root / "gameknife.sqlite3")).resolve()
        cors_origins = [item.strip() for item in os.getenv("GAMEKNIFE_CORS_ORIGINS", "*").split(",") if item.strip()]
        return cls(storage_root=storage_root, database_path=database_path, cors_origins=cors_origins or ["*"])


def build_runtime_state(app, settings: CommunitySettings) -> None:
    app.state.settings = settings
    app.state.repository = SQLiteGameKnifeRepository(settings.database_path)
    app.state.storage = LocalStorageProvider(settings.storage_root)


def get_repository(request: Request) -> SQLiteGameKnifeRepository:
    return request.app.state.repository


def get_request_context(request: Request) -> RequestContext:
    storage = request.app.state.storage
    return RequestContext(
        principal=Principal(id="anonymous", kind="anonymous", display_name="本地用户"),
        workspace=Workspace(id="local", kind="local", name="本地工作区"),
        permissions=AllowAllPermissionChecker(),
        capabilities=CapabilitySet(edition="community", features=COMMUNITY_FEATURES),
        storage=storage,
    )
