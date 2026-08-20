from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from gameknife_core import RequestContext
from gameknife_jobs import JobSubmissionResult, TaskSubmission
from gameknife_processors import BackgroundRemoveProcessor

from .errors import WorkflowInputNotFoundError, WorkflowModelNotInstalledError
from .job_helpers import WorkflowRepository, create_job_record, run_image_output_job


background_processor = BackgroundRemoveProcessor()


class BackgroundRemoveModel(Protocol):
    device_label: str

    def is_installed(self) -> bool:
        ...

    def predict_alpha(self, image):
        ...


def create_background_remove_workflow(
    repository: WorkflowRepository,
    context: RequestContext,
    model: BackgroundRemoveModel,
    *,
    input_asset_id: str,
    parameters: dict[str, Any],
    submission: TaskSubmission | None = None,
) -> tuple[JobSubmissionResult, Callable[[], None]]:
    if not model.is_installed():
        raise WorkflowModelNotInstalledError("BiRefNet 模型尚未下载安装，请先到设置页下载安装模型文件。")

    input_asset = repository.get_asset_for_workspace(input_asset_id, context.workspace.id)
    if input_asset is None:
        raise WorkflowInputNotFoundError("输入素材不存在。")

    # Creation validation lives in the workflow so every API entry point reuses the same orchestration path.
    # The API layer only maps HTTP status codes, avoiding duplicated model checks and asset-ownership rules.
    submitted = create_job_record(
        repository,
        context,
        job_type="background_remove",
        input_asset_id=input_asset.id,
        parameters=parameters,
        submission=submission,
    )

    def run() -> None:
        run_background_remove_workflow(repository, context, model, submitted.job.id)

    return submitted, run


def run_background_remove_workflow(
    repository: WorkflowRepository,
    context: RequestContext,
    model: BackgroundRemoveModel,
    job_id: str,
) -> None:
    run_image_output_job(
        repository,
        context,
        job_id,
        output_kind="background_remove",
        output_mime_type="image/png",
        output_suffix="_cutout.png",
        processor=lambda input_path, output_path, job_parameters: background_processor.process(
            input_path,
            output_path,
            job_parameters,
            model,
        ),
    )
