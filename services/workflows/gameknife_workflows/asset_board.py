from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from PIL import Image

from gameknife_core import JobRecord, RequestContext
from gameknife_processors import AssetBoardSplitProcessor

from .errors import WorkflowInputNotFoundError, WorkflowModelNotInstalledError
from .job_helpers import WorkflowRepository, create_job_record, mark_failed, mark_running, mark_success, run_image_output_job


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
) -> tuple[JobRecord, Callable[[], None]]:
    input_asset = repository.get_asset_for_workspace(input_asset_id, context.workspace.id)
    if input_asset is None:
        raise WorkflowInputNotFoundError("输入素材不存在。")

    # 区域识别只做素材板连通域分析，不传入 BiRefNet 模型服务。
    # 这样它可以作为快速预检独立运行，抠图任务再显式依赖模型。
    job = create_job_record(
        repository,
        context,
        job_type="asset_board_region_detect",
        input_asset_id=input_asset.id,
        parameters=parameters,
    )

    def run() -> None:
        run_asset_board_region_workflow(repository, context, job.id)

    return job, run


def create_asset_board_cutout_workflow(
    repository: WorkflowRepository,
    context: RequestContext,
    model: AssetBoardCutoutModel,
    *,
    input_asset_id: str,
    parameters: dict[str, Any],
) -> tuple[JobRecord, Callable[[], None]]:
    if not model.is_installed():
        raise WorkflowModelNotInstalledError("BiRefNet 模型尚未下载安装，请先到设置页下载安装模型文件。")

    input_asset = repository.get_asset_for_workspace(input_asset_id, context.workspace.id)
    if input_asset is None:
        raise WorkflowInputNotFoundError("输入素材不存在。")

    # 素材板抠图显式接收模型服务，原因是它和区域识别的依赖完全不同。
    # 创建阶段先检查模型安装状态，后台任务只负责读取本地缓存并生成抠图资产。
    job = create_job_record(
        repository,
        context,
        job_type="asset_board_cutout",
        input_asset_id=input_asset.id,
        parameters=parameters,
    )

    def run() -> None:
        run_image_output_job(
            repository,
            context,
            job.id,
            output_kind="asset_cutout",
            output_mime_type="image/png",
            output_suffix="_cutout.png",
            processor=lambda input_path, output_path, job_parameters: asset_board_processor.cutout(input_path, output_path, job_parameters, model),
        )

    return job, run


def run_asset_board_region_workflow(repository: WorkflowRepository, context: RequestContext, job_id: str) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    input_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if input_asset is None:
        mark_failed(repository, context, job_id, "输入素材不存在。")
        return

    mark_running(repository, context, job_id)
    try:
        result = asset_board_processor.detect_source_regions(
            context.storage.resolve_asset_path(input_asset.path),
            json.loads(job.parameters_json),
        )
        final_result = {
            **result.result,
            "input_asset_url": f"/api/assets/{input_asset.id}",
        }
        mark_success(repository, context, job_id, result, final_result)
    except Exception as exc:  # noqa: BLE001
        mark_failed(repository, context, job_id, str(exc))
