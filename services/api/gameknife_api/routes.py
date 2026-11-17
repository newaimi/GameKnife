from __future__ import annotations

import json
import platform
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, RedirectResponse
from gameknife_core import (
    AssetRecord,
    AssetRelationRecord,
    JobRecord,
    RequestContext,
    StorageProvider,
)
from gameknife_jobs import (
    GameKnifeRepository,
    JobDispatcher,
    JobParameterValidationError,
    JobSubmissionResult,
    ResourceReferenceError,
    SequenceActiveJobError,
    TaskSubmission,
    canonical_asset_quality_check_parameters,
)
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
    create_job_record,
    create_project_export_workflow,
    create_sequence_frames_export_workflow,
    create_sequence_spine_export_workflow,
    create_sound_effect_workflow,
    create_upscale_workflow,
    persist_asset_file,
)
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from gameknife_api.birefnet import BIREFNET_MODEL_ID, BiRefNetService
from gameknife_api.deps import (
    CommunitySettings,
    get_birefnet_service,
    get_community_settings,
    get_job_dispatcher,
    get_job_history_configuration,
    get_job_submission_replay,
    get_repository,
    get_request_context,
    get_stable_audio_service,
    get_task_submission,
    get_upscale_model_service,
)
from gameknife_api.history import JobHistoryConfiguration
from gameknife_api.job_service import (
    create_job,
    delete_job,
)
from gameknife_api.responses import (
    build_asset_response,
    build_job_response,
    build_resource_reference_detail,
)
from gameknife_api.schemas import (
    AssetBoardExportRequest,
    AssetBoardRefineRequest,
    AssetDetailResponse,
    AssetJobRequest,
    AssetPageResponse,
    AssetQualityCheckRequest,
    AssetResponse,
    ContextResponse,
    JobPageResponse,
    JobResponse,
    ProjectExportRequest,
    SequenceFrameResponse,
    SequenceFramesUpdateRequest,
    SequenceResponse,
    SequenceTaskRequest,
    SequenceUpdateRequest,
    SettingsResponse,
    SoundEffectRequest,
    VideoToSequenceRequest,
)
from gameknife_api.stable_audio import StableAudioService
from gameknife_api.upscale_model import UpscaleModelService

router = APIRouter()

