from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ComponentCandidate:
    id: int
    bbox: tuple[int, int, int, int]
    area: int
    selected: bool = True


@dataclass(slots=True)
class ProcessResult:
    output_paths: list[Path] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    device: str | None = None


@dataclass(frozen=True, slots=True)
class AssetRecord:
    id: str
    workspace_id: str
    created_by: str
    kind: str
    original_name: str
    path: str
    mime_type: str
    size_bytes: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class JobRecord:
    id: str
    workspace_id: str
    created_by: str
    job_type: str
    status: str
    input_asset_id: str
    parameters_json: str
    result_json: str
    device: str | None
    duration_ms: int
    error_message: str | None
    created_at: str
    updated_at: str
