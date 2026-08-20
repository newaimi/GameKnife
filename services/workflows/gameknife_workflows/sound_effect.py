from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol
from uuid import uuid4

from gameknife_core import AssetRecord, ProcessResult, RequestContext
from gameknife_jobs import AssetWriteInProgressError, JobSubmissionResult, TaskSubmission

from .errors import WorkflowModelNotInstalledError, WorkflowServiceUnavailableError, WorkflowValidationError
from .asset_persistence import persist_asset_file
from .job_helpers import (
    WorkflowRepository,
    claim_job,
    cleanup_registered_output_assets,
    create_job_record,
    download_object,
    mark_failed,
    mark_success,
    output_path,
    register_output_assets,
    temporary_job_directory,
)


class SoundEffectService(Protocol):
    def install_status(self) -> dict[str, Any]:
        ...

    def generate_sound_effect(self, prompt: str, output_path: Path, parameters: dict[str, Any]) -> dict[str, Any]:
        ...


def create_sound_effect_workflow(
    repository: WorkflowRepository,
    context: RequestContext,
    service: SoundEffectService,
    *,
    parameters: dict[str, Any],
    submission: TaskSubmission | None = None,
) -> tuple[JobSubmissionResult, Callable[[], None]]:
    prompt = str(parameters.get("prompt") or "").strip()
    if not prompt:
        raise WorkflowValidationError("请输入声效提示词。")

    install_status = service.install_status()
    if install_status.get("status") in {"unconfigured", "unavailable"}:
        raise WorkflowServiceUnavailableError(str(install_status.get("message") or "Stable Audio 声效服务不可用。"))
    if not install_status.get("installed"):
        raise WorkflowModelNotInstalledError("Stable Audio Open 模型尚未安装，请先到设置页下载安装模型文件。")

    try:
        prompt_asset, prompt_asset_created = _get_or_create_prompt_asset(
            repository,
            context,
            prompt,
            submission,
        )
    except AssetWriteInProgressError as exc:
        raise WorkflowServiceUnavailableError("相同声效任务正在提交，请稍后重试。") from exc
    try:
        submitted = create_job_record(
            repository,
            context,
            job_type="sound_effect_generate",
            input_asset_id=prompt_asset.id,
            parameters={**parameters, "prompt": prompt},
            submission=submission,
        )
    except AssetWriteInProgressError as exc:
        raise WorkflowServiceUnavailableError("相同声效任务正在提交，请稍后重试。") from exc
    except Exception:
        # Persisting the prompt as an asset gives job history a stable input. If subsequent job creation fails,
        # remove both the file and record so credit or permission rejection cannot leave an unreachable temporary asset.
        if prompt_asset_created:
            _delete_prompt_asset_best_effort(repository, context, prompt_asset)
        raise

    if submitted.replayed and prompt_asset_created and submitted.job.input_asset_id != prompt_asset.id:
        # A repository owns the final idempotency comparison. If it resolves this request to an earlier Job whose
        # input differs, the prompt created for the rejected candidate is not referenced and must not leak.
        _delete_prompt_asset_best_effort(repository, context, prompt_asset)

    def run() -> None:
        run_sound_effect_workflow(repository, context, service, submitted.job.id)

    return submitted, run


def run_sound_effect_workflow(
    repository: WorkflowRepository,
    context: RequestContext,
    service: SoundEffectService,
    job_id: str,
) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    if not claim_job(repository, context, job.id):
        return
    prompt_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if prompt_asset is None:
        mark_failed(repository, context, job_id, "声效提示词不存在。")
        return

    output_assets: list[dict[str, str]] = []
    try:
        with temporary_job_directory(job.id) as working_directory:
            prompt_path = download_object(
                context,
                prompt_asset.path,
                working_directory / "inputs" / "sound_prompt.txt",
            )
            prompt = prompt_path.read_text(encoding="utf-8").strip()
            if not prompt:
                raise RuntimeError("声效提示词不能为空。")
            parameters = json.loads(job.parameters_json)
            target_path = output_path(working_directory, "sound_effect.wav")
            metadata = service.generate_sound_effect(prompt, target_path, parameters)
            result = ProcessResult(
                output_paths=[target_path],
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
            output_assets = register_output_assets(repository, context, job.id, result.output_paths, "sound_effect", "audio/wav")
        mark_success(repository, context, job_id, result, {**result.result, "output_assets": output_assets})
    except Exception as exc:  # noqa: BLE001
        cleanup_registered_output_assets(repository, context, job_id, output_assets)
        mark_failed(repository, context, job_id, str(exc))


def _get_or_create_prompt_asset(
    repository: WorkflowRepository,
    context: RequestContext,
    prompt: str,
    submission: TaskSubmission | None,
) -> tuple[AssetRecord, bool]:
    # Sound-effect jobs use the shared input_asset_id relationship required by job history, cleanup, and repository implementations.
    # Saving the prompt as a text asset keeps the original input available to audit and retry flows.
    asset_id = _prompt_asset_id(context, prompt, submission)
    deterministic_id = submission is not None and submission.idempotency_key is not None
    if deterministic_id:
        existing = repository.get_asset_for_workspace(asset_id, context.workspace.id)
        if existing is not None:
            return existing, False

    content = prompt.encode("utf-8")
    now = _now()
    try:
        with TemporaryDirectory(prefix="gameknife-prompt-") as directory:
            source_path = Path(directory) / "sound_prompt.txt"
            source_path.write_bytes(content)
            asset = persist_asset_file(
                repository,
                context.storage,
                AssetRecord(
                    id=asset_id,
                    workspace_id=context.workspace.id,
                    created_by=context.principal.id,
                    kind="sound_prompt",
                    original_name="sound_prompt.txt",
                    path="",
                    mime_type="text/plain",
                    size_bytes=len(content),
                    created_at=now,
                    updated_at=now,
                ),
                source_path,
            )
    except Exception:
        # Concurrent retries with the same key produce the same prompt content and Asset ID. Reuse the ready row
        # that won the race; the persistence helper has already settled this attempt's pending state and object.
        if deterministic_id:
            existing = repository.get_asset_for_workspace(asset_id, context.workspace.id)
            if existing is not None:
                return existing, False
        raise
    return asset, True


def _prompt_asset_id(context: RequestContext, prompt: str, submission: TaskSubmission | None) -> str:
    if submission is None or submission.idempotency_key is None:
        return uuid4().hex
    # Stable prompt inputs keep a Commercial request digest identical across retries. Including the prompt separates
    # a reused key with changed input, allowing the repository to report an idempotency conflict without overwriting
    # the object referenced by the original Job.
    digest = sha256(
        "\0".join(
            (
                context.workspace.id,
                context.principal.id,
                submission.idempotency_key,
                prompt,
            )
        ).encode("utf-8")
    ).hexdigest()
    return digest


def _delete_prompt_asset_best_effort(
    repository: WorkflowRepository,
    context: RequestContext,
    prompt_asset: AssetRecord,
) -> None:
    try:
        repository.delete_assets_for_workspace([prompt_asset.id], context.workspace.id)
    except Exception:  # noqa: BLE001
        return
    try:
        context.storage.delete_object(prompt_asset.path)
    except Exception:  # noqa: BLE001
        pass


def _now() -> str:
    return datetime.now(UTC).isoformat()
