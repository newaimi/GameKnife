from __future__ import annotations

import json
import platform
import re
import sys
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse
from PIL import Image, UnidentifiedImageError

from gameknife_api.deps import (
    CommunitySettings,
    get_birefnet_service,
    get_community_settings,
    get_job_dispatcher,
    get_repository,
    get_request_context,
    get_stable_audio_service,
    get_upscale_model_service,
)
from gameknife_api.job_service import (
    create_job,
    delete_job,
)
from gameknife_api.schemas import (
    AssetBoardExportRequest,
    AssetBoardRefineRequest,
    AssetJobRequest,
    AssetResponse,
    ContextResponse,
    JobPageResponse,
    JobResponse,
    SequenceFrameResponse,
    SequenceFramesUpdateRequest,
    SequenceResponse,
    SequenceTaskRequest,
    SequenceUpdateRequest,
    SettingsResponse,
    SoundEffectRequest,
    VideoGenerationConfigRequest,
    VideoGenerationConfigResponse,
    VideoSequenceGenerateRequest,
    VideoToSequenceRequest,
)
from gameknife_core import AssetRecord, JobRecord, RequestContext, StoredObject
from gameknife_jobs import (
    GameKnifeRepository,
    JobDispatcher,
    ResourceReferenceError,
    SequenceActiveJobError,
    TaskSubmission,
)
from gameknife_api.birefnet import BIREFNET_MODEL_ID, BiRefNetService
from gameknife_api.stable_audio import StableAudioService
from gameknife_api.upscale_model import UpscaleModelService
from gameknife_api.video_generation import VideoGenerationClient
from gameknife_workflows import (
    WorkflowInputNotFoundError,
    WorkflowModelNotInstalledError,
    WorkflowServiceUnavailableError,
    WorkflowValidationError,
    create_asset_board_cutout_workflow,
    create_asset_board_export_workflow,
    create_asset_board_refine_workflow,
    create_asset_board_region_workflow,
    create_background_remove_workflow,
    create_sequence_frames_export_workflow,
    create_sequence_spine_export_workflow,
    create_sound_effect_workflow,
    create_upscale_workflow,
)

router = APIRouter()

DOWNLOADABLE_JOB_TYPES = [
    "background_remove",
    "asset_board_cutout",
    "asset_board_export",
    "sequence_export_frames",
    "sequence_export_spine",
    "image_upscale",
    "sound_effect_generate",
]
JOB_CATEGORY_TYPES = {
    "background": ["background_remove"],
    "upscale": ["image_upscale"],
    "sound": ["sound_effect_generate"],
    "asset_board": ["asset_board_region_detect", "asset_board_cutout", "asset_board_region_refine", "asset_board_export"],
    "sequence": ["sequence_clean", "sequence_generate_video", "sequence_video_to_frames", "sequence_export_frames", "sequence_export_spine"],
}
PROJECT_WORKFLOW_PERMISSION = "jobs.create"
SETTINGS_MANAGE_PERMISSION = "settings.manage"
ALLOWED_SEQUENCE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
ALLOWED_MANUAL_EDIT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
DEFAULT_SEQUENCE_CLEAN_PARAMETERS = {
    "alpha_threshold": 24,
    "alpha_smoothing": 0,
    "trim_padding": 6,
    "background_tolerance": 18,
    "anchor_mode": "bottom_center",
    "color_match": True,
    "stabilize": False,
    "stabilize_strength": 35,
}


