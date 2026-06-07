from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from gameknife_core import AssetRecord, JobRecord, ProcessResult, RequestContext


class WorkflowRepository(Protocol):
    def create_asset(self, asset: AssetRecord) -> None:
        ...

    def delete_assets_for_workspace(self, asset_ids: list[str], workspace_id: str) -> None:
        ...

    def get_asset_for_workspace(self, asset_id: str, workspace_id: str) -> AssetRecord | None:
        ...

    def create_job(self, job: JobRecord) -> None:
        ...

    def get_job_for_workspace(self, job_id: str, workspace_id: str) -> JobRecord | None:
        ...

    def update_job(
        self,
        job_id: str,
        workspace_id: str,
        *,
        updated_at: str,
        status: str | None = None,
        result_json: str | None = None,
        device: str | None = None,
        duration_ms: int | None = None,
        error_message: str | None = None,
    ) -> None:
        ...


def create_job_record(
    repository: WorkflowRepository,
    context: RequestContext,
    *,
    job_type: str,
    input_asset_id: str,
    parameters: dict[str, Any],
) -> JobRecord:
    # job 创建属于公共工作流边界，原因是 Community 和 Commercial 都需要统一的权限动作和字段写入语义。
    # Community 注入放行权限，Commercial 注入 RBAC，工作流层只依赖 RequestContext。
    context.permissions.require("jobs.create", {"job_type": job_type, "input_asset_id": input_asset_id})
    now = _now()
    job = JobRecord(
        id=uuid4().hex,
        workspace_id=context.workspace.id,
        created_by=context.principal.id,
        job_type=job_type,
        status="pending",
        input_asset_id=input_asset_id,
        parameters_json=json.dumps(parameters, ensure_ascii=False),
        result_json="{}",
        device=None,
        duration_ms=0,
        error_message=None,
        created_at=now,
        updated_at=now,
    )
    repository.create_job(job)
    stored = repository.get_job_for_workspace(job.id, context.workspace.id)
    if stored is None:
        raise RuntimeError("任务创建失败。")
    return stored


def run_image_output_job(
    repository: WorkflowRepository,
    context: RequestContext,
    job_id: str,
    *,
    output_kind: str,
    output_mime_type: str,
    output_suffix: str,
    processor: Callable[[Path, Path, dict[str, Any]], ProcessResult],
) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    input_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if input_asset is None:
        mark_failed(repository, context, job_id, "输入素材不存在。")
        return

    repository.update_job(job_id, context.workspace.id, status="running", updated_at=_now())
    try:
        output_name = f"{Path(input_asset.original_name).stem}{output_suffix}"
        result = processor(
            context.storage.resolve_asset_path(input_asset.path),
            output_path(context, job.id, output_name),
            json.loads(job.parameters_json),
        )
        output_assets = register_output_assets(repository, context, result.output_paths, output_kind, output_mime_type)
        final_result = {
            **result.result,
            "input_asset_url": f"/api/assets/{input_asset.id}",
            "output_assets": output_assets,
        }
        if output_kind == "asset_cutout" and output_assets:
            # 素材板后续刷新框和导出依赖 cutout_asset_id 直连抠图结果。
            # 通用 output_assets 保留下载列表，专用字段保留工作台链路的稳定输入。
            final_result["cutout_asset_id"] = output_assets[0]["id"]
            final_result["cutout_url"] = output_assets[0]["url"]
        mark_success(repository, context, job_id, result, final_result)
    except Exception as exc:  # noqa: BLE001
        mark_failed(repository, context, job_id, str(exc))


def register_output_assets(
    repository: WorkflowRepository,
    context: RequestContext,
    paths: list[Path],
    kind: str,
    mime_type: str,
) -> list[dict[str, str]]:
    output_assets: list[dict[str, str]] = []
    for path in paths:
        asset_id = uuid4().hex
        now = _now()
        relative_path = path.resolve().relative_to(context.storage.root.resolve()).as_posix()
        asset = AssetRecord(
            id=asset_id,
            workspace_id=context.workspace.id,
            created_by=context.principal.id,
            kind=kind,
            original_name=path.name,
            path=relative_path,
            mime_type=mime_type,
            size_bytes=path.stat().st_size,
            created_at=now,
            updated_at=now,
        )
        repository.create_asset(asset)
        output_assets.append({"id": asset.id, "url": f"/api/assets/{asset.id}"})
    return output_assets


def mark_success(
    repository: WorkflowRepository,
    context: RequestContext,
    job_id: str,
    result: ProcessResult,
    final_result: dict[str, Any],
) -> None:
    repository.update_job(
        job_id,
        context.workspace.id,
        status="success",
        result_json=json.dumps(final_result, ensure_ascii=False),
        device=result.device,
        duration_ms=result.duration_ms,
        updated_at=_now(),
    )


def mark_running(repository: WorkflowRepository, context: RequestContext, job_id: str) -> None:
    repository.update_job(job_id, context.workspace.id, status="running", updated_at=_now())


def mark_failed(repository: WorkflowRepository, context: RequestContext, job_id: str, error_message: str) -> None:
    repository.update_job(
        job_id,
        context.workspace.id,
        status="failed",
        error_message=error_message,
        updated_at=_now(),
    )


def output_path(context: RequestContext, job_id: str, filename: str) -> Path:
    path = context.storage.root / "outputs" / job_id / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _now() -> str:
    return datetime.now(UTC).isoformat()
