from __future__ import annotations

import sqlite3
from io import BytesIO
from pathlib import Path
import zipfile

import cv2
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from community_api.main import create_app
from gameknife_api.deps import CommunitySettings


def make_client(tmp_path: Path) -> TestClient:
    settings = CommunitySettings(
        storage_root=tmp_path / "storage",
        database_path=tmp_path / "storage" / "gameknife.sqlite3",
        cors_origins=["*"],
    )
    return TestClient(create_app(settings))


def make_png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def make_transparent_png_bytes() -> bytes:
    image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    for x in range(2, 6):
        for y in range(2, 6):
            image.putpixel((x, y), (255, 0, 0, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def make_asset_board_png_bytes() -> bytes:
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


def make_character_rig_png_bytes() -> bytes:
    image = Image.new("RGBA", (40, 24), (0, 0, 0, 0))
    for x in range(3, 13):
        for y in range(5, 17):
            image.putpixel((x, y), (255, 0, 0, 255))
    for x in range(24, 34):
        for y in range(4, 18):
            image.putpixel((x, y), (0, 0, 255, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def make_opaque_character_png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", (16, 16), (255, 255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def make_video_bytes(tmp_path: Path) -> bytes:
    video_path = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 4.0, (16, 12))
    if not writer.isOpened():
        raise RuntimeError("测试视频编码器不可用。")
    try:
        for index, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]):
            frame = np.zeros((12, 16, 3), dtype=np.uint8)
            frame[:, :] = color
            frame[2:10, 4:12] = (index * 40, 255 - index * 30, 120)
            writer.write(frame)
    finally:
        writer.release()
    return video_path.read_bytes()


def make_sequence_frame_bytes(color: tuple[int, int, int, int]) -> bytes:
    image = Image.new("RGBA", (12, 12), (0, 0, 0, 0))
    for x in range(3, 9):
        for y in range(2, 10):
            image.putpixel((x, y), color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class FakeStableAudioService:
    def install_status(self) -> dict[str, object]:
        return {"status": "success", "installed": True, "message": "ok", "error": None}

    def generate_sound_effect(self, prompt: str, output_path: Path, parameters: dict[str, object]) -> dict[str, object]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
        return {
            "model": "fake-stable-audio",
            "device": "cpu",
            "sample_rate": 44100,
            "queue_wait_ms": 0,
            "duration_ms": 5,
        }


def test_context_is_anonymous_local_workspace(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/context")

    assert response.status_code == 200
    data = response.json()
    assert data["principal"]["id"] == "anonymous"
    assert data["principal"]["kind"] == "anonymous"
    assert data["workspace"]["id"] == "local"
    assert data["workspace"]["kind"] == "local"
    assert data["capabilities"]["edition"] == "community"


def test_image_upload_creates_local_anonymous_asset(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/assets/images",
            files={"file": ("sprite.png", make_png_bytes(), "image/png")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "sprite.png"
    assert data["mime_type"] == "image/png"
    assert data["url"].startswith("/api/assets/")

    with sqlite3.connect(tmp_path / "storage" / "gameknife.sqlite3") as connection:
        row = connection.execute(
            "SELECT workspace_id, created_by, kind, original_name FROM assets WHERE id = ?",
            (data["id"],),
        ).fetchone()
        columns = [item[1] for item in connection.execute("PRAGMA table_info(assets)").fetchall()]

    assert row == ("local", "anonymous", "image", "sprite.png")
    assert "user_id" not in columns


def test_uploaded_asset_can_be_read_without_authorization(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sprite.png", make_png_bytes(), "image/png")},
        )
        asset_url = upload.json()["url"]
        response = client.get(asset_url)

    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")


def test_invalid_image_returns_chinese_error(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/assets/images",
            files={"file": ("broken.png", b"not image", "image/png")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "上传文件不是有效图片。"


def test_manual_edit_save_creates_new_asset_and_preserves_alpha(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        source = client.post(
            "/api/assets/images",
            files={"file": ("source.png", make_png_bytes(), "image/png")},
        ).json()
        response = client.post(
            "/api/manual-edits/save",
            data={"name": "edited-zombie", "source_asset_id": source["id"], "source_context": "manual-edit"},
            files={"file": ("edited.png", make_transparent_png_bytes(), "image/png")},
        )
        saved = response.json()
        saved_file = client.get(saved["url"])

    assert response.status_code == 200
    assert saved["filename"] == "edited-zombie.png"
    assert saved["mime_type"] == "image/png"
    with Image.open(BytesIO(saved_file.content)) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 0
        assert image.getpixel((4, 4))[3] == 255
    with sqlite3.connect(tmp_path / "storage" / "gameknife.sqlite3") as connection:
        source_row = connection.execute("SELECT kind FROM assets WHERE id = ?", (source["id"],)).fetchone()
        saved_row = connection.execute("SELECT workspace_id, created_by, kind FROM assets WHERE id = ?", (saved["id"],)).fetchone()
    assert source_row == ("image",)
    assert saved_row == ("local", "anonymous", "manual_edit")


def test_manual_edit_save_rejects_invalid_image_and_missing_source(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        bad_file = client.post(
            "/api/manual-edits/save",
            files={"file": ("note.txt", b"not image", "text/plain")},
        )
        missing_source = client.post(
            "/api/manual-edits/save",
            data={"source_asset_id": "missing-source"},
            files={"file": ("edited.png", make_transparent_png_bytes(), "image/png")},
        )

    assert bad_file.status_code == 400
    assert bad_file.json()["detail"] == "只支持 JPG、PNG 和 WebP 图片。"
    assert missing_source.status_code == 404
    assert missing_source.json()["detail"] == "输入素材不存在。"


def test_settings_are_readable_without_login(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json()["edition"] == "community"
    assert response.json()["models"]["stable_audio"]["status"] == "unconfigured"


def test_sound_effect_unconfigured_returns_chinese_error(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/jobs/sound-effect",
            json={"prompt": "coin pickup", "duration_seconds": 1, "steps": 20, "cfg_scale": 5},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Stable Audio 声效服务未配置。"


def test_sound_effect_job_creates_wav_asset(tmp_path: Path) -> None:
    settings = CommunitySettings(
        storage_root=tmp_path / "storage",
        database_path=tmp_path / "storage" / "gameknife.sqlite3",
        cors_origins=["*"],
        stable_audio_base_url="http://stable-audio",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.stable_audio = FakeStableAudioService()
        created = client.post(
            "/api/jobs/sound-effect",
            json={"prompt": "coin pickup", "duration_seconds": 1, "steps": 20, "cfg_scale": 5},
        )
        job = client.get(f"/api/jobs/{created.json()['id']}").json()
        output = client.get(job["result"]["output_assets"][0]["url"])

    assert created.status_code == 200
    assert job["status"] == "success"
    assert job["type"] == "sound_effect_generate"
    assert job["result"]["prompt"] == "coin pickup"
    assert job["result"]["output_assets"][0]["url"].startswith("/api/assets/")
    assert output.status_code == 200
    assert output.content.startswith(b"RIFF")
    with sqlite3.connect(tmp_path / "storage" / "gameknife.sqlite3") as connection:
        row = connection.execute(
            "SELECT kind, mime_type FROM assets WHERE id = ?",
            (job["input_asset_id"],),
        ).fetchone()
    assert row == ("sound_prompt", "text/plain")


def test_pixel_upscale_job_creates_output_asset(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sprite.png", make_png_bytes(), "image/png")},
        )
        asset_id = upload.json()["id"]

        created = client.post(
            "/api/jobs/upscale",
            json={"input_asset_id": asset_id, "parameters": {"style": "pixel", "scale": 2}},
        )
        job_id = created.json()["id"]
        job = client.get(f"/api/jobs/{job_id}").json()

        assert created.status_code == 200
        assert job["status"] == "success"
        assert job["result"]["output_size"] == [4, 4]
        assert "output_files" not in job["result"]
        output_asset = job["result"]["output_assets"][0]
        output = client.get(output_asset["url"])

    assert output.status_code == 200
    assert Image.open(BytesIO(output.content)).size == (4, 4)


def test_non_pixel_upscale_requires_installed_model(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sprite.png", make_png_bytes(), "image/png")},
        )
        response = client.post(
            "/api/jobs/upscale",
            json={"input_asset_id": upload.json()["id"], "parameters": {"style": "general", "scale": 4}},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "图片放大模型尚未下载安装，请先到设置页下载安装模型文件。"


def test_asset_board_region_job_does_not_create_output_assets(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sheet.png", make_asset_board_png_bytes(), "image/png")},
        )
        created = client.post(
            "/api/jobs/asset-board/regions",
            json={"input_asset_id": upload.json()["id"], "parameters": {"min_component_area": 4, "alpha_threshold": 16}},
        )
        job = client.get(f"/api/jobs/{created.json()['id']}").json()

    assert created.status_code == 200
    assert job["status"] == "success"
    assert job["type"] == "asset_board_region_detect"
    assert job["result"]["component_count"] == 2
    assert "output_assets" not in job["result"]


def test_job_history_and_delete_output_asset(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sprite.png", make_png_bytes(), "image/png")},
        )
        created = client.post(
            "/api/jobs/upscale",
            json={"input_asset_id": upload.json()["id"], "parameters": {"style": "pixel", "scale": 2}},
        )
        job_id = created.json()["id"]
        job = client.get(f"/api/jobs/{job_id}").json()
        output_url = job["result"]["output_assets"][0]["url"]

        history = client.get("/api/jobs/history", params={"category": "upscale", "downloadable": "true"})
        deleted = client.delete(f"/api/jobs/{job_id}")
        deleted_asset = client.get(output_url)

    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert deleted.status_code == 204
    assert deleted_asset.status_code == 404


def test_sequence_import_sorts_frames_and_uses_assets(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/sequences/import",
            data={"name": "walk", "fps": "12"},
            files=[
                ("files", ("walk_002.png", make_sequence_frame_bytes((0, 0, 255, 255)), "image/png")),
                ("files", ("walk_001.png", make_sequence_frame_bytes((255, 0, 0, 255)), "image/png")),
            ],
        )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "walk"
    assert data["frame_count"] == 2
    assert [frame["original_name"] for frame in data["frames"]] == ["walk_001.png", "walk_002.png"]
    assert data["frames"][0]["source_url"].startswith("/api/assets/")
    assert "source_file_id" not in data["frames"][0]


def test_sequence_clean_and_export_zip(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        imported = client.post(
            "/api/sequences/import",
            data={"name": "idle", "fps": "8"},
            files=[
                ("files", ("idle_001.png", make_sequence_frame_bytes((255, 0, 0, 255)), "image/png")),
                ("files", ("idle_002.png", make_sequence_frame_bytes((0, 0, 255, 255)), "image/png")),
            ],
        ).json()
        sequence_id = imported["id"]

        clean_created = client.post(f"/api/sequences/{sequence_id}/clean", json={"parameters": {"canvas_padding": 2}})
        clean_job = client.get(f"/api/jobs/{clean_created.json()['id']}").json()
        cleaned_sequence = client.get(f"/api/sequences/{sequence_id}").json()
        export_created = client.post(f"/api/sequences/{sequence_id}/export/frames", json={"parameters": {}})
        export_job = client.get(f"/api/jobs/{export_created.json()['id']}").json()
        archive_response = client.get(export_job["result"]["output_assets"][0]["url"])

    assert clean_created.status_code == 200
    assert clean_job["status"] == "success"
    assert all(frame["processed_asset_id"] for frame in cleaned_sequence["frames"])
    assert export_job["status"] == "success"
    assert export_job["type"] == "sequence_export_frames"
    with zipfile.ZipFile(BytesIO(archive_response.content)) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "spritesheet.png" in names


def test_sequence_delete_removes_source_assets(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        imported = client.post(
            "/api/sequences/import",
            data={"name": "delete-me", "fps": "12"},
            files=[("files", ("frame_001.png", make_sequence_frame_bytes((255, 0, 0, 255)), "image/png"))],
        ).json()
        sequence_id = imported["id"]
        source_url = imported["frames"][0]["source_url"]
        deleted = client.delete(f"/api/sequences/{sequence_id}")
        source_after_delete = client.get(source_url)

    assert deleted.status_code == 204
    assert source_after_delete.status_code == 404


def test_video_to_sequence_extracts_frames_into_sequence(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        upload = client.post(
            "/api/assets/videos",
            files={"file": ("walk.avi", make_video_bytes(tmp_path), "video/avi")},
        )
        created = client.post(
            "/api/sequences/from-video",
            json={"video_asset_id": upload.json()["id"], "name": "walk-video", "fps": 4, "max_frames": 3},
        )
        job = client.get(f"/api/jobs/{created.json()['id']}").json()
        sequence = client.get(f"/api/sequences/{job['result']['sequence_id']}").json()
        frame_asset = client.get(sequence["frames"][0]["source_url"])

    assert upload.status_code == 200
    assert created.status_code == 200
    assert job["status"] == "success"
    assert job["type"] == "sequence_video_to_frames"
    assert job["result"]["frame_count"] == 3
    assert "output_files" not in job["result"]
    assert "output_assets" not in job["result"]
    assert sequence["name"] == "walk-video"
    assert sequence["frame_count"] == 3
    assert sequence["fps"] == 4
    assert frame_asset.status_code == 200
    assert Image.open(BytesIO(frame_asset.content)).size == (16, 12)
    with sqlite3.connect(tmp_path / "storage" / "gameknife.sqlite3") as connection:
        frame_count = connection.execute("SELECT COUNT(*) FROM assets WHERE kind = 'sequence_frame'").fetchone()[0]
    assert frame_count == 3


def test_video_to_sequence_background_remove_requires_model_at_creation(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        upload = client.post(
            "/api/assets/videos",
            files={"file": ("walk.avi", make_video_bytes(tmp_path), "video/avi")},
        ).json()
        response = client.post(
            "/api/sequences/from-video",
            json={"video_asset_id": upload["id"], "name": "walk-video", "fps": 4, "max_frames": 3, "remove_background": True},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "BiRefNet 模型尚未下载安装，请先到设置页下载安装模型文件。"


def test_character_rig_import_analyze_refine_export_and_delete(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        imported = client.post(
            "/api/character-rigs/import",
            data={"name": "hero"},
            files={"file": ("hero.png", make_character_rig_png_bytes(), "image/png")},
        )
        rig = imported.json()
        analyze_created = client.post(
            f"/api/character-rigs/{rig['id']}/analyze",
            json={"parameters": {"min_component_area": 8, "padding": 1}},
        )
        analyze_job = client.get(f"/api/jobs/{analyze_created.json()['id']}").json()
        analyzed = client.get(f"/api/character-rigs/{rig['id']}").json()
        first_part = analyzed["parts"][0]
        patched = client.patch(
            f"/api/character-rigs/{rig['id']}/parts",
            json={"parts": [{"id": first_part["id"], "name": "head", "pivot_x": 0.4, "pivot_y": 0.6}]},
        ).json()
        refine_created = client.post(
            f"/api/character-rigs/{rig['id']}/parts/{first_part['id']}/refine",
            json={"parameters": {"padding": 2}},
        )
        refine_job = client.get(f"/api/jobs/{refine_created.json()['id']}").json()
        spine_created = client.post(f"/api/character-rigs/{rig['id']}/export/spine", json={"parameters": {}})
        spine_job = client.get(f"/api/jobs/{spine_created.json()['id']}").json()
        spine_zip = client.get(spine_job["result"]["output_assets"][0]["url"])
        dragonbones_created = client.post(f"/api/character-rigs/{rig['id']}/export/dragonbones", json={"parameters": {}})
        dragonbones_job = client.get(f"/api/jobs/{dragonbones_created.json()['id']}").json()
        dragonbones_zip = client.get(dragonbones_job["result"]["output_assets"][0]["url"])
        source_url = analyzed["source_url"]
        part_url = analyzed["parts"][0]["part_url"]
        deleted = client.delete(f"/api/character-rigs/{rig['id']}")
        deleted_source = client.get(source_url)
        deleted_part = client.get(part_url)

    assert imported.status_code == 200
    assert rig["source_asset_id"]
    assert analyze_created.status_code == 200
    assert analyze_job["status"] == "success"
    assert analyze_job["type"] == "character_rig_analyze"
    assert analyze_job["result"]["part_count"] == 2
    assert analyzed["part_count"] == 2
    assert analyzed["parts"][0]["part_asset_id"]
    assert "part_file_id" not in analyzed["parts"][0]
    assert patched["parts"][0]["name"] == "head"
    assert patched["parts"][0]["pivot_x"] == 0.4
    assert refine_job["status"] == "success"
    assert spine_job["status"] == "success"
    with zipfile.ZipFile(BytesIO(spine_zip.content)) as archive:
        spine_names = set(archive.namelist())
    assert "rig_manifest.json" in spine_names
    assert "hero.json" in spine_names
    assert any(name.startswith("parts/") for name in spine_names)
    assert dragonbones_job["status"] == "success"
    with zipfile.ZipFile(BytesIO(dragonbones_zip.content)) as archive:
        dragonbones_names = set(archive.namelist())
    assert "hero_ske.json" in dragonbones_names
    assert "hero_tex.json" in dragonbones_names
    assert deleted.status_code == 204
    assert deleted_source.status_code == 404
    assert deleted_part.status_code == 404


def test_character_rig_opaque_source_requires_models_at_creation(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        rig = client.post(
            "/api/character-rigs/import",
            data={"name": "opaque"},
            files={"file": ("opaque.png", make_opaque_character_png_bytes(), "image/png")},
        ).json()
        response = client.post(
            f"/api/character-rigs/{rig['id']}/analyze",
            json={"parameters": {}},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "骨骼拆分模型尚未下载安装，请先到设置页下载安装模型文件。"