ASSET_CATEGORY_KINDS = {
    "image": [
        "image",
        "manual_edit",
        "background_remove",
        "upscale_result",
        "asset_cutout",
        "image_generated",
        "sequence_frame",
        "sequence_frame_processed",
    ],
    "video": ["video", "sequence_video"],
    "audio": ["sound_effect"],
    "model": ["model_3d_glb", "model_3d_fbx", "model_3d_obj"],
    "export": ["asset_export", "sequence_export", "sequence_spine", "project_export"],
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
MAX_ASSET_UPLOAD_BYTES = 50 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
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
        "device": "Standalone SFX service",
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
    delivery_only: bool = Query(False),
    job_status: str | None = Query(None, alias="status"),
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    history_configuration: JobHistoryConfiguration = Depends(
        get_job_history_configuration
    ),
) -> JobPageResponse:
    if job_status is not None and job_status not in {"pending", "running", "success", "failed"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported job status.")
    job_types = _resolve_history_job_types(
        category,
        downloadable,
        delivery_only,
        history_configuration,
    )
    if job_types == []:
        return JobPageResponse(items=[], total=0, page=page, page_size=page_size)

    status_filter = "success" if downloadable else job_status
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return _job_response(job, context, repository)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_job(
    job_id: str,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> Response:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/jobs/background-remove", response_model=JobResponse)
def create_background_remove_job(
    payload: AssetJobRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    birefnet: BiRefNetService = Depends(get_birefnet_service),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(get_task_submission),
    replayed_submission: JobSubmissionResult | None = Depends(
        get_job_submission_replay
    ),
) -> JobResponse:
    if replayed_submission is not None:
        return _job_response(replayed_submission.job, context, repository)
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
    submission: TaskSubmission = Depends(get_task_submission),
    replayed_submission: JobSubmissionResult | None = Depends(
        get_job_submission_replay
    ),
) -> JobResponse:
    if replayed_submission is not None:
        return _job_response(replayed_submission.job, context, repository)
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
    submission: TaskSubmission = Depends(get_task_submission),
    replayed_submission: JobSubmissionResult | None = Depends(
        get_job_submission_replay
    ),
) -> JobResponse:
    if replayed_submission is not None:
        return _job_response(replayed_submission.job, context, repository)
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
    submission: TaskSubmission = Depends(get_task_submission),
    replayed_submission: JobSubmissionResult | None = Depends(
        get_job_submission_replay
    ),
) -> JobResponse:
    if replayed_submission is not None:
        return _job_response(replayed_submission.job, context, repository)
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
    submission: TaskSubmission = Depends(get_task_submission),
    replayed_submission: JobSubmissionResult | None = Depends(
        get_job_submission_replay
    ),
) -> JobResponse:
    if replayed_submission is not None:
        return _job_response(replayed_submission.job, context, repository)
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
    submission: TaskSubmission = Depends(get_task_submission),
    replayed_submission: JobSubmissionResult | None = Depends(
        get_job_submission_replay
    ),
) -> JobResponse:
    if replayed_submission is not None:
        return _job_response(replayed_submission.job, context, repository)
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
    submission: TaskSubmission = Depends(get_task_submission),
    replayed_submission: JobSubmissionResult | None = Depends(
        get_job_submission_replay
    ),
) -> JobResponse:
    if replayed_submission is not None:
        return _job_response(replayed_submission.job, context, repository)
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one sequence frame.")
    if fps < 1 or fps > 60:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Frame rate must be between 1 and 60.")

    ordered_files, warnings = _sort_sequence_uploads(files)
    created_assets: list[AssetRecord] = []
    frame_payloads: list[dict[str, object]] = []
    try:
        for upload in ordered_files:
            asset, frame_payload = await _save_sequence_upload(upload, context, repository)
            created_assets.append(asset)
            frame_payloads.append(frame_payload)
        sequence = await run_in_threadpool(
            repository.create_sequence_with_frames,
            workspace_id=context.workspace.id,
            created_by=context.principal.id,
            name=(name or _guess_sequence_name(ordered_files)).strip() or "Untitled sequence",
            fps=fps,
            loop=True,
            clean_parameters=DEFAULT_SEQUENCE_CLEAN_PARAMETERS,
            frames=frame_payloads,
            created_at=_now(),
        )
    except HTTPException:
        await run_in_threadpool(_cleanup_created_assets, repository, context, created_assets)
        raise
    except Exception as exc:  # noqa: BLE001
        await run_in_threadpool(_cleanup_created_assets, repository, context, created_assets)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to import sequence frames.") from exc

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found.")
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The sequence is processing and cannot be edited yet.") from exc
    if sequence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found.")
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found.")
    try:
        repository.update_sequence_frames(
            sequence_id,
            context.workspace.id,
            [frame.model_dump(exclude_none=True) for frame in payload.frames],
            updated_at=_now(),
        )
    except SequenceActiveJobError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The sequence is processing and cannot be edited yet.") from exc
    updated = repository.get_sequence_for_workspace(sequence_id, context.workspace.id)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found.")
    return _sequence_response(updated, context, repository)


