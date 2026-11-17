from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from PIL import Image

from gameknife_core import AssetQualityCheckRecord, RequestContext
from gameknife_jobs import JobSubmissionResult, TaskSubmission
from gameknife_processors import AssetBoardSplitProcessor, check_component_archive

from .errors import WorkflowInputNotFoundError, WorkflowModelNotInstalledError
from .job_helpers import (
    WorkflowRepository,
    claim_job,
    cleanup_registered_output_assets,
    create_job_record,
    download_object,
    mark_failed,
    mark_success,
    output_path,
    register_output_assets,
    run_image_output_job,
    temporary_job_directory,
)


asset_board_processor = AssetBoardSplitProcessor()


class AssetBoardCutoutModel(Protocol):
    device_label: str

    def is_installed(self) -> bool:
        ...

    def predict_alpha(self, image: Image.Image):
        ...


def create_asset_board_region_workflow(
    repository: WorkflowRepository,
    context: RequestContext,
    *,
    input_asset_id: str,
    parameters: dict[str, Any],
    submission: TaskSubmission | None = None,
) -> tuple[JobSubmissionResult, Callable[[], None]]:
    input_asset = repository.get_asset_for_workspace(input_asset_id, context.workspace.id)
    if input_asset is None:
        raise WorkflowInputNotFoundError("Input asset not found.")

    # Region detection performs connected-component analysis without receiving the BiRefNet service.
    # It can run independently as a fast preflight, while extraction declares its model dependency explicitly.
    submitted = create_job_record(
        repository,
        context,
        job_type="asset_board_region_detect",
        input_asset_id=input_asset.id,
        parameters=parameters,
        submission=submission,
    )

    def run() -> None:
        run_asset_board_region_workflow(repository, context, submitted.job.id)

    return submitted, run


def create_asset_board_cutout_workflow(
    repository: WorkflowRepository,
    context: RequestContext,
    model: AssetBoardCutoutModel,
    *,
    input_asset_id: str,
    parameters: dict[str, Any],
    submission: TaskSubmission | None = None,
) -> tuple[JobSubmissionResult, Callable[[], None]]:
    if not model.is_installed():
        raise WorkflowModelNotInstalledError("BiRefNet is not installed. Install the model files from Settings first.")

    input_asset = repository.get_asset_for_workspace(input_asset_id, context.workspace.id)
    if input_asset is None:
        raise WorkflowInputNotFoundError("Input asset not found.")

    # Asset extraction receives the model service explicitly because its dependencies differ from region detection.
    # Creation checks installation first, and the background job only reads local cache and writes the extracted asset.
    submitted = create_job_record(
        repository,
        context,
        job_type="asset_board_cutout",
        input_asset_id=input_asset.id,
        parameters=parameters,
        submission=submission,
    )

    def run() -> None:
        run_asset_board_cutout_workflow(repository, context, model, submitted.job.id)

    return submitted, run


def create_asset_board_refine_workflow(
    repository: WorkflowRepository,
    context: RequestContext,
    *,
    cutout_asset_id: str,
    parameters: dict[str, Any],
    submission: TaskSubmission | None = None,
) -> tuple[JobSubmissionResult, Callable[[], None]]:
    cutout_asset = repository.get_asset_for_workspace(cutout_asset_id, context.workspace.id)
    if cutout_asset is None:
        raise WorkflowInputNotFoundError("Background removal result not found.")

    submitted = create_job_record(
        repository,
        context,
        job_type="asset_board_region_refine",
        input_asset_id=cutout_asset.id,
        parameters=parameters,
        submission=submission,
    )

    def run() -> None:
        run_asset_board_refine_workflow(repository, context, submitted.job.id)

    return submitted, run


def create_asset_board_export_workflow(
    repository: WorkflowRepository,
    context: RequestContext,
    *,
    cutout_asset_id: str,
    selected_component_ids: list[int],
    components: list[dict[str, Any]],
    parameters: dict[str, Any],
    submission: TaskSubmission | None = None,
) -> tuple[JobSubmissionResult, Callable[[], None]]:
    cutout_asset = repository.get_asset_for_workspace(cutout_asset_id, context.workspace.id)
    if cutout_asset is None:
        raise WorkflowInputNotFoundError("Background removal result not found.")

    # Export receives the confirmed components and selection explicitly instead of depending on an earlier refine job.
    # Passing current UI state is sufficient to execute ZIP export independently.
    submitted = create_job_record(
        repository,
        context,
        job_type="asset_board_export",
        input_asset_id=cutout_asset.id,
        parameters={**parameters, "selected_component_ids": selected_component_ids, "components": components},
        submission=submission,
    )

    def run() -> None:
        run_asset_board_export_workflow(repository, context, submitted.job.id)

    return submitted, run