def _task_submission(
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    quote_id: str | None = Header(None, alias="X-GameKnife-Quote-Id"),
) -> TaskSubmission:
    try:
        return TaskSubmission(idempotency_key=idempotency_key, quote_id=quote_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


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
def settings(
    settings: CommunitySettings = Depends(get_community_settings),
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    birefnet: BiRefNetService = Depends(get_birefnet_service),
    upscale_models: UpscaleModelService = Depends(get_upscale_model_service),
    stable_audio: StableAudioService = Depends(get_stable_audio_service),
) -> SettingsResponse:
    _require_settings_manage(context, "read_settings")
    birefnet_settings = {
        "model_id": BIREFNET_MODEL_ID,
        "device": birefnet.device_label,
        "model_input_size": birefnet.model_input_size,
        "gpu_concurrency": 1,
        "lazy_load": True,
        "install_status": birefnet.install_status(),
    }
    upscale_settings = {
        "models": upscale_models.model_specs(),
        "device": upscale_models.device_label,
        "lazy_load": True,
        "install_status": upscale_models.install_status(),
    }
    stable_audio_settings = {
        "model_id": settings.stable_audio_model_id,
        "device": "独立声效服务",
        "base_url_configured": stable_audio.is_configured,
        "lazy_load": True,
        "install_status": stable_audio.install_status(),
    }
    return SettingsResponse(
        edition=context.capabilities.edition,
        workspace_id=context.workspace.id,
        storage="enterprise_storage" if context.capabilities.edition == "commercial" else "local_file_storage",
        system={
            "app_version": settings.app_version,
            "build_number": settings.build_number,
            "git_sha": settings.git_sha,
            "build_time": settings.build_time,
            "storage_root": str(settings.storage_root),
            "database_path": str(settings.database_path),
            "max_upload_mb": settings.max_upload_mb,
            "cors_origins": settings.cors_origins,
        },
        runtime=_read_runtime_info(),
        birefnet=birefnet_settings,
        upscale_models=upscale_settings,
        stable_audio=stable_audio_settings,
        video_generation=VideoGenerationClient(repository).read_config(),
    )


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs(
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> list[JobResponse]:
    return [_job_response(job, context, repository) for job in repository.list_jobs_for_workspace(context.workspace.id)]


@router.get("/jobs/history", response_model=JobPageResponse)
def list_job_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str = Query("all"),
    created_from: str | None = Query(None),
    created_to: str | None = Query(None),
    downloadable: bool = Query(False),
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> JobPageResponse:
    job_types = _resolve_history_job_types(category, downloadable)
    if job_types == []:
        return JobPageResponse(items=[], total=0, page=page, page_size=page_size)

    status_filter = "success" if downloadable else None
    total = repository.count_job_page_for_workspace(
        context.workspace.id,
        job_types=job_types,
        status=status_filter,
        created_from=created_from,
        created_to=created_to,
    )
    jobs = repository.list_job_page_for_workspace(
        context.workspace.id,
        limit=page_size,
        offset=(page - 1) * page_size,
        job_types=job_types,
        status=status_filter,
        created_from=created_from,
        created_to=created_to,
    )
    return JobPageResponse(
        items=[_job_response(job, context, repository) for job in jobs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/jobs/runtime")
def job_runtime() -> dict[str, str]:
    return {"device": _runtime_device_label(_read_runtime_info())}


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> JobResponse:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在。")
    return _job_response(job, context, repository)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_job(
    job_id: str,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> Response:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在。")
    _require_project_workflow_write(
        context,
        "delete_job",
        {"job_id": job_id, "created_by": job.created_by},
    )
    try:
        deleted = delete_job(repository, context, job_id)
    except ResourceReferenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_resource_reference_detail(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在。")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/jobs/background-remove", response_model=JobResponse)
def create_background_remove_job(
    payload: AssetJobRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    birefnet: BiRefNetService = Depends(get_birefnet_service),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(_task_submission),
) -> JobResponse:
    try:
        submitted, _runner = create_background_remove_workflow(
            repository,
            context,
            birefnet,
            input_asset_id=payload.input_asset_id,
            parameters=payload.parameters,
            submission=submission,
        )
    except WorkflowModelNotInstalledError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except WorkflowInputNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    job = submitted.job
    if not submitted.replayed:
        dispatcher.dispatch(job.id, job.workspace_id)
    return _job_response(job, context, repository)


@router.post("/jobs/upscale", response_model=JobResponse)
def create_upscale_job(
    payload: AssetJobRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    upscale_models: UpscaleModelService = Depends(get_upscale_model_service),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(_task_submission),
) -> JobResponse:
    try:
        submitted, _runner = create_upscale_workflow(
            repository,
            context,
            upscale_models,
            input_asset_id=payload.input_asset_id,
            parameters=payload.parameters,
            submission=submission,
        )
    except WorkflowModelNotInstalledError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except WorkflowInputNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    job = submitted.job
    if not submitted.replayed:
        dispatcher.dispatch(job.id, job.workspace_id)
    return _job_response(job, context, repository)


@router.post("/jobs/sound-effect", response_model=JobResponse)
def create_sound_effect_job(
    payload: SoundEffectRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    stable_audio: StableAudioService = Depends(get_stable_audio_service),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(_task_submission),
) -> JobResponse:
    try:
        submitted, _runner = create_sound_effect_workflow(
            repository,
            context,
            stable_audio,
            parameters=payload.model_dump(),
            submission=submission,
        )
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except WorkflowServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except WorkflowModelNotInstalledError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    job = submitted.job
    if not submitted.replayed:
        dispatcher.dispatch(job.id, job.workspace_id)
    return _job_response(job, context, repository)


@router.post("/jobs/asset-board/regions", response_model=JobResponse)
def create_asset_board_region_job(
    payload: AssetJobRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(_task_submission),
) -> JobResponse:
    try:
        submitted, _runner = create_asset_board_region_workflow(
            repository,
            context,
            input_asset_id=payload.input_asset_id,
            parameters=payload.parameters,
            submission=submission,
        )
    except WorkflowInputNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    job = submitted.job
    if not submitted.replayed:
        dispatcher.dispatch(job.id, job.workspace_id)
    return _job_response(job, context, repository)


@router.post("/jobs/asset-board/cutout", response_model=JobResponse)
def create_asset_board_cutout_job(
    payload: AssetJobRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    birefnet: BiRefNetService = Depends(get_birefnet_service),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(_task_submission),
) -> JobResponse:
    try:
        submitted, _runner = create_asset_board_cutout_workflow(
            repository,
            context,
            birefnet,
            input_asset_id=payload.input_asset_id,
            parameters=payload.parameters,
            submission=submission,
        )
    except WorkflowModelNotInstalledError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except WorkflowInputNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    job = submitted.job
    if not submitted.replayed:
        dispatcher.dispatch(job.id, job.workspace_id)
    return _job_response(job, context, repository)


@router.post("/jobs/asset-board/refine", response_model=JobResponse)
def create_asset_board_refine_job(
    payload: AssetBoardRefineRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(_task_submission),
) -> JobResponse:
    try:
        submitted, _runner = create_asset_board_refine_workflow(
            repository,
            context,
            cutout_asset_id=payload.cutout_asset_id,
            parameters=payload.parameters,
            submission=submission,
        )
    except WorkflowInputNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    job = submitted.job
    if not submitted.replayed:
        dispatcher.dispatch(job.id, job.workspace_id)
    return _job_response(job, context, repository)


@router.post("/jobs/asset-board/export", response_model=JobResponse)
def create_asset_board_export_job(
    payload: AssetBoardExportRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(_task_submission),
) -> JobResponse:
    try:
        submitted, _runner = create_asset_board_export_workflow(
            repository,
            context,
            cutout_asset_id=payload.cutout_asset_id,
            selected_component_ids=payload.selected_component_ids,
            components=payload.components,
            parameters=payload.parameters,
            submission=submission,
        )
    except WorkflowInputNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    job = submitted.job
    if not submitted.replayed:
        dispatcher.dispatch(job.id, job.workspace_id)
    return _job_response(job, context, repository)


@router.post("/sequences/import", response_model=SequenceResponse)
async def import_sequence_frames(
    files: list[UploadFile] = File(...),
    name: str | None = Form(None),
    fps: int = Form(12),
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> SequenceResponse:
    _require_project_workflow_write(context, "import_sequence_frames")
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少选择一张序列帧。")
    if fps < 1 or fps > 60:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="帧率必须在 1 到 60 之间。")

    ordered_files, warnings = _sort_sequence_uploads(files)
    created_assets: list[AssetRecord] = []
    frame_payloads: list[dict[str, object]] = []
    try:
        for upload in ordered_files:
            asset, frame_payload = await _save_sequence_upload(upload, context, repository)
            created_assets.append(asset)
            frame_payloads.append(frame_payload)
        sequence = repository.create_sequence_with_frames(
            workspace_id=context.workspace.id,
            created_by=context.principal.id,
            name=(name or _guess_sequence_name(ordered_files)).strip() or "未命名序列帧",
            fps=fps,
            loop=True,
            clean_parameters=DEFAULT_SEQUENCE_CLEAN_PARAMETERS,
            frames=frame_payloads,
            created_at=_now(),
        )
    except HTTPException:
        _cleanup_created_assets(repository, context, created_assets)
        raise
    except Exception as exc:  # noqa: BLE001
        _cleanup_created_assets(repository, context, created_assets)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="序列帧导入失败。") from exc

    return _sequence_response(sequence, context, repository, warnings=warnings)


@router.post("/sequences/videos/import", response_model=AssetResponse)
async def import_sequence_video(
    file: UploadFile = File(...),
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> AssetResponse:
    _require_project_workflow_write(context, "import_sequence_video")
    return await upload_video_asset(file, context, repository)


@router.get("/sequences", response_model=list[SequenceResponse])
def list_sequences(
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> list[SequenceResponse]:
    return [_sequence_response(sequence, context, repository, include_frames=False) for sequence in repository.list_sequences_for_workspace(context.workspace.id)]


@router.get("/sequences/{sequence_id}", response_model=SequenceResponse)
def get_sequence(
    sequence_id: str,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> SequenceResponse:
    sequence = repository.get_sequence_for_workspace(sequence_id, context.workspace.id)
    if sequence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="序列帧不存在。")
    return _sequence_response(sequence, context, repository)


@router.patch("/sequences/{sequence_id}", response_model=SequenceResponse)
def update_sequence(
    sequence_id: str,
    payload: SequenceUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> SequenceResponse:
    _require_project_workflow_write(context, "update_sequence", {"sequence_id": sequence_id})
    try:
        sequence = repository.update_sequence(
            sequence_id,
            context.workspace.id,
            name=payload.name.strip() if payload.name else None,
            fps=payload.fps,
            loop=payload.loop,
            canvas_width=payload.canvas_width,
            canvas_height=payload.canvas_height,
            anchor_mode=payload.anchor_mode,
            anchor_x=payload.anchor_x,
            anchor_y=payload.anchor_y,
            clean_parameters=payload.clean_parameters,
            updated_at=_now(),
        )
    except SequenceActiveJobError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="序列帧正在处理中，暂时不能修改。") from exc
    if sequence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="序列帧不存在。")
    return _sequence_response(sequence, context, repository)


@router.patch("/sequences/{sequence_id}/frames", response_model=SequenceResponse)
def update_sequence_frames(
    sequence_id: str,
    payload: SequenceFramesUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> SequenceResponse:
    _require_project_workflow_write(context, "update_sequence_frames", {"sequence_id": sequence_id})
    sequence = repository.get_sequence_for_workspace_including_processing(sequence_id, context.workspace.id)
    if sequence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="序列帧不存在。")
    try:
        repository.update_sequence_frames(
            sequence_id,
            context.workspace.id,
            [frame.model_dump(exclude_none=True) for frame in payload.frames],
            updated_at=_now(),
        )
    except SequenceActiveJobError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="序列帧正在处理中，暂时不能修改。") from exc
    updated = repository.get_sequence_for_workspace(sequence_id, context.workspace.id)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="序列帧不存在。")
    return _sequence_response(updated, context, repository)


@router.delete("/sequences/{sequence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sequence(
    sequence_id: str,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> Response:
    sequence = repository.get_sequence_for_workspace_including_processing(sequence_id, context.workspace.id)
    if sequence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="序列帧不存在。")
    _require_project_workflow_write(
        context,
        "delete_sequence",
        {"sequence_id": sequence_id, "created_by": str(sequence["created_by"])},
    )

    try:
        asset_records = repository.delete_sequence_for_workspace(sequence_id, context.workspace.id)
    except SequenceActiveJobError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="序列帧正在处理中，暂时不能删除。") from exc
    if asset_records is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="序列帧不存在。")
    # The repository already deleted the Sequence and every now-unreferenced Asset in one transaction. Returned
    # records are the exact object cleanup set; Assets shared with Jobs or other Sequences remain in the database.
    for asset in asset_records:
        try:
            context.storage.delete_object(asset.path)
        except Exception:  # noqa: BLE001
            # Sequence and Asset rows are already removed. Community keeps object cleanup best effort; Commercial
            # replaces this boundary with its durable deletion outbox in the storage-lifecycle phase.
            continue
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sequences/{sequence_id}/clean", response_model=JobResponse)
def create_sequence_clean_task(
    sequence_id: str,
    payload: SequenceTaskRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(_task_submission),
) -> JobResponse:
    sequence, input_asset_id = _ensure_sequence_job_input(repository, context, sequence_id)
    if sequence["active_job_id"] is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="序列帧正在处理中，请稍后重试。")
    enabled_frames = repository.list_sequence_frames(sequence_id, context.workspace.id, enabled_only=True)
    submitted = create_job(
        repository,
        context,
        job_type="sequence_clean",
        input_asset_id=input_asset_id,
        parameters={
            **payload.parameters,
            # Capacity inputs are server snapshots. Clients cannot understate them to bypass Commercial storage holds.
            "sequence_id": sequence_id,
            "sequence_revision": int(sequence["revision"]),
            "frame_count": len(enabled_frames),
            "canvas_width": int(sequence["canvas_width"]),
            "canvas_height": int(sequence["canvas_height"]),
        },
        submission=submission,
    )
    job = submitted.job
    if not submitted.replayed:
        dispatcher.dispatch(job.id, job.workspace_id)
    return _job_response(job, context, repository)


