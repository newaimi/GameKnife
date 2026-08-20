from __future__ import annotations

import json
from pathlib import Path

from gameknife_api import video_generation
from gameknife_api.video_generation import (
    VideoGenerationClient,
    VideoGenerationPollResult,
    VideoGenerationProviderAdapter,
    VideoGenerationSubmission,
)
from PIL import Image


def test_video_provider_adapter_submits_and_polls_one_request_per_call(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "hero.png"
    Image.new("RGBA", (32, 32), (255, 0, 0, 128)).save(image_path)
    responses = iter(
        [
            {"id": "task-1"},
            {"status": "running"},
            {"status": "succeeded", "content": {"video_url": "https://example.com/video.mp4"}},
        ]
    )
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, url: str, _config: dict, _body: dict | None) -> dict:
        calls.append((method, url))
        return next(responses)

    monkeypatch.setattr(video_generation, "_request_json", fake_request)
    adapter = VideoGenerationProviderAdapter(
        {
            "provider": "seedance",
            "base_url": "https://ark.example.com",
            "api_key": "provider-secret",
            "model": "seedance-test",
        }
    )

    submitted = adapter.submit(image_path, {"prompt": "idle", "duration": 2, "resolution": "720P"})
    pending = adapter.poll_once(submitted.external_task_id)
    succeeded = adapter.poll_once(submitted.external_task_id)

    assert submitted.external_task_id == "task-1"
    assert pending.state == "pending"
    assert succeeded.state == "succeeded"
    assert succeeded.video_url == "https://example.com/video.mp4"
    assert [method for method, _url in calls] == ["POST", "GET", "GET"]


def test_community_client_keeps_in_process_polling_and_download_behavior(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "hero.png"
    output_path = tmp_path / "generated.mp4"
    Image.new("RGBA", (32, 32), (0, 0, 255, 255)).save(image_path)
    repository = _SettingsRepository(
        {
            "provider": "aliyun_dashscope",
            "base_url": "https://dashscope.example.com",
            "api_key": "provider-secret",
        }
    )
    poll_results = iter(
        [
            VideoGenerationPollResult("pending", "RUNNING", None, None, {"output": {"task_status": "RUNNING"}}),
            VideoGenerationPollResult(
                "succeeded",
                "SUCCEEDED",
                "https://example.com/video.mp4",
                None,
                {"output": {"task_status": "SUCCEEDED", "video_url": "https://example.com/video.mp4"}},
            ),
        ]
    )
    poll_count = 0

    def fake_submit(_self, _image_path: Path, _parameters: dict) -> VideoGenerationSubmission:
        return VideoGenerationSubmission("task-1", "aliyun_dashscope", {"output": {"task_id": "task-1"}})

    def fake_poll(_self, _external_task_id: str) -> VideoGenerationPollResult:
        nonlocal poll_count
        poll_count += 1
        return next(poll_results)

    def fake_download(_self, _video_url: str, target: Path) -> Path:
        target.write_bytes(b"fake mp4")
        return target

    monkeypatch.setattr(VideoGenerationProviderAdapter, "submit", fake_submit)
    monkeypatch.setattr(VideoGenerationProviderAdapter, "poll_once", fake_poll)
    monkeypatch.setattr(VideoGenerationProviderAdapter, "download", fake_download)
    monkeypatch.setattr(video_generation.time, "sleep", lambda _seconds: None)

    result = VideoGenerationClient(repository).generate_video(image_path, output_path, {"action": "idle"})

    assert result.external_task_id == "task-1"
    assert result.video_url == "https://example.com/video.mp4"
    assert result.output_path.read_bytes() == b"fake mp4"
    assert poll_count == 2


class _SettingsRepository:
    def __init__(self, config: dict):
        self.config = config

    def read_setting(self, _key: str, _default: str = "") -> str:
        return json.dumps(self.config)
