from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from gameknife_core import AssetRecord, StorageProvider
from gameknife_jobs import AssetWriteInProgressError


class AssetPersistenceRepository(Protocol):
    """Repository boundary for one storage-neutral Asset write.

    Commercial implementations reserve quota and persist the pending state before remote I/O. Community keeps the
    same ordering but may defer its local SQLite insert because it has neither shared quota nor remote storage.
    """

    def create_pending_asset(
        self,
        asset: AssetRecord,
        *,
        reserved_bytes: int,
        reservation_job_id: str | None = None,
    ) -> AssetRecord | None:
        ...

    def finalize_pending_asset(self, asset: AssetRecord) -> None:
        ...

    def fail_pending_asset(
        self,
        asset_id: str,
        workspace_id: str,
        *,
        storage_key: str | None,
        failure_code: str,
        updated_at: str,
    ) -> None:
        ...


def persist_asset_file(
    repository: AssetPersistenceRepository,
    storage: StorageProvider,
    asset: AssetRecord,
    source_path: Path,
    *,
    reservation_job_id: str | None = None,
) -> AssetRecord:
    """Reserve, store, verify, and finalize one Asset without exposing provider details.

    The storage provider performs its own transfer and integrity verification. A durable pending row exists before
    remote I/O in Commercial, while a stable failure code and optional object key let its reconciler release quota
    and retry deletion after any partial write.
    """

    source_size = source_path.stat().st_size
    source_checksum = _sha256(source_path)
    pending = replace(
        asset,
        path="",
        size_bytes=source_size,
        storage_state="pending",
        storage_etag=None,
        checksum_sha256=source_checksum,
    )
    existing = repository.create_pending_asset(
        pending,
        reserved_bytes=source_size,
        reservation_job_id=reservation_job_id,
    )
    if existing is not None:
        if existing.storage_state != "ready":
            raise AssetWriteInProgressError(asset.id)
        return existing

    stored = None
    try:
        stored = storage.put_file(asset.id, asset.original_name, source_path)
        if stored.size_bytes != source_size:
            raise OSError("Stored object size does not match the staged Asset.")
        if stored.checksum_sha256 is not None and stored.checksum_sha256 != source_checksum:
            raise OSError("Stored object checksum does not match the staged Asset.")
        ready = replace(
            pending,
            path=stored.key,
            size_bytes=stored.size_bytes,
            storage_state="ready",
            storage_etag=stored.etag,
            checksum_sha256=stored.checksum_sha256 or source_checksum,
            updated_at=_now(),
        )
        repository.finalize_pending_asset(ready)
        return ready
    except Exception as exc:
        # Settlement is best-effort here so a secondary database outage cannot hide the original transfer failure.
        # Commercial reconciliation can later recover a stale pending row or delete the recorded object key.
        try:
            repository.fail_pending_asset(
                asset.id,
                asset.workspace_id,
                storage_key=None if stored is None else stored.key,
                failure_code=type(exc).__name__[:96],
                updated_at=_now(),
            )
        except Exception:  # noqa: BLE001, S110
            pass
        if stored is not None:
            try:
                storage.delete_object(stored.key)
            except Exception:  # noqa: BLE001, S110
                pass
        raise


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
