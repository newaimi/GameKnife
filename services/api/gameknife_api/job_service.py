from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from gameknife_core import AssetRecord, JobRecord, ProcessResult, RequestContext
from gameknife_jobs import SQLiteGameKnifeRepository
from gameknife_processors import AssetBoardSplitProcessor, UpscaleProcessor

upscale_processor = UpscaleProcessor()
asset_board_processor = AssetBoardSplitProcessor()


def create_job(
    repository: SQLiteGameKnifeRepository,
    context: RequestContext,
    *,
    job_type: str,
    input_asset_id: str,
    parameters: dict[str, Any],
) -> JobRecord:
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


def run_upscale_job(repository: SQLiteGameKnifeRepository, context: RequestContext, job_id: str) -> None:
    _run_image_output_job(
        repository,
        context,
        job_id,
        output_kind="upscale_result",
        output_mime_type="image/png",
        output_suffix="_upscale.png",
        processor=lambda input_path, output_path, parameters: upscale_processor.process(input_path, output_path, parameters),
    )


def run_asset_board_region_job(repository: SQLiteGameKnifeRepository, context: RequestContext, job_id: str) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    input_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if input_asset is None:
        _mark_failed(repository, context, job_id, "输入素材不存在。")
        return

    repository.update_job(job_id, context.workspace.id, status="running", updated_at=_now())
    try:
        result = asset_board_processor.detect_source_regions(
            context.storage.resolve_asset_path(input_asset.path),
            json.loads(job.parameters_json),
        )
        final_result = {
            **result.result,
            "input_asset_url": f"/api/assets/{input_asset.id}",
        }
        _mark_success(repository, context, job_id, result, final_result)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(repository, context, job_id, str(exc))


def run_asset_board_refine_job(repository: SQLiteGameKnifeRepository, context: RequestContext, job_id: str) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    cutout_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if cutout_asset is None:
        _mark_failed(repository, context, job_id, "抠图结果不存在。")
        return

    repository.update_job(job_id, context.workspace.id, status="running", updated_at=_now())
    try:
        result = asset_board_processor.refine_cutout_regions(
            context.storage.resolve_asset_path(cutout_asset.path),
            json.loads(job.parameters_json),
        )
        final_result = {
            **result.result,
            "cutout_asset_id": cutout_asset.id,
            "cutout_url": f"/api/assets/{cutout_asset.id}",
        }
        _mark_success(repository, context, job_id, result, final_result)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(repository, context, job_id, str(exc))


def run_asset_board_export_job(repository: SQLiteGameKnifeRepository, context: RequestContext, job_id: str) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    cutout_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if cutout_asset is None:
        _mark_failed(repository, context, job_id, "抠图结果不存在。")
        return

    repository.update_job(job_id, context.workspace.id, status="running", updated_at=_now())
    try:
        parameters = json.loads(job.parameters_json)
        output_path = _output_path(context, job.id, f"{Path(cutout_asset.original_name).stem}_components.zip")
        result = asset_board_processor.export_components(
            context.storage.resolve_asset_path(cutout_asset.path),
            output_path,
            [int(item) for item in parameters.get("selected_component_ids", [])],
            parameters,
            parameters.get("components") if isinstance(parameters.get("components"), list) else None,
        )
        output_assets = _register_output_assets(repository, context, result.output_paths, "asset_component", "application/zip")
        _mark_success(repository, context, job_id, result, {**result.result, "output_assets": output_assets})
    except Exception as exc:  # noqa: BLE001
        _mark_failed(repository, context, job_id, str(exc))


def delete_job(repository: SQLiteGameKnifeRepository, context: RequestContext, job_id: str) -> bool:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return False
    if job.status in {"pending", "running"}:
        raise ValueError("任务正在处理中，完成后再删除。")

    result = json.loads(job.result_json)
    asset_ids = _collect_result_asset_ids(result)
    asset_records = repository.list_assets_by_ids_for_workspace(asset_ids, context.workspace.id)
    repository.delete_job_for_workspace(job_id, context.workspace.id)
    repository.delete_assets_for_workspace([asset.id for asset in asset_records], context.workspace.id)
    for asset in asset_records:
        context.storage.remove_asset_file(asset.path)
    return True


def _run_image_output_job(
    repository: SQLiteGameKnifeRepository,
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
        _mark_failed(repository, context, job_id, "输入素材不存在。")
        return

    repository.update_job(job_id, context.workspace.id, status="running", updated_at=_now())
    try:
        output_name = f"{Path(input_asset.original_name).stem}{output_suffix}"
        result = processor(
            context.storage.resolve_asset_path(input_asset.path),
            _output_path(context, job.id, output_name),
            json.loads(job.parameters_json),
        )
        output_assets = _register_output_assets(repository, context, result.output_paths, output_kind, output_mime_type)
        final_result = {
            **result.result,
            "input_asset_url": f"/api/assets/{input_asset.id}",
            "output_assets": output_assets,
        }
        _mark_success(repository, context, job_id, result, final_result)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(repository, context, job_id, str(exc))


def _register_output_assets(
    repository: SQLiteGameKnifeRepository,
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


def _mark_success(
    repository: SQLiteGameKnifeRepository,
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


def _mark_failed(repository: SQLiteGameKnifeRepository, context: RequestContext, job_id: str, error_message: str) -> None:
    repository.update_job(
        job_id,
        context.workspace.id,
        status="failed",
        error_message=error_message,
        updated_at=_now(),
    )


def _output_path(context: RequestContext, job_id: str, filename: str) -> Path:
    path = context.storage.root / "outputs" / job_id / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _collect_result_asset_ids(result: dict[str, Any]) -> list[str]:
    asset_ids: list[str] = []

    def append_asset_id(value: Any) -> None:
        if isinstance(value, str) and value not in asset_ids:
            asset_ids.append(value)

    append_asset_id(result.get("cutout_asset_id"))
    append_asset_id(result.get("video_asset_id"))
    for output_asset in result.get("output_assets", []):
        if isinstance(output_asset, dict):
            append_asset_id(output_asset.get("id"))
    for component in result.get("components", []):
        if isinstance(component, dict):
            append_asset_id(component.get("preview_asset_id"))
    return asset_ids


def _now() -> str:
    return datetime.now(UTC).isoformat()
