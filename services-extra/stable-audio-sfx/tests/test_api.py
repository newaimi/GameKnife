from __future__ import annotations

import io
import queue
import sys
import wave
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main


def test_health() -> None:
    response = TestClient(main.app).get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "gameknife-stable-audio-sfx"


def test_generate_returns_wav(monkeypatch) -> None:
    monkeypatch.setattr(main, "model_files_cached", lambda: True)
    monkeypatch.setattr(main, "missing_runtime_dependencies", lambda: [])
    monkeypatch.setattr(main.StableAudioWorkerPool, "_generate", _fake_generate)
    client = TestClient(main.app)

    response = client.post(
        "/generate",
        json={"prompt": "coin pickup", "duration_seconds": 1, "steps": 20, "cfg_scale": 5},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["x-stable-audio-device"]
    assert response.content.startswith(b"RIFF")


def test_status_reports_missing_runtime_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(main, "model_files_cached", lambda: True)
    monkeypatch.setattr(main, "missing_runtime_dependencies", lambda: ["stable-audio-tools"])

    response = TestClient(main.app).get("/models/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["installed"] is False
    assert payload["model_files_cached"] is True
    assert payload["runtime_dependencies"]["missing"] == ["stable-audio-tools"]
    assert "stable-audio-tools" in payload["error"]


def test_generate_rejects_missing_runtime_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(main, "model_files_cached", lambda: True)
    monkeypatch.setattr(main, "missing_runtime_dependencies", lambda: ["stable-audio-tools"])

    response = TestClient(main.app).post("/generate", json={"prompt": "coin pickup"})

    assert response.status_code == 503
    assert "stable-audio-tools" in response.json()["detail"]


def test_model_files_cached_uses_local_snapshot(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def fake_snapshot_download(model_id: str, *, repo_type: str, local_files_only: bool) -> None:
        calls["model_id"] = model_id
        calls["repo_type"] = repo_type
        calls["local_files_only"] = local_files_only

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=fake_snapshot_download))

    assert main.model_files_cached() is True
    assert calls == {
        "model_id": main.MODEL_ID,
        "repo_type": "model",
        "local_files_only": True,
    }


def test_token_is_required_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(main, "SERVICE_TOKEN", "secret-token")
    response = TestClient(main.app).get("/models/status")
    assert response.status_code == 401


def test_encode_wav_pcm16_uses_standard_wav_container() -> None:
    audio = np.array([[0, 1200, -1200], [600, -600, 0]], dtype=np.int16)
    payload = main.encode_wav_pcm16(audio, 44100)

    assert payload.startswith(b"RIFF")
    with wave.open(io.BytesIO(payload), "rb") as wav_file:
        assert wav_file.getnchannels() == 2
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 44100
        assert wav_file.getnframes() == 3


def test_queue_limit_returns_429() -> None:
    pool = object.__new__(main.StableAudioWorkerPool)
    pool.jobs = queue.Queue(maxsize=1)
    pool.jobs.put(main.AudioJob(request=main.GenerateRequest(prompt="held"), created_at=0))

    with pytest.raises(HTTPException) as exc:
        pool.submit(main.GenerateRequest(prompt="next"))

    assert exc.value.status_code == 429


def _fake_generate(self, state, request):
    return b"RIFF\x24\x00\x00\x00WAVEfmt ", {"sample_rate": 44100}
