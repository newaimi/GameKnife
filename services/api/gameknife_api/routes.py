from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from gameknife_api.deps import get_repository, get_request_context
from gameknife_api.schemas import AssetResponse, ContextResponse, SettingsResponse
from gameknife_core import AssetRecord, RequestContext
from gameknife_jobs import SQLiteGameKnifeRepository

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "edition": "community"}


@router.get("/context", response_model=ContextResponse)
def context(context: RequestContext = Depends(get_request_context)) -> ContextResponse:
    return ContextResponse(
        principal={
            "id": context.principal.id,
            "kind": context.principal.kind,
            "displayName": context.principal.display_name,
        },
        workspace={
            "id": context.workspace.id,
            "kind": context.workspace.kind,
            "name": context.workspace.name,
        },
        capabilities={
            "edition": context.capabilities.edition,
            "features": sorted(context.capabilities.features),
        },
    )


@router.get("/settings", response_model=SettingsResponse)
def settings(context: RequestContext = Depends(get_request_context)) -> SettingsResponse:
    return SettingsResponse(
        edition="community",
        workspace_id=context.workspace.id,
        storage="local_file_storage",
        models={},
    )


@router.post("/assets/images", response_model=AssetResponse)
async def upload_image_asset(
    file: UploadFile = File(...),
    context: RequestContext = Depends(get_request_context),
    repository: SQLiteGameKnifeRepository = Depends(get_repository),
) -> AssetResponse:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="上传文件必须是图片。")

    content = await file.read()
    _verify_image(content)

    asset_id = uuid4().hex
    filename = Path(file.filename or "upload.png").name
    now = _now()
    relative_path = context.storage.write_asset(asset_id, filename, content)
    asset = AssetRecord(
        id=asset_id,
        workspace_id=context.workspace.id,
        created_by=context.principal.id,
        kind="image",
        original_name=filename,
        path=relative_path,
        mime_type=file.content_type,
        size_bytes=len(content),
        created_at=now,
        updated_at=now,
    )

    try:
        repository.create_asset(asset)
    except Exception:
        # 上传时先写磁盘再写数据库，失败时清理刚生成的文件。
        # 这样不会留下没有数据库记录的游离文件，后续资产列表也不会出现不可追踪数据。
        context.storage.remove_asset_file(relative_path)
        raise

    return _asset_response(asset)


@router.post("/assets/videos", response_model=AssetResponse)
async def upload_video_asset(
    file: UploadFile = File(...),
    context: RequestContext = Depends(get_request_context),
    repository: SQLiteGameKnifeRepository = Depends(get_repository),
) -> AssetResponse:
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="上传文件必须是视频。")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件不能为空。")

    asset_id = uuid4().hex
    filename = Path(file.filename or "upload.mp4").name
    now = _now()
    relative_path = context.storage.write_asset(asset_id, filename, content)
    asset = AssetRecord(
        id=asset_id,
        workspace_id=context.workspace.id,
        created_by=context.principal.id,
        kind="video",
        original_name=filename,
        path=relative_path,
        mime_type=file.content_type,
        size_bytes=len(content),
        created_at=now,
        updated_at=now,
    )
    try:
        repository.create_asset(asset)
    except Exception:
        context.storage.remove_asset_file(relative_path)
        raise
    return _asset_response(asset)


@router.get("/assets/{asset_id}")
def get_asset(
    asset_id: str,
    context: RequestContext = Depends(get_request_context),
    repository: SQLiteGameKnifeRepository = Depends(get_repository),
) -> FileResponse:
    asset = repository.get_asset_for_workspace(asset_id, context.workspace.id)
    if not asset:
        raise HTTPException(status_code=404, detail="素材不存在或已被删除。")

    try:
        file_path = context.storage.resolve_asset_path(asset.path)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="素材文件不存在。")

    return FileResponse(file_path, media_type=asset.mime_type, filename=asset.original_name)


def _verify_image(content: bytes) -> None:
    if not content:
        raise HTTPException(status_code=400, detail="上传文件不能为空。")
    try:
        Image.open(BytesIO(content)).verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="上传文件不是有效图片。") from exc


def _asset_response(asset: AssetRecord) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        filename=asset.original_name,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
        url=f"/api/assets/{asset.id}",
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
