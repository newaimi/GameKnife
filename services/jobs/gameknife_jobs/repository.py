from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from gameknife_core import AssetRecord, AssetReferenceSummary, JobOutputAssetRecord, JobRecord

from .submission import JobSubmissionResult, TaskSubmission


class GameKnifeRepository(Protocol):
    """Persistence interface used by the public API.

    Each runtime entry point may inject its own database implementation, while the public API depends only on
    these stable methods. SQLite and other compatible implementations can therefore connect without binding the
    public processing path to one persistence strategy.
    """

    def create_asset(self, asset: AssetRecord) -> None:
        ...

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

    def get_asset_for_workspace(self, asset_id: str, workspace_id: str) -> AssetRecord | None:
        ...

    def list_assets_for_workspace(self, workspace_id: str) -> list[AssetRecord]:
        ...

    def list_assets_by_ids_for_workspace(self, asset_ids: list[str], workspace_id: str) -> list[AssetRecord]:
        ...

    def delete_assets_for_workspace(self, asset_ids: list[str], workspace_id: str) -> None:
        ...

    def get_asset_reference_summaries(
        self,
        asset_ids: list[str],
        workspace_id: str,
    ) -> list[AssetReferenceSummary]:
        ...

    def create_job(
        self,
        job: JobRecord,
        submission: TaskSubmission | None = None,
    ) -> JobSubmissionResult:
        ...

    def claim_job_for_workspace(
        self,
        job_id: str,
        workspace_id: str,
        *,
        updated_at: str,
    ) -> bool:
        ...

    def create_job_output_asset(self, output: JobOutputAssetRecord) -> None:
        ...

    def list_job_output_assets_for_workspace(
        self,
        job_id: str,
        workspace_id: str,
    ) -> list[JobOutputAssetRecord]:
        ...

    def cleanup_job_output_assets_for_workspace(
        self,
        job_id: str,
        workspace_id: str,
        asset_ids: list[str],
    ) -> list[AssetRecord]:
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

    def delete_job_for_workspace(self, job_id: str, workspace_id: str) -> list[AssetRecord]:
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

    def create_sequence_with_frames_for_job(
        self,
        *,
        workspace_id: str,
        created_by: str,
        job_id: str,
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

    def get_sequence_for_workspace_including_processing(
        self,
        sequence_id: str,
        workspace_id: str,
    ) -> Mapping[str, Any] | None:
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

    def claim_sequence_for_job(
        self,
        sequence_id: str,
        workspace_id: str,
        job_id: str,
        expected_revision: int,
        *,
        updated_at: str,
    ) -> int | None:
        ...

    def finalize_sequence_clean_job(
        self,
        sequence_id: str,
        workspace_id: str,
        job_id: str,
        claimed_revision: int,
        *,
        processed_assets_by_frame: Mapping[str, str],
        canvas_width: int,
        canvas_height: int,
        clean_parameters: dict[str, Any],
        result_json: str,
        device: str | None,
        duration_ms: int,
        updated_at: str,
    ) -> int:
        ...

    def fail_sequence_clean_job(
        self,
        sequence_id: str,
        workspace_id: str,
        job_id: str,
        claimed_revision: int,
        *,
        error_message: str,
        updated_at: str,
    ) -> list[AssetRecord]:
        ...

    def finalize_sequence_from_video_job(
        self,
        sequence_id: str,
        workspace_id: str,
        job_id: str,
        *,
        processed_assets_by_frame: Mapping[str, str],
        canvas_width: int,
        canvas_height: int,
        clean_parameters: dict[str, Any],
        result_json: str,
        device: str | None,
        duration_ms: int,
        updated_at: str,
    ) -> int:
        ...

    def fail_sequence_from_video_job(
        self,
        workspace_id: str,
        job_id: str,
        *,
        sequence_id: str | None,
        error_message: str,
        updated_at: str,
    ) -> list[AssetRecord]:
        ...

    def list_sequence_processed_asset_ids(self, sequence_id: str, workspace_id: str) -> list[str]:
        ...

    def delete_sequence_for_workspace(
        self,
        sequence_id: str,
        workspace_id: str,
    ) -> list[AssetRecord] | None:
        ...

    def recover_incomplete_jobs(self, *, error_message: str, updated_at: str) -> list[AssetRecord]:
        ...

    def list_settings(self) -> dict[str, str]:
        ...

    def read_setting(self, key: str, default: str = "") -> str:
        ...

    def write_setting(self, key: str, value: str, *, updated_at: str) -> None:
        ...

    def table_columns(self, table_name: str) -> list[str]:
        ...