@router.post("/sequences/generate-from-image", response_model=JobResponse)
def create_sequence_generate_video_task(
    payload: VideoSequenceGenerateRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(_task_submission),
) -> JobResponse:
    if not payload.confirmed_external_api:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先确认调用外部视频生成 API。")
    input_asset = _ensure_asset_exists(repository, context, payload.input_asset_id)
    if not input_asset.mime_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="输入素材必须是图片。")
    try:
        VideoGenerationClient(repository).ensure_configured()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    parameters = payload.model_dump()
    submitted = create_job(
        repository,
        context,
        job_type="sequence_generate_video",
        input_asset_id=input_asset.id,
        parameters=parameters,
        submission=submission,
    )
    job = submitted.job
    if not submitted.replayed:
        dispatcher.dispatch(job.id, job.workspace_id)
    return _job_response(job, context, repository)


@router.post("/sequences/from-video", response_model=JobResponse)
def create_sequence_from_video_task(
    payload: VideoToSequenceRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    birefnet: BiRefNetService = Depends(get_birefnet_service),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(_task_submission),
) -> JobResponse:
    video_asset = _ensure_asset_exists(repository, context, payload.video_asset_id)
    if not video_asset.mime_type.startswith("video/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="输入素材必须是视频。")
    if payload.remove_background:
        # Frame extraction can run locally by itself, while background removal has an explicit model dependency.
        # Reject missing installations during creation so execution uses only the injected local model service.
        _ensure_birefnet_installed(birefnet)

    parameters = {
        **payload.parameters,
        "name": (payload.name or Path(video_asset.original_name).stem or "video_sequence").strip(),
        "fps": payload.fps,
        "max_frames": payload.max_frames,
        "start_second": payload.start_second,
        "duration_seconds": payload.duration_seconds,
        "remove_background": payload.remove_background,
    }
    submitted = create_job(
        repository,
        context,
        job_type="sequence_video_to_frames",
        input_asset_id=video_asset.id,
        parameters=parameters,
        submission=submission,
    )
    job = submitted.job
    if not submitted.replayed:
        dispatcher.dispatch(job.id, job.workspace_id)
    return _job_response(job, context, repository)


@router.post("/sequences/{sequence_id}/export/frames", response_model=JobResponse)
def create_sequence_frames_export_task(
    sequence_id: str,
    payload: SequenceTaskRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(_task_submission),
) -> JobResponse:
    try:
        submitted, _runner = create_sequence_frames_export_workflow(
            repository,
            context,
            sequence_id=sequence_id,
            parameters=payload.parameters,
            submission=submission,
        )
    except WorkflowInputNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    job = submitted.job
    if not submitted.replayed:
        dispatcher.dispatch(job.id, job.workspace_id)
    return _job_response(job, context, repository)


@router.post("/sequences/{sequence_id}/export/spine", response_model=JobResponse)
def create_sequence_spine_export_task(
    sequence_id: str,
    payload: SequenceTaskRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(_task_submission),
) -> JobResponse:
    try:
        submitted, _runner = create_sequence_spine_export_workflow(
            repository,
            context,
            sequence_id=sequence_id,
            parameters=payload.parameters,
            submission=submission,
        )
    except WorkflowInputNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    job = submitted.job
    if not submitted.replayed:
        dispatcher.dispatch(job.id, job.workspace_id)
    return _job_response(job, context, repository)


@router.post("/assets/images", response_model=AssetResponse)
async def upload_image_asset(
    file: UploadFile = File(...),
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> AssetResponse:
    _require_project_workflow_write(context, "upload_image")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="上传文件必须是图片。")

    content = await file.read()
    _verify_image(content)

    asset_id = uuid4().hex
    filename = Path(file.filename or "upload.png").name
    now = _now()
    stored = _put_bytes(context, asset_id, filename, content)
    asset = AssetRecord(
        id=asset_id,
        workspace_id=context.workspace.id,
        created_by=context.principal.id,
        kind="image",
        original_name=filename,
        path=stored.key,
        mime_type=file.content_type,
        size_bytes=stored.size_bytes,
        created_at=now,
        updated_at=now,
    )

    try:
        repository.create_asset(asset)
    except Exception:
        # Uploads write the file before the database record and remove the new file if persistence fails.
        # This prevents orphaned files and keeps every asset-list entry traceable to a database record.
        context.storage.delete_object(stored.key)
        raise

    return _asset_response(asset)


@router.post("/assets/videos", response_model=AssetResponse)
async def upload_video_asset(
    file: UploadFile = File(...),
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> AssetResponse:
    _require_project_workflow_write(context, "upload_video")
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="上传文件必须是视频。")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件不能为空。")

    asset_id = uuid4().hex
    filename = Path(file.filename or "upload.mp4").name
    now = _now()
    stored = _put_bytes(context, asset_id, filename, content)
    asset = AssetRecord(
        id=asset_id,
        workspace_id=context.workspace.id,
        created_by=context.principal.id,
        kind="video",
        original_name=filename,
        path=stored.key,
        mime_type=file.content_type,
        size_bytes=stored.size_bytes,
        created_at=now,
        updated_at=now,
    )
    try:
        repository.create_asset(asset)
    except Exception:
        context.storage.delete_object(stored.key)
        raise
    return _asset_response(asset)


@router.get("/assets/{asset_id}")
def get_asset(
    asset_id: str,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> Response:
    asset = repository.get_asset_for_workspace(asset_id, context.workspace.id)
    if not asset:
        raise HTTPException(status_code=404, detail="素材不存在或已被删除。")

    try:
        file_path = context.storage.local_path(asset.path)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if file_path is not None:
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="素材文件不存在。")
        return FileResponse(file_path, media_type=asset.mime_type, filename=asset.original_name)

    download_url = context.storage.create_download_url(
        asset.path,
        asset.original_name,
        asset.mime_type,
        expires_seconds=300,
    )
    if not download_url:
        raise HTTPException(status_code=500, detail="存储服务未提供素材下载方式。")
    return RedirectResponse(download_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: str,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> Response:
    asset = repository.get_asset_for_workspace(asset_id, context.workspace.id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="素材不存在或已被删除。")
    _require_project_workflow_write(
        context,
        "delete_asset",
        {"asset_id": asset.id, "created_by": asset.created_by},
    )
    try:
        # Repository reference checks and deletion share one transaction, so a concurrent Job or Sequence reference
        # either wins first and returns 409, or observes the Asset as already absent.
        repository.delete_assets_for_workspace([asset.id], context.workspace.id)
    except ResourceReferenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_resource_reference_detail(exc),
        ) from exc
    try:
        context.storage.delete_object(asset.path)
    except Exception:  # noqa: BLE001
        # The Asset row is authoritative for Community. Commercial replaces this best-effort edge with its durable
        # object deletion outbox when the S3 lifecycle is implemented.
        pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/manual-edits/save", response_model=AssetResponse)
async def save_manual_edit_asset(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    source_asset_id: str | None = Form(None),
    source_context: str | None = Form(None),
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> AssetResponse:
    _require_project_workflow_write(context, "save_manual_edit", {"source_asset_id": source_asset_id})
    if source_asset_id:
        _ensure_asset_exists(repository, context, source_asset_id)
    if file.content_type not in ALLOWED_MANUAL_EDIT_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只支持 JPG、PNG 和 WebP 图片。")

    content = await file.read()
    _verify_image(content)

    suffix = ALLOWED_MANUAL_EDIT_TYPES[file.content_type]
    filename = _manual_edit_name(name, file.filename, "manual-edit", suffix)
    asset_id = uuid4().hex
    now = _now()
    stored = _put_bytes(context, asset_id, filename, content)
    asset = AssetRecord(
        id=asset_id,
        workspace_id=context.workspace.id,
        created_by=context.principal.id,
        kind="manual_edit",
        original_name=filename,
        path=stored.key,
        mime_type=file.content_type,
        size_bytes=stored.size_bytes,
        created_at=now,
        updated_at=now,
    )
    try:
        repository.create_asset(asset)
    except Exception:
        # Manual-edit saves create a new asset and remove its file if the database write fails.
        # This prevents an edited result without a traceable record from appearing in later job-history flows.
        context.storage.delete_object(stored.key)
        raise
    return _asset_response(asset)


def _verify_image(content: bytes) -> None:
    if not content:
        raise HTTPException(status_code=400, detail="上传文件不能为空。")
    try:
        Image.open(BytesIO(content)).verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="上传文件不是有效图片。") from exc


def _put_bytes(context: RequestContext, asset_id: str, original_name: str, content: bytes) -> StoredObject:
    # Upload validation still operates on request bytes, but durable storage accepts local source paths so remote
    # providers can use their normal multipart and retry implementation without exposing provider details here.
    with TemporaryDirectory(prefix="gameknife-upload-") as directory:
        source_path = Path(directory) / (Path(original_name).name or "upload.bin")
        source_path.write_bytes(content)
        return context.storage.put_file(asset_id, original_name, source_path)


def _manual_edit_name(name: str | None, filename: str | None, fallback: str, suffix: str) -> str:
    raw_name = Path(name or filename or fallback).name.strip() or fallback
    if Path(raw_name).suffix:
        return raw_name
    return f"{raw_name}{suffix}"


def _asset_response(asset: AssetRecord) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        filename=asset.original_name,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
        url=f"/api/assets/{asset.id}",
    )


