from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gameknife_api.deps import CommunitySettings, build_runtime_state
from gameknife_api.routes import router
from gameknife_api.spa import mount_spa
from gameknife_jobs import init_sqlite_schema


def create_community_app(settings: CommunitySettings | None = None) -> FastAPI:
    resolved_settings = settings or CommunitySettings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 启动时统一初始化 schema，保证测试、开发和 Docker 入口使用同一套建表逻辑。
        # Community 不迁移旧库，缺表时直接按 GameKnife 新 schema 创建。
        init_sqlite_schema(resolved_settings.database_path)
        build_runtime_state(app, resolved_settings)
        yield

    app = FastAPI(title="GameKnife Community", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    mount_spa(app, resolved_settings.web_dist, assets_name="community-assets")
    return app
