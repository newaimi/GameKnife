from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_spa(app: FastAPI, web_dist: Path | None, *, assets_name: str) -> None:
    """Mount a Vite build in a FastAPI application.

    Same-port deployments provide their dist directory and static-asset mount name. This entry point serves
    root-level public files, handles frontend route fallback, and prevents that fallback from capturing missing
    API routes. When dist is unavailable, the application remains API-only and registers no frontend routes.
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
        # Public API routes use the /api prefix. Missing endpoints must retain their 404 instead of falling back to index.html.
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="接口不存在。")

        requested_file = (web_dist_root / path).resolve()
        # Vite copies public files into the dist root. Validate the boundary before reading to block paths outside dist.
        if requested_file.is_relative_to(web_dist_root) and requested_file.is_file():
            if requested_file.name == "index.html":
                return FileResponse(requested_file, headers={"Cache-Control": "no-store"})
            return FileResponse(requested_file)

        # Browser routes fall back to the entry file, which disables caching so deployments load the latest asset manifest.
        return FileResponse(web_dist_root / "index.html", headers={"Cache-Control": "no-store"})