def _resource_reference_detail(exc: ResourceReferenceError) -> dict[str, object]:
    return {
        "code": "RESOURCE_REFERENCED",
        "message": "资源仍被其他任务或序列使用，无法删除。",
        "resource": {"kind": exc.resource_kind, "id": exc.resource_id},
        "references": [
            {
                "asset_id": reference.asset_id,
                "input_job_ids": list(reference.input_job_ids),
                "output_job_ids": list(reference.output_job_ids),
                "source_sequence_frame_ids": list(reference.source_sequence_frame_ids),
                "processed_sequence_frame_ids": list(reference.processed_sequence_frame_ids),
            }
            for reference in exc.references
        ],
    }


def _require_project_workflow_write(context: RequestContext, operation: str, resource: dict[str, object] | None = None) -> None:
    # v1 groups workspace writes from public tools under jobs.create because uploads, imports, manual-edit saves,
    # and job creation form one tool workflow. Restricting only job creation would still let a constrained caller
    # bypass the frontend and write orphaned assets to the workspace.
    context.permissions.require(PROJECT_WORKFLOW_PERMISSION, {"operation": operation, **(resource or {})})


def _require_settings_manage(context: RequestContext, operation: str) -> None:
    # Model installation and video API configuration change the service-wide runtime environment.
    # Community allows the operation by default; callers that enforce permissions decide through PermissionChecker.
    context.permissions.require(SETTINGS_MANAGE_PERMISSION, {"operation": operation})


