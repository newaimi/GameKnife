from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol
from uuid import uuid4

from gameknife_core import AssetRecord, JobOutputAssetRecord, JobRecord, ProcessResult, RequestContext
from gameknife_jobs import JobSubmissionResult, TaskSubmission


class WorkflowRepository(Protocol):
    def create_asset(self, asset: AssetRecord) -> None:
        ...

    def delete_assets_for_workspace(self, asset_ids: list[str], workspace_id: str) -> None:
        ...

    def get_asset_for_workspace(self, asset_id: str, workspace_id: str) -> AssetRecord | None:
        ...

    def list_assets_by_ids_for_workspace(self, asset_ids: list[str], workspace_id: str) -> list[AssetRecord]:
        ...

    def create_job(
        self,
        job: JobRecord,
        submission: TaskSubmission | None = None,
    ) -> JobSubmissionResult:
        ...

    def claim_job_for_workspace(
        self,
        job_id: str,
        workspace_id: str,
        *,
        updated_at: str,
    ) -> bool:
        ...

    def create_job_output_asset(self, output: JobOutputAssetRecord) -> None:
        ...

    def cleanup_job_output_assets_for_workspace(
        self,
        job_id: str,
        workspace_id: str,
        asset_ids: list[str],
    ) -> list[AssetRecord]:
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
    submission: TaskSubmission | None = None,
) -> JobSubmissionResult:
    # Job creation is a public workflow boundary, giving every entry point the same permission action and field semantics.
    # Callers inject permission behavior through RequestContext, so the workflow never reads account or role data.
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
    # A Commercial repository may return an earlier Job for an idempotent replay. Preserve that signal together
    # with the reloaded record so API routes can avoid dispatching the same accepted request twice.
    return JobSubmissionResult(job=stored, replayed=submitted.replayed)


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
    if not claim_job(repository, context, job.id):
        return
    input_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if input_asset is None:
        mark_failed(repository, context, job_id, "输入素材不存在。")
        return

    output_assets: list[dict[str, str]] = []
    try:
        with temporary_job_directory(job.id) as working_directory:
            input_path = download_object(
                context,
                input_asset.path,
                working_directory / "inputs" / _safe_filename(input_asset.original_name, "input.bin"),
            )
            output_name = f"{Path(input_asset.original_name).stem}{output_suffix}"
            result = processor(
                input_path,
                output_path(working_directory, output_name),
                json.loads(job.parameters_json),
            )
            output_assets = register_output_assets(repository, context, job.id, result.output_paths, output_kind, output_mime_type)
            final_result = {
                **result.result,
                "input_asset_url": f"/api/assets/{input_asset.id}",
                "output_assets": output_assets,
            }
            if output_kind == "asset_cutout" and output_assets:
                # Asset-board refresh and export flows use cutout_asset_id to address the extracted result directly.
                # Generic output_assets preserves the download list, while the dedicated field provides a stable workbench input.
                final_result["cutout_asset_id"] = output_assets[0]["id"]
                final_result["cutout_url"] = output_assets[0]["url"]
        # TemporaryDirectory cleanup is part of execution. A cleanup failure must fail the Job before its terminal
        # state is persisted, because a successful Job cannot subsequently transition to failed.
        mark_success(repository, context, job_id, result, final_result)
    except Exception as exc:  # noqa: BLE001
        cleanup_registered_output_assets(repository, context, job_id, output_assets)
        mark_failed(repository, context, job_id, str(exc))


def register_output_assets(
    repository: WorkflowRepository,
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
                # State-changing jobs may persist assets owned by their target entity. Other processors must record
                # the job-output relationship before success so delivery checks never depend on result JSON alone.
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
        # Output registration is all-or-nothing for one processor result. Remove any relationships before Assets
        # because the reference-safe schema deliberately restricts deleting a delivered object.
        _cleanup_assets_best_effort(repository, context, job_id, stored_assets)
        raise
    return output_assets


def cleanup_registered_output_assets(
    repository: WorkflowRepository,
    context: RequestContext,
    job_id: str,
    output_assets: list[dict[str, str]],
) -> None:
    asset_ids = [str(item["id"]) for item in output_assets if item.get("id")]
    if not asset_ids:
        return
    try:
        assets = repository.list_assets_by_ids_for_workspace(asset_ids, context.workspace.id)
    except Exception:  # noqa: BLE001
        return
    _cleanup_assets_best_effort(repository, context, job_id, assets)


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


def claim_job(repository: WorkflowRepository, context: RequestContext, job_id: str) -> bool:
    return repository.claim_job_for_workspace(job_id, context.workspace.id, updated_at=_now())


def mark_failed(repository: WorkflowRepository, context: RequestContext, job_id: str, error_message: str) -> None:
    repository.update_job(
        job_id,
        context.workspace.id,
        status="failed",
        error_message=error_message,
        updated_at=_now(),
    )


@contextmanager
def temporary_job_directory(job_id: str) -> Iterator[Path]:
    # Processors require local paths, while the durable provider may be remote. Each execution receives its own
    # staging directory so retries and concurrent jobs cannot observe or overwrite another attempt's files.
    with TemporaryDirectory(prefix=f"gameknife-{job_id}-") as directory:
        yield Path(directory)


def download_object(context: RequestContext, key: str, destination: Path) -> Path:
    return context.storage.download_to(key, destination)


def _cleanup_assets_best_effort(
    repository: WorkflowRepository,
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
        # both ownership and the durable object intact so a later recovery pass can identify the same candidates.
        return
    for asset in removed_assets:
        try:
            context.storage.delete_object(asset.path)
        except Exception:  # noqa: BLE001
            # Object deletion is best effort until the Commercial runtime supplies a durable delete outbox.
            continue


def output_path(working_directory: Path, filename: str) -> Path:
    path = working_directory / "outputs" / Path(filename).name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _safe_filename(value: str, fallback: str) -> str:
    filename = Path(value).name.strip()
    return filename or fallback


def _now() -> str:
    return datetime.now(UTC).isoformat()
