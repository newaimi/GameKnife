from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from gameknife_core import AllowAllPermissionChecker, AssetRecord, CapabilitySet, Principal, RequestContext, Workspace
from gameknife_jobs import SQLiteGameKnifeRepository, init_sqlite_schema
from gameknife_storage import LocalStorageProvider
from gameknife_workflows import (
    WorkflowInputNotFoundError,
    WorkflowModelNotInstalledError,
    create_asset_board_cutout_workflow,
    create_asset_board_region_workflow,
)


class FakeAssetBoardCutoutModel:
    device_label = "CPU"

    def __init__(self, *, installed: bool = True) -> None:
        self.installed = installed
        self.predict_calls = 0

    def is_installed(self) -> bool:
        return self.installed

    def predict_alpha(self, image: Image.Image) -> np.ndarray:
        self.predict_calls += 1
        alpha = np.zeros((image.height, image.width), dtype=np.uint8)
        alpha[1 : image.height - 1, 1 : image.width - 1] = 255
        return alpha


def test_asset_board_region_workflow_rejects_missing_input_asset(tmp_path: Path) -> None:
    repository, context, _asset = _make_repository_context_and_asset(tmp_path)

    try:
        create_asset_board_region_workflow(
            repository,
            context,
            input_asset_id="missing-asset",
            parameters={"min_component_area": 4, "alpha_threshold": 16},
        )
    except WorkflowInputNotFoundError as exc:
        assert str(exc) == "输入素材不存在。"
    else:
        raise AssertionError("输入素材不存在时必须阻止创建素材板区域识别任务。")


def test_asset_board_region_workflow_detects_components_without_output_assets(tmp_path: Path) -> None:
    repository, context, asset = _make_repository_context_and_asset(tmp_path)

    job, runner = create_asset_board_region_workflow(
        repository,
        context,
        input_asset_id=asset.id,
        parameters={"min_component_area": 4, "alpha_threshold": 16},
    )
    runner()

    stored = repository.get_job_for_workspace(job.id, context.workspace.id)
    assert stored is not None
    result = json.loads(stored.result_json)
    assert stored.status == "success"
    assert stored.job_type == "asset_board_region_detect"
    assert result["component_count"] == 2
    assert result["input_asset_url"] == f"/api/assets/{asset.id}"
    assert "output_assets" not in result


def test_asset_board_cutout_workflow_rejects_missing_model(tmp_path: Path) -> None:
    repository, context, asset = _make_repository_context_and_asset(tmp_path)

    try:
        create_asset_board_cutout_workflow(
            repository,
            context,
            FakeAssetBoardCutoutModel(installed=False),
            input_asset_id=asset.id,
            parameters={},
        )
    except WorkflowModelNotInstalledError as exc:
        assert str(exc) == "BiRefNet 模型尚未下载安装，请先到设置页下载安装模型文件。"
    else:
        raise AssertionError("素材板抠图缺少模型时必须阻止创建任务。")


def test_asset_board_cutout_workflow_rejects_missing_input_asset(tmp_path: Path) -> None:
    repository, context, _asset = _make_repository_context_and_asset(tmp_path)

    try:
        create_asset_board_cutout_workflow(
            repository,
            context,
            FakeAssetBoardCutoutModel(),
            input_asset_id="missing-asset",
            parameters={},
        )
    except WorkflowInputNotFoundError as exc:
        assert str(exc) == "输入素材不存在。"
    else:
        raise AssertionError("输入素材不存在时必须阻止创建素材板抠图任务。")


def test_asset_board_cutout_workflow_creates_cutout_asset(tmp_path: Path) -> None:
    repository, context, asset = _make_repository_context_and_asset(tmp_path)
    model = FakeAssetBoardCutoutModel()

    job, runner = create_asset_board_cutout_workflow(
        repository,
        context,
        model,
        input_asset_id=asset.id,
        parameters={},
    )
    runner()

    stored = repository.get_job_for_workspace(job.id, context.workspace.id)
    assert stored is not None
    result = json.loads(stored.result_json)
    output_asset = repository.get_asset_for_workspace(result["cutout_asset_id"], context.workspace.id)
    assert stored.status == "success"
    assert stored.job_type == "asset_board_cutout"
    assert result["cutout_asset_id"] == result["output_assets"][0]["id"]
    assert output_asset is not None
    assert output_asset.kind == "asset_cutout"
    assert context.storage.resolve_asset_path(output_asset.path).read_bytes().startswith(b"\x89PNG")
    assert model.predict_calls == 1


def _make_repository_context_and_asset(tmp_path: Path) -> tuple[SQLiteGameKnifeRepository, RequestContext, AssetRecord]:
    storage = LocalStorageProvider(tmp_path / "storage")
    database_path = tmp_path / "storage" / "gameknife.sqlite3"
    init_sqlite_schema(database_path)
    repository = SQLiteGameKnifeRepository(database_path)
    asset_id = "asset-1"
    asset_path = storage.write_asset(asset_id, "sheet.png", _make_asset_board_png_bytes())
    asset = AssetRecord(
        id=asset_id,
        workspace_id="local",
        created_by="anonymous",
        kind="image",
        original_name="sheet.png",
        path=asset_path,
        mime_type="image/png",
        size_bytes=storage.resolve_asset_path(asset_path).stat().st_size,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    repository.create_asset(asset)
    context = RequestContext(
        principal=Principal(id="anonymous", kind="anonymous", display_name="本地用户"),
        workspace=Workspace(id="local", kind="local", name="本地工作区"),
        permissions=AllowAllPermissionChecker(),
        capabilities=CapabilitySet(edition="community", features=frozenset({"asset-board"})),
        storage=storage,
    )
    return repository, context, asset


def _make_asset_board_png_bytes() -> bytes:
    image = Image.new("RGBA", (32, 16), (0, 0, 0, 0))
    for x in range(2, 8):
        for y in range(2, 8):
            image.putpixel((x, y), (255, 0, 0, 255))
    for x in range(18, 26):
        for y in range(4, 12):
            image.putpixel((x, y), (0, 0, 255, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
