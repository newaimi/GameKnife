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
        # Initialize the schema at startup so tests, development, and Docker use the same table-creation path.
        # Community does not migrate legacy databases; missing tables are created from the current GameKnife schema.
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
