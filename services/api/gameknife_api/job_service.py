from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from gameknife_core import AssetRecord, JobRecord, ProcessResult, RequestContext
from gameknife_jobs import GameKnifeRepository
from gameknife_processors import BackgroundRemoveProcessor, SequenceFrameProcessor
from gameknife_api.birefnet import BiRefNetService
from gameknife_api.video_generation import VideoGenerationClient

sequence_processor = SequenceFrameProcessor()
background_processor = BackgroundRemoveProcessor()
DEFAULT_SEQUENCE_CLEAN_PARAMETERS = {
    "alpha_threshold": 24,
    "alpha_smoothing": 0,
    "trim_padding": 6,
    "background_tolerance": 18,
    "anchor_mode": "bottom_center",
    "color_match": True,
    "stabilize": False,
    "stabilize_strength": 35,
}


def create_job(
    repository: GameKnifeRepository,
    context: RequestContext,
    *,
    job_type: str,
    input_asset_id: str,
    parameters: dict[str, Any],
) -> JobRecord:
    # Job creation is the shared entry point for long-running workflows, so permission checks establish one boundary for every caller.
    # RequestContext supplies the permission rules, keeping account and role data out of public workflows.
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


def run_background_remove_job(repository: GameKnifeRepository, context: RequestContext, service: BiRefNetService, job_id: str) -> None:
    _run_image_output_job(
        repository,
        context,
        job_id,
        output_kind="background_remove",
        output_mime_type="image/png",
        output_suffix="_cutout.png",
        processor=lambda input_path, output_path, parameters: background_processor.process(input_path, output_path, parameters, service),
    )


def run_sequence_clean_job(repository: GameKnifeRepository, context: RequestContext, job_id: str, sequence_id: str) -> None:
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


def run_sequence_from_video_job(repository: GameKnifeRepository, context: RequestContext, service: BiRefNetService, job_id: str) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    video_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if video_asset is None:
        _mark_failed(repository, context, job_id, "视频素材不存在。")
        return

    repository.update_job(job_id, context.workspace.id, status="running", updated_at=_now())
    frame_asset_ids: list[str] = []
    sequence_id: str | None = None
    try:
        parameters = json.loads(job.parameters_json)
        raw_result, outputs = sequence_processor.extract_video_frames(
            context.storage.resolve_asset_path(video_asset.path),
            context.storage.root / "outputs" / job_id / "video_frames",
            parameters,
            service,
        )
        frame_payloads: list[dict[str, Any]] = []
        for output in outputs:
            asset = _register_output_assets(repository, context, [output.output_path], "sequence_frame", "image/png")[0]
            frame_asset_ids.append(asset["id"])
            frame_payloads.append(
                {
                    "source_asset_id": asset["id"],
                    "original_name": output.original_name,
                    "width": output.width,
                    "height": output.height,
                    "bbox": output.bbox,
                    "duration_ms": output.duration_ms,
                    "enabled": True,
                    "is_generated": True,
                }
            )
        clean_parameters = _video_sequence_clean_parameters(parameters)
        sequence = repository.create_sequence_with_frames(
            workspace_id=context.workspace.id,
            created_by=context.principal.id,
            name=_video_sequence_name(video_asset.original_name, parameters),
            fps=int(raw_result.result["fps"]),
            loop=bool(parameters.get("loop", True)),
            clean_parameters=clean_parameters,
            frames=frame_payloads,
            created_at=_now(),
        )
        sequence_id = sequence["id"]
        frames = repository.list_sequence_frames(sequence_id, context.workspace.id)
        clean_result, processed_outputs = sequence_processor.clean_frames(
            _sequence_mapping(sequence),
            _frame_mappings(context, frames),
            context.storage.root / "outputs" / job_id / "sequence_frames",
            clean_parameters,
        )
        for output in processed_outputs:
            output_assets = _register_output_assets(repository, context, [output.output_path], "sequence_frame_processed", "image/png")
            frame_asset_ids.append(output_assets[0]["id"])
            repository.update_sequence_frame_processed_asset(output.frame_id, sequence_id, output_assets[0]["id"], updated_at=_now())

        canvas_size = clean_result.result.get("canvas_size", [sequence["canvas_width"], sequence["canvas_height"]])
        repository.update_sequence(
            sequence_id,
            context.workspace.id,
            canvas_width=int(canvas_size[0]),
            canvas_height=int(canvas_size[1]),
            clean_parameters=clean_parameters,
            status="ready",
            updated_at=_now(),
        )
        combined_result = ProcessResult(
            output_paths=[],
            result={
                **clean_result.result,
                "source_fps": raw_result.result.get("source_fps"),
            },
            duration_ms=raw_result.duration_ms + clean_result.duration_ms,
            device=raw_result.device,
        )
        final_result = {
            **combined_result.result,
            "sequence_id": sequence_id,
            "video_asset_id": video_asset.id,
            "frame_count": len(frame_payloads),
            "fps": int(raw_result.result["fps"]),
            "clip_start_seconds": float(parameters.get("start_second") or 0),
            "duration_seconds": parameters.get("duration_seconds"),
        }
        _mark_success(repository, context, job_id, combined_result, final_result)
    except Exception as exc:  # noqa: BLE001
        if sequence_id:
            frame_asset_ids.extend(repository.collect_sequence_asset_ids(sequence_id, context.workspace.id))
            repository.delete_sequence_for_workspace(sequence_id, context.workspace.id)
        frame_assets = repository.list_assets_by_ids_for_workspace(list(dict.fromkeys(frame_asset_ids)), context.workspace.id)
        repository.delete_assets_for_workspace([asset.id for asset in frame_assets], context.workspace.id)
        for asset in frame_assets:
            context.storage.remove_asset_file(asset.path)
        _mark_failed(repository, context, job_id, str(exc))