@router.delete("/sequences/{sequence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sequence(
    sequence_id: str,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> Response:
    sequence = repository.get_sequence_for_workspace_including_processing(sequence_id, context.workspace.id)
    if sequence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found.")
    _require_project_workflow_write(
        context,
        "delete_sequence",
        {"sequence_id": sequence_id, "created_by": str(sequence["created_by"])},
    )

    try:
        asset_records = repository.delete_sequence_for_workspace(sequence_id, context.workspace.id)
    except SequenceActiveJobError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The sequence is processing and cannot be deleted yet.") from exc
    if asset_records is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found.")
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
    submission: TaskSubmission = Depends(get_task_submission),
    replayed_submission: JobSubmissionResult | None = Depends(
        get_job_submission_replay
    ),
) -> JobResponse:
    if replayed_submission is not None:
        return _job_response(replayed_submission.job, context, repository)
    sequence, input_asset_id = _ensure_sequence_job_input(repository, context, sequence_id)
    if sequence["active_job_id"] is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The sequence is processing. Try again later.")
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


@router.post("/sequences/from-video", response_model=JobResponse)
def create_sequence_from_video_task(
    payload: VideoToSequenceRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    birefnet: BiRefNetService = Depends(get_birefnet_service),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(get_task_submission),
    replayed_submission: JobSubmissionResult | None = Depends(
        get_job_submission_replay
    ),
) -> JobResponse:
    if replayed_submission is not None:
        return _job_response(replayed_submission.job, context, repository)
    video_asset = _ensure_asset_exists(repository, context, payload.video_asset_id)
    if not video_asset.mime_type.startswith("video/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The input asset must be a video.")
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
    submission: TaskSubmission = Depends(get_task_submission),
    replayed_submission: JobSubmissionResult | None = Depends(
        get_job_submission_replay
    ),
) -> JobResponse:
    if replayed_submission is not None:
        return _job_response(replayed_submission.job, context, repository)
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
    submission: TaskSubmission = Depends(get_task_submission),
    replayed_submission: JobSubmissionResult | None = Depends(
        get_job_submission_replay
    ),
) -> JobResponse:
    if replayed_submission is not None:
        return _job_response(replayed_submission.job, context, repository)
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


@router.post("/jobs/project-export", response_model=JobResponse)
def create_project_export_job(
    payload: ProjectExportRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(get_task_submission),
    replayed_submission: JobSubmissionResult | None = Depends(get_job_submission_replay),
) -> JobResponse:
    if replayed_submission is not None:
        return _job_response(replayed_submission.job, context, repository)
    try:
        submitted, _runner = create_project_export_workflow(
            repository,
            context,
            asset_ids=payload.asset_ids,
            preset=payload.preset,
            package_name=payload.package_name,
            submission=submission,
        )
    except WorkflowInputNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not submitted.replayed:
        dispatcher.dispatch(submitted.job.id, submitted.job.workspace_id)
    return _job_response(submitted.job, context, repository)


@router.post("/assets/images", response_model=AssetResponse)
async def upload_image_asset(
    file: UploadFile = File(...),
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> AssetResponse:
    _require_project_workflow_write(context, "upload_image")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="The uploaded file must be an image.")

    asset_id = uuid4().hex
    filename = Path(file.filename or "upload.png").name
    now = _now()
    with TemporaryDirectory(prefix="gameknife-upload-", ignore_cleanup_errors=True) as directory:
        source_path, size_bytes = await _stage_upload(file, Path(directory), filename)
        _verify_image_path(source_path)
        # Reserve, object storage, and finalize stay in one worker-thread call so no partial persistence
        # state is exposed by splitting the workflow across separate thread-pool operations.
        asset = await run_in_threadpool(
            persist_asset_file,
            repository,
            context.storage,
            AssetRecord(
                id=asset_id,
                workspace_id=context.workspace.id,
                created_by=context.principal.id,
                kind="image",
                original_name=filename,
                path="",
                mime_type=file.content_type,
                size_bytes=size_bytes,
                created_at=now,
                updated_at=now,
            ),
            source_path,
        )

    return _asset_response(asset)


