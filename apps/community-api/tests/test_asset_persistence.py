from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from gameknife_core import AssetRecord, StoredObject
from gameknife_jobs import AssetWriteInProgressError
from gameknife_workflows import persist_asset_file


class RecordingRepository:
    def __init__(self, events: list[str], *, fail_finalize: bool = False) -> None:
        self.events = events
        self.fail_finalize = fail_finalize
        self.failed: tuple[str | None, str] | None = None

    def create_pending_asset(self, asset, *, reserved_bytes, reservation_job_id=None) -> None:
        assert asset.storage_state == "pending"
        assert reserved_bytes == 7
        assert reservation_job_id == "job-1"
        self.events.append("pending")

    def finalize_pending_asset(self, asset) -> None:
        self.events.append("finalize")
        if self.fail_finalize:
            raise RuntimeError("database unavailable")

    def fail_pending_asset(
        self,
        _asset_id,
        _workspace_id,
        *,
        storage_key,
        failure_code,
        updated_at,
    ) -> None:
        assert updated_at
        self.failed = (storage_key, failure_code)
        self.events.append("failed")


class RecordingStorage:
    def __init__(self, events: list[str], *, fail_put: bool = False) -> None:
        self.events = events
        self.fail_put = fail_put
        self.deleted: list[str] = []

    def put_file(self, _asset_id: str, _original_name: str, _source_path: Path) -> StoredObject:
        self.events.append("put")
        if self.fail_put:
            raise OSError("storage unavailable")
        return StoredObject(
            key="projects/local/assets/asset-1.png",
            size_bytes=7,
            etag="etag-1",
            checksum_sha256=sha256(b"content").hexdigest(),
        )

    def delete_object(self, key: str) -> None:
        self.events.append("delete")
        self.deleted.append(key)

    def download_to(self, key: str, destination: Path) -> Path:  # pragma: no cover - protocol completeness
        raise NotImplementedError

    def local_path(self, key: str) -> Path | None:  # pragma: no cover - protocol completeness
        raise NotImplementedError

    def create_download_url(
        self,
        key: str,
        filename: str,
        mime_type: str,
        expires_seconds: int,
    ) -> str | None:  # pragma: no cover - protocol completeness
        raise NotImplementedError


class ExistingAssetRepository(RecordingRepository):
    def __init__(self, events: list[str], existing: AssetRecord) -> None:
        super().__init__(events)
        self.existing = existing

    def create_pending_asset(self, asset, *, reserved_bytes, reservation_job_id=None):
        super().create_pending_asset(
            asset,
            reserved_bytes=reserved_bytes,
            reservation_job_id=reservation_job_id,
        )
        return self.existing


class BusyAssetRepository(RecordingRepository):
    def create_pending_asset(self, asset, *, reserved_bytes, reservation_job_id=None):
        super().create_pending_asset(
            asset,
            reserved_bytes=reserved_bytes,
            reservation_job_id=reservation_job_id,
        )
        raise AssetWriteInProgressError(asset.id)


def _asset() -> AssetRecord:
    return AssetRecord(
        id="asset-1",
        workspace_id="local",
        created_by="anonymous",
        kind="image",
        original_name="sprite.png",
        path="",
        mime_type="image/png",
        size_bytes=7,
        created_at="2026-08-20T00:00:00+00:00",
        updated_at="2026-08-20T00:00:00+00:00",
    )


def test_asset_persistence_reserves_before_storage_and_finalizes_verified_metadata(tmp_path: Path) -> None:
    source = tmp_path / "sprite.png"
    source.write_bytes(b"content")
    events: list[str] = []
    repository = RecordingRepository(events)
    storage = RecordingStorage(events)

    ready = persist_asset_file(repository, storage, _asset(), source, reservation_job_id="job-1")

    assert events == ["pending", "put", "finalize"]
    assert ready.storage_state == "ready"
    assert ready.path == "projects/local/assets/asset-1.png"
    assert ready.storage_etag == "etag-1"
    assert ready.checksum_sha256 == sha256(b"content").hexdigest()
    assert repository.failed is None


def test_asset_persistence_records_transfer_failure_without_an_object_key(tmp_path: Path) -> None:
    source = tmp_path / "sprite.png"
    source.write_bytes(b"content")
    events: list[str] = []
    repository = RecordingRepository(events)
    storage = RecordingStorage(events, fail_put=True)

    with pytest.raises(OSError, match="storage unavailable"):
        persist_asset_file(repository, storage, _asset(), source, reservation_job_id="job-1")

    assert events == ["pending", "put", "failed"]
    assert repository.failed == (None, "OSError")
    assert storage.deleted == []


def test_asset_persistence_records_and_deletes_object_when_finalization_fails(tmp_path: Path) -> None:
    source = tmp_path / "sprite.png"
    source.write_bytes(b"content")
    events: list[str] = []
    repository = RecordingRepository(events, fail_finalize=True)
    storage = RecordingStorage(events)

    with pytest.raises(RuntimeError, match="database unavailable"):
        persist_asset_file(repository, storage, _asset(), source, reservation_job_id="job-1")

    assert events == ["pending", "put", "finalize", "failed", "delete"]
    assert repository.failed == ("projects/local/assets/asset-1.png", "RuntimeError")
    assert storage.deleted == ["projects/local/assets/asset-1.png"]


def test_asset_persistence_reuses_an_existing_ready_asset_without_storage_io(tmp_path: Path) -> None:
    source = tmp_path / "sprite.png"
    source.write_bytes(b"content")
    events: list[str] = []
    existing = _asset()
    repository = ExistingAssetRepository(events, existing)
    storage = RecordingStorage(events)

    replayed = persist_asset_file(repository, storage, _asset(), source, reservation_job_id="job-1")

    assert replayed is existing
    assert events == ["pending"]
    assert repository.failed is None


def test_asset_persistence_does_not_settle_another_writer_pending_asset(tmp_path: Path) -> None:
    source = tmp_path / "sprite.png"
    source.write_bytes(b"content")
    events: list[str] = []
    repository = BusyAssetRepository(events)
    storage = RecordingStorage(events)

    with pytest.raises(AssetWriteInProgressError):
        persist_asset_file(repository, storage, _asset(), source, reservation_job_id="job-1")

    assert events == ["pending"]
    assert repository.failed is None
    assert storage.deleted == []
