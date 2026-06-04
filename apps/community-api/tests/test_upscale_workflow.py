from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from gameknife_core import AllowAllPermissionChecker, AssetRecord, CapabilitySet, Principal, RequestContext, Workspace
from gameknife_jobs import SQLiteGameKnifeRepository, init_sqlite_schema
from gameknife_storage import LocalStorageProvider
from gameknife_workflows import WorkflowInputNotFoundError, WorkflowModelNotInstalledError, create_upscale_workflow


class FakeUpscaleModel:
    device_label = "CPU"

    def __init__(self, *, installed: bool = True) -> None:
        self.installed = installed
        self.upscale_calls = 0

    def is_installed(self) -> bool:
        return self.installed

    def upscale_image(
        self,
        image: Image.Image,
        *,
        style: str,
        target_scale: int,
        denoise: int,
        tile_size: int,
    ) -> tuple[Image.Image, str, str, list[str]]:
        self.upscale_calls += 1
        output = image.resize((image.width * target_scale, image.height * target_scale), Image.Resampling.BICUBIC)
        return output, "fake-real-esrgan", "CPU", []


def test_pixel_upscale_workflow_runs_without_installed_model(tmp_path: Path) -> None:
    repository, context, asset = _make_repository_context_and_asset(tmp_path)
    model = FakeUpscaleModel(installed=False)

    job, runner = create_upscale_workflow(
        repository,
        context,
        model,
        input_asset_id=asset.id,
        parameters={"style": "pixel", "scale": 2},
    )
    runner()

    stored = repository.get_job_for_workspace(job.id, context.workspace.id)
    assert stored is not None
    result = json.loads(stored.result_json)
    assert stored.status == "success"
    assert result["model"] == "nearest-neighbor"
    assert result["output_size"] == [6, 6]
    assert len(result["output_assets"]) == 1
    assert model.upscale_calls == 0


def test_ai_upscale_workflow_rejects_missing_model(tmp_path: Path) -> None:
    repository, context, asset = _make_repository_context_and_asset(tmp_path)

    try:
        create_upscale_workflow(
            repository,
            context,
            FakeUpscaleModel(installed=False),
            input_asset_id=asset.id,
            parameters={"style": "general", "scale": 2},
        )
    except WorkflowModelNotInstalledError as exc:
        assert str(exc) == "图片放大模型尚未下载安装，请先到设置页下载安装模型文件。"
    else:
        raise AssertionError("AI 图片放大缺少模型时必须阻止创建任务。")


def test_ai_upscale_workflow_uses_installed_model(tmp_path: Path) -> None:
    repository, context, asset = _make_repository_context_and_asset(tmp_path)
    model = FakeUpscaleModel()

    job, runner = create_upscale_workflow(
        repository,
        context,
        model,
        input_asset_id=asset.id,
        parameters={"style": "general", "scale": 2, "denoise": 1, "tile_size": 128},
    )
    runner()

    stored = repository.get_job_for_workspace(job.id, context.workspace.id)
    assert stored is not None
    result = json.loads(stored.result_json)
    assert stored.status == "success"
    assert result["model"] == "fake-real-esrgan"
    assert result["output_size"] == [6, 6]
    assert model.upscale_calls == 1


def test_upscale_workflow_rejects_missing_input_asset(tmp_path: Path) -> None:
    repository, context, _asset = _make_repository_context_and_asset(tmp_path)

    try:
        create_upscale_workflow(
            repository,
            context,
            FakeUpscaleModel(),
            input_asset_id="missing-asset",
            parameters={"style": "pixel", "scale": 2},
        )
    except WorkflowInputNotFoundError as exc:
        assert str(exc) == "输入素材不存在。"
    else:
        raise AssertionError("输入素材不存在时必须阻止创建图片放大任务。")


def _make_repository_context_and_asset(tmp_path: Path) -> tuple[SQLiteGameKnifeRepository, RequestContext, AssetRecord]:
    storage = LocalStorageProvider(tmp_path / "storage")
    database_path = tmp_path / "storage" / "gameknife.sqlite3"
    init_sqlite_schema(database_path)
    repository = SQLiteGameKnifeRepository(database_path)
    asset_id = "asset-1"
    asset_path = storage.write_asset(asset_id, "sprite.png", _make_png_bytes())
    asset = AssetRecord(
        id=asset_id,
        workspace_id="local",
        created_by="anonymous",
        kind="image",
        original_name="sprite.png",
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
        capabilities=CapabilitySet(edition="community", features=frozenset({"upscale"})),
        storage=storage,
    )
    return repository, context, asset


def _make_png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", (3, 3), (255, 0, 0, 255)).save(buffer, format="PNG")
    return buffer.getvalue()
