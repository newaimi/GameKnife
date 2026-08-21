from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from gameknife_core import (
    AssetRecord,
    AssetReferenceSummary,
    AssetRelationRecord,
    JobOutputAssetRecord,
    JobRecord,
)

from .errors import (
    InvalidJobStateTransitionError,
    JobDeliveryRequirementError,
    ResourceReferenceError,
    SequenceActiveJobError,
)
from .job_types import JOB_TYPE_REGISTRY, JobDeliveryRequirement
from .submission import JobSubmissionResult, TaskSubmission

SQLITE_SCHEMA_VERSION = 2


_JOBS_COLUMNS_SQL = """(
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    input_asset_id TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    device TEXT,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK(status IN ('pending', 'running', 'success', 'failed')),
    FOREIGN KEY(input_asset_id) REFERENCES assets(id) ON DELETE RESTRICT
)"""

_JOB_OUTPUT_ASSETS_COLUMNS_SQL = """(
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    job_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(job_id, asset_id),
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE RESTRICT
)"""

_ASSET_RELATIONS_COLUMNS_SQL = """(
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    source_asset_id TEXT NOT NULL,
    derived_asset_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    job_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(source_asset_id, derived_asset_id, relation_type),
    CHECK(source_asset_id <> derived_asset_id),
    FOREIGN KEY(source_asset_id) REFERENCES assets(id) ON DELETE RESTRICT,
    FOREIGN KEY(derived_asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE SET NULL
)"""

_SEQUENCES_COLUMNS_SQL = """(
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    name TEXT NOT NULL,
    fps INTEGER NOT NULL DEFAULT 12,
    loop INTEGER NOT NULL DEFAULT 1,
    canvas_width INTEGER NOT NULL DEFAULT 0,
    canvas_height INTEGER NOT NULL DEFAULT 0,
    anchor_mode TEXT NOT NULL DEFAULT 'bottom_center',
    anchor_x REAL NOT NULL DEFAULT 0.5,
    anchor_y REAL NOT NULL DEFAULT 1.0,
    clean_parameters_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',
    active_job_id TEXT,
    revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)"""

_SEQUENCE_FRAMES_COLUMNS_SQL = """(
    id TEXT PRIMARY KEY,
    sequence_id TEXT NOT NULL,
    source_asset_id TEXT NOT NULL,
    processed_asset_id TEXT,
    frame_index INTEGER NOT NULL,
    original_name TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    bbox_json TEXT NOT NULL,
    offset_x INTEGER NOT NULL DEFAULT 0,
    offset_y INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    is_generated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(sequence_id) REFERENCES sequences(id) ON DELETE CASCADE,
    FOREIGN KEY(source_asset_id) REFERENCES assets(id) ON DELETE RESTRICT,
    FOREIGN KEY(processed_asset_id) REFERENCES assets(id) ON DELETE RESTRICT
)"""


SCHEMA_SQL = f"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    kind TEXT NOT NULL,
    original_name TEXT NOT NULL,
    path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs {_JOBS_COLUMNS_SQL};

CREATE TABLE IF NOT EXISTS job_output_assets {_JOB_OUTPUT_ASSETS_COLUMNS_SQL};

CREATE TABLE IF NOT EXISTS asset_relations {_ASSET_RELATIONS_COLUMNS_SQL};

CREATE TABLE IF NOT EXISTS sequences {_SEQUENCES_COLUMNS_SQL};

CREATE TABLE IF NOT EXISTS sequence_frames {_SEQUENCE_FRAMES_COLUMNS_SQL};

CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_assets_workspace ON assets(workspace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_workspace ON jobs(workspace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_job_output_assets_workspace_job ON job_output_assets(workspace_id, job_id);
CREATE INDEX IF NOT EXISTS idx_job_output_assets_asset ON job_output_assets(asset_id);
CREATE INDEX IF NOT EXISTS idx_asset_relations_workspace_source ON asset_relations(workspace_id, source_asset_id, created_at);
CREATE INDEX IF NOT EXISTS idx_asset_relations_workspace_derived ON asset_relations(workspace_id, derived_asset_id, created_at);
CREATE INDEX IF NOT EXISTS idx_asset_relations_job ON asset_relations(job_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sequences_active_job ON sequences(active_job_id) WHERE active_job_id IS NOT NULL;
"""


def init_sqlite_schema(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current_version > SQLITE_SCHEMA_VERSION:
            raise RuntimeError(
                f"SQLite schema version {current_version} is newer than the supported version {SQLITE_SCHEMA_VERSION}."
            )
        if current_version == SQLITE_SCHEMA_VERSION:
            connection.execute("PRAGMA foreign_keys = ON")
            _assert_foreign_keys(connection)
            return

        if current_version == 0 and not _has_application_tables(connection):
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                f"BEGIN IMMEDIATE;\n{SCHEMA_SQL}\nPRAGMA user_version = {SQLITE_SCHEMA_VERSION};\nCOMMIT;"
            )
        elif current_version == 0:
            _migrate_v0_to_v1(connection)
            current_version = 1

        if current_version == 1:
            _migrate_v1_to_v2(connection)

        connection.execute("PRAGMA foreign_keys = ON")
        _assert_foreign_keys(connection)
    finally:
        connection.close()


class SQLiteGameKnifeRepository:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    def create_asset(self, asset: AssetRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO assets (
                    id, workspace_id, created_by, kind, original_name, path,
                    mime_type, size_bytes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset.id,
                    asset.workspace_id,
                    asset.created_by,
                    asset.kind,
                    asset.original_name,
                    asset.path,
                    asset.mime_type,
                    asset.size_bytes,
                    asset.created_at,
                    asset.updated_at,
                ),
            )

    def create_pending_asset(
        self,
        asset: AssetRecord,
        *,
        reserved_bytes: int,
        reservation_job_id: str | None = None,
    ) -> AssetRecord | None:
        # Community has no shared quota or remote object store. Deferring the SQLite insert until finalization keeps
        # pending Commercial lifecycle state out of the local database while preserving the same public call order.
        del reservation_job_id
        if asset.storage_state != "pending" or reserved_bytes < 0:
            raise ValueError("Pending assets require a non-negative reservation.")
        return None

    def finalize_pending_asset(self, asset: AssetRecord) -> None:
        if asset.storage_state != "ready":
            raise ValueError("Only ready assets can be finalized.")
        self.create_asset(asset)

    def fail_pending_asset(
        self,
        asset_id: str,
        workspace_id: str,
        *,
        storage_key: str | None,
        failure_code: str,
        updated_at: str,
    ) -> None:
        # No pending row is created for Community, so a failed local write has no database state to settle.
        del asset_id, workspace_id, storage_key, failure_code, updated_at

    def get_asset_for_workspace(self, asset_id: str, workspace_id: str) -> AssetRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, workspace_id, created_by, kind, original_name, path,
                       mime_type, size_bytes, created_at, updated_at
                FROM assets
                WHERE id = ? AND workspace_id = ?
                """,
                (asset_id, workspace_id),
            ).fetchone()
        return _asset_from_row(row) if row else None

    def list_assets_for_workspace(self, workspace_id: str) -> list[AssetRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, workspace_id, created_by, kind, original_name, path,
                       mime_type, size_bytes, created_at, updated_at
                FROM assets
                WHERE workspace_id = ?
                ORDER BY created_at DESC
                """,
                (workspace_id,),
            ).fetchall()
        return [_asset_from_row(row) for row in rows]

    def list_assets_by_ids_for_workspace(self, asset_ids: list[str], workspace_id: str) -> list[AssetRecord]:
        if not asset_ids:
            return []

        placeholders = ",".join("?" for _ in asset_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, workspace_id, created_by, kind, original_name, path,
                       mime_type, size_bytes, created_at, updated_at
                FROM assets
                WHERE workspace_id = ? AND id IN ({placeholders})
                """,
                (workspace_id, *asset_ids),
            ).fetchall()
        return [_asset_from_row(row) for row in rows]

    def list_asset_page_for_workspace(
        self,
        workspace_id: str,
        *,
        limit: int,
        offset: int,
        kinds: list[str] | None = None,
        search: str | None = None,
    ) -> list[AssetRecord]:
        where_sql, values = _asset_page_filter(workspace_id, kinds, search)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, workspace_id, created_by, kind, original_name, path,
                       mime_type, size_bytes, created_at, updated_at
                FROM assets
                WHERE {where_sql}
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (*values, limit, offset),
            ).fetchall()
        return [_asset_from_row(row) for row in rows]

    def count_asset_page_for_workspace(
        self,
        workspace_id: str,
        *,
        kinds: list[str] | None = None,
        search: str | None = None,
    ) -> int:
        where_sql, values = _asset_page_filter(workspace_id, kinds, search)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS total FROM assets WHERE {where_sql}",
                values,
            ).fetchone()
        return int(row["total"])

    def create_asset_relation(self, relation: AssetRelationRecord) -> None:
        if relation.source_asset_id == relation.derived_asset_id:
            raise ValueError("An asset cannot be derived from itself.")
        with self._connect() as connection:
            _insert_asset_relation(connection, relation)

    def list_asset_relations_for_workspace(
        self,
        asset_id: str,
        workspace_id: str,
    ) -> list[AssetRelationRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, workspace_id, created_by, source_asset_id, derived_asset_id,
                       relation_type, job_id, created_at
                FROM asset_relations
                WHERE workspace_id = ? AND (source_asset_id = ? OR derived_asset_id = ?)
                ORDER BY created_at ASC, id ASC
                """,
                (workspace_id, asset_id, asset_id),
            ).fetchall()
        return [AssetRelationRecord(**dict(row)) for row in rows]

    def delete_assets_for_workspace(self, asset_ids: list[str], workspace_id: str) -> None:
        if not asset_ids:
            return

        placeholders = ",".join("?" for _ in asset_ids)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            references = _asset_reference_summaries(connection, asset_ids, workspace_id)
            blocked = tuple(summary for summary in references if summary.is_referenced)
            if blocked:
                raise ResourceReferenceError("asset", blocked[0].asset_id, blocked)
            connection.execute(
                f"DELETE FROM assets WHERE workspace_id = ? AND id IN ({placeholders})",
                (workspace_id, *asset_ids),
            )

    def get_asset_reference_summaries(
        self,
        asset_ids: list[str],
        workspace_id: str,
    ) -> list[AssetReferenceSummary]:
        if not asset_ids:
            return []
        with self._connect() as connection:
            return _asset_reference_summaries(connection, asset_ids, workspace_id)

    def create_job(
        self,
        job: JobRecord,
        submission: TaskSubmission | None = None,
    ) -> JobSubmissionResult:
        if submission is not None and not isinstance(submission, TaskSubmission):
            raise TypeError("submission must be a TaskSubmission")
        JOB_TYPE_REGISTRY.require(job.job_type)
        if job.status != "pending":
            raise ValueError("New jobs must start in the pending state.")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, workspace_id, created_by, job_type, status, input_asset_id,
                    parameters_json, result_json, device, duration_ms, error_message,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.workspace_id,
                    job.created_by,
                    job.job_type,
                    job.status,
                    job.input_asset_id,
                    job.parameters_json,
                    job.result_json,
                    job.device,
                    job.duration_ms,
                    job.error_message,
                    job.created_at,
                    job.updated_at,
                ),
            )
        return JobSubmissionResult(job=job, replayed=False)

    def claim_job_for_workspace(
        self,
        job_id: str,
        workspace_id: str,
        *,
        updated_at: str,
    ) -> bool:
        # One conditional write is the execution ownership boundary. Duplicate in-process dispatches and future
        # at-least-once workers can both call this method without running the processor more than once.
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            claimed = connection.execute(
                """
                UPDATE jobs
                SET status = 'running', error_message = NULL, updated_at = ?
                WHERE id = ? AND workspace_id = ? AND status = 'pending'
                """,
                (updated_at, job_id, workspace_id),
            )
            return claimed.rowcount == 1

    def create_job_output_asset(self, output: JobOutputAssetRecord) -> None:
        with self._connect() as connection:
            job_and_asset = connection.execute(
                """
                SELECT j.id AS job_id, j.input_asset_id, j.job_type, j.created_by, a.id AS asset_id
                FROM jobs j
                JOIN assets a ON a.id = ? AND a.workspace_id = ?
                WHERE j.id = ? AND j.workspace_id = ?
                """,
                (output.asset_id, output.workspace_id, output.job_id, output.workspace_id),
            ).fetchone()
            if job_and_asset is None:
                raise ValueError("Job output asset must belong to the same workspace as its job.")
            connection.execute(
                """
                INSERT INTO job_output_assets (
                    id, workspace_id, created_by, job_id, asset_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, asset_id) DO NOTHING
                """,
                (
                    output.id,
                    output.workspace_id,
                    output.created_by,
                    output.job_id,
                    output.asset_id,
                    output.created_at,
                ),
            )
            source_asset_id = str(job_and_asset["input_asset_id"])
            if source_asset_id != output.asset_id:
                _insert_asset_relation(
                    connection,
                    AssetRelationRecord(
                        id=uuid4().hex,
                        workspace_id=output.workspace_id,
                        created_by=output.created_by,
                        source_asset_id=source_asset_id,
                        derived_asset_id=output.asset_id,
                        relation_type=(
                            "export"
                            if str(job_and_asset["job_type"]) == "project_export_package"
                            else "derived"
                        ),
                        job_id=output.job_id,
                        created_at=output.created_at,
                    ),
                )

    def list_job_output_assets_for_workspace(
        self,
        job_id: str,
        workspace_id: str,
    ) -> list[JobOutputAssetRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, workspace_id, created_by, job_id, asset_id, created_at
                FROM job_output_assets
                WHERE job_id = ? AND workspace_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (job_id, workspace_id),
            ).fetchall()
        return [JobOutputAssetRecord(**dict(row)) for row in rows]

    def cleanup_job_output_assets_for_workspace(
        self,
        job_id: str,
        workspace_id: str,
        asset_ids: list[str],
    ) -> list[AssetRecord]:
        unique_asset_ids = list(dict.fromkeys(asset_ids))
        if not unique_asset_ids:
            return []
        placeholders = ",".join("?" for _ in unique_asset_ids)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                f"""
                SELECT id, workspace_id, created_by, kind, original_name, path,
                       mime_type, size_bytes, created_at, updated_at
                FROM assets
                WHERE workspace_id = ? AND id IN ({placeholders})
                """,
                (workspace_id, *unique_asset_ids),
            ).fetchall()
            candidates = [_asset_from_row(row) for row in rows]
            # Failed output registration and failed execution use this single transaction. Detaching ownership in
            # one commit and deleting the Asset in another would make a later failure impossible to recover by Job.
            connection.execute(
                f"""
                DELETE FROM job_output_assets
                WHERE job_id = ? AND workspace_id = ? AND asset_id IN ({placeholders})
                """,
                (job_id, workspace_id, *unique_asset_ids),
            )
            return _delete_unreferenced_candidate_assets(connection, candidates, workspace_id)

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
        if status is not None and status not in {"pending", "running", "success", "failed"}:
            raise ValueError(f"Unsupported job status: {status}")

        assignments = ["updated_at = ?"]
        values: list[Any] = [updated_at]
        if status is not None:
            assignments.append("status = ?")
            values.append(status)
        if result_json is not None:
            assignments.append("result_json = ?")
            values.append(result_json)
        if device is not None:
            assignments.append("device = ?")
            values.append(device)
        if duration_ms is not None:
            assignments.append("duration_ms = ?")
            values.append(duration_ms)
        if error_message is not None:
            assignments.append("error_message = ?")
            values.append(error_message)
        elif status in {"running", "success"}:
            assignments.append("error_message = NULL")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT status, job_type, result_json FROM jobs WHERE id = ? AND workspace_id = ?",
                (job_id, workspace_id),
            ).fetchone()
            if current is None:
                return
            current_status = str(current["status"])
            if status is None and current_status in {"success", "failed"}:
                return
            if status is not None:
                if current_status == status:
                    return
                allowed_targets = {
                    "pending": {"running", "failed"},
                    "running": {"success", "failed"},
                    "success": set(),
                    "failed": set(),
                }
                if status not in allowed_targets.get(current_status, set()):
                    raise InvalidJobStateTransitionError(job_id, current_status, status)
                if status == "success":
                    spec = JOB_TYPE_REGISTRY.require(str(current["job_type"]))
                    if spec.delivery_requirement == JobDeliveryRequirement.OUTPUT_ASSET:
                        delivered = connection.execute(
                            """
                            SELECT 1
                            FROM job_output_assets output
                            JOIN assets asset
                              ON asset.id = output.asset_id
                             AND asset.workspace_id = output.workspace_id
                            WHERE output.job_id = ? AND output.workspace_id = ?
                            LIMIT 1
                            """,
                            (job_id, workspace_id),
                        ).fetchone()
                        if delivered is None:
                            raise JobDeliveryRequirementError(job_id, spec.job_type)
                    elif spec.delivery_requirement == JobDeliveryRequirement.RESULT:
                        _require_non_empty_json_result(
                            result_json if result_json is not None else str(current["result_json"]),
                            job_id,
                            spec.job_type,
                        )
                    elif spec.delivery_requirement == JobDeliveryRequirement.STATE_CHANGE:
                        # State-changing deliveries need a workflow-specific atomic finalizer. The generic updater
                        # cannot prove that every target row and the terminal Job state commit in one transaction.
                        raise JobDeliveryRequirementError(job_id, spec.job_type)

            values.extend([job_id, workspace_id])
            connection.execute(
                f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ? AND workspace_id = ?",
                values,
            )

    def get_job_for_workspace(self, job_id: str, workspace_id: str) -> JobRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, workspace_id, created_by, job_type, status, input_asset_id,
                       parameters_json, result_json, device, duration_ms, error_message,
                       created_at, updated_at
                FROM jobs
                WHERE id = ? AND workspace_id = ?
                """,
                (job_id, workspace_id),
            ).fetchone()
        return _job_from_row(row) if row else None

    def list_jobs_for_workspace(self, workspace_id: str) -> list[JobRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, workspace_id, created_by, job_type, status, input_asset_id,
                       parameters_json, result_json, device, duration_ms, error_message,
                       created_at, updated_at
                FROM jobs
                WHERE workspace_id = ?
                ORDER BY created_at DESC
                """,
                (workspace_id,),
            ).fetchall()
        return [_job_from_row(row) for row in rows]

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
        where, values = _job_page_filter(workspace_id, job_types, status, created_from, created_to)
        values.extend([limit, offset])
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, workspace_id, created_by, job_type, status, input_asset_id,
                       parameters_json, result_json, device, duration_ms, error_message,
                       created_at, updated_at
                FROM jobs
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                values,
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def count_job_page_for_workspace(
        self,
        workspace_id: str,
        *,
        job_types: list[str] | None = None,
        status: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
    ) -> int:
        where, values = _job_page_filter(workspace_id, job_types, status, created_from, created_to)
        with self._connect() as connection:
            row = connection.execute(f"SELECT COUNT(*) AS total FROM jobs WHERE {where}", values).fetchone()
        return int(row["total"] if row else 0)

    def delete_job_for_workspace(self, job_id: str, workspace_id: str) -> list[AssetRecord]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            output_rows = connection.execute(
                """
                SELECT asset.id, asset.workspace_id, asset.created_by, asset.kind,
                       asset.original_name, asset.path, asset.mime_type, asset.size_bytes,
                       asset.created_at, asset.updated_at
                FROM job_output_assets output
                JOIN assets asset
                  ON asset.id = output.asset_id
                 AND asset.workspace_id = output.workspace_id
                WHERE output.job_id = ? AND output.workspace_id = ?
                """,
                (job_id, workspace_id),
            ).fetchall()
            output_assets = [_asset_from_row(row) for row in output_rows]
            output_asset_ids = [asset.id for asset in output_assets]
            references = _asset_reference_summaries(connection, output_asset_ids, workspace_id)
            downstream = tuple(_without_job_reference(summary, job_id) for summary in references)
            blocked = tuple(summary for summary in downstream if summary.is_referenced)
            if blocked:
                raise ResourceReferenceError("job", job_id, blocked)
            deleted = connection.execute(
                "DELETE FROM jobs WHERE id = ? AND workspace_id = ?",
                (job_id, workspace_id),
            )
            if deleted.rowcount == 0:
                return []
            if output_asset_ids:
                placeholders = ",".join("?" for _ in output_asset_ids)
                connection.execute(
                    f"DELETE FROM assets WHERE workspace_id = ? AND id IN ({placeholders})",
                    (workspace_id, *output_asset_ids),
                )
            return output_assets

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
    ) -> sqlite3.Row:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            sequence_id = _insert_sequence_with_frames(
                connection,
                workspace_id=workspace_id,
                created_by=created_by,
                name=name,
                fps=fps,
                loop=loop,
                clean_parameters=clean_parameters,
                frames=frames,
                status="ready",
                active_job_id=None,
                created_at=created_at,
            )
        sequence = self.get_sequence_for_workspace_including_processing(sequence_id, workspace_id)
        if sequence is None:
            raise RuntimeError("序列帧创建失败。")
        return sequence

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
    ) -> sqlite3.Row:
        # Video extraction publishes source assets before CPU/GPU frame cleaning. Binding the intermediate Sequence
        # to the running Job prevents normal edit and delete routes from observing a partially delivered result.
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute(
                """
                SELECT 1
                FROM jobs
                WHERE id = ? AND workspace_id = ? AND job_type = 'sequence_video_to_frames' AND status = 'running'
                """,
                (job_id, workspace_id),
            ).fetchone()
            if job is None:
                raise ValueError("Video sequence creation requires its running parent Job.")
            sequence_id = _insert_sequence_with_frames(
                connection,
                workspace_id=workspace_id,
                created_by=created_by,
                name=name,
                fps=fps,
                loop=loop,
                clean_parameters=clean_parameters,
                frames=frames,
                status="processing",
                active_job_id=job_id,
                created_at=created_at,
            )
        sequence = self.get_sequence_for_workspace_including_processing(sequence_id, workspace_id)
        if sequence is None:
            raise RuntimeError("序列帧创建失败。")
        return sequence

    def list_sequences_for_workspace(self, workspace_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT s.*,
                        COUNT(f.id) AS frame_count,
                        COALESCE(SUM(CASE WHEN f.enabled = 1 THEN 1 ELSE 0 END), 0) AS enabled_frame_count
                    FROM sequences s
                    LEFT JOIN sequence_frames f ON f.sequence_id = s.id
                    WHERE s.workspace_id = ? AND s.status <> 'processing'
                    GROUP BY s.id
                    ORDER BY s.updated_at DESC
                    """,
                    (workspace_id,),
                ).fetchall()
            )

    def get_sequence_for_workspace(self, sequence_id: str, workspace_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT s.*,
                    COUNT(f.id) AS frame_count,
                    COALESCE(SUM(CASE WHEN f.enabled = 1 THEN 1 ELSE 0 END), 0) AS enabled_frame_count
                FROM sequences s
                LEFT JOIN sequence_frames f ON f.sequence_id = s.id
                WHERE s.id = ? AND s.workspace_id = ? AND s.status <> 'processing'
                GROUP BY s.id
                """,
                (sequence_id, workspace_id),
            ).fetchone()

    def get_sequence_for_workspace_including_processing(
        self,
        sequence_id: str,
        workspace_id: str,
    ) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT s.*,
                    COUNT(f.id) AS frame_count,
                    COALESCE(SUM(CASE WHEN f.enabled = 1 THEN 1 ELSE 0 END), 0) AS enabled_frame_count
                FROM sequences s
                LEFT JOIN sequence_frames f ON f.sequence_id = s.id
                WHERE s.id = ? AND s.workspace_id = ?
                GROUP BY s.id
                """,
                (sequence_id, workspace_id),
            ).fetchone()

    def list_sequence_frames(self, sequence_id: str, workspace_id: str, *, enabled_only: bool = False) -> list[sqlite3.Row]:
        where_enabled = "AND f.enabled = 1" if enabled_only else ""
        with self._connect() as connection:
            return list(
                connection.execute(
                    f"""
                    SELECT f.*, sa.path AS source_path, sa.mime_type AS source_mime_type,
                        pa.path AS processed_path, pa.mime_type AS processed_mime_type
                    FROM sequence_frames f
                    JOIN sequences s ON s.id = f.sequence_id
                    JOIN assets sa ON sa.id = f.source_asset_id
                    LEFT JOIN assets pa ON pa.id = f.processed_asset_id
                    WHERE f.sequence_id = ? AND s.workspace_id = ? {where_enabled}
                    ORDER BY f.frame_index ASC, f.created_at ASC
                    """,
                    (sequence_id, workspace_id),
                ).fetchall()
            )

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
    ) -> sqlite3.Row | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT active_job_id FROM sequences WHERE id = ? AND workspace_id = ?",
                (sequence_id, workspace_id),
            ).fetchone()
            if current is None:
                return None
            if current["active_job_id"] is not None:
                raise SequenceActiveJobError(sequence_id)
            connection.execute(
                """
                UPDATE sequences
                SET name = COALESCE(?, name),
                    fps = COALESCE(?, fps),
                    loop = COALESCE(?, loop),
                    canvas_width = COALESCE(?, canvas_width),
                    canvas_height = COALESCE(?, canvas_height),
                    anchor_mode = COALESCE(?, anchor_mode),
                    anchor_x = COALESCE(?, anchor_x),
                    anchor_y = COALESCE(?, anchor_y),
                    clean_parameters_json = COALESCE(?, clean_parameters_json),
                    status = COALESCE(?, status),
                    revision = revision + 1,
                    updated_at = ?
                WHERE id = ? AND workspace_id = ? AND active_job_id IS NULL
                """,
                (
                    name,
                    fps,
                    None if loop is None else 1 if loop else 0,
                    canvas_width,
                    canvas_height,
                    anchor_mode,
                    anchor_x,
                    anchor_y,
                    None if clean_parameters is None else json.dumps(clean_parameters, ensure_ascii=False),
                    status,
                    updated_at,
                    sequence_id,
                    workspace_id,
                ),
            )
        return self.get_sequence_for_workspace(sequence_id, workspace_id)

    def update_sequence_frames(self, sequence_id: str, workspace_id: str, frames: list[dict[str, Any]], *, updated_at: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT active_job_id FROM sequences WHERE id = ? AND workspace_id = ?",
                (sequence_id, workspace_id),
            ).fetchone()
            if current is None:
                return
            if current["active_job_id"] is not None:
                raise SequenceActiveJobError(sequence_id)
            for frame in frames:
                connection.execute(
                    """
                    UPDATE sequence_frames
                    SET frame_index = COALESCE(?, frame_index),
                        offset_x = COALESCE(?, offset_x),
                        offset_y = COALESCE(?, offset_y),
                        duration_ms = COALESCE(?, duration_ms),
                        enabled = COALESCE(?, enabled),
                        updated_at = ?
                    WHERE id = ?
                    AND sequence_id = ?
                    AND EXISTS (
                        SELECT 1 FROM sequences
                        WHERE sequences.id = sequence_frames.sequence_id
                        AND sequences.workspace_id = ?
                        AND sequences.active_job_id IS NULL
                    )
                    """,
                    (
                        frame.get("frame_index"),
                        frame.get("offset_x"),
                        frame.get("offset_y"),
                        frame.get("duration_ms"),
                        None if frame.get("enabled") is None else 1 if frame["enabled"] else 0,
                        updated_at,
                        frame["id"],
                        sequence_id,
                        workspace_id,
                    ),
                )
            connection.execute(
                """
                UPDATE sequences
                SET revision = revision + 1, updated_at = ?
                WHERE id = ? AND workspace_id = ? AND active_job_id IS NULL
                """,
                (updated_at, sequence_id, workspace_id),
            )

    def claim_sequence_for_job(
        self,
        sequence_id: str,
        workspace_id: str,
        job_id: str,
        expected_revision: int,
        *,
        updated_at: str,
    ) -> int | None:
        # A clean job owns one exact Sequence revision. A second Job may be running, but it cannot mutate this target
        # until the first Job either commits delivery or restores and releases the claim.
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            claimed = connection.execute(
                """
                UPDATE sequences
                SET active_job_id = ?, status = 'cleaning', updated_at = ?
                WHERE id = ?
                  AND workspace_id = ?
                  AND active_job_id IS NULL
                  AND revision = ?
                  AND status = 'ready'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM sequences claimed_sequence
                      WHERE claimed_sequence.active_job_id = ?
                  )
                  AND EXISTS (
                      SELECT 1
                      FROM jobs
                      WHERE jobs.id = ?
                        AND jobs.workspace_id = sequences.workspace_id
                        AND jobs.job_type = 'sequence_clean'
                        AND jobs.status = 'running'
                  )
                """,
                (job_id, updated_at, sequence_id, workspace_id, expected_revision, job_id, job_id),
            )
            return expected_revision if claimed.rowcount == 1 else None

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
        completed_revision = claimed_revision + 1
        delivered = _require_non_empty_json_result(result_json, job_id, "sequence_clean")
        if (
            not isinstance(delivered, dict)
            or delivered.get("sequence_id") != sequence_id
            or delivered.get("sequence_revision") != completed_revision
        ):
            raise JobDeliveryRequirementError(job_id, "sequence_clean")
        frame_asset_pairs = [(str(frame_id), str(asset_id)) for frame_id, asset_id in processed_assets_by_frame.items()]
        asset_ids = [asset_id for _, asset_id in frame_asset_pairs]
        if not frame_asset_pairs or len(set(asset_ids)) != len(asset_ids):
            raise JobDeliveryRequirementError(job_id, "sequence_clean")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            _require_running_job(connection, job_id, workspace_id, "sequence_clean")
            sequence = connection.execute(
                """
                SELECT 1
                FROM sequences
                WHERE id = ? AND workspace_id = ? AND active_job_id = ?
                  AND revision = ? AND status = 'cleaning'
                """,
                (sequence_id, workspace_id, job_id, claimed_revision),
            ).fetchone()
            if sequence is None:
                raise JobDeliveryRequirementError(job_id, "sequence_clean")

            enabled_frame_ids = {
                str(row["id"])
                for row in connection.execute(
                    "SELECT id FROM sequence_frames WHERE sequence_id = ? AND enabled = 1",
                    (sequence_id,),
                ).fetchall()
            }
            if enabled_frame_ids != {frame_id for frame_id, _ in frame_asset_pairs}:
                raise JobDeliveryRequirementError(job_id, "sequence_clean")

            placeholders = ",".join("?" for _ in asset_ids)
            workspace_assets = {
                str(row["id"])
                for row in connection.execute(
                    f"SELECT id FROM assets WHERE workspace_id = ? AND id IN ({placeholders})",
                    (workspace_id, *asset_ids),
                ).fetchall()
            }
            owned_assets = {
                str(row["asset_id"])
                for row in connection.execute(
                    f"""
                    SELECT asset_id
                    FROM job_output_assets
                    WHERE job_id = ? AND workspace_id = ? AND asset_id IN ({placeholders})
                    """,
                    (job_id, workspace_id, *asset_ids),
                ).fetchall()
            }
            all_job_outputs = {
                str(row["asset_id"])
                for row in connection.execute(
                    "SELECT asset_id FROM job_output_assets WHERE job_id = ? AND workspace_id = ?",
                    (job_id, workspace_id),
                ).fetchall()
            }
            if workspace_assets != set(asset_ids) or owned_assets != set(asset_ids) or all_job_outputs != set(asset_ids):
                raise JobDeliveryRequirementError(job_id, "sequence_clean")

            for frame_id, asset_id in frame_asset_pairs:
                updated = connection.execute(
                    """
                    UPDATE sequence_frames
                    SET processed_asset_id = ?, updated_at = ?
                    WHERE id = ? AND sequence_id = ?
                    """,
                    (asset_id, updated_at, frame_id, sequence_id),
                )
                if updated.rowcount != 1:
                    raise JobDeliveryRequirementError(job_id, "sequence_clean")

            completed = connection.execute(
                """
                UPDATE sequences
                SET canvas_width = ?, canvas_height = ?, clean_parameters_json = ?,
                    status = 'ready', active_job_id = NULL, revision = ?, updated_at = ?
                WHERE id = ? AND workspace_id = ? AND active_job_id = ?
                  AND revision = ? AND status = 'cleaning'
                """,
                (
                    canvas_width,
                    canvas_height,
                    json.dumps(clean_parameters, ensure_ascii=False),
                    completed_revision,
                    updated_at,
                    sequence_id,
                    workspace_id,
                    job_id,
                    claimed_revision,
                ),
            )
            if completed.rowcount != 1:
                raise JobDeliveryRequirementError(job_id, "sequence_clean")
            finalized = connection.execute(
                """
                UPDATE jobs
                SET status = 'success', result_json = ?, device = ?, duration_ms = ?,
                    error_message = NULL, updated_at = ?
                WHERE id = ? AND workspace_id = ? AND status = 'running'
                """,
                (result_json, device, duration_ms, updated_at, job_id, workspace_id),
            )
            if finalized.rowcount != 1:
                raise InvalidJobStateTransitionError(job_id, "not-running", "success")
            # These relationships only make pre-delivery assets recoverable. Once every frame reference and the Job
            # terminal state commit together, the Sequence becomes the durable owner of the processed assets.
            connection.execute(
                "DELETE FROM job_output_assets WHERE job_id = ? AND workspace_id = ?",
                (job_id, workspace_id),
            )
        return completed_revision

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
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute(
                "SELECT status FROM jobs WHERE id = ? AND workspace_id = ? AND job_type = 'sequence_clean'",
                (job_id, workspace_id),
            ).fetchone()
            if job is None or str(job["status"]) == "success":
                return []
            # A dispatcher may have marked the Job failed after an exception escaped the runner. The Sequence claim
            # and staged outputs still need idempotent cleanup even when the terminal Job update is already complete.
            candidates = _job_output_asset_records(connection, [job_id], workspace_id)
            connection.execute(
                "DELETE FROM job_output_assets WHERE job_id = ? AND workspace_id = ?",
                (job_id, workspace_id),
            )
            connection.execute(
                """
                UPDATE sequences
                SET active_job_id = NULL, status = 'ready', updated_at = ?
                WHERE id = ? AND workspace_id = ? AND active_job_id = ?
                  AND revision = ? AND status = 'cleaning'
                """,
                (updated_at, sequence_id, workspace_id, job_id, claimed_revision),
            )
            connection.execute(
                """
                UPDATE jobs
                SET status = 'failed', error_message = ?, updated_at = ?
                WHERE id = ? AND workspace_id = ? AND status IN ('pending', 'running')
                """,
                (error_message, updated_at, job_id, workspace_id),
            )
            return _delete_unreferenced_candidate_assets(connection, candidates, workspace_id)

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
        delivered = _require_non_empty_json_result(result_json, job_id, "sequence_video_to_frames")
        if not isinstance(delivered, dict) or delivered.get("sequence_id") != sequence_id:
            raise JobDeliveryRequirementError(job_id, "sequence_video_to_frames")
        frame_asset_pairs = [(str(frame_id), str(asset_id)) for frame_id, asset_id in processed_assets_by_frame.items()]
        processed_asset_ids = [asset_id for _, asset_id in frame_asset_pairs]
        if not frame_asset_pairs or len(set(processed_asset_ids)) != len(processed_asset_ids):
            raise JobDeliveryRequirementError(job_id, "sequence_video_to_frames")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            _require_running_job(connection, job_id, workspace_id, "sequence_video_to_frames")
            sequence = connection.execute(
                """
                SELECT revision
                FROM sequences
                WHERE id = ? AND workspace_id = ? AND active_job_id = ? AND status = 'processing'
                """,
                (sequence_id, workspace_id, job_id),
            ).fetchone()
            if sequence is None:
                raise JobDeliveryRequirementError(job_id, "sequence_video_to_frames")

            frames = connection.execute(
                """
                SELECT frame.id, frame.source_asset_id, source.workspace_id AS source_workspace_id
                FROM sequence_frames frame
                JOIN assets source ON source.id = frame.source_asset_id
                WHERE frame.sequence_id = ?
                """,
                (sequence_id,),
            ).fetchall()
            if not frames:
                raise JobDeliveryRequirementError(job_id, "sequence_video_to_frames")
            if {str(frame["id"]) for frame in frames} != {frame_id for frame_id, _ in frame_asset_pairs}:
                raise JobDeliveryRequirementError(job_id, "sequence_video_to_frames")
            frame_asset_ids = set(processed_asset_ids)
            for frame in frames:
                if frame["source_workspace_id"] != workspace_id:
                    raise JobDeliveryRequirementError(job_id, "sequence_video_to_frames")
                frame_asset_ids.add(str(frame["source_asset_id"]))
            placeholders = ",".join("?" for _ in processed_asset_ids)
            stored_processed_assets = {
                str(row["id"])
                for row in connection.execute(
                    f"SELECT id FROM assets WHERE workspace_id = ? AND id IN ({placeholders})",
                    (workspace_id, *processed_asset_ids),
                ).fetchall()
            }
            if stored_processed_assets != set(processed_asset_ids):
                raise JobDeliveryRequirementError(job_id, "sequence_video_to_frames")
            owned_assets = {
                str(row["asset_id"])
                for row in connection.execute(
                    "SELECT asset_id FROM job_output_assets WHERE job_id = ? AND workspace_id = ?",
                    (job_id, workspace_id),
                ).fetchall()
            }
            if owned_assets != frame_asset_ids:
                raise JobDeliveryRequirementError(job_id, "sequence_video_to_frames")

            for frame_id, asset_id in frame_asset_pairs:
                updated = connection.execute(
                    """
                    UPDATE sequence_frames
                    SET processed_asset_id = ?, updated_at = ?
                    WHERE id = ? AND sequence_id = ?
                    """,
                    (asset_id, updated_at, frame_id, sequence_id),
                )
                if updated.rowcount != 1:
                    raise JobDeliveryRequirementError(job_id, "sequence_video_to_frames")

            completed_revision = int(sequence["revision"]) + 1
            completed = connection.execute(
                """
                UPDATE sequences
                SET canvas_width = ?, canvas_height = ?, clean_parameters_json = ?,
                    status = 'ready', active_job_id = NULL, revision = ?, updated_at = ?
                WHERE id = ? AND workspace_id = ? AND active_job_id = ? AND status = 'processing'
                """,
                (
                    canvas_width,
                    canvas_height,
                    json.dumps(clean_parameters, ensure_ascii=False),
                    completed_revision,
                    updated_at,
                    sequence_id,
                    workspace_id,
                    job_id,
                ),
            )
            if completed.rowcount != 1:
                raise JobDeliveryRequirementError(job_id, "sequence_video_to_frames")
            finalized = connection.execute(
                """
                UPDATE jobs
                SET status = 'success', result_json = ?, device = ?, duration_ms = ?,
                    error_message = NULL, updated_at = ?
                WHERE id = ? AND workspace_id = ? AND status = 'running'
                """,
                (result_json, device, duration_ms, updated_at, job_id, workspace_id),
            )
            if finalized.rowcount != 1:
                raise InvalidJobStateTransitionError(job_id, "not-running", "success")
        return completed_revision

    def fail_sequence_from_video_job(
        self,
        workspace_id: str,
        job_id: str,
        *,
        sequence_id: str | None,
        error_message: str,
        updated_at: str,
    ) -> list[AssetRecord]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute(
                "SELECT status FROM jobs WHERE id = ? AND workspace_id = ? AND job_type = 'sequence_video_to_frames'",
                (job_id, workspace_id),
            ).fetchone()
            if job is None or str(job["status"]) == "success":
                return []
            candidates = _job_output_asset_records(connection, [job_id], workspace_id)
            if sequence_id is not None:
                connection.execute(
                    "DELETE FROM sequences WHERE id = ? AND workspace_id = ? AND active_job_id = ?",
                    (sequence_id, workspace_id, job_id),
                )
            else:
                connection.execute(
                    "DELETE FROM sequences WHERE workspace_id = ? AND active_job_id = ?",
                    (workspace_id, job_id),
                )
            connection.execute(
                "DELETE FROM job_output_assets WHERE job_id = ? AND workspace_id = ?",
                (job_id, workspace_id),
            )
            connection.execute(
                """
                UPDATE jobs
                SET status = 'failed', error_message = ?, updated_at = ?
                WHERE id = ? AND workspace_id = ? AND status IN ('pending', 'running')
                """,
                (error_message, updated_at, job_id, workspace_id),
            )
            return _delete_unreferenced_candidate_assets(connection, candidates, workspace_id)

    def list_sequence_processed_asset_ids(self, sequence_id: str, workspace_id: str) -> list[str]:
        frames = self.list_sequence_frames(sequence_id, workspace_id)
        return [frame["processed_asset_id"] for frame in frames if frame["processed_asset_id"]]

    def delete_sequence_for_workspace(
        self,
        sequence_id: str,
        workspace_id: str,
    ) -> list[AssetRecord] | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT active_job_id FROM sequences WHERE id = ? AND workspace_id = ?",
                (sequence_id, workspace_id),
            ).fetchone()
            if current is None:
                return None
            if current["active_job_id"] is not None:
                raise SequenceActiveJobError(sequence_id)
            # The Asset snapshot and Sequence deletion share the same write transaction. A clean finalizer cannot
            # attach a new processed Asset between these operations and leave an object outside the cleanup set.
            rows = connection.execute(
                """
                SELECT DISTINCT asset.id, asset.workspace_id, asset.created_by, asset.kind,
                       asset.original_name, asset.path, asset.mime_type, asset.size_bytes,
                       asset.created_at, asset.updated_at
                FROM assets asset
                JOIN sequence_frames frame
                  ON frame.sequence_id = ?
                 AND (frame.source_asset_id = asset.id OR frame.processed_asset_id = asset.id)
                WHERE asset.workspace_id = ?
                """,
                (sequence_id, workspace_id),
            ).fetchall()
            asset_records = [_asset_from_row(row) for row in rows]
            cursor = connection.execute(
                "DELETE FROM sequences WHERE id = ? AND workspace_id = ? AND active_job_id IS NULL",
                (sequence_id, workspace_id),
            )
            if cursor.rowcount != 1:
                raise SequenceActiveJobError(sequence_id)
            # Frame references disappear with the Sequence. Remove only candidates that have no remaining Job or
            # Sequence owner before committing, so a process exit cannot strand unreferenced Asset rows afterward.
            return _delete_unreferenced_candidate_assets(connection, asset_records, workspace_id)

    def recover_incomplete_jobs(self, *, error_message: str, updated_at: str) -> list[AssetRecord]:
        # Community has no durable worker. A process restart therefore terminates every persisted pending/running
        # execution. The database transition removes only assets owned by those incomplete Jobs and leaves any Asset
        # that is still referenced by a successful Job, another Job input, or a delivered Sequence intact.
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            incomplete_jobs = connection.execute(
                "SELECT id, workspace_id, job_type FROM jobs WHERE status IN ('pending', 'running')"
            ).fetchall()
            if not incomplete_jobs:
                return []

            cleanup_assets: list[AssetRecord] = []
            jobs_by_workspace: dict[str, list[sqlite3.Row]] = {}
            for job in incomplete_jobs:
                jobs_by_workspace.setdefault(str(job["workspace_id"]), []).append(job)

            for workspace_id, jobs in jobs_by_workspace.items():
                job_ids = [str(job["id"]) for job in jobs]
                candidates = _job_output_asset_records(connection, job_ids, workspace_id)
                video_job_ids = [
                    str(job["id"])
                    for job in jobs
                    if str(job["job_type"]) == "sequence_video_to_frames"
                ]
                if video_job_ids:
                    placeholders = ",".join("?" for _ in video_job_ids)
                    connection.execute(
                        f"DELETE FROM sequences WHERE workspace_id = ? AND active_job_id IN ({placeholders})",
                        (workspace_id, *video_job_ids),
                    )
                placeholders = ",".join("?" for _ in job_ids)
                connection.execute(
                    f"""
                    UPDATE sequences
                    SET active_job_id = NULL, status = 'ready', updated_at = ?
                    WHERE workspace_id = ? AND active_job_id IN ({placeholders})
                    """,
                    (updated_at, workspace_id, *job_ids),
                )
                connection.execute(
                    f"DELETE FROM job_output_assets WHERE workspace_id = ? AND job_id IN ({placeholders})",
                    (workspace_id, *job_ids),
                )
                cleanup_assets.extend(_delete_unreferenced_candidate_assets(connection, candidates, workspace_id))

            connection.execute(
                """
                UPDATE jobs
                SET status = 'failed', error_message = ?, updated_at = ?
                WHERE status IN ('pending', 'running')
                """,
                (error_message, updated_at),
            )
            return cleanup_assets

    def list_settings(self) -> dict[str, str]:
        with self._connect() as connection:
            rows = connection.execute("SELECT key, value FROM system_settings ORDER BY key").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def read_setting(self, key: str, default: str = "") -> str:
        with self._connect() as connection:
            row = connection.execute("SELECT value FROM system_settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def write_setting(self, key: str, value: str, *, updated_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO system_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value, updated_at),
            )

    def table_columns(self, table_name: str) -> list[str]:
        # Tests inspect the real schema so account fields cannot re-enter Community tables unnoticed.
        with self._connect() as connection:
            rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return [row["name"] for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _insert_sequence_with_frames(
    connection: sqlite3.Connection,
    *,
    workspace_id: str,
    created_by: str,
    name: str,
    fps: int,
    loop: bool,
    clean_parameters: dict[str, Any],
    frames: list[dict[str, Any]],
    status: str,
    active_job_id: str | None,
    created_at: str,
) -> str:
    source_asset_ids = {str(frame["source_asset_id"]) for frame in frames}
    if source_asset_ids:
        placeholders = ",".join("?" for _ in source_asset_ids)
        stored_source_ids = {
            str(row["id"])
            for row in connection.execute(
                f"SELECT id FROM assets WHERE workspace_id = ? AND id IN ({placeholders})",
                (workspace_id, *source_asset_ids),
            ).fetchall()
        }
        if stored_source_ids != source_asset_ids:
            raise ValueError("Every Sequence source Asset must belong to the same workspace.")

    sequence_id = uuid4().hex
    canvas_width = max((int(frame["width"]) for frame in frames), default=0)
    canvas_height = max((int(frame["height"]) for frame in frames), default=0)
    connection.execute(
        """
        INSERT INTO sequences (
            id, workspace_id, created_by, name, fps, loop, canvas_width, canvas_height,
            anchor_mode, anchor_x, anchor_y, clean_parameters_json,
            status, active_job_id, revision, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'bottom_center', 0.5, 1.0, ?, ?, ?, 0, ?, ?)
        """,
        (
            sequence_id,
            workspace_id,
            created_by,
            name,
            fps,
            1 if loop else 0,
            canvas_width,
            canvas_height,
            json.dumps(clean_parameters, ensure_ascii=False),
            status,
            active_job_id,
            created_at,
            created_at,
        ),
    )
    for index, frame in enumerate(frames):
        connection.execute(
            """
            INSERT INTO sequence_frames (
                id, sequence_id, source_asset_id, frame_index, original_name,
                width, height, bbox_json, duration_ms, enabled, is_generated, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid4().hex,
                sequence_id,
                frame["source_asset_id"],
                index,
                frame["original_name"],
                int(frame["width"]),
                int(frame["height"]),
                json.dumps(frame["bbox"], ensure_ascii=False),
                int(frame.get("duration_ms", 0)),
                1 if frame.get("enabled", True) else 0,
                1 if frame.get("is_generated", False) else 0,
                created_at,
                created_at,
            ),
        )
    return sequence_id


def _require_running_job(
    connection: sqlite3.Connection,
    job_id: str,
    workspace_id: str,
    job_type: str,
) -> None:
    job = connection.execute(
        "SELECT status FROM jobs WHERE id = ? AND workspace_id = ? AND job_type = ?",
        (job_id, workspace_id, job_type),
    ).fetchone()
    if job is None:
        raise JobDeliveryRequirementError(job_id, job_type)
    if str(job["status"]) != "running":
        raise InvalidJobStateTransitionError(job_id, str(job["status"]), "success")


def _job_output_asset_records(
    connection: sqlite3.Connection,
    job_ids: list[str],
    workspace_id: str,
) -> list[AssetRecord]:
    if not job_ids:
        return []
    placeholders = ",".join("?" for _ in job_ids)
    rows = connection.execute(
        f"""
        SELECT DISTINCT asset.id, asset.workspace_id, asset.created_by, asset.kind,
               asset.original_name, asset.path, asset.mime_type, asset.size_bytes,
               asset.created_at, asset.updated_at
        FROM job_output_assets output
        JOIN assets asset ON asset.id = output.asset_id AND asset.workspace_id = output.workspace_id
        WHERE output.workspace_id = ? AND output.job_id IN ({placeholders})
        """,
        (workspace_id, *job_ids),
    ).fetchall()
    return [_asset_from_row(row) for row in rows]


def _delete_unreferenced_candidate_assets(
    connection: sqlite3.Connection,
    candidates: list[AssetRecord],
    workspace_id: str,
) -> list[AssetRecord]:
    if not candidates:
        return []
    summaries = {
        summary.asset_id: summary
        for summary in _asset_reference_summaries(connection, [asset.id for asset in candidates], workspace_id)
    }
    removable = [
        asset
        for asset in candidates
        if asset.workspace_id == workspace_id
        and (asset.id not in summaries or not summaries[asset.id].is_referenced)
    ]
    if not removable:
        return []
    placeholders = ",".join("?" for _ in removable)
    connection.execute(
        f"DELETE FROM assets WHERE workspace_id = ? AND id IN ({placeholders})",
        (workspace_id, *(asset.id for asset in removable)),
    )
    return removable


def _require_non_empty_json_result(result_json: str, job_id: str, job_type: str) -> Any:
    try:
        result = json.loads(result_json)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise JobDeliveryRequirementError(job_id, job_type) from exc
    if result in (None, "", [], {}):
        raise JobDeliveryRequirementError(job_id, job_type)
    return result


def _has_application_tables(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        LIMIT 1
        """
    ).fetchone()
    return row is not None


def _migrate_v0_to_v1(connection: sqlite3.Connection) -> None:
    required_tables = {"assets", "jobs", "sequences", "sequence_frames", "system_settings"}
    existing_tables = {
        str(row["name"])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    missing_tables = sorted(required_tables - existing_tables)
    if missing_tables:
        raise RuntimeError(f"Cannot migrate incomplete SQLite schema; missing tables: {', '.join(missing_tables)}")

    # SQLite cannot change a foreign-key action in place. The migration disables enforcement only while both
    # referencing tables are rebuilt in one immediate transaction, then verifies every preserved row before commit.
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DROP TABLE IF EXISTS jobs_v1")
        connection.execute(f"CREATE TABLE jobs_v1 {_JOBS_COLUMNS_SQL}")
        connection.execute(
            """
            INSERT INTO jobs_v1 (
                id, workspace_id, created_by, job_type, status, input_asset_id,
                parameters_json, result_json, device, duration_ms, error_message,
                created_at, updated_at
            )
            SELECT id, workspace_id, created_by, job_type, status, input_asset_id,
                   parameters_json, result_json, device, duration_ms, error_message,
                   created_at, updated_at
            FROM jobs
            """
        )

        connection.execute("DROP TABLE IF EXISTS sequence_frames_v1")
        connection.execute(f"CREATE TABLE sequence_frames_v1 {_SEQUENCE_FRAMES_COLUMNS_SQL}")
        connection.execute(
            """
            INSERT INTO sequence_frames_v1 (
                id, sequence_id, source_asset_id, processed_asset_id, frame_index,
                original_name, width, height, bbox_json, offset_x, offset_y,
                duration_ms, enabled, is_generated, created_at, updated_at
            )
            SELECT id, sequence_id, source_asset_id, processed_asset_id, frame_index,
                   original_name, width, height, bbox_json, offset_x, offset_y,
                   duration_ms, enabled, is_generated, created_at, updated_at
            FROM sequence_frames
            """
        )

        # Version zero predates target-level execution ownership. Existing local Sequences start unlocked at
        # revision zero; their frame and metadata rows remain unchanged.
        connection.execute("ALTER TABLE sequences ADD COLUMN active_job_id TEXT")
        connection.execute("ALTER TABLE sequences ADD COLUMN revision INTEGER NOT NULL DEFAULT 0")

        connection.execute("DROP TABLE jobs")
        connection.execute("ALTER TABLE jobs_v1 RENAME TO jobs")
        connection.execute("DROP TABLE sequence_frames")
        connection.execute("ALTER TABLE sequence_frames_v1 RENAME TO sequence_frames")
        connection.execute(f"CREATE TABLE job_output_assets {_JOB_OUTPUT_ASSETS_COLUMNS_SQL}")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_assets_workspace ON assets(workspace_id, created_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_workspace ON jobs(workspace_id, created_at)")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_job_output_assets_workspace_job ON job_output_assets(workspace_id, job_id)"
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_job_output_assets_asset ON job_output_assets(asset_id)")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_sequences_active_job ON sequences(active_job_id) WHERE active_job_id IS NOT NULL"
        )
        _backfill_job_output_assets(connection)

        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError("SQLite migration found invalid asset references and was rolled back.")
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def _backfill_job_output_assets(connection: sqlite3.Connection) -> None:
    jobs = connection.execute(
        "SELECT id, workspace_id, created_by, result_json, created_at FROM jobs"
    ).fetchall()
    for job in jobs:
        try:
            result = json.loads(str(job["result_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(result, dict):
            continue
        outputs = result.get("output_assets")
        if not isinstance(outputs, list):
            continue
        asset_ids = list(
            dict.fromkeys(
                str(output["id"])
                for output in outputs
                if isinstance(output, dict) and output.get("id")
            )
        )
        for asset_id in asset_ids:
            asset = connection.execute(
                "SELECT id FROM assets WHERE id = ? AND workspace_id = ?",
                (asset_id, job["workspace_id"]),
            ).fetchone()
            if asset is None:
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO job_output_assets (
                    id, workspace_id, created_by, job_id, asset_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid4().hex,
                    job["workspace_id"],
                    job["created_by"],
                    job["id"],
                    asset_id,
                    job["created_at"],
                ),
            )


def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(f"CREATE TABLE asset_relations {_ASSET_RELATIONS_COLUMNS_SQL}")
        connection.execute(
            "CREATE INDEX idx_asset_relations_workspace_source ON asset_relations(workspace_id, source_asset_id, created_at)"
        )
        connection.execute(
            "CREATE INDEX idx_asset_relations_workspace_derived ON asset_relations(workspace_id, derived_asset_id, created_at)"
        )
        connection.execute("CREATE INDEX idx_asset_relations_job ON asset_relations(job_id)")
        rows = connection.execute(
            """
            SELECT output.workspace_id, output.created_by, output.job_id, output.asset_id,
                   output.created_at, job.input_asset_id
            FROM job_output_assets output
            JOIN jobs job ON job.id = output.job_id AND job.workspace_id = output.workspace_id
            WHERE job.input_asset_id <> output.asset_id
            """
        ).fetchall()
        for row in rows:
            _insert_asset_relation(
                connection,
                AssetRelationRecord(
                    id=uuid4().hex,
                    workspace_id=str(row["workspace_id"]),
                    created_by=str(row["created_by"]),
                    source_asset_id=str(row["input_asset_id"]),
                    derived_asset_id=str(row["asset_id"]),
                    relation_type="derived",
                    job_id=str(row["job_id"]),
                    created_at=str(row["created_at"]),
                ),
            )
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError("SQLite asset-relation migration found invalid references and was rolled back.")
        connection.execute("PRAGMA user_version = 2")
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _assert_foreign_keys(connection: sqlite3.Connection) -> None:
    if int(connection.execute("PRAGMA foreign_keys").fetchone()[0]) != 1:
        raise RuntimeError("SQLite foreign-key enforcement is disabled.")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RuntimeError("SQLite schema contains invalid foreign-key references.")


def _insert_asset_relation(connection: sqlite3.Connection, relation: AssetRelationRecord) -> None:
    source = connection.execute(
        "SELECT id FROM assets WHERE id = ? AND workspace_id = ?",
        (relation.source_asset_id, relation.workspace_id),
    ).fetchone()
    derived = connection.execute(
        "SELECT id FROM assets WHERE id = ? AND workspace_id = ?",
        (relation.derived_asset_id, relation.workspace_id),
    ).fetchone()
    if source is None or derived is None:
        raise ValueError("Asset relations require source and derived assets in the same workspace.")
    if relation.job_id is not None:
        job = connection.execute(
            "SELECT id FROM jobs WHERE id = ? AND workspace_id = ?",
            (relation.job_id, relation.workspace_id),
        ).fetchone()
        if job is None:
            raise ValueError("Asset relation job must belong to the same workspace.")
    connection.execute(
        """
        INSERT INTO asset_relations (
            id, workspace_id, created_by, source_asset_id, derived_asset_id,
            relation_type, job_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_asset_id, derived_asset_id, relation_type) DO NOTHING
        """,
        (
            relation.id,
            relation.workspace_id,
            relation.created_by,
            relation.source_asset_id,
            relation.derived_asset_id,
            relation.relation_type,
            relation.job_id,
            relation.created_at,
        ),
    )


def _asset_reference_summaries(
    connection: sqlite3.Connection,
    asset_ids: list[str],
    workspace_id: str,
) -> list[AssetReferenceSummary]:
    unique_asset_ids = list(dict.fromkeys(asset_ids))
    if not unique_asset_ids:
        return []
    placeholders = ",".join("?" for _ in unique_asset_ids)
    existing_ids = {
        str(row["id"])
        for row in connection.execute(
            f"SELECT id FROM assets WHERE workspace_id = ? AND id IN ({placeholders})",
            (workspace_id, *unique_asset_ids),
        ).fetchall()
    }
    references: dict[str, dict[str, list[str]]] = {
        asset_id: {
            "input_job_ids": [],
            "output_job_ids": [],
            "source_sequence_frame_ids": [],
            "processed_sequence_frame_ids": [],
            "derived_asset_ids": [],
        }
        for asset_id in unique_asset_ids
        if asset_id in existing_ids
    }
    if not references:
        return []

    reference_ids = list(references)
    reference_placeholders = ",".join("?" for _ in reference_ids)
    for row in connection.execute(
        f"""
        SELECT id, input_asset_id
        FROM jobs
        WHERE workspace_id = ? AND input_asset_id IN ({reference_placeholders})
        """,
        (workspace_id, *reference_ids),
    ).fetchall():
        references[str(row["input_asset_id"])]["input_job_ids"].append(str(row["id"]))

    for row in connection.execute(
        f"""
        SELECT job_id, asset_id
        FROM job_output_assets
        WHERE workspace_id = ? AND asset_id IN ({reference_placeholders})
        """,
        (workspace_id, *reference_ids),
    ).fetchall():
        references[str(row["asset_id"])]["output_job_ids"].append(str(row["job_id"]))

    for row in connection.execute(
        f"""
        SELECT f.id, f.source_asset_id, f.processed_asset_id
        FROM sequence_frames f
        JOIN sequences s ON s.id = f.sequence_id
        WHERE s.workspace_id = ?
          AND (
              f.source_asset_id IN ({reference_placeholders})
              OR f.processed_asset_id IN ({reference_placeholders})
          )
        """,
        (workspace_id, *reference_ids, *reference_ids),
    ).fetchall():
        source_asset_id = str(row["source_asset_id"])
        if source_asset_id in references:
            references[source_asset_id]["source_sequence_frame_ids"].append(str(row["id"]))
        processed_asset_id = row["processed_asset_id"]
        if processed_asset_id is not None and str(processed_asset_id) in references:
            references[str(processed_asset_id)]["processed_sequence_frame_ids"].append(str(row["id"]))

    for row in connection.execute(
        f"""
        SELECT source_asset_id, derived_asset_id
        FROM asset_relations
        WHERE workspace_id = ? AND source_asset_id IN ({reference_placeholders})
        """,
        (workspace_id, *reference_ids),
    ).fetchall():
        references[str(row["source_asset_id"])]["derived_asset_ids"].append(str(row["derived_asset_id"]))

    return [
        AssetReferenceSummary(
            asset_id=asset_id,
            input_job_ids=tuple(sorted(values["input_job_ids"])),
            output_job_ids=tuple(sorted(values["output_job_ids"])),
            source_sequence_frame_ids=tuple(sorted(values["source_sequence_frame_ids"])),
            processed_sequence_frame_ids=tuple(sorted(values["processed_sequence_frame_ids"])),
            derived_asset_ids=tuple(sorted(values["derived_asset_ids"])),
        )
        for asset_id, values in references.items()
    ]


def _without_job_reference(summary: AssetReferenceSummary, job_id: str) -> AssetReferenceSummary:
    return AssetReferenceSummary(
        asset_id=summary.asset_id,
        input_job_ids=tuple(reference_id for reference_id in summary.input_job_ids if reference_id != job_id),
        output_job_ids=tuple(reference_id for reference_id in summary.output_job_ids if reference_id != job_id),
        source_sequence_frame_ids=summary.source_sequence_frame_ids,
        processed_sequence_frame_ids=summary.processed_sequence_frame_ids,
        derived_asset_ids=summary.derived_asset_ids,
    )


def _asset_from_row(row: sqlite3.Row) -> AssetRecord:
    data: dict[str, Any] = dict(row)
    return AssetRecord(**data)


def _job_from_row(row: sqlite3.Row) -> JobRecord:
    data: dict[str, Any] = dict(row)
    return JobRecord(**data)


def _asset_page_filter(workspace_id: str, kinds: list[str] | None, search: str | None) -> tuple[str, list[Any]]:
    conditions = ["workspace_id = ?", "kind <> 'sound_prompt'"]
    values: list[Any] = [workspace_id]
    normalized_kinds = list(dict.fromkeys(item.strip() for item in (kinds or []) if item.strip()))
    if normalized_kinds:
        placeholders = ",".join("?" for _ in normalized_kinds)
        conditions.append(f"kind IN ({placeholders})")
        values.extend(normalized_kinds)
    normalized_search = (search or "").strip().lower()
    if normalized_search:
        conditions.append("LOWER(original_name) LIKE ?")
        values.append(f"%{normalized_search}%")
    return " AND ".join(conditions), values


def _job_page_filter(
    workspace_id: str,
    job_types: list[str] | None,
    status: str | None,
    created_from: str | None,
    created_to: str | None,
) -> tuple[str, list[Any]]:
    where = ["workspace_id = ?"]
    values: list[Any] = [workspace_id]
    if job_types is not None:
        if not job_types:
            return "1 = 0", []
        placeholders = ",".join("?" for _ in job_types)
        where.append(f"job_type IN ({placeholders})")
        values.extend(job_types)
    if status is not None:
        where.append("status = ?")
        values.append(status)
    if created_from:
        where.append("created_at >= ?")
        values.append(created_from)
    if created_to:
        where.append("created_at <= ?")
        values.append(created_to)
    return " AND ".join(where), values
