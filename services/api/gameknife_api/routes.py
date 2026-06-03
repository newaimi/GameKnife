from __future__ import annotations

import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from gameknife_api.deps import get_repository, get_request_context
from gameknife_api.job_service import (
    create_job,
    delete_job,
    run_asset_board_export_job,
    run_asset_board_refine_job,
    run_asset_board_region_job,
    run_upscale_job,
)
from gameknife_api.schemas import (
    AssetBoardExportRequest,
    AssetBoardRefineRequest,
    AssetJobRequest,
    AssetResponse,
    ContextResponse,
    JobPageResponse,
    JobResponse,
    SettingsResponse,
    SoundEffectRequest,
)
from gameknife_core import AssetRecord, JobRecord, RequestContext
from gameknife_jobs import SQLiteGameKnifeRepository

router = APIRouter()

DOWNLOADABLE_JOB_TYPES = [
    "background_remove",
    "asset_board_cutout",
    "asset_board_export",
    "sequence_export_frames",
    "sequence_export_spine",
    "character_rig_export_spine",
    "character_rig_export_dragonbones",
    "image_upscale",
    "sound_effect_generate",
]
JOB_CATEGORY_TYPES = {
    "background": ["background_remove"],
    "upscale": ["image_upscale"],
    "sound": ["sound_effect_generate"],
    "asset_board": ["asset_board_region_detect", "asset_board_cutout", "asset_board_region_refine", "asset_board_export"],
    "sequence": ["sequence_clean", "sequence_generate_video", "sequence_video_to_frames", "sequence_export_frames", "sequence_export_spine"],
    "character_rig": ["character_rig_analyze", "character_rig_refine_part", "character_rig_export_spine", "character_rig_export_dragonbones"],
}


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


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs(
    context: RequestContext = Depends(get_request_context),
    repository: SQLiteGameKnifeRepository = Depends(get_repository),
) -> list[JobResponse]:
    return [_job_response(job, context, repository) for job in repository.list_jobs_for_workspace(context.workspace.id)]


@router.get("/jobs/history", response_model=JobPageResponse)
def list_job_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str = Query("all"),
    downloadable: bool = Query(False),
    context: RequestContext = Depends(get_request_context),
    repository: SQLiteGameKnifeRepository = Depends(get_repository),
) -> JobPageResponse:
    job_types = _resolve_history_job_types(category, downloadable)
    if job_types == []:
        return JobPageResponse(items=[], total=0, page=page, page_size=page_size)

    status_filter = "success" if downloadable else None
    total = repository.count_job_page_for_workspace(context.workspace.id, job_types=job_types, status=status_filter)
    jobs = repository.list_job_page_for_workspace(
        context.workspace.id,
        limit=page_size,
        offset=(page - 1) * page_size,
        job_types=job_types,
        status=status_filter,
    )
    return JobPageResponse(
        items=[_job_response(job, context, repository) for job in jobs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/jobs/runtime")
def job_runtime() -> dict[str, str]:
    return {"device": "CPU"}


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    context: RequestContext = Depends(get_request_context),
    repository: SQLiteGameKnifeRepository = Depends(get_repository),
) -> JobResponse:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在。")
    return _job_response(job, context, repository)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_job(
    job_id: str,
    context: RequestContext = Depends(get_request_context),
    repository: SQLiteGameKnifeRepository = Depends(get_repository),
) -> Response:
    try:
        deleted = delete_job(repository, context, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在。")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/jobs/background-remove", response_model=JobResponse)
def create_background_remove_job() -> JobResponse:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="BiRefNet 模型尚未下载安装，请先到设置页下载安装模型文件。")


@router.post("/jobs/upscale", response_model=JobResponse)
def create_upscale_job(
    payload: AssetJobRequest,
    background_tasks: BackgroundTasks,
    context: RequestContext = Depends(get_request_context),
    repository: SQLiteGameKnifeRepository = Depends(get_repository),
) -> JobResponse:
    parameters = payload.parameters
    if str(parameters.get("style") or "general") != "pixel":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="图片放大模型尚未下载安装，请先到设置页下载安装模型文件。")

    _ensure_asset_exists(repository, context, payload.input_asset_id)
    job = create_job(repository, context, job_type="image_upscale", input_asset_id=payload.input_asset_id, parameters=parameters)
    background_tasks.add_task(run_upscale_job, repository, context, job.id)
    return _job_response(job, context, repository)


