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
    storage_state: str = "ready"
    storage_etag: str | None = None
    checksum_sha256: str | None = None


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


@dataclass(frozen=True, slots=True)
class JobOutputAssetRecord:
    """Immutable relationship between a job and one persisted output asset."""

    id: str
    workspace_id: str
    created_by: str
    job_id: str
    asset_id: str
    created_at: str


@dataclass(frozen=True, slots=True)
class AssetRelationRecord:
    """Stable provenance edge from one source asset to a derived asset."""

    id: str
    workspace_id: str
    created_by: str
    source_asset_id: str
    derived_asset_id: str
    relation_type: str
    job_id: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class AssetReferenceSummary:
    """References that must be resolved before an asset can be deleted safely."""

    asset_id: str
    input_job_ids: tuple[str, ...] = ()
    output_job_ids: tuple[str, ...] = ()
    source_sequence_frame_ids: tuple[str, ...] = ()
    processed_sequence_frame_ids: tuple[str, ...] = ()
    derived_asset_ids: tuple[str, ...] = ()

    @property
    def is_referenced(self) -> bool:
        return any(
            (
                self.input_job_ids,
                self.output_job_ids,
                self.source_sequence_frame_ids,
                self.processed_sequence_frame_ids,
                self.derived_asset_ids,
            )
        )
