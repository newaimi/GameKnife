from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from gameknife_core import JobRecord, ProcessResult, RequestContext
from gameknife_processors import SequenceFrameProcessor

from .errors import WorkflowInputNotFoundError, WorkflowValidationError
from .job_helpers import WorkflowRepository, create_job_record, mark_failed, mark_running, mark_success, output_path, register_output_assets


sequence_processor = SequenceFrameProcessor()


class SequenceWorkflowRepository(WorkflowRepository, Protocol):
    def get_sequence_for_workspace(self, sequence_id: str, workspace_id: str) -> Any | None:
        ...

    def list_sequence_frames(self, sequence_id: str, workspace_id: str, *, enabled_only: bool = False) -> list[Any]:
        ...


def create_sequence_frames_export_workflow(
    repository: SequenceWorkflowRepository,
    context: RequestContext,
    *,
    sequence_id: str,
    parameters: dict[str, Any],
) -> tuple[JobRecord, Callable[[], None]]:
    _sequence, input_asset_id = _ensure_sequence_export_input(repository, context, sequence_id)
    # 导出任务只依赖当前序列帧记录和启用帧，不要求先运行清洗任务。
    # 这样用户导入序列帧后可以直接导出原始 PNG 包。
    job = create_job_record(
        repository,
        context,
        job_type="sequence_export_frames",
        input_asset_id=input_asset_id,
        parameters={"sequence_id": sequence_id, **parameters},
    )

    def run() -> None:
        run_sequence_frames_export_workflow(repository, context, job.id, sequence_id)

    return job, run


def create_sequence_spine_export_workflow(
    repository: SequenceWorkflowRepository,
    context: RequestContext,
    *,
    sequence_id: str,
    parameters: dict[str, Any],
) -> tuple[JobRecord, Callable[[], None]]:
    _sequence, input_asset_id = _ensure_sequence_export_input(repository, context, sequence_id)
    # Spine 导出和 PNG 包导出共用同一套序列帧输入校验，避免两个入口对空帧、缺序列的处理不一致。
    job = create_job_record(
        repository,
        context,
        job_type="sequence_export_spine",
        input_asset_id=input_asset_id,
        parameters={"sequence_id": sequence_id, **parameters},
    )

    def run() -> None:
        run_sequence_spine_export_workflow(repository, context, job.id, sequence_id)

    return job, run


def run_sequence_frames_export_workflow(
    repository: SequenceWorkflowRepository,
    context: RequestContext,
    job_id: str,
    sequence_id: str,
) -> None:
    _run_sequence_export_workflow(
        repository,
        context,
        job_id,
        sequence_id,
        output_suffix="_frames.zip",
        output_kind="sequence_export",
        processor=lambda sequence, frames, target_path, parameters: sequence_processor.export_frames_zip(sequence, frames, target_path, parameters),
    )


def run_sequence_spine_export_workflow(
    repository: SequenceWorkflowRepository,
    context: RequestContext,
    job_id: str,
    sequence_id: str,
) -> None:
    _run_sequence_export_workflow(
        repository,
        context,
        job_id,
        sequence_id,
        output_suffix="_spine.zip",
        output_kind="sequence_spine",
        processor=lambda sequence, frames, target_path, parameters: sequence_processor.export_spine_zip(sequence, frames, target_path, parameters),
    )


def _ensure_sequence_export_input(
    repository: SequenceWorkflowRepository,
    context: RequestContext,
    sequence_id: str,
) -> tuple[Any, str]:
    sequence = repository.get_sequence_for_workspace(sequence_id, context.workspace.id)
    if sequence is None:
        raise WorkflowInputNotFoundError("序列帧不存在。")
    frames = repository.list_sequence_frames(sequence_id, context.workspace.id, enabled_only=True)
    if not frames:
        raise WorkflowValidationError("序列帧没有可用帧。")
    return sequence, str(frames[0]["source_asset_id"])


def _run_sequence_export_workflow(
    repository: SequenceWorkflowRepository,
    context: RequestContext,
    job_id: str,
    sequence_id: str,
    *,
    output_suffix: str,
    output_kind: str,
    processor: Callable[[dict[str, Any], list[dict[str, Any]], Path, dict[str, Any]], ProcessResult],
) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    sequence = repository.get_sequence_for_workspace(sequence_id, context.workspace.id)
    if job is None:
        return
    if sequence is None:
        mark_failed(repository, context, job_id, "序列帧不存在。")
        return
    frames = repository.list_sequence_frames(sequence_id, context.workspace.id, enabled_only=True)
    if not frames:
        mark_failed(repository, context, job_id, "序列帧没有可导出的帧。")
        return

    mark_running(repository, context, job_id)
    try:
        target_path = output_path(context, job_id, f"{_safe_name(str(sequence['name']))}{output_suffix}")
        result = processor(
            _sequence_mapping(sequence),
            _frame_mappings(context, frames),
            target_path,
            json.loads(job.parameters_json),
        )
        output_assets = register_output_assets(repository, context, result.output_paths, output_kind, "application/zip")
        mark_success(repository, context, job_id, result, {**result.result, "output_assets": output_assets})
    except Exception as exc:  # noqa: BLE001
        mark_failed(repository, context, job_id, str(exc))


def _sequence_mapping(sequence: Any) -> dict[str, Any]:
    return {
        "id": sequence["id"],
        "name": sequence["name"],
        "fps": sequence["fps"],
        "loop": sequence["loop"],
        "canvas_width": sequence["canvas_width"],
        "canvas_height": sequence["canvas_height"],
        "anchor_mode": sequence["anchor_mode"],
        "anchor_x": sequence["anchor_x"],
        "anchor_y": sequence["anchor_y"],
    }


def _frame_mappings(context: RequestContext, frames: list[Any]) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for frame in frames:
        source_path = context.storage.resolve_asset_path(frame["source_path"])
        processed_path = context.storage.resolve_asset_path(frame["processed_path"]) if frame["processed_path"] else None
        mapped.append(
            {
                "id": frame["id"],
                "sequence_id": frame["sequence_id"],
                "source_asset_id": frame["source_asset_id"],
                "processed_asset_id": frame["processed_asset_id"],
                "frame_index": int(frame["frame_index"]),
                "original_name": frame["original_name"],
                "width": int(frame["width"]),
                "height": int(frame["height"]),
                "bbox_json": frame["bbox_json"],
                "offset_x": int(frame["offset_x"]),
                "offset_y": int(frame["offset_y"]),
                "duration_ms": int(frame["duration_ms"]),
                "enabled": bool(frame["enabled"]),
                "is_generated": bool(frame["is_generated"]),
                "source_path": str(source_path),
                "processed_path": str(processed_path) if processed_path else None,
            }
        )
    return mapped


def _safe_name(value: str) -> str:
    name = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    return name or "sequence"
