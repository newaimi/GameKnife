from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from gameknife_core import JobRecord, RequestContext
from gameknife_jobs import JOB_TYPE_REGISTRY, GameKnifeRepository, JobExecutionHandler
from gameknife_workflows import (
    run_asset_board_cutout_workflow,
    run_asset_board_export_workflow,
    run_asset_board_refine_workflow,
    run_asset_board_region_workflow,
    run_background_remove_workflow,
    run_project_export_workflow,
    run_sequence_frames_export_workflow,
    run_sequence_spine_export_workflow,
    run_sound_effect_workflow,
    run_upscale_workflow,
)
from gameknife_workflows.background_remove import BackgroundRemoveModel
from gameknife_workflows.sound_effect import SoundEffectService
from gameknife_workflows.upscale import UpscaleModel

from gameknife_api.job_service import (
    run_sequence_clean_job,
    run_sequence_from_video_job,
    run_sequence_generate_video_job,
)

ContextResolver = Callable[[], RequestContext]
BackgroundRemoveModelResolver = Callable[[], BackgroundRemoveModel]
UpscaleModelResolver = Callable[[], UpscaleModel]
SoundEffectServiceResolver = Callable[[], SoundEffectService]
PersistedJobExecutor = Callable[[JobRecord, RequestContext, Mapping[str, Any]], None]


def build_job_execution_handlers(
    repository: GameKnifeRepository,
    context_resolver: ContextResolver,
    *,
    birefnet_resolver: BackgroundRemoveModelResolver,
    upscale_model_resolver: UpscaleModelResolver,
    stable_audio_resolver: SoundEffectServiceResolver,
) -> dict[str, JobExecutionHandler]:
    """Build the complete public executor map from already-assembled runtime services."""

    handlers = {
        "background_remove": _bind_persisted_job(
            repository,
            context_resolver,
            lambda job, context, _parameters: run_background_remove_workflow(
                repository,
                context,
                birefnet_resolver(),
                job.id,
            ),
        ),
        "asset_board_region_detect": _bind_persisted_job(
            repository,
            context_resolver,
            lambda job, context, _parameters: run_asset_board_region_workflow(repository, context, job.id),
        ),
        "asset_board_cutout": _bind_persisted_job(
            repository,
            context_resolver,
            lambda job, context, _parameters: run_asset_board_cutout_workflow(
                repository,
                context,
                birefnet_resolver(),
                job.id,
            ),
        ),
        "asset_board_region_refine": _bind_persisted_job(
            repository,
            context_resolver,
            lambda job, context, _parameters: run_asset_board_refine_workflow(repository, context, job.id),
        ),
        "asset_board_export": _bind_persisted_job(
            repository,
            context_resolver,
            lambda job, context, _parameters: run_asset_board_export_workflow(repository, context, job.id),
        ),
        "image_upscale": _bind_persisted_job(
            repository,
            context_resolver,
            lambda job, context, _parameters: run_upscale_workflow(
                repository,
                context,
                upscale_model_resolver(),
                job.id,
            ),
        ),
        "sequence_clean": _bind_persisted_job(
            repository,
            context_resolver,
            lambda job, context, parameters: run_sequence_clean_job(
                repository,
                context,
                job.id,
                _required_string(parameters, "sequence_id"),
            ),
        ),
        "sequence_generate_video": _bind_persisted_job(
            repository,
            context_resolver,
            lambda job, context, _parameters: run_sequence_generate_video_job(repository, context, job.id),
        ),
        "sequence_video_to_frames": _bind_persisted_job(
            repository,
            context_resolver,
            lambda job, context, _parameters: run_sequence_from_video_job(
                repository,
                context,
                birefnet_resolver(),
                job.id,
            ),
        ),
        "sequence_export_frames": _bind_persisted_job(
            repository,
            context_resolver,
            lambda job, context, parameters: run_sequence_frames_export_workflow(
                repository,
                context,
                job.id,
                _required_string(parameters, "sequence_id"),
            ),
        ),
        "sequence_export_spine": _bind_persisted_job(
            repository,
            context_resolver,
            lambda job, context, parameters: run_sequence_spine_export_workflow(
                repository,
                context,
                job.id,
                _required_string(parameters, "sequence_id"),
            ),
        ),
        "sound_effect_generate": _bind_persisted_job(
            repository,
            context_resolver,
            lambda job, context, _parameters: run_sound_effect_workflow(
                repository,
                context,
                stable_audio_resolver(),
                job.id,
            ),
        ),
        "project_export_package": _bind_persisted_job(
            repository,
            context_resolver,
            lambda job, context, _parameters: run_project_export_workflow(
                repository,
                context,
                job.id,
            ),
        ),
    }
    expected_executors = {spec.executor for spec in JOB_TYPE_REGISTRY.values()}
    if set(handlers) != expected_executors:
        missing = sorted(expected_executors - set(handlers))
        unexpected = sorted(set(handlers) - expected_executors)
        raise RuntimeError(
            "Incomplete job execution handlers: "
            f"missing={','.join(missing) or '-'} unexpected={','.join(unexpected) or '-'}"
        )
    return handlers


def _bind_persisted_job(
    repository: GameKnifeRepository,
    context_resolver: ContextResolver,
    executor: PersistedJobExecutor,
) -> JobExecutionHandler:
    def execute(job_id: str, workspace_id: str) -> None:
        # The scheduled callback reconstructs execution state from stable identifiers. Request objects, request-scoped
        # contexts, parameters, secrets, paths, and factory runner closures never cross the scheduling boundary.
        context = context_resolver()
        if context.workspace.id != workspace_id:
            raise RuntimeError("Dispatched workspace does not match the assembled runtime context")
        job = repository.get_job_for_workspace(job_id, workspace_id)
        if job is None:
            return
        try:
            parameters = _job_parameters(job)
            executor(job, context, parameters)
        except Exception as exc:  # noqa: BLE001
            # Invalid persisted parameters and runtime assembly failures happen before a workflow can claim the Job.
            # Move the record to a terminal failure instead of allowing a BackgroundTasks exception to leave it pending.
            try:
                repository.update_job(
                    job.id,
                    workspace_id,
                    status="failed",
                    error_message=str(exc) or exc.__class__.__name__,
                    updated_at=datetime.now(UTC).isoformat(),
                )
            except Exception:  # noqa: BLE001
                # A concurrent runner may already own or finish the Job. Repository transition rules remain the
                # authority, and scheduling callbacks must not leak an exception into the completed HTTP response.
                return

    return execute


def _job_parameters(job: JobRecord) -> Mapping[str, Any]:
    try:
        parameters = json.loads(job.parameters_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid parameters for job {job.id}") from exc
    if not isinstance(parameters, dict):
        raise RuntimeError(f"Invalid parameters for job {job.id}")
    return parameters


def _required_string(parameters: Mapping[str, Any], name: str) -> str:
    value = parameters.get(name)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Missing required job parameter: {name}")
    return value
