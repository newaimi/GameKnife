from __future__ import annotations

import json
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
from gameknife_api.video_generation import VideoGenerationClient, VideoGenerationResult
from gameknife_core import AssetRecord, JobRecord
from gameknife_processors.character_rig import CharacterRigDetection, CharacterRigHints


def make_client(tmp_path: Path) -> TestClient:
    settings = CommunitySettings(
        storage_root=tmp_path / "storage",
        database_path=tmp_path / "storage" / "gameknife.sqlite3",
        cors_origins=["*"],
    )
    return TestClient(create_app(settings))


def make_client_with_web_dist(tmp_path: Path) -> TestClient:
    web_dist = tmp_path / "web-dist"
    web_dist.mkdir(parents=True)
    (web_dist / "index.html").write_text("<!doctype html><title>GameKnife</title>", encoding="utf-8")
    (web_dist / "gameknife-logo.png").write_bytes(make_png_bytes())
    settings = CommunitySettings(
        storage_root=tmp_path / "storage",
        database_path=tmp_path / "storage" / "gameknife.sqlite3",
        cors_origins=["*"],
        web_dist=web_dist,
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
    def __init__(self) -> None:
        self.install_calls = 0

    def install_status(self) -> dict[str, object]:
        return {"status": "success", "installed": True, "message": "ok", "error": None}

    def start_install(self) -> dict[str, object]:
        self.install_calls += 1
        return self.install_status()

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


class FakeBiRefNetService:
    device_label = "CPU"

    def __init__(self) -> None:
        self.predict_calls = 0
        self.install_calls = 0

    def install_status(self) -> dict[str, object]:
        return {"status": "success", "installed": True, "loaded": True, "progress": 100, "message": "ok", "error": None}

    def is_installed(self) -> bool:
        return True

    def start_install(self) -> dict[str, object]:
        self.install_calls += 1
        return self.install_status()

    def predict_alpha(self, image: Image.Image) -> np.ndarray:
        self.predict_calls += 1
        alpha = np.zeros((image.height, image.width), dtype=np.uint8)
        alpha[1 : image.height - 1, 1 : image.width - 1] = 255
        return alpha


class FakeUpscaleModelService:
    device_label = "CPU"

    def __init__(self) -> None:
        self.upscale_calls = 0
        self.install_calls = 0

    def install_status(self) -> dict[str, object]:
        return {"status": "success", "installed": True, "loaded": True, "progress": 100, "message": "ok", "error": None}

    def is_installed(self) -> bool:
        return True

    def start_install(self) -> dict[str, object]:
        self.install_calls += 1
        return self.install_status()

    def model_specs(self) -> list[dict[str, str]]:
        return [{"key": "general", "name": "fake-real-esrgan", "role": "测试", "filename": "fake.pth"}]

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


class FakeCharacterRigModelService:
    device_label = "CPU"

    def __init__(self) -> None:
        self.describe_calls = 0
        self.detect_calls = 0
        self.refine_calls = 0
        self.install_calls = 0

    def install_status(self) -> dict[str, object]:
        return {"status": "success", "installed": True, "loaded": True, "progress": 100, "message": "ok", "error": None}

    def is_installed(self) -> bool:
        return True

    def start_install(self) -> dict[str, object]:
        self.install_calls += 1
        return self.install_status()

    def model_specs(self) -> list[dict[str, str]]:
        return [{"key": "florence", "name": "fake-florence", "role": "测试", "model_id": "fake"}]

    def describe_parts(self, image: Image.Image, parameters: dict[str, object]) -> CharacterRigHints:
        self.describe_calls += 1
        return CharacterRigHints(description="head and torso", candidate_keys=[])

    def detect_parts(self, image: Image.Image, candidate_keys: list[str], parameters: dict[str, object]) -> list[CharacterRigDetection]:
        self.detect_calls += 1
        return [CharacterRigDetection(key="head", label="head", bbox=[2, 2, 12, 12], score=0.9)]

    def refine_bbox(self, image: Image.Image, bbox: list[int], alpha: np.ndarray, parameters: dict[str, object]) -> np.ndarray:
        self.refine_calls += 1
        x, y, width, height = bbox
        mask = np.zeros((image.height, image.width), dtype=np.uint8)
        mask[y : y + height, x : x + width] = 255
        return mask

    def model_report(self) -> dict[str, str]:
        return {"florence": "fake", "grounding_dino": "fake", "sam": "fake"}


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


def test_community_serves_web_dist_on_same_port(tmp_path: Path) -> None:
    with make_client_with_web_dist(tmp_path) as client:
        root_response = client.get("/")
        logo_response = client.get("/gameknife-logo.png")
        spa_response = client.get("/tools/background-remove")
        api_response = client.get("/api/health")

    assert root_response.status_code == 200
    assert "GameKnife" in root_response.text
    assert logo_response.status_code == 200
    assert logo_response.headers["content-type"] == "image/png"
    assert spa_response.status_code == 200
    assert api_response.status_code == 200


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
    assert response.json()["runtime"]["python_version"]
    assert response.json()["birefnet"]["model_id"]
    assert response.json()["stable_audio"]["base_url_configured"] is False
    assert response.json()["stable_audio"]["install_status"]["status"] == "unconfigured"
    assert "models" not in response.json()


def test_aggregate_model_install_status_endpoint_is_not_exposed(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/settings/models/install-status")

    assert response.status_code == 404


def test_job_history_filters_by_created_range(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        repository = client.app.state.repository
        asset_path = tmp_path / "storage" / "outputs" / "finished.png"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(make_png_bytes())
        asset = AssetRecord(
            id="history-asset",
            workspace_id="local",
            created_by="anonymous",
            kind="background_remove",
            original_name="hero.png",
            path=str(asset_path),
            mime_type="image/png",
            size_bytes=asset_path.stat().st_size,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        repository.create_asset(asset)
        for job_id, created_at in (("old-job", "2026-01-01T00:00:00Z"), ("new-job", "2026-02-01T00:00:00Z")):
            repository.create_job(
                JobRecord(
                    id=job_id,
                    workspace_id="local",
                    created_by="anonymous",
                    job_type="background_remove",
                    status="success",
                    input_asset_id=asset.id,
                    parameters_json="{}",
                    result_json=json.dumps({"output_assets": [{"id": asset.id, "url": f"/api/assets/{asset.id}"}]}),
                    device="CPU",
                    duration_ms=1,
                    error_message=None,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )

        response = client.get(
            "/api/jobs/history",
            params={"page": 1, "page_size": 12, "category": "background", "created_from": "2026-02-01T00:00:00Z", "downloadable": "true"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert [item["id"] for item in data["items"]] == ["new-job"]


def test_birefnet_install_status_is_readable_without_login(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/settings/birefnet/install")

    assert response.status_code == 200
    assert "installed" in response.json()


def test_birefnet_install_can_start_without_login(tmp_path: Path) -> None:
    fake_birefnet = FakeBiRefNetService()
    with make_client(tmp_path) as client:
        # 模型下载按钮调用 POST，测试里替换成 Fake 服务，避免验收接口时触发真实模型下载。
        client.app.state.birefnet = fake_birefnet
        response = client.post("/api/settings/birefnet/install")

    assert response.status_code == 200
    assert response.json()["installed"] is True
    assert fake_birefnet.install_calls == 1


def test_character_rig_model_install_status_is_readable_without_login(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/settings/character-rig-models/install")

    assert response.status_code == 200
    assert "installed" in response.json()


def test_character_rig_model_install_can_start_without_login(tmp_path: Path) -> None:
    fake_models = FakeCharacterRigModelService()
    with make_client(tmp_path) as client:
        # Community 本地部署没有账号体系，设置页安装模型必须能直接触发后端本地管理员能力。
        client.app.state.character_rig_models = fake_models
        response = client.post("/api/settings/character-rig-models/install")

    assert response.status_code == 200
    assert response.json()["installed"] is True
    assert fake_models.install_calls == 1


def test_upscale_model_install_status_is_readable_without_login(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/settings/upscale-models/install")

    assert response.status_code == 200
    assert "installed" in response.json()


def test_upscale_model_install_can_start_without_login(tmp_path: Path) -> None:
    fake_upscale = FakeUpscaleModelService()
    with make_client(tmp_path) as client:
        # AI 超分模型和 BiRefNet 一样由设置页显式安装，任务阶段不能依赖隐式下载兜底。
        client.app.state.upscale_models = fake_upscale
        response = client.post("/api/settings/upscale-models/install")

    assert response.status_code == 200
    assert response.json()["installed"] is True
    assert fake_upscale.install_calls == 1


def test_stable_audio_install_can_start_without_login_when_service_configured(tmp_path: Path) -> None:
    settings = CommunitySettings(
        storage_root=tmp_path / "storage",
        database_path=tmp_path / "storage" / "gameknife.sqlite3",
        cors_origins=["*"],
        stable_audio_base_url="http://stable-audio",
    )
    app = create_app(settings)
    fake_stable_audio = FakeStableAudioService()
    with TestClient(app) as client:
        app.state.stable_audio = fake_stable_audio
        response = client.post("/api/settings/stable-audio/install")

    assert response.status_code == 200
    assert response.json()["installed"] is True
    assert fake_stable_audio.install_calls == 1


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


def test_pixel_upscale_does_not_call_ai_model_service(tmp_path: Path) -> None:
    fake_upscale = FakeUpscaleModelService()
    with make_client(tmp_path) as client:
        client.app.state.upscale_models = fake_upscale
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sprite.png", make_png_bytes(), "image/png")},
        )
        created = client.post(
            "/api/jobs/upscale",
            json={"input_asset_id": upload.json()["id"], "parameters": {"style": "pixel", "scale": 2}},
        )
        job = client.get(f"/api/jobs/{created.json()['id']}").json()

    assert created.status_code == 200
    assert job["status"] == "success"
    assert job["result"]["model"] == "nearest-neighbor"
    assert fake_upscale.upscale_calls == 0


def test_ai_upscale_job_uses_installed_model_service(tmp_path: Path) -> None:
    fake_upscale = FakeUpscaleModelService()
    with make_client(tmp_path) as client:
        client.app.state.upscale_models = fake_upscale
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sprite.png", make_png_bytes(), "image/png")},
        )
        created = client.post(
            "/api/jobs/upscale",
            json={"input_asset_id": upload.json()["id"], "parameters": {"style": "general", "scale": 4, "denoise": 1, "tile_size": 128}},
        )
        job_id = created.json()["id"]
        job = client.get(f"/api/jobs/{job_id}").json()
        output_asset = job["result"]["output_assets"][0]
        output = client.get(output_asset["url"])

    assert created.status_code == 200
    assert job["status"] == "success"
    assert job["result"]["output_size"] == [8, 8]
    assert job["result"]["model"] == "fake-real-esrgan"
    assert job["device"] == "CPU"
    assert fake_upscale.upscale_calls == 1
    assert output.status_code == 200
    assert Image.open(BytesIO(output.content)).size == (8, 8)


def test_background_remove_requires_installed_birefnet(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sprite.png", make_png_bytes(), "image/png")},
        )
        response = client.post(
            "/api/jobs/background-remove",
            json={"input_asset_id": upload.json()["id"], "parameters": {}},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "BiRefNet 模型尚未下载安装，请先到设置页下载安装模型文件。"


def test_background_remove_job_creates_png_asset_with_fake_birefnet(tmp_path: Path) -> None:
    app = create_app(
        CommunitySettings(
            storage_root=tmp_path / "storage",
            database_path=tmp_path / "storage" / "gameknife.sqlite3",
            cors_origins=["*"],
        )
    )
    fake_birefnet = FakeBiRefNetService()
    with TestClient(app) as client:
        app.state.birefnet = fake_birefnet
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sprite.png", make_png_bytes(), "image/png")},
        )
        created = client.post(
            "/api/jobs/background-remove",
            json={"input_asset_id": upload.json()["id"], "parameters": {"alpha_smoothing": 0}},
        )
        job = client.get(f"/api/jobs/{created.json()['id']}").json()
        output = client.get(job["result"]["output_assets"][0]["url"])

    assert created.status_code == 200
    assert job["status"] == "success"
    assert job["type"] == "background_remove"
    assert output.status_code == 200
    with Image.open(BytesIO(output.content)) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 0
    assert fake_birefnet.predict_calls == 1


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


def test_asset_board_region_does_not_call_birefnet(tmp_path: Path) -> None:
    app = create_app(
        CommunitySettings(
            storage_root=tmp_path / "storage",
            database_path=tmp_path / "storage" / "gameknife.sqlite3",
            cors_origins=["*"],
        )
    )
    fake_birefnet = FakeBiRefNetService()
    with TestClient(app) as client:
        app.state.birefnet = fake_birefnet
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sheet.png", make_asset_board_png_bytes(), "image/png")},
        )
        created = client.post(
            "/api/jobs/asset-board/regions",
            json={"input_asset_id": upload.json()["id"], "parameters": {"min_component_area": 4, "alpha_threshold": 16}},
        )
        job = client.get(f"/api/jobs/{created.json()['id']}").json()

    assert job["status"] == "success"
    assert fake_birefnet.predict_calls == 0


def test_asset_board_cutout_job_creates_cutout_asset_with_fake_birefnet(tmp_path: Path) -> None:
    app = create_app(
        CommunitySettings(
            storage_root=tmp_path / "storage",
            database_path=tmp_path / "storage" / "gameknife.sqlite3",
            cors_origins=["*"],
        )
    )
    fake_birefnet = FakeBiRefNetService()
    with TestClient(app) as client:
        app.state.birefnet = fake_birefnet
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sheet.png", make_asset_board_png_bytes(), "image/png")},
        )
        created = client.post(
            "/api/jobs/asset-board/cutout",
            json={"input_asset_id": upload.json()["id"], "parameters": {}},
        )
        job = client.get(f"/api/jobs/{created.json()['id']}").json()
        output = client.get(job["result"]["cutout_url"])

    assert created.status_code == 200
    assert job["status"] == "success"
    assert job["type"] == "asset_board_cutout"
    assert job["result"]["cutout_asset_id"] == job["result"]["output_assets"][0]["id"]
    assert output.status_code == 200
    assert output.content.startswith(b"\x89PNG")
    assert fake_birefnet.predict_calls == 1


def test_asset_board_refine_job_refreshes_components(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sheet.png", make_asset_board_png_bytes(), "image/png")},
        )
        created = client.post(
            "/api/jobs/asset-board/refine",
            json={"cutout_asset_id": upload.json()["id"], "parameters": {"min_component_area": 4, "alpha_threshold": 16}},
        )
        job = client.get(f"/api/jobs/{created.json()['id']}").json()

    assert created.status_code == 200
    assert job["status"] == "success"
    assert job["type"] == "asset_board_region_refine"
    assert job["result"]["component_count"] == 2
    assert job["result"]["cutout_asset_id"] == upload.json()["id"]


def test_asset_board_export_job_creates_zip_asset(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sheet.png", make_asset_board_png_bytes(), "image/png")},
        )
        created = client.post(
            "/api/jobs/asset-board/export",
            json={
                "cutout_asset_id": upload.json()["id"],
                "selected_component_ids": [],
                "components": [],
                "parameters": {"min_component_area": 4, "alpha_threshold": 16},
            },
        )
        job = client.get(f"/api/jobs/{created.json()['id']}").json()
        output = client.get(job["result"]["output_assets"][0]["url"])

    assert created.status_code == 200
    assert job["status"] == "success"
    assert job["type"] == "asset_board_export"
    assert job["result"]["selected_count"] == 2
    assert output.status_code == 200
    with zipfile.ZipFile(BytesIO(output.content)) as archive:
        assert len(archive.namelist()) == 2


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


def test_sequence_export_spine_zip(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        imported = client.post(
            "/api/sequences/import",
            data={"name": "walk", "fps": "12"},
            files=[
                ("files", ("walk_001.png", make_sequence_frame_bytes((255, 0, 0, 255)), "image/png")),
                ("files", ("walk_002.png", make_sequence_frame_bytes((0, 0, 255, 255)), "image/png")),
            ],
        ).json()
        sequence_id = imported["id"]
        export_created = client.post(f"/api/sequences/{sequence_id}/export/spine", json={"parameters": {}})
        export_job = client.get(f"/api/jobs/{export_created.json()['id']}").json()
        archive_response = client.get(export_job["result"]["output_assets"][0]["url"])

    assert export_created.status_code == 200
    assert export_job["status"] == "success"
    assert export_job["type"] == "sequence_export_spine"
    with zipfile.ZipFile(BytesIO(archive_response.content)) as archive:
        names = set(archive.namelist())
    assert "walk.png" in names
    assert "walk.atlas" in names
    assert "walk.json" in names


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


def test_video_to_sequence_background_remove_uses_installed_birefnet(tmp_path: Path) -> None:
    fake_birefnet = FakeBiRefNetService()
    with make_client(tmp_path) as client:
        # 视频抽帧是本地能力，remove_background 才需要模型；这里替换为已安装 Fake 服务，验证显式依赖链路可执行。
        client.app.state.birefnet = fake_birefnet
        upload = client.post(
            "/api/assets/videos",
            files={"file": ("walk.avi", make_video_bytes(tmp_path), "video/avi")},
        )
        created = client.post(
            "/api/sequences/from-video",
            json={
                "video_asset_id": upload.json()["id"],
                "name": "walk-video",
                "fps": 4,
                "max_frames": 3,
                "remove_background": True,
                "parameters": {"alpha_smoothing": 0, "alpha_threshold": 24, "output_size": 128, "loop": False, "stabilize": True},
            },
        )
        job = client.get(f"/api/jobs/{created.json()['id']}").json()
        sequence = client.get(f"/api/sequences/{job['result']['sequence_id']}").json()
        frame_asset = client.get(sequence["frames"][0]["source_url"])
        preview_asset = client.get(sequence["frames"][0]["preview_url"])

    assert upload.status_code == 200
    assert created.status_code == 200
    assert job["status"] == "success"
    assert job["type"] == "sequence_video_to_frames"
    assert job["result"]["frame_count"] == 3
    assert job["result"]["consistency_report"]["stabilize"] is True
    assert sequence["frame_count"] == 3
    assert sequence["loop"] is False
    assert sequence["canvas_width"] == 128
    assert sequence["canvas_height"] == 128
    assert sequence["frames"][0]["processed_asset_id"]
    assert fake_birefnet.predict_calls == 3
    with Image.open(BytesIO(frame_asset.content)) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 0
    with Image.open(BytesIO(preview_asset.content)) as image:
        assert image.size == (128, 128)


def test_video_generation_settings_save_test_and_mask_secret(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        saved = client.patch(
            "/api/settings/video-generation",
            json={"provider": "seedance", "base_url": "https://ark.example.com", "api_key": "sk-1234567890"},
        )
        tested = client.post(
            "/api/settings/video-generation/test",
            json={"provider": "seedance", "base_url": "https://ark.example.com"},
        )
        settings = client.get("/api/settings").json()

    assert saved.status_code == 200
    assert saved.json()["provider"] == "seedance"
    assert saved.json()["api_key_configured"] is True
    assert saved.json()["masked_api_key"] == "sk-1****7890"
    assert tested.status_code == 200
    assert tested.json()["ok"] is True
    assert settings["video_generation"]["api_key_configured"] is True


def test_video_generation_requires_confirmation_and_config(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        upload = client.post(
            "/api/assets/images",
            files={"file": ("hero.png", make_transparent_png_bytes(), "image/png")},
        ).json()
        not_confirmed = client.post(
            "/api/sequences/generate-from-image",
            json={"input_asset_id": upload["id"], "confirmed_external_api": False},
        )
        not_configured = client.post(
            "/api/sequences/generate-from-image",
            json={"input_asset_id": upload["id"], "confirmed_external_api": True},
        )

    assert not_confirmed.status_code == 400
    assert not_confirmed.json()["detail"] == "请先确认调用外部视频生成 API。"
    assert not_configured.status_code == 409
    assert not_configured.json()["detail"] == "视频生成 API 缺少 API Key。"


def test_video_generation_job_creates_video_asset(tmp_path: Path, monkeypatch) -> None:
    def fake_generate(self: VideoGenerationClient, image_path: Path, output_path: Path, parameters: dict) -> VideoGenerationResult:
        assert image_path.is_file()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake mp4")
        return VideoGenerationResult(
            external_task_id="external-1",
            video_url="https://example.com/video.mp4",
            output_path=output_path,
            provider="seedance",
            final_response={"status": "succeeded"},
        )

    monkeypatch.setattr(VideoGenerationClient, "generate_video", fake_generate)
    with make_client(tmp_path) as client:
        client.patch(
            "/api/settings/video-generation",
            json={"provider": "seedance", "base_url": "https://ark.example.com", "api_key": "sk-1234567890"},
        )
        upload = client.post(
            "/api/assets/images",
            files={"file": ("hero.png", make_transparent_png_bytes(), "image/png")},
        ).json()
        created = client.post(
            "/api/sequences/generate-from-image",
            json={
                "input_asset_id": upload["id"],
                "action": "idle",
                "duration": 2,
                "resolution": "720P",
                "confirmed_external_api": True,
            },
        )
        job = client.get(f"/api/jobs/{created.json()['id']}").json()
        video = client.get(job["result"]["video_url"])

    assert created.status_code == 200
    assert job["status"] == "success"
    assert job["type"] == "sequence_generate_video"
    assert job["result"]["external_task_id"] == "external-1"
    assert job["result"]["provider"] == "seedance"
    assert job["result"]["video_asset_id"]
    assert job["result"]["output_assets"][0]["url"] == job["result"]["video_url"]
    assert video.status_code == 200
    assert video.content == b"fake mp4"
    with sqlite3.connect(tmp_path / "storage" / "gameknife.sqlite3") as connection:
        row = connection.execute(
            "SELECT kind, mime_type FROM assets WHERE id = ?",
            (job["result"]["video_asset_id"],),
        ).fetchone()
    assert row == ("sequence_video", "video/mp4")


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


def test_character_rig_opaque_source_uses_installed_model_service(tmp_path: Path) -> None:
    fake_models = FakeCharacterRigModelService()
    with make_client(tmp_path) as client:
        client.app.state.character_rig_models = fake_models
        rig = client.post(
            "/api/character-rigs/import",
            data={"name": "opaque"},
            files={"file": ("opaque.png", make_opaque_character_png_bytes(), "image/png")},
        ).json()
        created = client.post(
            f"/api/character-rigs/{rig['id']}/analyze",
            json={"parameters": {"min_mask_area": 16}},
        )
        job = client.get(f"/api/jobs/{created.json()['id']}").json()
        analyzed = client.get(f"/api/character-rigs/{rig['id']}").json()
        part = analyzed["parts"][0]
        part_asset = client.get(part["part_url"])

    assert created.status_code == 200
    assert job["status"] == "success"
    assert job["result"]["part_count"] == 1
    assert job["result"]["models"]["sam"] == "fake"
    assert analyzed["part_count"] == 1
    assert part["semantic_type"] == "head"
    assert part_asset.status_code == 200
    assert fake_models.describe_calls == 1
    assert fake_models.detect_calls == 1
    assert fake_models.refine_calls == 1
