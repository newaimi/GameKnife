from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from gameknife_core import (
    AssetRecord,
    AssetRelationRecord,
    ProcessResult,
    RequestContext,
)
from gameknife_jobs import (
    JobParameterValidationError,
    JobSubmissionResult,
    TaskSubmission,
    canonical_project_export_parameters,
)

from .errors import WorkflowInputNotFoundError, WorkflowValidationError
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

EXPORT_PRESETS = frozenset({"generic", "unity", "godot"})
MAX_EXPORT_ASSETS = 100


class ProjectExportRepository(WorkflowRepository, Protocol):
    def create_asset_relation(self, relation: AssetRelationRecord) -> None:
        ...


def create_project_export_workflow(
    repository: ProjectExportRepository,
    context: RequestContext,
    *,
    asset_ids: list[str],
    preset: str,
    package_name: str,
    submission: TaskSubmission | None = None,
) -> tuple[JobSubmissionResult, Callable[[], None]]:
    assets, parameters = prepare_project_export_parameters(
        repository,
        context,
        asset_ids=asset_ids,
        preset=preset,
        package_name=package_name,
    )
    submitted = create_job_record(
        repository,
        context,
        job_type="project_export_package",
        input_asset_id=assets[0].id,
        parameters=parameters,
        submission=submission,
    )

    def run() -> None:
        run_project_export_workflow(repository, context, submitted.job.id)

    return submitted, run


def prepare_project_export_parameters(
    repository: ProjectExportRepository,
    context: RequestContext,
    *,
    asset_ids: list[str],
    preset: str,
    package_name: str,
) -> tuple[list[AssetRecord], dict[str, Any]]:
    unique_ids = list(dict.fromkeys(str(asset_id).strip() for asset_id in asset_ids if str(asset_id).strip()))
    if not unique_ids:
        raise WorkflowValidationError("请至少选择一个素材。")
    if len(unique_ids) > MAX_EXPORT_ASSETS:
        raise WorkflowValidationError(f"单次最多导出 {MAX_EXPORT_ASSETS} 个素材。")
    normalized_preset = preset.strip().lower()
    if normalized_preset not in EXPORT_PRESETS:
        raise WorkflowValidationError("不支持的导出预设。")

    stored = {
        asset.id: asset
        for asset in repository.list_assets_by_ids_for_workspace(unique_ids, context.workspace.id)
        if asset.storage_state == "ready"
    }
    missing = [asset_id for asset_id in unique_ids if asset_id not in stored]
    if missing:
        raise WorkflowInputNotFoundError("部分素材不存在或尚未就绪。")
    assets = [stored[asset_id] for asset_id in unique_ids]
    try:
        parameters = canonical_project_export_parameters(
            asset_ids=unique_ids,
            preset=normalized_preset,
            package_name=package_name,
            input_total_bytes=sum(asset.size_bytes for asset in assets),
        )
    except JobParameterValidationError as exc:
        raise WorkflowValidationError(str(exc)) from exc
    return assets, parameters


def run_project_export_workflow(
    repository: ProjectExportRepository,
    context: RequestContext,
    job_id: str,
) -> None:
    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None or not claim_job(repository, context, job.id):
        return

    output_assets: list[dict[str, str]] = []
    try:
        parameters = json.loads(job.parameters_json)
        assets, canonical = prepare_project_export_parameters(
            repository,
            context,
            asset_ids=list(parameters.get("asset_ids") or []),
            preset=str(parameters.get("preset") or "generic"),
            package_name=str(parameters.get("package_name") or "gameknife-export"),
        )
        if canonical != parameters:
            raise WorkflowValidationError("导出参数与当前素材不一致，请重新提交。")

        with temporary_job_directory(job.id) as working_directory:
            package_path = output_path(
                working_directory,
                f"{canonical['package_name']}-{canonical['preset']}.zip",
            )
            result = _build_export_package(context, assets, package_path, canonical["preset"], working_directory)
            output_assets = register_output_assets(
                repository,
                context,
                job.id,
                result.output_paths,
                "project_export",
                "application/zip",
            )
            export_asset_id = output_assets[0]["id"]
            for source in assets:
                repository.create_asset_relation(
                    AssetRelationRecord(
                        id=uuid4().hex,
                        workspace_id=context.workspace.id,
                        created_by=context.principal.id,
                        source_asset_id=source.id,
                        derived_asset_id=export_asset_id,
                        relation_type="export",
                        job_id=job.id,
                        created_at=job.updated_at,
                    )
                )
        mark_success(
            repository,
            context,
            job.id,
            result,
            {**result.result, "output_assets": output_assets},
        )
    except Exception as exc:  # noqa: BLE001
        cleanup_registered_output_assets(repository, context, job.id, output_assets)
        mark_failed(repository, context, job.id, str(exc))


def _build_export_package(
    context: RequestContext,
    assets: list[AssetRecord],
    target_path: Path,
    preset: str,
    working_directory: Path,
) -> ProcessResult:
    manifest_assets: list[dict[str, Any]] = []
    used_paths: set[str] = set()
    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, asset in enumerate(assets):
            staged = download_object(
                context,
                asset.path,
                working_directory / "inputs" / asset.id / _safe_filename(asset.original_name, f"asset-{index + 1}"),
            )
            archive_path = _unique_archive_path(
                _asset_archive_path(preset, asset),
                used_paths,
            )
            archive.write(staged, archive_path)
            manifest_assets.append(
                {
                    "id": asset.id,
                    "kind": asset.kind,
                    "filename": asset.original_name,
                    "mime_type": asset.mime_type,
                    "size_bytes": asset.size_bytes,
                    "checksum_sha256": asset.checksum_sha256,
                    "path": archive_path,
                }
            )

        manifest = {
            "schema_version": 1,
            "workspace_id": context.workspace.id,
            "workspace_name": context.workspace.name,
            "preset": preset,
            "created_at": datetime.now(UTC).isoformat(),
            "assets": manifest_assets,
        }
        archive.writestr("gameknife-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    return ProcessResult(
        output_paths=[target_path],
        result={
            "preset": preset,
            "source_asset_ids": [asset.id for asset in assets],
            "manifest": "gameknife-manifest.json",
        },
        duration_ms=0,
        device="CPU",
    )


def _asset_archive_path(preset: str, asset: AssetRecord) -> str:
    category = _asset_category(asset)
    filename = _safe_filename(asset.original_name, asset.id)
    if preset == "unity":
        return f"Assets/GameKnife/{category}/{filename}"
    if preset == "godot":
        return f"gameknife_assets/{category}/{filename}"
    return f"assets/{category}/{filename}"


def _asset_category(asset: AssetRecord) -> str:
    if asset.mime_type.startswith("image/"):
        return "images"
    if asset.mime_type.startswith("video/"):
        return "videos"
    if asset.mime_type.startswith("audio/"):
        return "audio"
    return "files"


def _unique_archive_path(candidate: str, used_paths: set[str]) -> str:
    path = Path(candidate)
    next_path = candidate
    suffix = 2
    while next_path in used_paths:
        next_path = str(path.with_name(f"{path.stem}-{suffix}{path.suffix}"))
        suffix += 1
    used_paths.add(next_path)
    return next_path


def _safe_filename(value: str, fallback: str) -> str:
    filename = Path(value).name.strip()
    if not filename:
        filename = fallback
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in filename)
