from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from gameknife_core import StoredObject


class LocalStorageProvider:
    def __init__(self, root: Path):
        self.root = root
        self.assets_dir = self.root / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def put_file(self, asset_id: str, original_name: str, source_path: Path) -> StoredObject:
        suffix = Path(original_name).suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,12}", suffix):
            suffix = ".bin"

        target = self.assets_dir / f"{asset_id}{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target)
        return StoredObject(
            key=target.relative_to(self.root).as_posix(),
            size_bytes=target.stat().st_size,
            checksum_sha256=_sha256(target),
        )

    def download_to(self, key: str, destination: Path) -> Path:
        source = self._resolve_key(key)
        if not source.is_file():
            raise FileNotFoundError(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return destination

    def local_path(self, key: str) -> Path | None:
        return self._resolve_key(key)

    def create_download_url(
        self,
        key: str,
        filename: str,
        mime_type: str,
        expires_seconds: int,
    ) -> str | None:
        return None

    def delete_object(self, key: str) -> None:
        try:
            self._resolve_key(key).unlink(missing_ok=True)
        except OSError:
            # Database state is authoritative for deletion; disk cleanup is best effort.
            # A locked or user-moved local file must not invalidate the database operation.
            return None

    def _resolve_key(self, key: str) -> Path:
        root = self.root.resolve()
        candidate = (self.root / key).resolve()
        if not candidate.is_relative_to(root):
            # Treat persisted keys as untrusted input so malformed database data cannot escape the storage root.
            raise ValueError("素材路径超出本地存储目录。")
        return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