@router.post("/jobs/sound-effect", response_model=JobResponse)
def create_sound_effect_job(payload: SoundEffectRequest) -> JobResponse:
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stable Audio 声效服务不可用。")


@router.post("/jobs/asset-board/regions", response_model=JobResponse)
def create_asset_board_region_job(
    payload: AssetJobRequest,
    background_tasks: BackgroundTasks,
    context: RequestContext = Depends(get_request_context),
    repository: SQLiteGameKnifeRepository = Depends(get_repository),
) -> JobResponse:
    _ensure_asset_exists(repository, context, payload.input_asset_id)
    job = create_job(
        repository,
        context,
        job_type="asset_board_region_detect",
        input_asset_id=payload.input_asset_id,
        parameters=payload.parameters,
    )
    background_tasks.add_task(run_asset_board_region_job, repository, context, job.id)
    return _job_response(job, context, repository)


@router.post("/jobs/asset-board/cutout", response_model=JobResponse)
def create_asset_board_cutout_job() -> JobResponse:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="BiRefNet 模型尚未下载安装，请先到设置页下载安装模型文件。")


@router.post("/jobs/asset-board/refine", response_model=JobResponse)
def create_asset_board_refine_job(
    payload: AssetBoardRefineRequest,
    background_tasks: BackgroundTasks,
    context: RequestContext = Depends(get_request_context),
    repository: SQLiteGameKnifeRepository = Depends(get_repository),
) -> JobResponse:
    _ensure_asset_exists(repository, context, payload.cutout_asset_id)
    job = create_job(
        repository,
        context,
        job_type="asset_board_region_refine",
        input_asset_id=payload.cutout_asset_id,
        parameters=payload.parameters,
    )
    background_tasks.add_task(run_asset_board_refine_job, repository, context, job.id)
    return _job_response(job, context, repository)


@router.post("/jobs/asset-board/export", response_model=JobResponse)
def create_asset_board_export_job(
    payload: AssetBoardExportRequest,
    background_tasks: BackgroundTasks,
    context: RequestContext = Depends(get_request_context),
    repository: SQLiteGameKnifeRepository = Depends(get_repository),
) -> JobResponse:
    _ensure_asset_exists(repository, context, payload.cutout_asset_id)
    parameters = {
        **payload.parameters,
        "selected_component_ids": payload.selected_component_ids,
        "components": payload.components,
    }
    job = create_job(
        repository,
        context,
        job_type="asset_board_export",
        input_asset_id=payload.cutout_asset_id,
        parameters=parameters,
    )
    background_tasks.add_task(run_asset_board_export_job, repository, context, job.id)
    return _job_response(job, context, repository)


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


def _job_response(job: JobRecord, context: RequestContext, repository: SQLiteGameKnifeRepository) -> JobResponse:
    result = json.loads(job.result_json)
    input_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if input_asset is not None:
        result.setdefault("input_asset_url", f"/api/assets/{input_asset.id}")

    return JobResponse(
        id=job.id,
        type=job.job_type,
        status=job.status,  # type: ignore[arg-type]
        input_asset_id=job.input_asset_id,
        input_filename=input_asset.original_name if input_asset is not None else None,
        input_mime_type=input_asset.mime_type if input_asset is not None else None,
        input_size_bytes=input_asset.size_bytes if input_asset is not None else None,
        parameters=json.loads(job.parameters_json),
        result=result,
        device=job.device,
        duration_ms=job.duration_ms,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _ensure_asset_exists(repository: SQLiteGameKnifeRepository, context: RequestContext, asset_id: str) -> AssetRecord:
    asset = repository.get_asset_for_workspace(asset_id, context.workspace.id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="输入素材不存在。")
    return asset


def _resolve_history_job_types(category: str, downloadable: bool) -> list[str] | None:
    category_types = None if category == "all" else JOB_CATEGORY_TYPES.get(category, [category])
    if not downloadable:
        return category_types

    downloadable_types = set(DOWNLOADABLE_JOB_TYPES)
    if category_types is None:
        return DOWNLOADABLE_JOB_TYPES
    return [job_type for job_type in category_types if job_type in downloadable_types]


def _now() -> str:
    return datetime.now(UTC).isoformat()
