from __future__ import annotations

import sqlite3
from io import BytesIO
from pathlib import Path
import zipfile

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
