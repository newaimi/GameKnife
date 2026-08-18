from __future__ import annotations

import re
from pathlib import Path


class LocalStorageProvider:
    def __init__(self, root: Path):
        self.root = root
        self.assets_dir = self.root / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def write_asset(self, asset_id: str, original_name: str, content: bytes) -> str:
        suffix = Path(original_name).suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,12}", suffix):
            suffix = ".bin"

        target = self.assets_dir / f"{asset_id}{suffix}"
        target.write_bytes(content)
        return target.relative_to(self.root).as_posix()

    def remove_asset_file(self, relative_path: str) -> None:
        try:
            self.resolve_asset_path(relative_path).unlink(missing_ok=True)
        except OSError:
            # Database state is authoritative for deletion; disk cleanup is best effort.
            # A locked or user-moved local file must not invalidate the database operation.
            return None

    def resolve_asset_path(self, relative_path: str) -> Path:
        root = self.root.resolve()
        candidate = (self.root / relative_path).resolve()
        if not candidate.is_relative_to(root):
            # Treat database paths as untrusted input so malformed data cannot escape the local storage root.
            raise ValueError("素材路径超出本地存储目录。")
        return candidate
