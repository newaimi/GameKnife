from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory as RealTemporaryDirectory

import numpy as np
import pytest
from PIL import Image

import gameknife_workflows.job_helpers as job_helpers
from gameknife_core import AllowAllPermissionChecker, AssetRecord, CapabilitySet, Principal, RequestContext, Workspace
from gameknife_jobs import SQLiteGameKnifeRepository, init_sqlite_schema
from gameknife_storage import LocalStorageProvider
from gameknife_workflows import (
    WorkflowInputNotFoundError,
    WorkflowModelNotInstalledError,
    create_background_remove_workflow,
)


class FakeBackgroundRemoveModel:
    device_label = "CPU"

    def __init__(self, *, installed: bool = True) -> None:
        self.installed = installed
        self.predict_calls = 0

    def is_installed(self) -> bool:
        return self.installed

    def predict_alpha(self, image: Image.Image) -> np.ndarray:
        self.predict_calls += 1
        alpha = np.zeros((image.height, image.width), dtype=np.uint8)
        alpha[:, :] = 255
        return alpha


class RejectSuccessRepository(SQLiteGameKnifeRepository):
    def update_job(self, job_id: str, workspace_id: str, **changes) -> None:
        if changes.get("status") == "success":
            raise RuntimeError("forced success persistence failure")
        super().update_job(job_id, workspace_id, **changes)


def test_background_remove_workflow_rejects_missing_model(tmp_path: Path) -> None:
    repository, context, asset = _make_repository_context_and_asset(tmp_path)

    try:
        create_background_remove_workflow(
            repository,
            context,
            FakeBackgroundRemoveModel(installed=False),
            input_asset_id=asset.id,
            parameters={},
        )
    except WorkflowModelNotInstalledError as exc:
        assert str(exc) == "BiRefNet 模型尚未下载安装，请先到设置页下载安装模型文件。"
    else:
        raise AssertionError("缺少模型时必须阻止创建背景移除任务。")


def test_background_remove_workflow_rejects_missing_input_asset(tmp_path: Path) -> None:
    repository, context, _asset = _make_repository_context_and_asset(tmp_path)

    try:
        create_background_remove_workflow(
            repository,
            context,
            FakeBackgroundRemoveModel(),
            input_asset_id="missing-asset",
            parameters={},
        )
    except WorkflowInputNotFoundError as exc:
        assert str(exc) == "输入素材不存在。"
    else:
        raise AssertionError("输入素材不存在时必须阻止创建背景移除任务。")


def test_background_remove_workflow_creates_job_and_output_asset(tmp_path: Path) -> None:
    repository, context, asset = _make_repository_context_and_asset(tmp_path)
    model = FakeBackgroundRemoveModel()

    submitted, runner = create_background_remove_workflow(
        repository,
        context,
        model,
        input_asset_id=asset.id,
        parameters={"alpha_smoothing": 0},
    )
    job = submitted.job
    runner()

    stored = repository.get_job_for_workspace(job.id, context.workspace.id)
    assert stored is not None
    result = json.loads(stored.result_json)
    assert stored.job_type == "background_remove"
    assert stored.status == "success"
    assert result["input_asset_url"] == f"/api/assets/{asset.id}"
    assert len(result["output_assets"]) == 1
    assert model.predict_calls == 1


