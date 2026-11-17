from __future__ import annotations

import json
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from gameknife_core import (
    AllowAllPermissionChecker,
    AssetRecord,
    CapabilitySet,
    Principal,
    RequestContext,
    Workspace,
)
from gameknife_jobs import SQLiteGameKnifeRepository, init_sqlite_schema
from gameknife_processors import (
    MODEL_3D_QUALITY_RULES_VERSION,
    AssetQualityResult,
    QualityCheckItem,
)
from gameknife_storage import LocalStorageProvider
from gameknife_workflows import create_job_record, run_asset_quality_check_workflow
from PIL import Image


def test_unavailable_checker_persists_unchecked_fact_and_fails_retry_job(
    tmp_path: Path,
) -> None:
    repository, context, asset = _repository_context_and_asset(tmp_path)
    submitted = create_job_record(
        repository,
        context,
        job_type="asset_quality_check",
        input_asset_id=asset.id,
        parameters={"asset_id": asset.id, "source_quality_check_id": None},
    )

    def fail_checker(*_args, **_kwargs):
        raise RuntimeError("checker unavailable")

    run_asset_quality_check_workflow(
        repository,
        context,
        submitted.job.id,
        image_checker=fail_checker,
    )

    stored_job = repository.get_job_for_workspace(
        submitted.job.id,
        context.workspace.id,
    )
    quality = repository.get_current_asset_quality_check(
        asset.id,
        context.workspace.id,
    )
    assert stored_job is not None
    assert stored_job.status == "failed"
    assert stored_job.error_message == "Automatic quality checks are temporarily unavailable. Try again later."
    assert quality is not None
    assert quality.status == "unchecked"
    payload = json.loads(quality.checks_json)
    assert payload["parameters"]["check_type"] == "image"
    assert payload["checks"][0]["code"] == "QUALITY_CHECK_UNAVAILABLE"


def test_model_asset_quality_retry_uses_explicit_glb_policy(tmp_path: Path) -> None:
    repository, context = _repository_and_context(tmp_path)
    source_path = tmp_path / "model.glb"
    source_path.write_bytes(b"glTF-model-test")
    stored = context.storage.put_file("model-1", "model.glb", source_path)
    asset = AssetRecord(
        id="model-1",
        workspace_id="local",
        created_by="anonymous",
        kind="model_3d_glb",
        original_name="model.glb",
        path=stored.key,
        mime_type="model/gltf-binary",
        size_bytes=stored.size_bytes,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    repository.create_asset(asset)
    submitted = create_job_record(
        repository,
        context,
        job_type="asset_quality_check",
        input_asset_id=asset.id,
        parameters={"asset_id": asset.id, "source_quality_check_id": None},
    )
    calls = []

    def model_checker(path: Path, **parameters):
        calls.append((path.read_bytes(), parameters))
        return AssetQualityResult(
            status="passed",
            rules_version=MODEL_3D_QUALITY_RULES_VERSION,
            content_sha256=sha256(path.read_bytes()).hexdigest(),
            checks=(
                QualityCheckItem(
                    code="MODEL_GLTF_PARSE",
                    status="passed",
                    message="valid",
                    metrics={},
                ),
            ),
            parameters={"check_type": "model_3d", **parameters},
        )

    run_asset_quality_check_workflow(
        repository,
        context,
        submitted.job.id,
        model_checker=model_checker,
    )

    job = repository.get_job_for_workspace(submitted.job.id, "local")
    quality = repository.get_current_asset_quality_check(asset.id, "local")
    assert job is not None and job.status == "success"
    assert quality is not None and quality.rules_version == "model-3d-v1"
    assert calls == [
        (
            b"glTF-model-test",
            {"max_triangles": None, "require_uv": True, "require_pbr": True},
        )
    ]


def _repository_context_and_asset(
    tmp_path: Path,
) -> tuple[SQLiteGameKnifeRepository, RequestContext, AssetRecord]:
    repository, context = _repository_and_context(tmp_path)
    storage = context.storage
    source_path = tmp_path / "hero.png"
    buffer = BytesIO()
    image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    for offset in range(2, 6):
        image.putpixel((offset, offset), (255, 0, 0, 255))
    image.save(buffer, format="PNG")
    source_path.write_bytes(buffer.getvalue())
    stored = storage.put_file("asset-1", "hero.png", source_path)
    asset = AssetRecord(
        id="asset-1",
        workspace_id="local",
        created_by="anonymous",
        kind="image",
        original_name="hero.png",
        path=stored.key,
        mime_type="image/png",
        size_bytes=stored.size_bytes,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    repository.create_asset(asset)
    return repository, context, asset


def _repository_and_context(
    tmp_path: Path,
) -> tuple[SQLiteGameKnifeRepository, RequestContext]:
    storage = LocalStorageProvider(tmp_path / "storage")
    database_path = tmp_path / "storage" / "gameknife.sqlite3"
    init_sqlite_schema(database_path)
    repository = SQLiteGameKnifeRepository(database_path)
    context = RequestContext(
        principal=Principal(
            id="anonymous",
            kind="anonymous",
            display_name="Local User",
        ),
        workspace=Workspace(id="local", kind="local", name="Local Workspace"),
        permissions=AllowAllPermissionChecker(),
        capabilities=CapabilitySet(edition="community", features=frozenset()),
        storage=storage,
    )
    return repository, context
