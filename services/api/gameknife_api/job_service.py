from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from gameknife_core import AssetRecord, JobRecord, ProcessResult, RequestContext
from gameknife_jobs import SQLiteGameKnifeRepository
from gameknife_processors import AssetBoardSplitProcessor, SequenceFrameProcessor, UpscaleProcessor
from gameknife_api.stable_audio import StableAudioService

upscale_processor = UpscaleProcessor()
asset_board_processor = AssetBoardSplitProcessor()
sequence_processor = SequenceFrameProcessor()


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


def run_sound_effect_job(
    repository: SQLiteGameKnifeRepository,
    context: RequestContext,
    stable_audio: StableAudioService,
    job_id: str,
) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    prompt_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if prompt_asset is None:
        _mark_failed(repository, context, job_id, "声效提示词不存在。")
        return

    repository.update_job(job_id, context.workspace.id, status="running", updated_at=_now())
    try:
        prompt_path = context.storage.resolve_asset_path(prompt_asset.path)
        prompt = prompt_path.read_text(encoding="utf-8").strip()
        if not prompt:
            raise RuntimeError("声效提示词不能为空。")
        parameters = json.loads(job.parameters_json)
        output_path = _output_path(context, job.id, "sound_effect.wav")
        metadata = stable_audio.generate_sound_effect(prompt, output_path, parameters)
        result = ProcessResult(
            output_paths=[output_path],
            result={
                "prompt": prompt,
                "duration_seconds": parameters.get("duration_seconds"),
                "seed": parameters.get("seed"),
                "steps": parameters.get("steps"),
                "cfg_scale": parameters.get("cfg_scale"),
                "model": metadata.get("model"),
                "sample_rate": metadata.get("sample_rate"),
                "queue_wait_ms": metadata.get("queue_wait_ms"),
            },
            duration_ms=int(metadata.get("duration_ms") or 0),
            device=str(metadata.get("device") or ""),
        )
        output_assets = _register_output_assets(repository, context, result.output_paths, "sound_effect", "audio/wav")
        _mark_success(repository, context, job_id, result, {**result.result, "output_assets": output_assets})
    except Exception as exc:  # noqa: BLE001
        _mark_failed(repository, context, job_id, str(exc))


def run_sequence_clean_job(repository: SQLiteGameKnifeRepository, context: RequestContext, job_id: str, sequence_id: str) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    sequence = repository.get_sequence_for_workspace(sequence_id, context.workspace.id)
    if job is None:
        return
    if sequence is None:
        _mark_failed(repository, context, job_id, "序列帧不存在。")
        return

    frames = repository.list_sequence_frames(sequence_id, context.workspace.id, enabled_only=True)
    if not frames:
        _mark_failed(repository, context, job_id, "序列帧没有可用帧。")
        return

    repository.update_job(job_id, context.workspace.id, status="running", updated_at=_now())
    repository.update_sequence(sequence_id, context.workspace.id, status="cleaning", updated_at=_now())
    old_processed_ids = repository.list_sequence_processed_asset_ids(sequence_id, context.workspace.id)
    old_records = repository.list_assets_by_ids_for_workspace(old_processed_ids, context.workspace.id)
    try:
        parameters = {**json.loads(sequence["clean_parameters_json"]), **json.loads(job.parameters_json)}
        result, outputs = sequence_processor.clean_frames(
            _sequence_mapping(sequence),
            _frame_mappings(context, frames),
            context.storage.root / "outputs" / job_id / "sequence_frames",
            parameters,
        )
        for output in outputs:
            output_assets = _register_output_assets(repository, context, [output.output_path], "sequence_frame_processed", "image/png")
            repository.update_sequence_frame_processed_asset(output.frame_id, sequence_id, output_assets[0]["id"], updated_at=_now())

        repository.delete_assets_for_workspace([asset.id for asset in old_records], context.workspace.id)
        for asset in old_records:
            context.storage.remove_asset_file(asset.path)

        canvas_size = result.result.get("canvas_size", [sequence["canvas_width"], sequence["canvas_height"]])
        repository.update_sequence(
            sequence_id,
            context.workspace.id,
            canvas_width=int(canvas_size[0]),
            canvas_height=int(canvas_size[1]),
            clean_parameters=parameters,
            status="ready",
            updated_at=_now(),
        )
        _mark_success(repository, context, job_id, result, {**result.result, "output_assets": []})
    except Exception as exc:  # noqa: BLE001
        repository.update_sequence(sequence_id, context.workspace.id, status="ready", updated_at=_now())
        _mark_failed(repository, context, job_id, str(exc))


def run_sequence_export_frames_job(repository: SQLiteGameKnifeRepository, context: RequestContext, job_id: str, sequence_id: str) -> None:
    _run_sequence_export_job(
        repository,
        context,
        job_id,
        sequence_id,
        output_suffix="_frames.zip",
        output_kind="sequence_export",
        processor=lambda sequence, frames, output_path, parameters: sequence_processor.export_frames_zip(sequence, frames, output_path, parameters),
    )


def run_sequence_export_spine_job(repository: SQLiteGameKnifeRepository, context: RequestContext, job_id: str, sequence_id: str) -> None:
    _run_sequence_export_job(
        repository,
        context,
        job_id,
        sequence_id,
        output_suffix="_spine.zip",
        output_kind="sequence_spine",
        processor=lambda sequence, frames, output_path, parameters: sequence_processor.export_spine_zip(sequence, frames, output_path, parameters),
    )


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


def _run_sequence_export_job(
    repository: SQLiteGameKnifeRepository,
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
        _mark_failed(repository, context, job_id, "序列帧不存在。")
        return
    frames = repository.list_sequence_frames(sequence_id, context.workspace.id, enabled_only=True)
    if not frames:
        _mark_failed(repository, context, job_id, "序列帧没有可导出的帧。")
        return

    repository.update_job(job_id, context.workspace.id, status="running", updated_at=_now())
    try:
        output_path = _output_path(context, job_id, f"{_safe_name(str(sequence['name']))}{output_suffix}")
        result = processor(
            _sequence_mapping(sequence),
            _frame_mappings(context, frames),
            output_path,
            json.loads(job.parameters_json),
        )
        output_assets = _register_output_assets(repository, context, result.output_paths, output_kind, "application/zip")
        _mark_success(repository, context, job_id, result, {**result.result, "output_assets": output_assets})
    except Exception as exc:  # noqa: BLE001
        _mark_failed(repository, context, job_id, str(exc))


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


def _now() -> str:
    return datetime.now(UTC).isoformat()
