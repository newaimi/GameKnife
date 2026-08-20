from __future__ import annotations

import json
import sqlite3
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory as RealTemporaryDirectory
from types import SimpleNamespace
import zipfile

import cv2
import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

import gameknife_api.routes as api_routes
import gameknife_api.job_service as job_service
from community_api.main import create_app
from gameknife_api.deps import CommunitySettings
from gameknife_api.video_generation import VideoGenerationClient, VideoGenerationResult
from gameknife_core import AssetRecord, JobOutputAssetRecord, JobRecord


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


class PresignedDownloadStorage:
    def __init__(self, download_url: str) -> None:
        self.download_url = download_url
        self.request: tuple[str, str, str, int] | None = None

    def local_path(self, key: str) -> None:
        return None

    def create_download_url(self, key: str, filename: str, mime_type: str, expires_seconds: int) -> str:
        self.request = (key, filename, mime_type, expires_seconds)
        return self.download_url


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
        missing_api_response = client.get("/api")

    assert root_response.status_code == 200
    assert "GameKnife" in root_response.text
    assert logo_response.status_code == 200
    assert logo_response.headers["content-type"] == "image/png"
    assert spa_response.status_code == 200
    assert api_response.status_code == 200
    assert missing_api_response.status_code == 404
    assert missing_api_response.json()["detail"] == "接口不存在。"


def test_job_runtime_reports_detected_cuda_device(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        api_routes,
        "_read_runtime_info",
        lambda: {
            "cuda_available": True,
            "current_gpu_name": "NVIDIA Test GPU",
            "mps_available": False,
        },
    )

    with make_client(tmp_path) as client:
        response = client.get("/api/jobs/runtime")

    assert response.status_code == 200
    assert response.json() == {"device": "NVIDIA Test GPU"}


@pytest.mark.parametrize(
    ("runtime", "expected"),
    [
        ({"cuda_available": True, "current_gpu_name": None, "mps_available": False}, "CUDA"),
        ({"cuda_available": False, "current_gpu_name": None, "mps_available": True}, "MPS"),
        ({"cuda_available": False, "current_gpu_name": None, "mps_available": False}, "CPU"),
    ],
)
def test_runtime_device_label_covers_supported_backends(runtime: dict[str, object], expected: str) -> None:
    assert api_routes._runtime_device_label(runtime) == expected


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


