from __future__ import annotations

from pathlib import Path

from gameknife_api.birefnet import BiRefNetService
from gameknife_api.upscale_model import UPSCALE_MODEL_SPECS, UpscaleModelService


def test_birefnet_exposes_synchronous_install_for_durable_runtimes(monkeypatch, tmp_path: Path) -> None:
    service = BiRefNetService(model_cache_dir=tmp_path / "birefnet")
    calls: list[tuple[bool, bool]] = []
    monkeypatch.setattr(service, "is_installed", lambda: True)
    monkeypatch.setattr(service, "is_loaded", lambda: False)
    monkeypatch.setattr(
        service,
        "_ensure_model_loaded",
        lambda *, status_updates, local_files_only: calls.append((status_updates, local_files_only)),
    )
    monkeypatch.setattr(
        BiRefNetService,
        "_install_status",
        {"status": "idle", "progress": 0, "message": "idle", "error": None},
    )

    status = service.install()

    assert calls == [(True, False)]
    assert status["status"] == "success"
    assert status["progress"] == 100


def test_birefnet_synchronous_install_does_not_duplicate_running_install(monkeypatch, tmp_path: Path) -> None:
    service = BiRefNetService(model_cache_dir=tmp_path / "birefnet")
    monkeypatch.setattr(service, "is_installed", lambda: False)
    monkeypatch.setattr(service, "is_loaded", lambda: False)
    monkeypatch.setattr(
        BiRefNetService,
        "_install_status",
        {"status": "running", "progress": 25, "message": "running", "error": None},
    )
    monkeypatch.setattr(
        service,
        "_ensure_model_loaded",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("duplicate install")),
    )

    assert service.install()["status"] == "running"


def test_upscale_exposes_synchronous_install_for_durable_runtimes(monkeypatch, tmp_path: Path) -> None:
    service = UpscaleModelService(tmp_path / "upscale")
    downloaded: list[str] = []
    monkeypatch.setattr(service, "is_installed", lambda: True)
    monkeypatch.setattr(service, "is_loaded", lambda: False)
    monkeypatch.setattr(
        service,
        "_download_model",
        lambda spec, _start, _end: downloaded.append(spec.key),
    )
    monkeypatch.setattr(
        UpscaleModelService,
        "_install_status",
        {"status": "idle", "progress": 0, "message": "idle", "error": None},
    )

    status = service.install()

    assert downloaded == [spec.key for spec in UPSCALE_MODEL_SPECS]
    assert status["status"] == "success"
    assert status["progress"] == 100
