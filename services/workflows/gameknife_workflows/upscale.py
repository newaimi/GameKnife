from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from PIL import Image

from gameknife_core import JobRecord, RequestContext
from gameknife_processors import UpscaleProcessor

from .errors import WorkflowInputNotFoundError, WorkflowModelNotInstalledError
from .job_helpers import WorkflowRepository, create_job_record, run_image_output_job


upscale_processor = UpscaleProcessor()


class UpscaleModel(Protocol):
    device_label: str

    def is_installed(self) -> bool:
        ...

    def upscale_image(
        self,
        image: Image.Image,
        *,
        style: str,
        target_scale: int,
        denoise: int,
        tile_size: int,
    ) -> tuple[Image.Image, str, str, list[str]]:
        ...


def create_upscale_workflow(
    repository: WorkflowRepository,
    context: RequestContext,
    model: UpscaleModel,
    *,
    input_asset_id: str,
    parameters: dict[str, Any],
) -> tuple[JobRecord, Callable[[], None]]:
    if str(parameters.get("style") or "general") != "pixel" and not model.is_installed():
        raise WorkflowModelNotInstalledError("图片放大模型尚未下载安装，请先到设置页下载安装模型文件。")

    input_asset = repository.get_asset_for_workspace(input_asset_id, context.workspace.id)
    if input_asset is None:
        raise WorkflowInputNotFoundError("输入素材不存在。")

    # 像素风和 AI 超分共用同一个 job 类型，原因是前端任务历史和下载筛选都按 image_upscale 聚合。
    # 是否调用模型由参数显式决定，像素风单独开启时也能通过最近邻算法完成。
    job = create_job_record(repository, context, job_type="image_upscale", input_asset_id=input_asset.id, parameters=parameters)

    def run() -> None:
        run_image_output_job(
            repository,
            context,
            job.id,
            output_kind="upscale_result",
            output_mime_type="image/png",
            output_suffix="_upscale.png",
            processor=lambda input_path, output_path, job_parameters: upscale_processor.process(input_path, output_path, job_parameters, model),
        )

    return job, run