def run_asset_board_region_workflow(repository: WorkflowRepository, context: RequestContext, job_id: str) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    if not claim_job(repository, context, job.id):
        return
    input_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if input_asset is None:
        mark_failed(repository, context, job_id, "Input asset not found.")
        return

    try:
        with temporary_job_directory(job.id) as working_directory:
            input_path = download_object(
                context,
                input_asset.path,
                working_directory / "inputs" / Path(input_asset.original_name).name,
            )
            result = asset_board_processor.detect_source_regions(
                input_path,
                json.loads(job.parameters_json),
            )
            final_result = {
                **result.result,
                "input_asset_url": f"/api/assets/{input_asset.id}",
            }
        mark_success(repository, context, job_id, result, final_result)
    except Exception as exc:  # noqa: BLE001
        mark_failed(repository, context, job_id, str(exc))


def run_asset_board_cutout_workflow(
    repository: WorkflowRepository,
    context: RequestContext,
    model: AssetBoardCutoutModel,
    job_id: str,
) -> None:
    """Execute a persisted asset-board cutout job with the runtime's installed model service."""

    run_image_output_job(
        repository,
        context,
        job_id,
        output_kind="asset_cutout",
        output_mime_type="image/png",
        output_suffix="_cutout.png",
        processor=lambda input_path, output_path, job_parameters: asset_board_processor.cutout(
            input_path,
            output_path,
            job_parameters,
            model,
        ),
    )


def run_asset_board_refine_workflow(repository: WorkflowRepository, context: RequestContext, job_id: str) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    if not claim_job(repository, context, job.id):
        return
    cutout_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if cutout_asset is None:
        mark_failed(repository, context, job_id, "Background removal result not found.")
        return

    try:
        with temporary_job_directory(job.id) as working_directory:
            cutout_path = download_object(
                context,
                cutout_asset.path,
                working_directory / "inputs" / Path(cutout_asset.original_name).name,
            )
            result = asset_board_processor.refine_cutout_regions(
                cutout_path,
                json.loads(job.parameters_json),
            )
            final_result = {
                **result.result,
                "cutout_asset_id": cutout_asset.id,
                "cutout_url": f"/api/assets/{cutout_asset.id}",
            }
        mark_success(repository, context, job_id, result, final_result)
    except Exception as exc:  # noqa: BLE001
        mark_failed(repository, context, job_id, str(exc))


def run_asset_board_export_workflow(repository: WorkflowRepository, context: RequestContext, job_id: str) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    if not claim_job(repository, context, job.id):
        return
    cutout_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if cutout_asset is None:
        mark_failed(repository, context, job_id, "Background removal result not found.")
        return

    output_assets: list[dict[str, str]] = []
    try:
        with temporary_job_directory(job.id) as working_directory:
            parameters = json.loads(job.parameters_json)
            cutout_path = download_object(
                context,
                cutout_asset.path,
                working_directory / "inputs" / Path(cutout_asset.original_name).name,
            )
            target_path = output_path(working_directory, f"{Path(cutout_asset.original_name).stem}_components.zip")
            result = asset_board_processor.export_components(
                cutout_path,
                target_path,
                [int(item) for item in parameters.get("selected_component_ids", [])],
                parameters,
                parameters.get("components") if isinstance(parameters.get("components"), list) else None,
            )
            output_assets = register_output_assets(repository, context, job.id, result.output_paths, "asset_component", "application/zip")
            if output_assets:
                try:
                    quality = check_component_archive(target_path)
                    repository.create_asset_quality_check(
                        AssetQualityCheckRecord(
                            id=uuid4().hex,
                            workspace_id=context.workspace.id,
                            created_by=context.principal.id,
                            asset_id=output_assets[0]["id"],
                            content_sha256=quality.content_sha256,
                            rules_version=quality.rules_version,
                            status=quality.status,
                            checks_json=quality.checks_json(),
                            created_at=datetime.now(UTC).isoformat(),
                        )
                    )
                except Exception:  # noqa: BLE001, S110
                    # Quality inspection is recorded independently from the valid ZIP delivery. If the checker
                    # runtime is unavailable, Asset metadata remains unchecked and the export itself stays usable.
                    pass
        mark_success(repository, context, job_id, result, {**result.result, "output_assets": output_assets})
    except Exception as exc:  # noqa: BLE001
        cleanup_registered_output_assets(repository, context, job_id, output_assets)
        mark_failed(repository, context, job_id, str(exc))
