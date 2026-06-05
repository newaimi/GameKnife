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
            # 删除任务以数据库为准，磁盘清理按尽力执行。
            # 本地文件被占用或已被用户移动时，不应该反向破坏数据库状态。
            return None

    def resolve_asset_path(self, relative_path: str) -> Path:
        root = self.root.resolve()
        candidate = (self.root / relative_path).resolve()
        if not candidate.is_relative_to(root):
            # 数据库里的路径也按不可信输入处理，避免异常数据越过本地存储根目录。
            raise ValueError("素材路径超出本地存储目录。")
        return candidate