@router.post("/assets/videos", response_model=AssetResponse)
async def upload_video_asset(
    file: UploadFile = File(...),
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> AssetResponse:
    _require_project_workflow_write(context, "upload_video")
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="The uploaded file must be a video.")

    asset_id = uuid4().hex
    filename = Path(file.filename or "upload.mp4").name
    now = _now()
    with TemporaryDirectory(prefix="gameknife-upload-", ignore_cleanup_errors=True) as directory:
        source_path, size_bytes = await _stage_upload(file, Path(directory), filename)
        asset = await run_in_threadpool(
            persist_asset_file,
            repository,
            context.storage,
            AssetRecord(
                id=asset_id,
                workspace_id=context.workspace.id,
                created_by=context.principal.id,
                kind="video",
                original_name=filename,
                path="",
                mime_type=file.content_type,
                size_bytes=size_bytes,
                created_at=now,
                updated_at=now,
            ),
            source_path,
        )
    return _asset_response(asset)


@router.get("/assets", response_model=AssetPageResponse)
def list_asset_page(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    category: str = Query("all"),
    search: str | None = Query(None, max_length=200),
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> AssetPageResponse:
    if category != "all" and category not in ASSET_CATEGORY_KINDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported asset type.")
    kinds = ASSET_CATEGORY_KINDS.get(category)
    total = repository.count_asset_page_for_workspace(
        context.workspace.id,
        kinds=kinds,
        search=search,
    )
    assets = repository.list_asset_page_for_workspace(
        context.workspace.id,
        limit=page_size,
        offset=(page - 1) * page_size,
        kinds=kinds,
        search=search,
    )
    return AssetPageResponse(
        items=[_asset_response(asset) for asset in assets],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/assets/{asset_id}/metadata", response_model=AssetDetailResponse)
def get_asset_metadata(
    asset_id: str,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> AssetDetailResponse:
    asset = repository.get_asset_for_workspace(asset_id, context.workspace.id)
    if asset is None or asset.storage_state != "ready":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found or not ready.")
    relations = repository.list_asset_relations_for_workspace(asset.id, context.workspace.id)
    related_ids = list(
        dict.fromkeys(
            relation.source_asset_id if relation.derived_asset_id == asset.id else relation.derived_asset_id
            for relation in relations
        )
    )
    related_assets = {
        related.id: related
        for related in repository.list_assets_by_ids_for_workspace(related_ids, context.workspace.id)
        if related.storage_state == "ready"
    }
    quality_check = repository.get_current_asset_quality_check(
        asset.id,
        context.workspace.id,
    )
    return AssetDetailResponse(
        **_asset_response(asset).model_dump(),
        relations=[
            {
                "direction": "source" if relation.derived_asset_id == asset.id else "derived",
                "relation_type": relation.relation_type,
                "job_id": relation.job_id,
                "asset": _asset_response(related_assets[related_id]),
            }
            for relation in relations
            if (related_id := relation.source_asset_id if relation.derived_asset_id == asset.id else relation.derived_asset_id)
            in related_assets
        ],
        available_actions=_asset_actions(asset, context),
        quality_check=(
            {
                "id": quality_check.id,
                "status": quality_check.status,
                "rules_version": quality_check.rules_version,
                "content_sha256": quality_check.content_sha256,
                "parameters": _quality_parameters(quality_check.checks_json),
                "checks": _quality_checks(quality_check.checks_json),
                "created_at": quality_check.created_at,
            }
            if quality_check is not None
            else None
        ),
    )


@router.post("/assets/{asset_id}/quality-check", response_model=JobResponse)
def create_asset_quality_check_job(
    asset_id: str,
    payload: AssetQualityCheckRequest,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
    submission: TaskSubmission = Depends(get_task_submission),
    replayed_submission: JobSubmissionResult | None = Depends(
        get_job_submission_replay
    ),
) -> JobResponse:
    if replayed_submission is not None:
        return _job_response(replayed_submission.job, context, repository)
    asset = repository.get_asset_for_workspace(asset_id, context.workspace.id)
    if asset is None or asset.storage_state != "ready":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found or not ready.",
        )
    supports_image = asset.mime_type.startswith("image/")
    supports_components = (
        asset.kind == "asset_component"
        and asset.mime_type == "application/zip"
    )
    supports_audio = asset.mime_type in {"audio/wav", "audio/x-wav"}
    supports_model = (
        asset.kind == "model_3d_glb"
        and asset.mime_type == "model/gltf-binary"
    )
    if (
        not supports_image
        and not supports_components
        and not supports_audio
        and not supports_model
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Automatic quality checks do not support this asset type.",
        )
    source_quality_check_id = str(payload.source_quality_check_id or "").strip()
    if source_quality_check_id and repository.get_asset_quality_check_for_workspace(
        source_quality_check_id,
        asset.id,
        context.workspace.id,
    ) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The quality rules snapshot is missing. Reopen the asset details.",
        )
    try:
        parameters = canonical_asset_quality_check_parameters(
            {
                "asset_id": asset.id,
                "source_quality_check_id": source_quality_check_id or None,
            }
        )
    except JobParameterValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid quality check parameters.",
        ) from exc
    submitted = create_job_record(
        repository,
        context,
        job_type="asset_quality_check",
        input_asset_id=asset.id,
        parameters=parameters,
        submission=submission,
    )
    if not submitted.replayed:
        dispatcher.dispatch(submitted.job.id, submitted.job.workspace_id)
    return _job_response(submitted.job, context, repository)


