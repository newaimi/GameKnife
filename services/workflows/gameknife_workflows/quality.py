from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from gameknife_core import AssetQualityCheckRecord, AssetRecord, ProcessResult, RequestContext
from gameknife_jobs import canonical_asset_quality_check_parameters
from gameknife_processors import (
    AUDIO_QUALITY_RULES_VERSION,
    IMAGE_QUALITY_RULES_VERSION,
    MODEL_3D_QUALITY_RULES_VERSION,
    UI_COMPONENT_QUALITY_RULES_VERSION,
    AssetQualityResult,
    check_audio_asset,
    check_component_archive,
    check_generated_images,
    check_glb_asset,
    unavailable_quality_result,
)

from .job_helpers import (
    WorkflowRepository,
    claim_job,
    download_object,
    mark_failed,
    mark_success,
    temporary_job_directory,
)

ImageChecker = Callable[..., list[AssetQualityResult]]
ComponentChecker = Callable[[Path], AssetQualityResult]
AudioChecker = Callable[..., AssetQualityResult]
ModelChecker = Callable[..., AssetQualityResult]


def run_asset_quality_check_workflow(
    repository: WorkflowRepository,
    context: RequestContext,
    job_id: str,
    *,
    image_checker: ImageChecker = check_generated_images,
    component_checker: ComponentChecker = check_component_archive,
    audio_checker: AudioChecker = check_audio_asset,
    model_checker: ModelChecker = check_glb_asset,
) -> None:
    """Recheck one ready Asset against an immutable prior rule snapshot or safe defaults."""

    job = repository.get_job_for_workspace(job_id, context.workspace.id)
    if job is None:
        return
    if not claim_job(repository, context, job.id):
        return
    try:
        parameters = canonical_asset_quality_check_parameters(
            json.loads(job.parameters_json)
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        mark_failed(repository, context, job.id, "质量检查参数无效，请重新提交。")
        return
    asset = repository.get_asset_for_workspace(
        str(parameters["asset_id"]),
        context.workspace.id,
    )
    if (
        asset is None
        or asset.id != job.input_asset_id
        or asset.storage_state != "ready"
    ):
        mark_failed(repository, context, job.id, "素材不存在或尚未就绪，请重新选择素材。")
        return
    source_check_id = parameters.get("source_quality_check_id")
    source_check = None
    if source_check_id:
        source_check = repository.get_asset_quality_check_for_workspace(
            str(source_check_id),
            asset.id,
            context.workspace.id,
        )
        if source_check is None:
            mark_failed(repository, context, job.id, "质量规则快照不存在，请重新打开素材详情。")
            return
    try:
        rules_version, check_parameters = _quality_policy(asset, source_check)
    except ValueError as exc:
        mark_failed(repository, context, job.id, str(exc))
        return

    started = time.perf_counter()
    final_result: dict[str, Any] | None = None
    failure_message: str | None = None
    try:
        with temporary_job_directory(job.id) as working_directory:
            input_path = download_object(
                context,
                asset.path,
                working_directory / "inputs" / Path(asset.original_name).name,
            )
            try:
                quality = _execute_quality_check(
                    input_path,
                    rules_version=rules_version,
                    parameters=check_parameters,
                    image_checker=image_checker,
                    component_checker=component_checker,
                    audio_checker=audio_checker,
                    model_checker=model_checker,
                )
            except Exception:  # noqa: BLE001
                quality = unavailable_quality_result(
                    input_path,
                    rules_version=rules_version,
                    parameters=check_parameters,
                )
                failure_message = "自动质量检查暂时不可用，请稍后重试。"
            stored = persist_asset_quality_result(
                repository,
                context,
                asset,
                quality,
            )
            final_result = {
                "asset_id": asset.id,
                "quality_check_id": stored.id,
                "quality_status": stored.status,
                "rules_version": stored.rules_version,
                "content_sha256": stored.content_sha256,
            }
    except Exception:  # noqa: BLE001
        mark_failed(repository, context, job.id, "素材文件无法读取或保存检查结果，请重试。")
        return

    if failure_message is not None:
        mark_failed(repository, context, job.id, failure_message)
        return
    if final_result is None:
        mark_failed(repository, context, job.id, "自动质量检查没有生成结果，请重试。")
        return
    duration_ms = max(0, round((time.perf_counter() - started) * 1000))
    mark_success(
        repository,
        context,
        job.id,
        ProcessResult(duration_ms=duration_ms, device="cpu"),
        final_result,
    )


def _quality_policy(
    asset: AssetRecord,
    source_check: AssetQualityCheckRecord | None,
) -> tuple[str, dict[str, Any]]:
    if source_check is not None:
        try:
            payload = json.loads(source_check.checks_json)
            parameters = payload["parameters"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("质量规则快照无效，请联系管理员。") from exc
        if not isinstance(parameters, dict):
            raise ValueError("质量规则快照无效，请联系管理员。")
        return source_check.rules_version, _normalize_check_parameters(parameters)
    if asset.mime_type.startswith("image/"):
        return IMAGE_QUALITY_RULES_VERSION, {
            "check_type": "image",
            "expected_size": "ORIGINAL",
            "palette": [],
            "expect_no_text": False,
            "expect_transparency": False,
            "expect_seamless": False,
        }
    if asset.kind == "asset_component" and asset.mime_type == "application/zip":
        return UI_COMPONENT_QUALITY_RULES_VERSION, {"check_type": "ui_components"}
    if asset.mime_type in {"audio/wav", "audio/x-wav"}:
        return AUDIO_QUALITY_RULES_VERSION, {
            "check_type": "audio",
            "asset_type": "sound_effect" if asset.kind == "sound_effect" else "audio",
            "expected_duration_seconds": None,
            "expect_loop": False,
        }
    if asset.kind == "model_3d_glb" and asset.mime_type == "model/gltf-binary":
        return MODEL_3D_QUALITY_RULES_VERSION, {
            "check_type": "model_3d",
            "format": "glb",
            "max_triangles": None,
            "require_uv": True,
            "require_pbr": True,
            "gltf_validator": False,
        }
    raise ValueError("当前素材类型不支持自动质量检查。")


def _normalize_check_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    check_type = str(parameters.get("check_type") or "")
    if check_type == "ui_components":
        return {"check_type": "ui_components"}
    if check_type == "audio":
        raw_duration = parameters.get("expected_duration_seconds")
        if raw_duration is not None and (
            isinstance(raw_duration, bool)
            or not isinstance(raw_duration, (int, float))
            or not 0.1 <= float(raw_duration) <= 600
        ):
            raise ValueError("质量规则快照无效，请联系管理员。")
        asset_type = str(parameters.get("asset_type") or "audio")
        if asset_type not in {"audio", "sound_effect", "bgm", "voice"}:
            raise ValueError("质量规则快照无效，请联系管理员。")
        expect_loop = parameters.get("expect_loop", False)
        if not isinstance(expect_loop, bool):
            raise ValueError("质量规则快照无效，请联系管理员。")
        return {
            "check_type": "audio",
            "asset_type": asset_type,
            "expected_duration_seconds": (
                float(raw_duration) if raw_duration is not None else None
            ),
            "expect_loop": expect_loop,
        }
    if check_type == "model_3d":
        if str(parameters.get("format") or "").lower() != "glb":
            raise ValueError("质量规则快照无效，请联系管理员。")
        raw_max_triangles = parameters.get("max_triangles")
        if raw_max_triangles is not None and (
            isinstance(raw_max_triangles, bool)
            or not isinstance(raw_max_triangles, int)
            or not 100 <= raw_max_triangles <= 20_000
        ):
            raise ValueError("质量规则快照无效，请联系管理员。")
        require_uv = parameters.get("require_uv", True)
        require_pbr = parameters.get("require_pbr", True)
        if not isinstance(require_uv, bool) or not isinstance(require_pbr, bool):
            raise ValueError("质量规则快照无效，请联系管理员。")
        return {
            "check_type": "model_3d",
            "format": "glb",
            "max_triangles": raw_max_triangles,
            "require_uv": require_uv,
            "require_pbr": require_pbr,
            # Manual rechecks cannot inherit a claim that an external validator
            # ran; the local workflow records only checks it actually executes.
            "gltf_validator": False,
        }
    if check_type != "image":
        raise ValueError("质量规则快照无效，请联系管理员。")
    expected_size = str(parameters.get("expected_size") or "ORIGINAL").upper()
    if expected_size not in {"ORIGINAL", "2K", "3K", "4K"}:
        raise ValueError("质量规则快照无效，请联系管理员。")
    raw_palette = parameters.get("palette", [])
    if (
        not isinstance(raw_palette, list)
        or len(raw_palette) > 32
        or any(not isinstance(value, str) or len(value) > 16 for value in raw_palette)
    ):
        raise ValueError("质量规则快照无效，请联系管理员。")
    boolean_fields = (
        "expect_no_text",
        "expect_transparency",
        "expect_seamless",
    )
    if any(not isinstance(parameters.get(name, False), bool) for name in boolean_fields):
        raise ValueError("质量规则快照无效，请联系管理员。")
    return {
        "check_type": "image",
        "expected_size": expected_size,
        "palette": [value.strip() for value in raw_palette if value.strip()],
        **{name: bool(parameters.get(name, False)) for name in boolean_fields},
    }


def _execute_quality_check(
    path: Path,
    *,
    rules_version: str,
    parameters: Mapping[str, Any],
    image_checker: ImageChecker,
    component_checker: ComponentChecker,
    audio_checker: AudioChecker,
    model_checker: ModelChecker,
) -> AssetQualityResult:
    check_type = str(parameters["check_type"])
    if check_type == "image":
        if rules_version != IMAGE_QUALITY_RULES_VERSION:
            raise ValueError("图片质量规则版本不受当前运行时支持。")
        return image_checker(
            [path],
            expected_size=str(parameters["expected_size"]),
            palette=parameters.get("palette", []),
            expect_no_text=bool(parameters.get("expect_no_text", False)),
            expect_transparency=bool(
                parameters.get("expect_transparency", False)
            ),
            expect_seamless=bool(parameters.get("expect_seamless", False)),
        )[0]
    if check_type == "ui_components":
        if rules_version != UI_COMPONENT_QUALITY_RULES_VERSION:
            raise ValueError("UI 组件质量规则版本不受当前运行时支持。")
        return component_checker(path)
    if check_type == "audio":
        if rules_version != AUDIO_QUALITY_RULES_VERSION:
            raise ValueError("音频质量规则版本不受当前运行时支持。")
        return audio_checker(
            path,
            expected_duration_seconds=parameters.get(
                "expected_duration_seconds"
            ),
            expect_loop=bool(parameters.get("expect_loop", False)),
            asset_type=str(parameters.get("asset_type") or "audio"),
        )
    if check_type == "model_3d":
        if rules_version != MODEL_3D_QUALITY_RULES_VERSION:
            raise ValueError("3D 模型质量规则版本不受当前运行时支持。")
        return model_checker(
            path,
            max_triangles=parameters.get("max_triangles"),
            require_uv=bool(parameters.get("require_uv", True)),
            require_pbr=bool(parameters.get("require_pbr", True)),
        )
    raise ValueError("质量规则快照无效。")


def persist_asset_quality_result(
    repository: WorkflowRepository,
    context: RequestContext,
    asset: AssetRecord,
    quality: AssetQualityResult,
) -> AssetQualityCheckRecord:
    """Persist one hash-bound result and return the authoritative id after an idempotent upsert."""

    record = AssetQualityCheckRecord(
        id=uuid4().hex,
        workspace_id=context.workspace.id,
        created_by=context.principal.id,
        asset_id=asset.id,
        content_sha256=quality.content_sha256,
        rules_version=quality.rules_version,
        status=quality.status,
        checks_json=quality.checks_json(),
        created_at=_now(),
    )
    repository.create_asset_quality_check(record)
    stored = repository.get_current_asset_quality_check(
        asset.id,
        context.workspace.id,
    )
    if (
        stored is None
        or stored.content_sha256 != record.content_sha256
        or stored.rules_version != record.rules_version
        or stored.status != record.status
    ):
        raise RuntimeError("质量检查结果未能持久化。")
    return stored


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