@router.get("/settings/birefnet/install")
def read_birefnet_install(
    context: RequestContext = Depends(get_request_context),
    birefnet: BiRefNetService = Depends(get_birefnet_service),
) -> dict[str, object]:
    _require_settings_manage(context, "read_birefnet_install")
    return birefnet.install_status()


@router.post("/settings/birefnet/install")
def start_birefnet_install(
    context: RequestContext = Depends(get_request_context),
    birefnet: BiRefNetService = Depends(get_birefnet_service),
) -> dict[str, object]:
    _require_settings_manage(context, "install_birefnet")
    return birefnet.start_install()


@router.get("/settings/upscale-models/install")
def read_upscale_model_install(
    context: RequestContext = Depends(get_request_context),
    upscale_models: UpscaleModelService = Depends(get_upscale_model_service),
) -> dict[str, object]:
    _require_settings_manage(context, "read_upscale_models_install")
    return upscale_models.install_status()


@router.post("/settings/upscale-models/install")
def start_upscale_model_install(
    context: RequestContext = Depends(get_request_context),
    upscale_models: UpscaleModelService = Depends(get_upscale_model_service),
) -> dict[str, object]:
    _require_settings_manage(context, "install_upscale_models")
    return upscale_models.start_install()


@router.get("/settings/stable-audio/install")
def read_stable_audio_install(
    context: RequestContext = Depends(get_request_context),
    stable_audio: StableAudioService = Depends(get_stable_audio_service),
) -> dict[str, object]:
    _require_settings_manage(context, "read_stable_audio_install")
    return stable_audio.install_status()


