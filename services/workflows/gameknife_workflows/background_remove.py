from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from gameknife_api.job_service import create_job, run_background_remove_job
from gameknife_core import JobRecord, RequestContext
from gameknife_jobs import SQLiteGameKnifeRepository


class BackgroundRemoveModel(Protocol):
    def is_installed(self) -> bool:
        ...


class WorkflowInputNotFoundError(ValueError):
    pass


class WorkflowModelNotInstalledError(ValueError):
    pass


def create_background_remove_workflow(
    repository: SQLiteGameKnifeRepository,
    context: RequestContext,
    model: BackgroundRemoveModel,
    *,
    input_asset_id: str,
    parameters: dict[str, Any],
) -> tuple[JobRecord, Callable[[], None]]:
    if not model.is_installed():
        raise WorkflowModelNotInstalledError("BiRefNet 模型尚未下载安装，请先到设置页下载安装模型文件。")

    input_asset = repository.get_asset_for_workspace(input_asset_id, context.workspace.id)
    if input_asset is None:
        raise WorkflowInputNotFoundError("输入素材不存在。")

    # 创建校验放在工作流层，原因是 Community 和 Commercial 都会复用同一条任务编排。
    # API 层只负责 HTTP 状态码转换，避免后续商用入口复制模型检查和资产归属判断。
    job = create_job(repository, context, job_type="background_remove", input_asset_id=input_asset.id, parameters=parameters)

    def run() -> None:
        run_background_remove_job(repository, context, model, job.id)

    return job, run
