from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_spa(app: FastAPI, web_dist: Path | None, *, assets_name: str) -> None:
    """把 Vite 构建产物挂载到 FastAPI 应用。

    Community 与 Studio 都采用同端口部署，调用方只需要提供各自的 dist 目录和静态资源挂载名。
    该入口负责返回根目录公共文件、处理前端路由回落，并阻止回落路由接管不存在的 API。
    dist 不存在时保持 API-only 运行方式，不注册任何前端路由。
    """

    if web_dist is None or not (web_dist / "index.html").is_file():
        return

    web_dist_root = web_dist.resolve()
    assets_dir = web_dist_root / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name=assets_name)

    @app.get("/")
    def spa_index() -> FileResponse:
        return FileResponse(web_dist_root / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/{path:path}", include_in_schema=False)
    def spa_fallback(path: str) -> FileResponse:
        # 公共 API 固定使用 /api 前缀。不存在的接口必须保留 404，避免前端 index.html 掩盖路由错误。
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="接口不存在。")

        requested_file = (web_dist_root / path).resolve()
        # Vite 会把 public 目录内容复制到 dist 根目录。边界检查先于文件读取，防止构造路径访问 dist 外部文件。
        if requested_file.is_relative_to(web_dist_root) and requested_file.is_file():
            if requested_file.name == "index.html":
                return FileResponse(requested_file, headers={"Cache-Control": "no-store"})
            return FileResponse(requested_file)

        # 浏览器侧路由统一回落到入口文件，入口禁用缓存以便部署后及时加载最新资源清单。
        return FileResponse(web_dist_root / "index.html", headers={"Cache-Control": "no-store"})