def run_sequence_generate_video_job(repository: GameKnifeRepository, context: RequestContext, job_id: str) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    input_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if input_asset is None:
        _mark_failed(repository, context, job_id, "输入素材不存在。")
        return

    repository.update_job(job_id, context.workspace.id, status="running", updated_at=_now())
    try:
        started = datetime.now(UTC)
        parameters = json.loads(job.parameters_json)
        output_path = _output_path(context, job.id, f"{Path(input_asset.original_name).stem}_generated.mp4")
        generated = VideoGenerationClient(repository).generate_video(
            context.storage.resolve_asset_path(input_asset.path),
            output_path,
            parameters,
        )
        result = ProcessResult(
            output_paths=[generated.output_path],
            result={
                "external_task_id": generated.external_task_id,
                "provider": generated.provider,
                "remote_video_url": generated.video_url,
            },
            duration_ms=round((datetime.now(UTC) - started).total_seconds() * 1000),
            device="外部API",
        )
        output_assets = _register_output_assets(repository, context, result.output_paths, "sequence_video", "video/mp4")
        video_asset = output_assets[0]
        final_result = {
            **result.result,
            "video_asset_id": video_asset["id"],
            "video_url": video_asset["url"],
            "output_assets": output_assets,
        }
        _mark_success(repository, context, job_id, result, final_result)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(repository, context, job_id, str(exc))


def delete_job(repository: GameKnifeRepository, context: RequestContext, job_id: str) -> bool:
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
    repository: GameKnifeRepository,
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
        if output_kind == "asset_cutout" and output_assets:
            final_result["cutout_asset_id"] = output_assets[0]["id"]
            final_result["cutout_url"] = output_assets[0]["url"]
        _mark_success(repository, context, job_id, result, final_result)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(repository, context, job_id, str(exc))


def _register_output_assets(
    repository: GameKnifeRepository,
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
    repository: GameKnifeRepository,
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


def _mark_failed(repository: GameKnifeRepository, context: RequestContext, job_id: str, error_message: str) -> None:
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


def _video_sequence_clean_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    output_size = max(64, int(parameters.get("output_size", 256)))
    return {
        **DEFAULT_SEQUENCE_CLEAN_PARAMETERS,
        "alpha_threshold": int(parameters.get("alpha_threshold", 24)),
        "alpha_smoothing": int(parameters.get("alpha_smoothing", 0)),
        "trim_padding": int(parameters.get("trim_padding", 6)),
        "canvas_padding": int(parameters.get("canvas_padding", 8)),
        "canvas_width": output_size,
        "canvas_height": output_size,
        "denoise": True,
        "color_match": True,
        "stabilize": bool(parameters.get("stabilize", True)),
        "stabilize_strength": int(parameters.get("stabilize_strength", 50)),
        "fit_canvas_size": True,
    }


def _video_sequence_name(original_name: str, parameters: dict[str, Any]) -> str:
    configured_name = str(parameters.get("name") or "").strip()
    if configured_name:
        return configured_name
    action = str(parameters.get("action") or "idle").strip() or "idle"
    return f"{Path(original_name).stem}_{action}".strip("_")


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
