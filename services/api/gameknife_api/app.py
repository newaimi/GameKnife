from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gameknife_api.deps import CommunitySettings, build_runtime_state
from gameknife_api.routes import router
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
    if resolved_settings.web_dist and (resolved_settings.web_dist / "index.html").is_file():
        web_dist_root = resolved_settings.web_dist.resolve()
        assets_dir = web_dist_root / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="community-assets")

        @app.get("/")
        def community_index() -> FileResponse:
            return FileResponse(web_dist_root / "index.html")

        @app.get("/{path:path}", include_in_schema=False)
        def community_spa(path: str) -> FileResponse:
            # 生产镜像由 FastAPI 同端口托管前端，SPA 路由统一回落到 index.html。
            # API 路由已经挂在 /api 前缀下，静态回落不会接管后端接口。
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail="接口不存在。")
            requested_file = (web_dist_root / path).resolve()
            # Vite 会把 public 目录里的 logo 等文件放到 dist 根部。
            # 先返回真实静态文件，才能让 Docker 同端口部署和开发构建产物保持一致。
            if requested_file.is_file() and requested_file.is_relative_to(web_dist_root):
                if requested_file.name == "index.html":
                    return FileResponse(requested_file, headers={"Cache-Control": "no-store"})
                return FileResponse(requested_file)
            return FileResponse(web_dist_root / "index.html", headers={"Cache-Control": "no-store"})
    return app
