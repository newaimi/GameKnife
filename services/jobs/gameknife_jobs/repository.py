from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from gameknife_core import AssetRecord, JobRecord


class GameKnifeRepository(Protocol):
    """Persistence interface used by the public API.

    Each runtime entry point may inject its own database implementation, while the public API depends only on
    these stable methods. SQLite and other compatible implementations can therefore connect without binding the
    public processing path to one persistence strategy.
    """

    def create_asset(self, asset: AssetRecord) -> None:
        ...

    def get_asset_for_workspace(self, asset_id: str, workspace_id: str) -> AssetRecord | None:
        ...

    def list_assets_for_workspace(self, workspace_id: str) -> list[AssetRecord]:
        ...

    def list_assets_by_ids_for_workspace(self, asset_ids: list[str], workspace_id: str) -> list[AssetRecord]:
        ...

    def delete_assets_for_workspace(self, asset_ids: list[str], workspace_id: str) -> None:
        ...

    def create_job(self, job: JobRecord) -> None:
        ...

    def update_job(
        self,
        job_id: str,
        workspace_id: str,
        *,
        status: str | None = None,
        result_json: str | None = None,
        device: str | None = None,
        duration_ms: int | None = None,
        error_message: str | None = None,
        updated_at: str,
    ) -> None:
        ...

    def get_job_for_workspace(self, job_id: str, workspace_id: str) -> JobRecord | None:
        ...

    def list_jobs_for_workspace(self, workspace_id: str) -> list[JobRecord]:
        ...

    def list_job_page_for_workspace(
        self,
        workspace_id: str,
        *,
        limit: int,
        offset: int,
        job_types: list[str] | None = None,
        status: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
    ) -> list[JobRecord]:
        ...

    def count_job_page_for_workspace(
        self,
        workspace_id: str,
        *,
        job_types: list[str] | None = None,
        status: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
    ) -> int:
        ...

    def delete_job_for_workspace(self, job_id: str, workspace_id: str) -> None:
        ...

    def create_sequence_with_frames(
        self,
        *,
        workspace_id: str,
        created_by: str,
        name: str,
        fps: int,
        loop: bool,
        clean_parameters: dict[str, Any],
        frames: list[dict[str, Any]],
        created_at: str,
    ) -> Mapping[str, Any]:
        ...

    def list_sequences_for_workspace(self, workspace_id: str) -> list[Mapping[str, Any]]:
        ...

    def get_sequence_for_workspace(self, sequence_id: str, workspace_id: str) -> Mapping[str, Any] | None:
        ...

    def list_sequence_frames(self, sequence_id: str, workspace_id: str, *, enabled_only: bool = False) -> list[Mapping[str, Any]]:
        ...

    def update_sequence(
        self,
        sequence_id: str,
        workspace_id: str,
        *,
        name: str | None = None,
        fps: int | None = None,
        loop: bool | None = None,
        canvas_width: int | None = None,
        canvas_height: int | None = None,
        anchor_mode: str | None = None,
        anchor_x: float | None = None,
        anchor_y: float | None = None,
        clean_parameters: dict[str, Any] | None = None,
        status: str | None = None,
        updated_at: str,
    ) -> Mapping[str, Any] | None:
        ...

    def update_sequence_frames(self, sequence_id: str, workspace_id: str, frames: list[dict[str, Any]], *, updated_at: str) -> None:
        ...

    def update_sequence_frame_processed_asset(self, frame_id: str, sequence_id: str, processed_asset_id: str | None, *, updated_at: str) -> None:
        ...

    def collect_sequence_asset_ids(self, sequence_id: str, workspace_id: str) -> list[str]:
        ...

    def list_sequence_processed_asset_ids(self, sequence_id: str, workspace_id: str) -> list[str]:
        ...

    def delete_sequence_for_workspace(self, sequence_id: str, workspace_id: str) -> bool:
        ...

    def list_settings(self) -> dict[str, str]:
        ...

    def read_setting(self, key: str, default: str = "") -> str:
        ...

    def write_setting(self, key: str, value: str, *, updated_at: str) -> None:
        ...

    def table_columns(self, table_name: str) -> list[str]:
        ...