def test_background_remove_workflow_removes_registered_output_when_success_persistence_fails(tmp_path: Path) -> None:
    _repository, context, asset = _make_repository_context_and_asset(tmp_path)
    repository = RejectSuccessRepository(tmp_path / "storage" / "gameknife.sqlite3")

    submitted, runner = create_background_remove_workflow(
        repository,
        context,
        FakeBackgroundRemoveModel(),
        input_asset_id=asset.id,
        parameters={"alpha_smoothing": 0},
    )
    job = submitted.job
    runner()

    stored = repository.get_job_for_workspace(job.id, context.workspace.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_message == "forced success persistence failure"
    assert repository.list_job_output_assets_for_workspace(job.id, context.workspace.id) == []
    assert [item.id for item in repository.list_assets_for_workspace(context.workspace.id)] == [asset.id]


def test_temporary_directory_cleanup_failure_marks_job_failed_before_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, context, asset = _make_repository_context_and_asset(tmp_path)

    class CleanupFailureTemporaryDirectory:
        def __init__(self, *args, **kwargs) -> None:
            self._temporary = RealTemporaryDirectory(*args, **kwargs)

        def __enter__(self) -> str:
            return self._temporary.__enter__()

        def __exit__(self, exc_type, exc_value, traceback) -> bool:
            self._temporary.__exit__(exc_type, exc_value, traceback)
            raise RuntimeError("temporary cleanup failed")

    monkeypatch.setattr(job_helpers, "TemporaryDirectory", CleanupFailureTemporaryDirectory)
    submitted, runner = create_background_remove_workflow(
        repository,
        context,
        FakeBackgroundRemoveModel(),
        input_asset_id=asset.id,
        parameters={"alpha_smoothing": 0},
    )
    job = submitted.job

    runner()

    stored = repository.get_job_for_workspace(job.id, context.workspace.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_message == "temporary cleanup failed"
    assert repository.list_job_output_assets_for_workspace(job.id, context.workspace.id) == []
    assert [item.id for item in repository.list_assets_for_workspace(context.workspace.id)] == [asset.id]


def test_delete_object_failure_does_not_mask_success_persistence_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repository, context, asset = _make_repository_context_and_asset(tmp_path)
    repository = RejectSuccessRepository(tmp_path / "storage" / "gameknife.sqlite3")

    def reject_delete(_key: str) -> None:
        raise RuntimeError("delete failed")

    monkeypatch.setattr(context.storage, "delete_object", reject_delete)
    submitted, runner = create_background_remove_workflow(
        repository,
        context,
        FakeBackgroundRemoveModel(),
        input_asset_id=asset.id,
        parameters={"alpha_smoothing": 0},
    )
    job = submitted.job

    runner()

    stored = repository.get_job_for_workspace(job.id, context.workspace.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_message == "forced success persistence failure"


def test_duplicate_runner_execution_claims_and_processes_job_once(tmp_path: Path) -> None:
    repository, context, asset = _make_repository_context_and_asset(tmp_path)
    model = FakeBackgroundRemoveModel()
    submitted, runner = create_background_remove_workflow(
        repository,
        context,
        model,
        input_asset_id=asset.id,
        parameters={"alpha_smoothing": 0},
    )
    job = submitted.job

    runner()
    runner()

    stored = repository.get_job_for_workspace(job.id, context.workspace.id)
    assert stored is not None and stored.status == "success"
    assert model.predict_calls == 1
    assert len(repository.list_job_output_assets_for_workspace(job.id, context.workspace.id)) == 1


def _make_repository_context_and_asset(tmp_path: Path) -> tuple[SQLiteGameKnifeRepository, RequestContext, AssetRecord]:
    storage = LocalStorageProvider(tmp_path / "storage")
    database_path = tmp_path / "storage" / "gameknife.sqlite3"
    init_sqlite_schema(database_path)
    repository = SQLiteGameKnifeRepository(database_path)
    asset_id = "asset-1"
    source_path = tmp_path / "sprite.png"
    source_path.write_bytes(_make_png_bytes())
    stored = storage.put_file(asset_id, "sprite.png", source_path)
    asset = AssetRecord(
        id=asset_id,
        workspace_id="local",
        created_by="anonymous",
        kind="image",
        original_name="sprite.png",
        path=stored.key,
        mime_type="image/png",
        size_bytes=stored.size_bytes,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    repository.create_asset(asset)
    context = RequestContext(
        principal=Principal(id="anonymous", kind="anonymous", display_name="本地用户"),
        workspace=Workspace(id="local", kind="local", name="本地工作区"),
        permissions=AllowAllPermissionChecker(),
        capabilities=CapabilitySet(edition="community", features=frozenset({"background-remove"})),
        storage=storage,
    )
    return repository, context, asset


def _make_png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", (3, 3), (255, 0, 0, 255)).save(buffer, format="PNG")
    return buffer.getvalue()
