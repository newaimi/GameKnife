from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from gameknife_core import AssetRecord, JobRecord, ProcessResult, RequestContext

from .errors import WorkflowModelNotInstalledError, WorkflowServiceUnavailableError, WorkflowValidationError
from .job_helpers import WorkflowRepository, create_job_record, mark_failed, mark_success, output_path, register_output_assets


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
) -> tuple[JobRecord, Callable[[], None]]:
    prompt = str(parameters.get("prompt") or "").strip()
    if not prompt:
        raise WorkflowValidationError("请输入声效提示词。")

    install_status = service.install_status()
    if install_status.get("status") in {"unconfigured", "unavailable"}:
        raise WorkflowServiceUnavailableError(str(install_status.get("message") or "Stable Audio 声效服务不可用。"))
    if not install_status.get("installed"):
        raise WorkflowModelNotInstalledError("Stable Audio Open 模型尚未安装，请先到设置页下载安装模型文件。")

    prompt_asset = _create_prompt_asset(repository, context, prompt)
    job = create_job_record(
        repository,
        context,
        job_type="sound_effect_generate",
        input_asset_id=prompt_asset.id,
        parameters={**parameters, "prompt": prompt},
    )

    def run() -> None:
        run_sound_effect_workflow(repository, context, service, job.id)

    return job, run


def run_sound_effect_workflow(
    repository: WorkflowRepository,
    context: RequestContext,
    service: SoundEffectService,
    job_id: str,
) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    prompt_asset = repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
    if prompt_asset is None:
        mark_failed(repository, context, job_id, "声效提示词不存在。")
        return

    repository.update_job(job_id, context.workspace.id, status="running", updated_at=_now())
    try:
        prompt_path = context.storage.resolve_asset_path(prompt_asset.path)
        prompt = prompt_path.read_text(encoding="utf-8").strip()
        if not prompt:
            raise RuntimeError("声效提示词不能为空。")
        parameters = json.loads(job.parameters_json)
        target_path = output_path(context, job.id, "sound_effect.wav")
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
        output_assets = register_output_assets(repository, context, result.output_paths, "sound_effect", "audio/wav")
        mark_success(repository, context, job_id, result, {**result.result, "output_assets": output_assets})
    except Exception as exc:  # noqa: BLE001
        mark_failed(repository, context, job_id, str(exc))


def _create_prompt_asset(repository: WorkflowRepository, context: RequestContext, prompt: str) -> AssetRecord:
    # 声效任务也走统一的 input_asset_id，原因是任务历史、删除清理和商用 repository 注入都依赖同一套资产关系。
    # 提示词保存为文本 asset 后，后续审计和失败重试能从资产链路找到原始输入。
    asset_id = uuid4().hex
    content = prompt.encode("utf-8")
    now = _now()
    relative_path = context.storage.write_asset(asset_id, "sound_prompt.txt", content)
    asset = AssetRecord(
        id=asset_id,
        workspace_id=context.workspace.id,
        created_by=context.principal.id,
        kind="sound_prompt",
        original_name="sound_prompt.txt",
        path=relative_path,
        mime_type="text/plain",
        size_bytes=len(content),
        created_at=now,
        updated_at=now,
    )
    try:
        repository.create_asset(asset)
    except Exception:
        context.storage.remove_asset_file(relative_path)
        raise
    return asset


def _now() -> str:
    return datetime.now(UTC).isoformat()