@router.get("/assets/{asset_id}")
def get_asset(
    asset_id: str,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> Response:
    asset = repository.get_asset_for_workspace(asset_id, context.workspace.id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found or already deleted.")

    try:
        file_path = context.storage.local_path(asset.path)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if file_path is not None:
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="Asset file not found.")
        return FileResponse(file_path, media_type=asset.mime_type, filename=asset.original_name)

    download_url = context.storage.create_download_url(
        asset.path,
        asset.original_name,
        asset.mime_type,
        expires_seconds=300,
    )
    if not download_url:
        raise HTTPException(status_code=500, detail="The storage provider cannot download this asset.")
    return RedirectResponse(download_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: str,
    context: RequestContext = Depends(get_request_context),
    repository: GameKnifeRepository = Depends(get_repository),
) -> Response:
    asset = repository.get_asset_for_workspace(asset_id, context.workspace.id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found or already deleted.")
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
        await run_in_threadpool(_ensure_asset_exists, repository, context, source_asset_id)
    if file.content_type not in ALLOWED_MANUAL_EDIT_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only JPG, PNG, and WebP images are supported.")

    suffix = ALLOWED_MANUAL_EDIT_TYPES[file.content_type]
    filename = _manual_edit_name(name, file.filename, "manual-edit", suffix)
    asset_id = uuid4().hex
    now = _now()
    with TemporaryDirectory(prefix="gameknife-upload-", ignore_cleanup_errors=True) as directory:
        source_path, size_bytes = await _stage_upload(file, Path(directory), filename)
        _verify_image_path(source_path)
        asset = await run_in_threadpool(
            _persist_manual_edit_asset,
            repository,
            context.storage,
            AssetRecord(
                id=asset_id,
                workspace_id=context.workspace.id,
                created_by=context.principal.id,
                kind="manual_edit",
                original_name=filename,
                path="",
                mime_type=file.content_type,
                size_bytes=size_bytes,
                created_at=now,
                updated_at=now,
            ),
            source_path,
            source_asset_id,
        )
    return _asset_response(asset)


def _verify_image_path(source_path: Path) -> None:
    try:
        Image.open(source_path).verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid image.") from exc


async def _stage_upload(upload: UploadFile, directory: Path, fallback_name: str) -> tuple[Path, int]:
    """Stream one request body to an isolated file before reserving durable storage."""

    source_path = directory / (Path(upload.filename or fallback_name).name or fallback_name)
    size_bytes = 0
    with source_path.open("wb") as target:
        while True:
            chunk = await upload.read(UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            size_bytes += len(chunk)
            if size_bytes > MAX_ASSET_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="The uploaded file cannot exceed 50 MB.",
                )
            target.write(chunk)
    if size_bytes == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file cannot be empty.")
    return source_path, size_bytes


def _manual_edit_name(name: str | None, filename: str | None, fallback: str, suffix: str) -> str:
    raw_name = Path(name or filename or fallback).name.strip() or fallback
    if Path(raw_name).suffix:
        return raw_name
    return f"{raw_name}{suffix}"


def _asset_response(asset: AssetRecord) -> AssetResponse:
    return build_asset_response(asset)


def _asset_actions(asset: AssetRecord, context: RequestContext) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = [
        {"id": "download", "label": "Download", "route": f"/api/assets/{asset.id}"}
    ]
    if not context.permissions.can(PROJECT_WORKFLOW_PERMISSION, {"asset_id": asset.id}):
        return actions
    if asset.mime_type.startswith("image/"):
        actions.extend(
            [
                {"id": "background_remove", "label": "Remove Background", "route": "/tools/background-remove"},
                {"id": "image_upscale", "label": "Upscale Image", "route": "/tools/upscale"},
                {"id": "asset_board", "label": "Asset Board", "route": "/tools/asset-board"},
                {"id": "manual_edit", "label": "Manual Edit", "route": "/manual-edit"},
            ]
        )
    elif asset.mime_type.startswith("video/"):
        actions.append({"id": "sequence_video_to_frames", "label": "Video to Frames", "route": "/tools/video-to-sequence"})
    return actions


def _persist_manual_edit_asset(
    repository: GameKnifeRepository,
    storage: StorageProvider,
    asset: AssetRecord,
    source_path: Path,
    source_asset_id: str | None,
) -> AssetRecord:
    stored = persist_asset_file(repository, storage, asset, source_path)
    if not source_asset_id:
        return stored
    try:
        repository.create_asset_relation(
            AssetRelationRecord(
                id=uuid4().hex,
                workspace_id=stored.workspace_id,
                created_by=stored.created_by,
                source_asset_id=source_asset_id,
                derived_asset_id=stored.id,
                relation_type="manual_edit",
                job_id=None,
                created_at=stored.created_at,
            )
        )
        return stored
    except Exception:
        try:
            repository.delete_assets_for_workspace([stored.id], stored.workspace_id)
        finally:
            try:
                storage.delete_object(stored.path)
            except Exception:  # noqa: BLE001
                pass
        raise


def _resource_reference_detail(exc: ResourceReferenceError) -> dict[str, object]:
    return build_resource_reference_detail(exc)


def _quality_checks(value: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    checks = payload.get("checks") if isinstance(payload, dict) else None
    return [item for item in checks if isinstance(item, dict)] if isinstance(checks, list) else []


def _quality_parameters(value: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    parameters = payload.get("parameters") if isinstance(payload, dict) else None
    return dict(parameters) if isinstance(parameters, dict) else {}


def _require_project_workflow_write(context: RequestContext, operation: str, resource: dict[str, object] | None = None) -> None:
    # v1 groups workspace writes from public tools under jobs.create because uploads, imports, manual-edit saves,
    # and job creation form one tool workflow. Restricting only job creation would still let a constrained caller
    # bypass the frontend and write orphaned assets to the workspace.
    context.permissions.require(PROJECT_WORKFLOW_PERMISSION, {"operation": operation, **(resource or {})})


def _require_settings_manage(context: RequestContext, operation: str) -> None:
    # Model installation and video API configuration change the service-wide runtime environment.
    # Community allows the operation by default; callers that enforce permissions decide through PermissionChecker.
    context.permissions.require(SETTINGS_MANAGE_PERMISSION, {"operation": operation})


def _require_model_status_read(context: RequestContext, operation: str) -> None:
    # Tool pages need installation status before creating a Job, while installing or reconfiguring a model changes
    # the service-wide runtime. Reuse the project workflow permission for read-only status without granting settings writes.
    context.permissions.require(PROJECT_WORKFLOW_PERMISSION, {"operation": operation})


@router.get("/settings/birefnet/install")
def read_birefnet_install(
    context: RequestContext = Depends(get_request_context),
    birefnet: BiRefNetService = Depends(get_birefnet_service),
) -> dict[str, object]:
    _require_model_status_read(context, "read_birefnet_install")
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
    _require_model_status_read(context, "read_upscale_models_install")
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
    _require_model_status_read(context, "read_stable_audio_install")
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


async def _save_sequence_upload(
    upload: UploadFile,
    context: RequestContext,
    repository: GameKnifeRepository,
) -> tuple[AssetRecord, dict[str, object]]:
    if upload.content_type not in ALLOWED_SEQUENCE_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{upload.filename or 'File'} is not a supported image format.")

    asset_id = uuid4().hex
    filename = Path(upload.filename or "frame.png").name
    now = _now()
    with TemporaryDirectory(prefix="gameknife-upload-", ignore_cleanup_errors=True) as directory:
        source_path, size_bytes = await _stage_upload(upload, Path(directory), filename)
        _verify_image_path(source_path)
        asset = await run_in_threadpool(
            persist_asset_file,
            repository,
            context.storage,
            AssetRecord(
                id=asset_id,
                workspace_id=context.workspace.id,
                created_by=context.principal.id,
                kind="sequence_frame",
                original_name=filename,
                path="",
                mime_type=upload.content_type or "application/octet-stream",
                size_bytes=size_bytes,
                created_at=now,
                updated_at=now,
            ),
            source_path,
        )

        try:
            with Image.open(source_path) as opened:
                image = opened.convert("RGBA")
                bbox = image.getchannel("A").getbbox() or (0, 0, image.width, image.height)
                width, height = image.size
        except Exception as exc:
            await run_in_threadpool(_cleanup_created_assets, repository, context, [asset])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to read {filename}.") from exc

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found.")
    frames = repository.list_sequence_frames(sequence_id, context.workspace.id, enabled_only=True)
    if not frames:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The sequence has no usable frames.")
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
        warnings.append("Some filenames have no numeric index and were sorted lexically after indexed files.")
    return sorted(files, key=sort_key), warnings


def _guess_sequence_name(files: list[UploadFile]) -> str:
    first_name = Path(files[0].filename or "Sequence").stem
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
    return build_job_response(job, context, repository)


def _ensure_asset_exists(repository: GameKnifeRepository, context: RequestContext, asset_id: str) -> AssetRecord:
    asset = repository.get_asset_for_workspace(asset_id, context.workspace.id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Input asset not found.")
    return asset


def _ensure_birefnet_installed(birefnet: BiRefNetService) -> None:
    if birefnet.is_installed():
        return
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="BiRefNet is not installed. Install the model files from Settings first.")


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
    except Exception as exc:  # pragma: no cover - only reached when the deployment is missing PyTorch
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


def _resolve_history_job_types(
    category: str,
    downloadable: bool,
    delivery_only: bool,
    configuration: JobHistoryConfiguration,
) -> list[str] | None:
    category_types = (
        None
        if category == "all"
        else list(configuration.category_job_types.get(category, (category,)))
    )
    if not downloadable and not delivery_only:
        return category_types
    allowed_job_types = (
        configuration.downloadable_job_types
        if downloadable
        else configuration.task_center_job_types
    )
    allowed_types = set(allowed_job_types)
    if category_types is None:
        return list(allowed_job_types)
    return [job_type for job_type in category_types if job_type in allowed_types]


def _now() -> str:
    return datetime.now(UTC).isoformat()
