from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from gameknife_core import AssetRecord, JobOutputAssetRecord, JobRecord, ProcessResult, RequestContext
from gameknife_jobs import GameKnifeRepository, JobSubmissionResult, TaskSubmission
from gameknife_processors import SequenceFrameProcessor
from gameknife_api.birefnet import BiRefNetService
from gameknife_api.video_generation import VideoGenerationClient

sequence_processor = SequenceFrameProcessor()
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
    submission: TaskSubmission | None = None,
) -> JobSubmissionResult:
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
    submitted = repository.create_job(job, submission)
    stored = repository.get_job_for_workspace(submitted.job.id, context.workspace.id)
    if stored is None:
        raise RuntimeError("任务创建失败。")
    return JobSubmissionResult(job=stored, replayed=submitted.replayed)


def run_sequence_clean_job(repository: GameKnifeRepository, context: RequestContext, job_id: str, sequence_id: str) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    if not _claim_job(repository, context, job.id):
        return
    sequence = repository.get_sequence_for_workspace(sequence_id, context.workspace.id)
    if sequence is None:
        _mark_failed(repository, context, job_id, "序列帧不存在。")
        return

    try:
        original_clean_parameters = json.loads(sequence["clean_parameters_json"])
        job_parameters = json.loads(job.parameters_json)
        expected_revision = job_parameters["sequence_revision"]
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise ValueError("序列帧版本无效。")
        delivery_keys = {"sequence_id", "sequence_revision", "frame_count", "canvas_width", "canvas_height"}
        clean_parameters = {
            **original_clean_parameters,
            **{key: value for key, value in job_parameters.items() if key not in delivery_keys},
        }
        processor_parameters = dict(clean_parameters)
        if bool(processor_parameters.get("fit_canvas_size", False)):
            # Capacity snapshots may be needed during this execution, but they are not user clean settings and must
            # not leak back into clean_parameters_json.
            processor_parameters.setdefault("canvas_width", int(job_parameters["canvas_width"]))
            processor_parameters.setdefault("canvas_height", int(job_parameters["canvas_height"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        _mark_failed(repository, context, job_id, str(exc))
        return

    claimed_revision = repository.claim_sequence_for_job(
        sequence_id,
        context.workspace.id,
        job.id,
        expected_revision,
        updated_at=_now(),
    )
    if claimed_revision is None:
        _mark_failed(repository, context, job_id, "序列帧已被其他任务修改或正在处理。")
        return

    old_records: list[AssetRecord] = []
    try:
        # Every read after the Sequence claim belongs to the same failure path. If persistence becomes unavailable,
        # the atomic failure finalizer releases the claim instead of leaving a failed Job with a locked Sequence.
        frames = repository.list_sequence_frames(sequence_id, context.workspace.id, enabled_only=True)
        if not frames:
            raise ValueError("序列帧没有可用帧。")
        old_processed_ids = repository.list_sequence_processed_asset_ids(sequence_id, context.workspace.id)
        old_records = repository.list_assets_by_ids_for_workspace(old_processed_ids, context.workspace.id)
        processed_assets_by_frame: dict[str, str] = {}
        with TemporaryDirectory(prefix=f"gameknife-{job.id}-") as directory:
            working_directory = Path(directory)
            result, outputs = sequence_processor.clean_frames(
                _sequence_mapping(sequence),
                _frame_mappings(context, frames, working_directory),
                working_directory / "outputs" / "sequence_frames",
                processor_parameters,
            )
            for output in outputs:
                output_assets = _register_output_assets(
                    repository,
                    context,
                    job.id,
                    [output.output_path],
                    "sequence_frame_processed",
                    "image/png",
                )
                processed_assets_by_frame[output.frame_id] = output_assets[0]["id"]

        canvas_size = result.result.get("canvas_size", [sequence["canvas_width"], sequence["canvas_height"]])
        completed_revision = claimed_revision + 1
        final_result = {
            **result.result,
            "sequence_id": sequence_id,
            "sequence_revision": completed_revision,
            "output_assets": [],
        }
        repository.finalize_sequence_clean_job(
            sequence_id,
            context.workspace.id,
            job.id,
            claimed_revision,
            processed_assets_by_frame=processed_assets_by_frame,
            canvas_width=int(canvas_size[0]),
            canvas_height=int(canvas_size[1]),
            clean_parameters=clean_parameters,
            result_json=json.dumps(final_result, ensure_ascii=False),
            device=result.device,
            duration_ms=result.duration_ms,
            updated_at=_now(),
        )
    except Exception as exc:  # noqa: BLE001
        try:
            cleanup_assets = repository.fail_sequence_clean_job(
                sequence_id,
                context.workspace.id,
                job.id,
                claimed_revision,
                error_message=str(exc),
                updated_at=_now(),
            )
            _delete_asset_objects_best_effort(context, cleanup_assets)
        except Exception:  # noqa: BLE001
            # Repository recovery on the next Community startup remains the final fallback if local persistence is
            # unavailable while the runner is already handling a processor or storage failure.
            return
    else:
        # The sequence and Job are already terminally successful. Old, now-unreferenced processed assets are only
        # cleanup candidates, so storage or database cleanup failures must not roll back the delivered sequence.
        _cleanup_unreferenced_assets_best_effort(repository, context, old_records)


def run_sequence_from_video_job(repository: GameKnifeRepository, context: RequestContext, service: BiRefNetService, job_id: str) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    if not _claim_job(repository, context, job.id):
        return
    video_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if video_asset is None:
        _mark_failed(repository, context, job_id, "视频素材不存在。")
        return

    sequence_id: str | None = None
    try:
        with TemporaryDirectory(prefix=f"gameknife-{job.id}-") as directory:
            working_directory = Path(directory)
            parameters = json.loads(job.parameters_json)
            video_path = _download_object(
                context,
                video_asset.path,
                working_directory / "inputs" / (Path(video_asset.original_name).name or "input-video.bin"),
            )
            raw_result, outputs = sequence_processor.extract_video_frames(
                video_path,
                working_directory / "outputs" / "video_frames",
                parameters,
                service,
            )
            frame_payloads: list[dict[str, Any]] = []
            for output in outputs:
                asset = _register_output_assets(
                    repository,
                    context,
                    job.id,
                    [output.output_path],
                    "sequence_frame",
                    "image/png",
                )[0]
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
            sequence = repository.create_sequence_with_frames_for_job(
                workspace_id=context.workspace.id,
                created_by=context.principal.id,
                job_id=job.id,
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
                _frame_mappings(context, frames, working_directory),
                working_directory / "outputs" / "sequence_frames",
                clean_parameters,
            )
            processed_assets_by_frame: dict[str, str] = {}
            for output in processed_outputs:
                output_assets = _register_output_assets(
                    repository,
                    context,
                    job.id,
                    [output.output_path],
                    "sequence_frame_processed",
                    "image/png",
                )
                processed_assets_by_frame[output.frame_id] = output_assets[0]["id"]

        canvas_size = clean_result.result.get("canvas_size", [sequence["canvas_width"], sequence["canvas_height"]])
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
        repository.finalize_sequence_from_video_job(
            sequence_id,
            context.workspace.id,
            job.id,
            processed_assets_by_frame=processed_assets_by_frame,
            canvas_width=int(canvas_size[0]),
            canvas_height=int(canvas_size[1]),
            clean_parameters=clean_parameters,
            result_json=json.dumps(final_result, ensure_ascii=False),
            device=combined_result.device,
            duration_ms=combined_result.duration_ms,
            updated_at=_now(),
        )
    except Exception as exc:  # noqa: BLE001
        try:
            cleanup_assets = repository.fail_sequence_from_video_job(
                context.workspace.id,
                job.id,
                sequence_id=sequence_id,
                error_message=str(exc),
                updated_at=_now(),
            )
            _delete_asset_objects_best_effort(context, cleanup_assets)
        except Exception:  # noqa: BLE001
            return


def run_sequence_generate_video_job(repository: GameKnifeRepository, context: RequestContext, job_id: str) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    if not _claim_job(repository, context, job.id):
        return
    input_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if input_asset is None:
        _mark_failed(repository, context, job_id, "输入素材不存在。")
        return

    output_assets: list[dict[str, str]] = []
    try:
        with TemporaryDirectory(prefix=f"gameknife-{job.id}-") as directory:
            working_directory = Path(directory)
            started = datetime.now(UTC)
            parameters = json.loads(job.parameters_json)
            input_path = _download_object(
                context,
                input_asset.path,
                working_directory / "inputs" / (Path(input_asset.original_name).name or "input.bin"),
            )
            output_path = _output_path(working_directory, f"{Path(input_asset.original_name).stem}_generated.mp4")
            generated = VideoGenerationClient(repository).generate_video(
                input_path,
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
            output_assets = _register_output_assets(
                repository,
                context,
                job.id,
                result.output_paths,
                "sequence_video",
                "video/mp4",
            )
            video_asset = output_assets[0]
            final_result = {
                **result.result,
                "video_asset_id": video_asset["id"],
                "video_url": video_asset["url"],
                "output_assets": output_assets,
            }
        _mark_success(repository, context, job_id, result, final_result)
    except Exception as exc:  # noqa: BLE001
        _cleanup_registered_output_assets(repository, context, job.id, output_assets)
        _mark_failed(repository, context, job_id, str(exc))


def delete_job(repository: GameKnifeRepository, context: RequestContext, job_id: str) -> bool:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return False
    if job.status in {"pending", "running"}:
        raise ValueError("任务正在处理中，完成后再删除。")

    # job_output_assets is the ownership boundary. Result payloads may also contain input or source Asset IDs and
    # must never decide what a Job deletion owns. The repository deletes Job rows and owned output Assets atomically.
    asset_records = repository.delete_job_for_workspace(job_id, context.workspace.id)
    for asset in asset_records:
        try:
            context.storage.delete_object(asset.path)
        except Exception:  # noqa: BLE001
            # Database deletion is authoritative. Remote providers may defer failed object cleanup to maintenance.
            continue
    return True


def _register_output_assets(
    repository: GameKnifeRepository,
    context: RequestContext,
    job_id: str,
    paths: list[Path],
    kind: str,
    mime_type: str,
    *,
    record_job_output: bool = True,
) -> list[dict[str, str]]:
    output_assets: list[dict[str, str]] = []
    stored_assets: list[AssetRecord] = []
    try:
        for path in paths:
            asset_id = uuid4().hex
            now = _now()
            stored = context.storage.put_file(asset_id, path.name, path)
            asset = AssetRecord(
                id=asset_id,
                workspace_id=context.workspace.id,
                created_by=context.principal.id,
                kind=kind,
                original_name=path.name,
                path=stored.key,
                mime_type=mime_type,
                size_bytes=stored.size_bytes,
                created_at=now,
                updated_at=now,
            )
            stored_assets.append(asset)
            repository.create_asset(asset)
            if record_job_output:
                repository.create_job_output_asset(
                    JobOutputAssetRecord(
                        id=uuid4().hex,
                        workspace_id=context.workspace.id,
                        created_by=context.principal.id,
                        job_id=job_id,
                        asset_id=asset.id,
                        created_at=now,
                    )
                )
            output_assets.append({"id": asset.id, "url": f"/api/assets/{asset.id}"})
    except Exception:
        _cleanup_assets_best_effort(repository, context, job_id, stored_assets)
        raise
    return output_assets


def _cleanup_registered_output_assets(
    repository: GameKnifeRepository,
    context: RequestContext,
    job_id: str,
    output_assets: list[dict[str, str]],
) -> None:
    asset_ids = [str(item["id"]) for item in output_assets if item.get("id")]
    _cleanup_asset_ids_best_effort(repository, context, job_id, asset_ids)


def _cleanup_asset_ids_best_effort(
    repository: GameKnifeRepository,
    context: RequestContext,
    job_id: str,
    asset_ids: list[str],
) -> None:
    if not asset_ids:
        return
    try:
        assets = repository.list_assets_by_ids_for_workspace(asset_ids, context.workspace.id)
    except Exception:  # noqa: BLE001
        return
    _cleanup_assets_best_effort(repository, context, job_id, assets)


def _cleanup_assets_best_effort(
    repository: GameKnifeRepository,
    context: RequestContext,
    job_id: str,
    assets: list[AssetRecord],
) -> None:
    asset_ids = [asset.id for asset in assets]
    if not asset_ids:
        return
    try:
        removed_assets = repository.cleanup_job_output_assets_for_workspace(
            job_id,
            context.workspace.id,
            asset_ids,
        )
    except Exception:  # noqa: BLE001
        # Relationship detachment and Asset deletion share one repository transaction. A failed transaction keeps
        # both ownership and the durable object intact so startup recovery can retry the same candidates.
        return
    for asset in removed_assets:
        try:
            context.storage.delete_object(asset.path)
        except Exception:  # noqa: BLE001
            # Object deletion remains best effort until Commercial supplies its durable delete outbox.
            continue


def _cleanup_unreferenced_assets_best_effort(
    repository: GameKnifeRepository,
    context: RequestContext,
    assets: list[AssetRecord],
) -> None:
    if not assets:
        return
    try:
        references = {
            summary.asset_id: summary
            for summary in repository.get_asset_reference_summaries(
                [asset.id for asset in assets],
                context.workspace.id,
            )
        }
        removable = [asset for asset in assets if not references.get(asset.id) or not references[asset.id].is_referenced]
        if not removable:
            return
        repository.delete_assets_for_workspace([asset.id for asset in removable], context.workspace.id)
    except Exception:  # noqa: BLE001
        # Cleanup runs after the terminal success boundary. Any database, reference, or local I/O failure leaves the
        # old Asset and object intact for a later maintenance pass and must not change the delivered Job state.
        return
    for asset in removable:
        try:
            context.storage.delete_object(asset.path)
        except Exception:  # noqa: BLE001
            # The Asset row is already gone, so object cleanup remains best effort until a durable delete outbox exists.
            continue


def _delete_asset_objects_best_effort(context: RequestContext, assets: list[AssetRecord]) -> None:
    for asset in assets:
        try:
            context.storage.delete_object(asset.path)
        except Exception:  # noqa: BLE001
            # Recovery and failure finalizers have already removed the database row. Local object deletion remains
            # best effort, matching the public deletion contract until Commercial supplies a durable delete outbox.
            continue


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


def _claim_job(repository: GameKnifeRepository, context: RequestContext, job_id: str) -> bool:
    return repository.claim_job_for_workspace(job_id, context.workspace.id, updated_at=_now())


def _mark_failed(repository: GameKnifeRepository, context: RequestContext, job_id: str, error_message: str) -> None:
    repository.update_job(
        job_id,
        context.workspace.id,
        status="failed",
        error_message=error_message,
        updated_at=_now(),
    )


def _download_object(context: RequestContext, key: str, destination: Path) -> Path:
    return context.storage.download_to(key, destination)


def _output_path(working_directory: Path, filename: str) -> Path:
    path = working_directory / "outputs" / Path(filename).name
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


def _frame_mappings(context: RequestContext, frames: list[Any], working_directory: Path) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for frame in frames:
        frame_directory = working_directory / "frames" / str(frame["id"])
        source_path = _download_object(
            context,
            frame["source_path"],
            frame_directory / f"source{Path(frame['source_path']).suffix or '.bin'}",
        )
        processed_path = (
            _download_object(
                context,
                frame["processed_path"],
                frame_directory / f"processed{Path(frame['processed_path']).suffix or '.bin'}",
            )
            if frame["processed_path"]
            else None
        )
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