@router.post("/settings/stable-audio/install")
def start_stable_audio_install(
    context: RequestContext = Depends(get_request_context),
    stable_audio: StableAudioService = Depends(get_stable_audio_service),
) -> dict[str, object]:
    _require_settings_manage(context, "install_stable_audio")
    try:
        return stable_audio.start_install()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/settings/video-generation", response_model=VideoGenerationConfigResponse)
def read_video_generation_settings(
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> VideoGenerationConfigResponse:
    _require_settings_manage(context, "read_video_generation")
    return VideoGenerationConfigResponse(**VideoGenerationClient(repository).read_config())


@router.patch("/settings/video-generation", response_model=VideoGenerationConfigResponse)
def update_video_generation_settings(
    payload: VideoGenerationConfigRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> VideoGenerationConfigResponse:
    _require_settings_manage(context, "update_video_generation")
    data = payload.model_dump()
    return VideoGenerationConfigResponse(**VideoGenerationClient(repository).save_config(data, updated_at=_now()))


@router.post("/settings/video-generation/test")
def test_video_generation_settings(
    payload: VideoGenerationConfigRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> dict[str, object]:
    _require_settings_manage(context, "test_video_generation")
    try:
        return VideoGenerationClient(repository).test_config(payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


async def _save_sequence_upload(
    upload: UploadFile,
    context: RequestContext,
    repository: GameKnifeRepository,
) -> tuple[AssetRecord, dict[str, object]]:
    if upload.content_type not in ALLOWED_SEQUENCE_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{upload.filename or '文件'} 不是支持的图片格式。")

    content = await upload.read()
    _verify_image(content)

    asset_id = uuid4().hex
    filename = Path(upload.filename or "frame.png").name
    now = _now()
    stored = _put_bytes(context, asset_id, filename, content)
    asset = AssetRecord(
        id=asset_id,
        workspace_id=context.workspace.id,
        created_by=context.principal.id,
        kind="sequence_frame",
        original_name=filename,
        path=stored.key,
        mime_type=upload.content_type or "application/octet-stream",
        size_bytes=stored.size_bytes,
        created_at=now,
        updated_at=now,
    )
    try:
        repository.create_asset(asset)
    except Exception:
        # The caller cannot add this Asset to its batch cleanup list until persistence returns. Remove the object
        # here so an insert failure never leaves a storage key with no corresponding database record.
        try:
            context.storage.delete_object(stored.key)
        except Exception:  # noqa: BLE001
            pass
        raise

    try:
        with Image.open(BytesIO(content)) as opened:
            image = opened.convert("RGBA")
            bbox = image.getchannel("A").getbbox() or (0, 0, image.width, image.height)
            width, height = image.size
    except Exception as exc:  # noqa: BLE001
        _cleanup_created_assets(repository, context, [asset])
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{filename} 读取失败。") from exc

    return asset, {
        "source_asset_id": asset.id,
        "original_name": asset.original_name,
        "width": width,
        "height": height,
        "bbox": list(bbox),
    }


def _sequence_response(
    sequence,
    context: RequestContext,
    repository: GameKnifeRepository,
    *,
    include_frames: bool = True,
    warnings: list[str] | None = None,
) -> SequenceResponse:
    frames = repository.list_sequence_frames(sequence["id"], context.workspace.id) if include_frames else []
    return SequenceResponse(
        id=sequence["id"],
        name=sequence["name"],
        fps=int(sequence["fps"]),
        loop=bool(sequence["loop"]),
        canvas_width=int(sequence["canvas_width"]),
        canvas_height=int(sequence["canvas_height"]),
        anchor_mode=sequence["anchor_mode"],
        anchor_x=float(sequence["anchor_x"]),
        anchor_y=float(sequence["anchor_y"]),
        clean_parameters=json.loads(sequence["clean_parameters_json"]),
        status=sequence["status"],
        frame_count=int(sequence["frame_count"]),
        enabled_frame_count=int(sequence["enabled_frame_count"]),
        frames=[_sequence_frame_response(frame) for frame in frames],
        warnings=warnings or [],
        created_at=sequence["created_at"],
        updated_at=sequence["updated_at"],
    )


def _sequence_frame_response(frame) -> SequenceFrameResponse:
    processed_asset_id = frame["processed_asset_id"]
    preview_asset_id = processed_asset_id or frame["source_asset_id"]
    return SequenceFrameResponse(
        id=frame["id"],
        sequence_id=frame["sequence_id"],
        source_asset_id=frame["source_asset_id"],
        processed_asset_id=processed_asset_id,
        frame_index=int(frame["frame_index"]),
        original_name=frame["original_name"],
        width=int(frame["width"]),
        height=int(frame["height"]),
        bbox=json.loads(frame["bbox_json"]),
        offset_x=int(frame["offset_x"]),
        offset_y=int(frame["offset_y"]),
        duration_ms=int(frame["duration_ms"]),
        enabled=bool(frame["enabled"]),
        is_generated=bool(frame["is_generated"]),
        source_url=f"/api/assets/{frame['source_asset_id']}",
        preview_url=f"/api/assets/{preview_asset_id}",
        created_at=frame["created_at"],
        updated_at=frame["updated_at"],
    )


def _ensure_sequence_job_input(
    repository: GameKnifeRepository,
    context: RequestContext,
    sequence_id: str,
):
    sequence = repository.get_sequence_for_workspace_including_processing(sequence_id, context.workspace.id)
    if sequence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="序列帧不存在。")
    frames = repository.list_sequence_frames(sequence_id, context.workspace.id, enabled_only=True)
    if not frames:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="序列帧没有可用帧。")
    return sequence, frames[0]["source_asset_id"]


def _sort_sequence_uploads(files: list[UploadFile]) -> tuple[list[UploadFile], list[str]]:
    number_pattern = re.compile(r"(\d+)(?!.*\d)")
    warnings: list[str] = []

    def sort_key(upload: UploadFile) -> tuple[int, int | str, str]:
        filename = Path(upload.filename or "").name
        match = number_pattern.search(filename)
        if match:
            return (0, int(match.group(1)), filename)
        return (1, filename, filename)

    if any(number_pattern.search(Path(upload.filename or "").name) is None for upload in files):
        warnings.append("部分文件名没有数字序号，已按文件名字典序排在数字序号之后。")
    return sorted(files, key=sort_key), warnings


def _guess_sequence_name(files: list[UploadFile]) -> str:
    first_name = Path(files[0].filename or "序列帧").stem
    return re.sub(r"[_ -]*\d+$", "", first_name).strip(" _-") or first_name


def _cleanup_created_assets(repository: GameKnifeRepository, context: RequestContext, assets: list[AssetRecord]) -> None:
    if not assets:
        return
    try:
        repository.delete_assets_for_workspace([asset.id for asset in assets], context.workspace.id)
    except Exception:  # noqa: BLE001
        # Keep objects when database cleanup does not commit; deleting them would leave durable Asset rows that point
        # to missing content and would hide the original import failure.
        return
    for asset in assets:
        try:
            context.storage.delete_object(asset.path)
        except Exception:  # noqa: BLE001
            continue


def _job_response(job: JobRecord, context: RequestContext, repository: GameKnifeRepository) -> JobResponse:
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


def _ensure_asset_exists(repository: GameKnifeRepository, context: RequestContext, asset_id: str) -> AssetRecord:
    asset = repository.get_asset_for_workspace(asset_id, context.workspace.id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="输入素材不存在。")
    return asset


def _ensure_birefnet_installed(birefnet: BiRefNetService) -> None:
    if birefnet.is_installed():
        return
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="BiRefNet 模型尚未下载安装，请先到设置页下载安装模型文件。")


def _read_runtime_info() -> dict[str, object]:
    # Settings report the actual Web-process runtime instead of asking the frontend to infer it from a device label.
    # The same Community package can run on CPU, CUDA, or macOS MPS; the active PyTorch backend determines inference support.
    info: dict[str, object] = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "pytorch_available": False,
        "pytorch_version": None,
        "cuda_available": False,
        "cuda_version": None,
        "cudnn_version": None,
        "mps_available": False,
        "gpu_count": 0,
        "current_gpu_index": None,
        "current_gpu_name": None,
        "gpus": [],
        "error": None,
    }

    try:
        import torch
    except Exception as exc:  # pragma: no cover - 只有部署环境缺 PyTorch 时才会触发
        info["error"] = str(exc)
        return info

    info["pytorch_available"] = True
    info["pytorch_version"] = torch.__version__
    info["cuda_available"] = bool(torch.cuda.is_available())
    info["cuda_version"] = getattr(torch.version, "cuda", None)

    try:
        cudnn_version = torch.backends.cudnn.version()
    except Exception:
        cudnn_version = None
    info["cudnn_version"] = str(cudnn_version) if cudnn_version else None

    mps_backend = getattr(torch.backends, "mps", None)
    info["mps_available"] = bool(mps_backend and mps_backend.is_available())

    if not info["cuda_available"]:
        return info

    gpu_count = torch.cuda.device_count()
    current_gpu_index = torch.cuda.current_device() if gpu_count else None
    info["gpu_count"] = gpu_count
    info["current_gpu_index"] = current_gpu_index

    gpus: list[dict[str, object]] = []
    for index in range(gpu_count):
        props = torch.cuda.get_device_properties(index)
        gpu = {
            "index": index,
            "name": torch.cuda.get_device_name(index),
            "total_memory_mb": int(props.total_memory / 1024 / 1024),
            "capability": f"{props.major}.{props.minor}",
        }
        gpus.append(gpu)

        if index == current_gpu_index:
            info["current_gpu_name"] = gpu["name"]

    info["gpus"] = gpus
    return info


def _runtime_device_label(runtime: dict[str, object]) -> str:
    # This endpoint preserves the existing single-field response so callers need not parse the full settings runtime structure.
    # CUDA returns the active GPU name, MPS uses a stable backend label, and every other environment reports CPU explicitly.
    if bool(runtime.get("cuda_available")):
        return str(runtime.get("current_gpu_name") or "CUDA")
    if bool(runtime.get("mps_available")):
        return "MPS"
    return "CPU"


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
