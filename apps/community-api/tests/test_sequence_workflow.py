from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

from PIL import Image

from gameknife_core import AllowAllPermissionChecker, AssetRecord, CapabilitySet, Principal, RequestContext, Workspace
from gameknife_jobs import SQLiteGameKnifeRepository, init_sqlite_schema
from gameknife_storage import LocalStorageProvider
from gameknife_workflows import create_sequence_frames_export_workflow, create_sequence_spine_export_workflow


def test_sequence_frames_export_workflow_creates_png_zip(tmp_path: Path) -> None:
    repository, context, sequence_id = _make_repository_context_and_sequence(tmp_path)

    job, runner = create_sequence_frames_export_workflow(repository, context, sequence_id=sequence_id, parameters={})
    runner()

    stored = repository.get_job_for_workspace(job.id, context.workspace.id)
    assert stored is not None
    result = json.loads(stored.result_json)
    output_asset = repository.get_asset_for_workspace(result["output_assets"][0]["id"], context.workspace.id)
    assert stored.status == "success"
    assert stored.job_type == "sequence_export_frames"
    assert output_asset is not None
    assert output_asset.kind == "sequence_export"
    with zipfile.ZipFile(context.storage.resolve_asset_path(output_asset.path)) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "spritesheet.png" in names


def test_sequence_spine_export_workflow_creates_spine_zip(tmp_path: Path) -> None:
    repository, context, sequence_id = _make_repository_context_and_sequence(tmp_path)

    job, runner = create_sequence_spine_export_workflow(repository, context, sequence_id=sequence_id, parameters={})
    runner()

    stored = repository.get_job_for_workspace(job.id, context.workspace.id)
    assert stored is not None
    result = json.loads(stored.result_json)
    output_asset = repository.get_asset_for_workspace(result["output_assets"][0]["id"], context.workspace.id)
    assert stored.status == "success"
    assert stored.job_type == "sequence_export_spine"
    assert result["warnings"] == ["Spine 导出为逐帧切换附件，不包含骨骼绑定和蒙皮权重。"]
    assert output_asset is not None
    assert output_asset.kind == "sequence_spine"
    with zipfile.ZipFile(context.storage.resolve_asset_path(output_asset.path)) as archive:
        names = set(archive.namelist())
    assert "walk.png" in names
    assert "walk.atlas" in names
    assert "walk.json" in names


def _make_repository_context_and_sequence(tmp_path: Path) -> tuple[SQLiteGameKnifeRepository, RequestContext, str]:
    storage = LocalStorageProvider(tmp_path / "storage")
    database_path = tmp_path / "storage" / "gameknife.sqlite3"
    init_sqlite_schema(database_path)
    repository = SQLiteGameKnifeRepository(database_path)
    assets: list[AssetRecord] = []
    for index, color in enumerate([(255, 0, 0, 255), (0, 0, 255, 255)], start=1):
        asset_id = f"asset-{index}"
        filename = f"walk_{index:03d}.png"
        asset_path = storage.write_asset(asset_id, filename, _make_sequence_frame_bytes(color))
        asset = AssetRecord(
            id=asset_id,
            workspace_id="local",
            created_by="anonymous",
            kind="sequence_frame",
            original_name=filename,
            path=asset_path,
            mime_type="image/png",
            size_bytes=storage.resolve_asset_path(asset_path).stat().st_size,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
        repository.create_asset(asset)
        assets.append(asset)
    sequence = repository.create_sequence_with_frames(
        workspace_id="local",
        created_by="anonymous",
        name="walk",
        fps=12,
        loop=True,
        clean_parameters={},
        frames=[
            {
                "source_asset_id": asset.id,
                "original_name": asset.original_name,
                "width": 6,
                "height": 6,
                "bbox": [0, 0, 6, 6],
                "duration_ms": 83,
                "enabled": True,
            }
            for asset in assets
        ],
        created_at="2026-01-01T00:00:00+00:00",
    )
    context = RequestContext(
        principal=Principal(id="anonymous", kind="anonymous", display_name="本地用户"),
        workspace=Workspace(id="local", kind="local", name="本地工作区"),
        permissions=AllowAllPermissionChecker(),
        capabilities=CapabilitySet(edition="community", features=frozenset({"sequence"})),
        storage=storage,
    )
    return repository, context, str(sequence["id"])


def _make_sequence_frame_bytes(color: tuple[int, int, int, int]) -> bytes:
    image = Image.new("RGBA", (6, 6), (0, 0, 0, 0))
    for x in range(1, 5):
        for y in range(1, 5):
            image.putpixel((x, y), color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
