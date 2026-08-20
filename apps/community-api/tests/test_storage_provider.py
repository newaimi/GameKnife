from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from gameknife_storage import LocalStorageProvider


def test_local_storage_round_trip_reports_integrity_metadata(tmp_path: Path) -> None:
    provider = LocalStorageProvider(tmp_path / "storage")
    content = b"gameknife-storage-contract"
    source = tmp_path / "source.png"
    source.write_bytes(content)

    stored = provider.put_file("asset-1", "sprite.png", source)

    assert stored.key == "assets/asset-1.png"
    assert stored.size_bytes == len(content)
    assert stored.etag is None
    assert stored.checksum_sha256 == hashlib.sha256(content).hexdigest()
    assert provider.local_path(stored.key) == tmp_path / "storage" / stored.key
    assert provider.create_download_url(stored.key, "sprite.png", "image/png", 300) is None

    downloaded = provider.download_to(stored.key, tmp_path / "download" / "sprite.png")
    assert downloaded.read_bytes() == content

    provider.delete_object(stored.key)
    deleted_path = provider.local_path(stored.key)
    assert deleted_path is not None
    assert not deleted_path.exists()


def test_local_storage_rejects_keys_outside_its_root(tmp_path: Path) -> None:
    provider = LocalStorageProvider(tmp_path / "storage")

    with pytest.raises(ValueError, match="素材路径超出本地存储目录"):
        provider.local_path("../outside.png")