def test_asset_download_redirects_to_presigned_provider_url(tmp_path: Path) -> None:
    provider = PresignedDownloadStorage("https://storage.example.test/presigned-object")
    with make_client(tmp_path) as client:
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sprite.png", make_png_bytes(), "image/png")},
        ).json()
        client.app.state.storage = provider
        response = client.get(upload["url"], follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == provider.download_url
    assert provider.request is not None
    assert provider.request[1:] == ("sprite.png", "image/png", 300)


def test_asset_delete_removes_unreferenced_record_and_object(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        uploaded = client.post(
            "/api/assets/images",
            files={"file": ("delete.png", make_png_bytes(), "image/png")},
        ).json()
        asset = client.app.state.repository.get_asset_for_workspace(uploaded["id"], "local")
        assert asset is not None
        object_path = client.app.state.storage.local_path(asset.path)

        deleted = client.delete(uploaded["url"])
        missing = client.get(uploaded["url"])

    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert object_path is not None and not object_path.exists()


def test_asset_delete_returns_reference_summary_for_job_and_sequence_owners(tmp_path: Path) -> None:
    timestamp = "2026-01-01T00:00:00+00:00"
    with make_client(tmp_path) as client:
        input_asset = client.post(
            "/api/assets/images",
            files={"file": ("input.png", make_png_bytes(), "image/png")},
        ).json()
        output_asset = client.post(
            "/api/assets/images",
            files={"file": ("output.png", make_png_bytes(), "image/png")},
        ).json()
        sequence = client.post(
            "/api/sequences/import",
            data={"name": "asset-reference", "fps": "8"},
            files=[("files", ("frame_001.png", make_sequence_frame_bytes((255, 0, 0, 255)), "image/png"))],
        ).json()
        sequence_asset = sequence["frames"][0]
        repository = client.app.state.repository
        for job_id in ("input-job", "output-job"):
            repository.create_job(
                JobRecord(
                    id=job_id,
                    workspace_id="local",
                    created_by="anonymous",
                    job_type="asset_board_region_detect",
                    status="pending",
                    input_asset_id=input_asset["id"],
                    parameters_json="{}",
                    result_json="{}",
                    device=None,
                    duration_ms=0,
                    error_message=None,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
        repository.create_job_output_asset(
            JobOutputAssetRecord(
                id="output-relation",
                workspace_id="local",
                created_by="anonymous",
                job_id="output-job",
                asset_id=output_asset["id"],
                created_at=timestamp,
            )
        )

        input_blocked = client.delete(input_asset["url"])
        output_blocked = client.delete(output_asset["url"])
        sequence_blocked = client.delete(sequence_asset["source_url"])

    assert input_blocked.status_code == 409
    assert "input-job" in input_blocked.json()["detail"]["references"][0]["input_job_ids"]
    assert output_blocked.status_code == 409
    assert output_blocked.json()["detail"]["references"][0]["output_job_ids"] == ["output-job"]
    assert sequence_blocked.status_code == 409
    assert sequence_blocked.json()["detail"]["references"][0]["source_sequence_frame_ids"]


def test_asset_delete_keeps_http_success_when_object_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with make_client(tmp_path) as client:
        uploaded = client.post(
            "/api/assets/images",
            files={"file": ("orphan.png", make_png_bytes(), "image/png")},
        ).json()

        def reject_delete(_key: str) -> None:
            raise OSError("object delete failed")

        monkeypatch.setattr(client.app.state.storage, "delete_object", reject_delete)
        deleted = client.delete(uploaded["url"])
        missing = client.get(uploaded["url"])

    assert deleted.status_code == 204
    assert missing.status_code == 404


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
                    status="pending",
                    input_asset_id=asset.id,
                    parameters_json="{}",
                    result_json="{}",
                    device=None,
                    duration_ms=0,
                    error_message=None,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
            repository.create_job_output_asset(
                JobOutputAssetRecord(
                    id=f"{job_id}-output",
                    workspace_id="local",
                    created_by="anonymous",
                    job_id=job_id,
                    asset_id=asset.id,
                    created_at=created_at,
                )
            )
            assert repository.claim_job_for_workspace(job_id, "local", updated_at=created_at) is True
            repository.update_job(
                job_id,
                "local",
                status="success",
                result_json=json.dumps({"output_assets": [{"id": asset.id, "url": f"/api/assets/{asset.id}"}]}),
                device="CPU",
                duration_ms=1,
                updated_at=created_at,
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


def test_model_status_read_uses_workflow_permission_without_granting_settings_write() -> None:
    actions: list[str] = []

    class RecordingPermissionChecker:
        def require(self, action: str, resource: object | None = None) -> None:
            del resource
            actions.append(action)

    context = SimpleNamespace(permissions=RecordingPermissionChecker())

    api_routes._require_model_status_read(context, "read_birefnet_install")
    api_routes._require_settings_manage(context, "install_birefnet")

    assert actions == ["jobs.create", "settings.manage"]


def test_birefnet_install_can_start_without_login(tmp_path: Path) -> None:
    fake_birefnet = FakeBiRefNetService()
    with make_client(tmp_path) as client:
        # 模型下载按钮调用 POST，测试里替换成 Fake 服务，避免验收接口时触发真实模型下载。
        client.app.state.birefnet = fake_birefnet
        response = client.post("/api/settings/birefnet/install")

    assert response.status_code == 200
    assert response.json()["installed"] is True
    assert fake_birefnet.install_calls == 1


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


def test_deleting_result_only_job_never_deletes_its_input_asset(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sheet.png", make_asset_board_png_bytes(), "image/png")},
        )
        created = client.post(
            "/api/jobs/asset-board/refine",
            json={
                "cutout_asset_id": upload.json()["id"],
                "parameters": {"min_component_area": 4, "alpha_threshold": 16},
            },
        )

        deleted = client.delete(f"/api/jobs/{created.json()['id']}")
        retained_input = client.get(upload.json()["url"])

    assert deleted.status_code == 204
    assert retained_input.status_code == 200


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


def test_job_delete_returns_reference_summary_until_sequence_is_detached(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        upload = client.post(
            "/api/assets/images",
            files={"file": ("sprite.png", make_png_bytes(), "image/png")},
        )
        created = client.post(
            "/api/jobs/upscale",
            json={"input_asset_id": upload.json()["id"], "parameters": {"style": "pixel", "scale": 2}},
        )
        job = client.get(f"/api/jobs/{created.json()['id']}").json()
        output_asset = job["result"]["output_assets"][0]
        sequence = client.app.state.repository.create_sequence_with_frames(
            workspace_id="local",
            created_by="anonymous",
            name="shared-output",
            fps=12,
            loop=True,
            clean_parameters={},
            frames=[
                {
                    "source_asset_id": output_asset["id"],
                    "original_name": "sprite_upscale.png",
                    "width": 4,
                    "height": 4,
                    "bbox": [0, 0, 4, 4],
                }
            ],
            created_at="2026-01-01T00:00:00+00:00",
        )

        blocked = client.delete(f"/api/jobs/{job['id']}")
        retained_before_detach = client.get(output_asset["url"])
        detached = client.delete(f"/api/sequences/{sequence['id']}")
        retained_after_detach = client.get(output_asset["url"])
        deleted = client.delete(f"/api/jobs/{job['id']}")
        removed_output = client.get(output_asset["url"])

    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "RESOURCE_REFERENCED"
    references = blocked.json()["detail"]["references"]
    assert references[0]["asset_id"] == output_asset["id"]
    assert len(references[0]["source_sequence_frame_ids"]) == 1
    assert retained_before_detach.status_code == 200
    assert detached.status_code == 204
    assert retained_after_detach.status_code == 200
    assert deleted.status_code == 204
    assert removed_output.status_code == 404


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


def test_sequence_import_removes_object_when_asset_persistence_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with make_client(tmp_path) as client:
        def reject_asset_create(_asset: AssetRecord) -> None:
            raise RuntimeError("asset insert failed")

        monkeypatch.setattr(client.app.state.repository, "create_asset", reject_asset_create)
        response = client.post(
            "/api/sequences/import",
            data={"name": "failed-import", "fps": "12"},
            files=[("files", ("failed_001.png", make_sequence_frame_bytes((255, 0, 0, 255)), "image/png"))],
        )
        stored_objects = list(client.app.state.storage.assets_dir.iterdir())

    assert response.status_code == 500
    assert response.json()["detail"] == "序列帧导入失败。"
    assert stored_objects == []


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
    assert isinstance(clean_job["result"]["sequence_revision"], int)
    assert all(frame["processed_asset_id"] for frame in cleaned_sequence["frames"])
    assert {
        "sequence_id",
        "sequence_revision",
        "frame_count",
        "canvas_width",
        "canvas_height",
    }.isdisjoint(cleaned_sequence["clean_parameters"])
    assert export_job["status"] == "success"
    assert export_job["type"] == "sequence_export_frames"
    with zipfile.ZipFile(BytesIO(archive_response.content)) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "spritesheet.png" in names


def test_cleaning_sequence_remains_readable_and_rejects_a_second_clean_job(tmp_path: Path) -> None:
    timestamp = "2026-01-01T00:00:00+00:00"
    with make_client(tmp_path) as client:
        imported = client.post(
            "/api/sequences/import",
            data={"name": "locked", "fps": "8"},
            files=[("files", ("locked_001.png", make_sequence_frame_bytes((255, 0, 0, 255)), "image/png"))],
        ).json()
        sequence_id = imported["id"]
        input_asset_id = imported["frames"][0]["source_asset_id"]
        repository = client.app.state.repository
        stored_sequence = repository.get_sequence_for_workspace(sequence_id, "local")
        assert stored_sequence is not None
        sequence_revision = int(stored_sequence["revision"])
        repository.create_job(
            JobRecord(
                id="active-clean-job",
                workspace_id="local",
                created_by="anonymous",
                job_type="sequence_clean",
                status="pending",
                input_asset_id=input_asset_id,
                parameters_json=json.dumps({"sequence_id": sequence_id, "sequence_revision": 0}),
                result_json="{}",
                device=None,
                duration_ms=0,
                error_message=None,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        assert repository.claim_job_for_workspace("active-clean-job", "local", updated_at=timestamp) is True
        assert repository.claim_sequence_for_job(
            sequence_id,
            "local",
            "active-clean-job",
            sequence_revision,
            updated_at=timestamp,
        ) == sequence_revision

        readable = client.get(f"/api/sequences/{sequence_id}")
        rejected = client.post(f"/api/sequences/{sequence_id}/clean", json={"parameters": {}})

    assert readable.status_code == 200
    assert readable.json()["status"] == "cleaning"
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "序列帧正在处理中，请稍后重试。"


def test_sequence_clean_releases_claim_when_repository_read_fails_after_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timestamp = "2026-01-01T00:00:00+00:00"
    with make_client(tmp_path) as client:
        imported = client.post(
            "/api/sequences/import",
            data={"name": "read-failure", "fps": "8"},
            files=[("files", ("read_001.png", make_sequence_frame_bytes((255, 0, 0, 255)), "image/png"))],
        ).json()
        repository = client.app.state.repository
        sequence_id = imported["id"]
        repository.create_job(
            JobRecord(
                id="read-failure-job",
                workspace_id="local",
                created_by="anonymous",
                job_type="sequence_clean",
                status="pending",
                input_asset_id=imported["frames"][0]["source_asset_id"],
                parameters_json=json.dumps(
                    {
                        "sequence_id": sequence_id,
                        "sequence_revision": 0,
                        "frame_count": 1,
                        "canvas_width": imported["canvas_width"],
                        "canvas_height": imported["canvas_height"],
                    }
                ),
                result_json="{}",
                device=None,
                duration_ms=0,
                error_message=None,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )

        def reject_frame_read(*_args, **_kwargs):
            raise RuntimeError("frame read failed")

        monkeypatch.setattr(repository, "list_sequence_frames", reject_frame_read)
        client.app.state.job_execution_handlers["sequence_clean"]("read-failure-job", "local")

        stored_job = repository.get_job_for_workspace("read-failure-job", "local")
        with sqlite3.connect(tmp_path / "storage" / "gameknife.sqlite3") as connection:
            active_job_id, sequence_status = connection.execute(
                "SELECT active_job_id, status FROM sequences WHERE id = ?",
                (sequence_id,),
            ).fetchone()

    assert stored_job is not None and stored_job.status == "failed"
    assert stored_job.error_message == "frame read failed"
    assert active_job_id is None
    assert sequence_status == "ready"


def test_sequence_clean_restores_previous_frames_when_success_persistence_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with make_client(tmp_path) as client:
        imported = client.post(
            "/api/sequences/import",
            data={"name": "rollback", "fps": "8"},
            files=[
                ("files", ("rollback_001.png", make_sequence_frame_bytes((255, 0, 0, 255)), "image/png")),
                ("files", ("rollback_002.png", make_sequence_frame_bytes((0, 0, 255, 255)), "image/png")),
            ],
        ).json()
        sequence_id = imported["id"]
        client.post(f"/api/sequences/{sequence_id}/clean", json={"parameters": {"canvas_padding": 2}})
        previous = client.get(f"/api/sequences/{sequence_id}").json()
        previous_processed_ids = [frame["processed_asset_id"] for frame in previous["frames"]]
        with sqlite3.connect(tmp_path / "storage" / "gameknife.sqlite3") as connection:
            previous_asset_count = connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0]

        def reject_success(*args, **kwargs) -> None:
            raise RuntimeError("forced sequence success persistence failure")

        monkeypatch.setattr(client.app.state.repository, "finalize_sequence_clean_job", reject_success)
        created = client.post(f"/api/sequences/{sequence_id}/clean", json={"parameters": {"canvas_padding": 6}}).json()
        failed_job = client.get(f"/api/jobs/{created['id']}").json()
        restored = client.get(f"/api/sequences/{sequence_id}").json()
        with sqlite3.connect(tmp_path / "storage" / "gameknife.sqlite3") as connection:
            restored_asset_count = connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0]

    assert failed_job["status"] == "failed"
    assert failed_job["error_message"] == "forced sequence success persistence failure"
    assert [frame["processed_asset_id"] for frame in restored["frames"]] == previous_processed_ids
    assert restored["clean_parameters"] == previous["clean_parameters"]
    assert restored_asset_count == previous_asset_count


def test_sequence_clean_temporary_cleanup_failure_releases_claim_and_fails_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CleanupFailureTemporaryDirectory:
        def __init__(self, *args, **kwargs) -> None:
            self._temporary = RealTemporaryDirectory(*args, **kwargs)

        def __enter__(self) -> str:
            return self._temporary.__enter__()

        def __exit__(self, exc_type, exc_value, traceback) -> bool:
            self._temporary.__exit__(exc_type, exc_value, traceback)
            raise RuntimeError("temporary cleanup failed")

    with make_client(tmp_path) as client:
        imported = client.post(
            "/api/sequences/import",
            data={"name": "cleanup", "fps": "8"},
            files=[("files", ("cleanup_001.png", make_sequence_frame_bytes((255, 0, 0, 255)), "image/png"))],
        ).json()
        sequence_id = imported["id"]
        monkeypatch.setattr(job_service, "TemporaryDirectory", CleanupFailureTemporaryDirectory)

        created = client.post(f"/api/sequences/{sequence_id}/clean", json={"parameters": {}}).json()
        failed_job = client.get(f"/api/jobs/{created['id']}").json()
        restored = client.get(f"/api/sequences/{sequence_id}").json()
        with sqlite3.connect(tmp_path / "storage" / "gameknife.sqlite3") as connection:
            active_job_id, revision = connection.execute(
                "SELECT active_job_id, revision FROM sequences WHERE id = ?",
                (sequence_id,),
            ).fetchone()

    assert failed_job["status"] == "failed"
    assert failed_job["error_message"] == "temporary cleanup failed"
    assert restored["frames"][0]["processed_asset_id"] is None
    assert active_job_id is None
    assert revision == 0


def test_community_startup_recovery_removes_incomplete_job_objects(tmp_path: Path) -> None:
    timestamp = "2026-01-01T00:00:00+00:00"
    with make_client(tmp_path) as client:
        repository = client.app.state.repository
        storage = client.app.state.storage
        source_file = tmp_path / "recovery-input.png"
        output_file = tmp_path / "recovery-output.png"
        source_file.write_bytes(make_png_bytes())
        output_file.write_bytes(make_transparent_png_bytes())
        stored_source = storage.put_file("recovery-input", source_file.name, source_file)
        stored_output = storage.put_file("recovery-output", output_file.name, output_file)
        repository.create_asset(
            AssetRecord(
                id="recovery-input",
                workspace_id="local",
                created_by="anonymous",
                kind="image",
                original_name=source_file.name,
                path=stored_source.key,
                mime_type="image/png",
                size_bytes=stored_source.size_bytes,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        repository.create_asset(
            AssetRecord(
                id="recovery-output",
                workspace_id="local",
                created_by="anonymous",
                kind="background_removed",
                original_name=output_file.name,
                path=stored_output.key,
                mime_type="image/png",
                size_bytes=stored_output.size_bytes,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        repository.create_job(
            JobRecord(
                id="recovery-job",
                workspace_id="local",
                created_by="anonymous",
                job_type="background_remove",
                status="pending",
                input_asset_id="recovery-input",
                parameters_json="{}",
                result_json="{}",
                device=None,
                duration_ms=0,
                error_message=None,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        assert repository.claim_job_for_workspace("recovery-job", "local", updated_at=timestamp) is True
        repository.create_job_output_asset(
            JobOutputAssetRecord(
                id="recovery-job-output",
                workspace_id="local",
                created_by="anonymous",
                job_id="recovery-job",
                asset_id="recovery-output",
                created_at=timestamp,
            )
        )
        output_object = storage.local_path(stored_output.key)
        assert output_object is not None and output_object.exists()

    with make_client(tmp_path) as client:
        recovered_job = client.get("/api/jobs/recovery-job")
        removed_asset = client.get("/api/assets/recovery-output")

    assert recovered_job.status_code == 200
    assert recovered_job.json()["status"] == "failed"
    assert recovered_job.json()["error_message"] == "服务重启，未完成任务已终止。"
    assert removed_asset.status_code == 404
    assert output_object is not None and not output_object.exists()


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


def test_sequence_delete_continues_when_object_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted_keys: list[str] = []

    with make_client(tmp_path) as client:
        imported = client.post(
            "/api/sequences/import",
            data={"name": "delete-with-storage-error", "fps": "12"},
            files=[
                ("files", ("frame_001.png", make_sequence_frame_bytes((255, 0, 0, 255)), "image/png")),
                ("files", ("frame_002.png", make_sequence_frame_bytes((0, 0, 255, 255)), "image/png")),
            ],
        ).json()
        source_urls = [frame["source_url"] for frame in imported["frames"]]

        def reject_delete(key: str) -> None:
            deleted_keys.append(key)
            raise OSError("object delete failed")

        monkeypatch.setattr(client.app.state.storage, "delete_object", reject_delete)
        deleted = client.delete(f"/api/sequences/{imported['id']}")
        source_responses = [client.get(url) for url in source_urls]

    assert deleted.status_code == 204
    assert len(deleted_keys) == 2
    assert all(response.status_code == 404 for response in source_responses)


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


def test_commercial_edition_cannot_use_raw_video_secret_settings() -> None:
    context = SimpleNamespace(capabilities=SimpleNamespace(edition="commercial"))

    with pytest.raises(HTTPException) as caught:
        api_routes._require_community_video_settings(context)

    assert caught.value.status_code == 404


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
