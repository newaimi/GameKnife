from __future__ import annotations

import sqlite3
from io import BytesIO
from pathlib import Path

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
