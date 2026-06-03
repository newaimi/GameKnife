from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from gameknife_core import AssetRecord, JobRecord


SCHEMA_SQL = """
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

CREATE TABLE IF NOT EXISTS jobs (
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
    FOREIGN KEY(input_asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sequences (
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
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sequence_frames (
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
    FOREIGN KEY(source_asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    FOREIGN KEY(processed_asset_id) REFERENCES assets(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS character_rigs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    source_asset_id TEXT NOT NULL,
    name TEXT NOT NULL,
    canvas_width INTEGER NOT NULL DEFAULT 0,
    canvas_height INTEGER NOT NULL DEFAULT 0,
    export_format TEXT NOT NULL DEFAULT 'spine',
    status TEXT NOT NULL DEFAULT 'ready',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(source_asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS character_parts (
    id TEXT PRIMARY KEY,
    rig_id TEXT NOT NULL,
    part_asset_id TEXT,
    mask_asset_id TEXT,
    name TEXT NOT NULL,
    semantic_type TEXT NOT NULL,
    bbox_json TEXT NOT NULL,
    pivot_x REAL NOT NULL DEFAULT 0.5,
    pivot_y REAL NOT NULL DEFAULT 0.5,
    parent_id TEXT,
    z_index INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    needs_completion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(rig_id) REFERENCES character_rigs(id) ON DELETE CASCADE,
    FOREIGN KEY(part_asset_id) REFERENCES assets(id) ON DELETE SET NULL,
    FOREIGN KEY(mask_asset_id) REFERENCES assets(id) ON DELETE SET NULL,
    FOREIGN KEY(parent_id) REFERENCES character_parts(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_assets_workspace ON assets(workspace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_workspace ON jobs(workspace_id, created_at);
"""


def init_sqlite_schema(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(SCHEMA_SQL)


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

    def delete_assets_for_workspace(self, asset_ids: list[str], workspace_id: str) -> None:
        if not asset_ids:
            return

        placeholders = ",".join("?" for _ in asset_ids)
        with self._connect() as connection:
            connection.execute(
                f"DELETE FROM assets WHERE workspace_id = ? AND id IN ({placeholders})",
                (workspace_id, *asset_ids),
            )

    def create_job(self, job: JobRecord) -> None:
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

        values.extend([job_id, workspace_id])
        with self._connect() as connection:
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
    ) -> list[JobRecord]:
        where, values = _job_page_filter(workspace_id, job_types, status)
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
    ) -> int:
        where, values = _job_page_filter(workspace_id, job_types, status)
        with self._connect() as connection:
            row = connection.execute(f"SELECT COUNT(*) AS total FROM jobs WHERE {where}", values).fetchone()
        return int(row["total"] if row else 0)

    def delete_job_for_workspace(self, job_id: str, workspace_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM jobs WHERE id = ? AND workspace_id = ?", (job_id, workspace_id))

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
        sequence_id = uuid4().hex
        canvas_width = max((int(frame["width"]) for frame in frames), default=0)
        canvas_height = max((int(frame["height"]) for frame in frames), default=0)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sequences (
                    id, workspace_id, created_by, name, fps, loop, canvas_width, canvas_height,
                    anchor_mode, anchor_x, anchor_y, clean_parameters_json,
                    status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'bottom_center', 0.5, 1.0, ?, 'ready', ?, ?)
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
        sequence = self.get_sequence_for_workspace(sequence_id, workspace_id)
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
                    WHERE s.workspace_id = ?
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
        current = self.get_sequence_for_workspace(sequence_id, workspace_id)
        if current is None:
            return None

        with self._connect() as connection:
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
                    updated_at = ?
                WHERE id = ? AND workspace_id = ?
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
                "UPDATE sequences SET updated_at = ? WHERE id = ? AND workspace_id = ?",
                (updated_at, sequence_id, workspace_id),
            )

    def update_sequence_frame_processed_asset(self, frame_id: str, sequence_id: str, processed_asset_id: str | None, *, updated_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sequence_frames
                SET processed_asset_id = ?, updated_at = ?
                WHERE id = ? AND sequence_id = ?
                """,
                (processed_asset_id, updated_at, frame_id, sequence_id),
            )

    def collect_sequence_asset_ids(self, sequence_id: str, workspace_id: str) -> list[str]:
        frames = self.list_sequence_frames(sequence_id, workspace_id)
        asset_ids: list[str] = []
        for frame in frames:
            for key in ("source_asset_id", "processed_asset_id"):
                value = frame[key]
                if value and value not in asset_ids:
                    asset_ids.append(value)
        return asset_ids

    def list_sequence_processed_asset_ids(self, sequence_id: str, workspace_id: str) -> list[str]:
        frames = self.list_sequence_frames(sequence_id, workspace_id)
        return [frame["processed_asset_id"] for frame in frames if frame["processed_asset_id"]]

    def delete_sequence_for_workspace(self, sequence_id: str, workspace_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM sequences WHERE id = ? AND workspace_id = ?", (sequence_id, workspace_id))
            return cursor.rowcount > 0

    def create_character_rig(
        self,
        *,
        workspace_id: str,
        created_by: str,
        source_asset_id: str,
        name: str,
        canvas_width: int,
        canvas_height: int,
        export_format: str,
        created_at: str,
    ) -> sqlite3.Row:
        rig_id = uuid4().hex
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO character_rigs (
                    id, workspace_id, created_by, source_asset_id, name,
                    canvas_width, canvas_height, export_format, status,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?)
                """,
                (
                    rig_id,
                    workspace_id,
                    created_by,
                    source_asset_id,
                    name,
                    canvas_width,
                    canvas_height,
                    export_format,
                    created_at,
                    created_at,
                ),
            )
        rig = self.get_character_rig_for_workspace(rig_id, workspace_id)
        if rig is None:
            raise RuntimeError("骨骼素材项目创建失败。")
        return rig

    def list_character_rigs_for_workspace(self, workspace_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT r.*,
                        COUNT(p.id) AS part_count
                    FROM character_rigs r
                    LEFT JOIN character_parts p ON p.rig_id = r.id
                    WHERE r.workspace_id = ?
                    GROUP BY r.id
                    ORDER BY r.updated_at DESC
                    """,
                    (workspace_id,),
                ).fetchall()
            )

    def get_character_rig_for_workspace(self, rig_id: str, workspace_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT r.*,
                    COUNT(p.id) AS part_count
                FROM character_rigs r
                LEFT JOIN character_parts p ON p.rig_id = r.id
                WHERE r.id = ? AND r.workspace_id = ?
                GROUP BY r.id
                """,
                (rig_id, workspace_id),
            ).fetchone()

    def list_character_parts(self, rig_id: str, workspace_id: str, *, enabled_only: bool = False) -> list[sqlite3.Row]:
        where_enabled = "AND p.enabled = 1" if enabled_only else ""
        with self._connect() as connection:
            return list(
                connection.execute(
                    f"""
                    SELECT p.*,
                        pa.path AS part_path,
                        pa.mime_type AS part_mime_type,
                        ma.path AS mask_path,
                        ma.mime_type AS mask_mime_type
                    FROM character_parts p
                    JOIN character_rigs r ON r.id = p.rig_id
                    LEFT JOIN assets pa ON pa.id = p.part_asset_id
                    LEFT JOIN assets ma ON ma.id = p.mask_asset_id
                    WHERE p.rig_id = ? AND r.workspace_id = ? {where_enabled}
                    ORDER BY p.z_index ASC, p.created_at ASC
                    """,
                    (rig_id, workspace_id),
                ).fetchall()
            )

    def get_character_part_for_workspace(self, rig_id: str, part_id: str, workspace_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT p.*,
                    pa.path AS part_path,
                    ma.path AS mask_path
                FROM character_parts p
                JOIN character_rigs r ON r.id = p.rig_id
                LEFT JOIN assets pa ON pa.id = p.part_asset_id
                LEFT JOIN assets ma ON ma.id = p.mask_asset_id
                WHERE p.id = ? AND p.rig_id = ? AND r.workspace_id = ?
                """,
                (part_id, rig_id, workspace_id),
            ).fetchone()

    def replace_character_parts(
        self,
        rig_id: str,
        workspace_id: str,
        parts: list[dict[str, Any]],
        *,
        updated_at: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM character_parts
                WHERE rig_id = ?
                AND EXISTS (
                    SELECT 1 FROM character_rigs
                    WHERE character_rigs.id = character_parts.rig_id
                    AND character_rigs.workspace_id = ?
                )
                """,
                (rig_id, workspace_id),
            )
            for part in parts:
                connection.execute(
                    """
                    INSERT INTO character_parts (
                        id, rig_id, part_asset_id, mask_asset_id, name, semantic_type,
                        bbox_json, pivot_x, pivot_y, parent_id, z_index, enabled,
                        needs_completion, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        part.get("id") or uuid4().hex,
                        rig_id,
                        part.get("part_asset_id"),
                        part.get("mask_asset_id"),
                        str(part.get("name") or "部件"),
                        str(part.get("semantic_type") or "part"),
                        json.dumps(part.get("bbox") or [0, 0, 1, 1], ensure_ascii=False),
                        float(part.get("pivot_x", 0.5)),
                        float(part.get("pivot_y", 0.5)),
                        part.get("parent_id"),
                        int(part.get("z_index", 0)),
                        1 if part.get("enabled", True) else 0,
                        1 if part.get("needs_completion", False) else 0,
                        updated_at,
                        updated_at,
                    ),
                )
            connection.execute(
                "UPDATE character_rigs SET status = 'ready', updated_at = ? WHERE id = ? AND workspace_id = ?",
                (updated_at, rig_id, workspace_id),
            )

    def update_character_rig(
        self,
        rig_id: str,
        workspace_id: str,
        *,
        name: str | None = None,
        export_format: str | None = None,
        status: str | None = None,
        updated_at: str,
    ) -> sqlite3.Row | None:
        current = self.get_character_rig_for_workspace(rig_id, workspace_id)
        if current is None:
            return None
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE character_rigs
                SET name = COALESCE(?, name),
                    export_format = COALESCE(?, export_format),
                    status = COALESCE(?, status),
                    updated_at = ?
                WHERE id = ? AND workspace_id = ?
                """,
                (name, export_format, status, updated_at, rig_id, workspace_id),
            )
        return self.get_character_rig_for_workspace(rig_id, workspace_id)

    def update_character_parts(
        self,
        rig_id: str,
        workspace_id: str,
        parts: list[dict[str, Any]],
        *,
        updated_at: str,
    ) -> None:
        with self._connect() as connection:
            for part in parts:
                connection.execute(
                    """
                    UPDATE character_parts
                    SET name = COALESCE(?, name),
                        semantic_type = COALESCE(?, semantic_type),
                        bbox_json = COALESCE(?, bbox_json),
                        pivot_x = COALESCE(?, pivot_x),
                        pivot_y = COALESCE(?, pivot_y),
                        parent_id = COALESCE(?, parent_id),
                        z_index = COALESCE(?, z_index),
                        enabled = COALESCE(?, enabled),
                        needs_completion = COALESCE(?, needs_completion),
                        updated_at = ?
                    WHERE id = ?
                    AND rig_id = ?
                    AND EXISTS (
                        SELECT 1 FROM character_rigs
                        WHERE character_rigs.id = character_parts.rig_id
                        AND character_rigs.workspace_id = ?
                    )
                    """,
                    (
                        part.get("name"),
                        part.get("semantic_type"),
                        None if part.get("bbox") is None else json.dumps(part["bbox"], ensure_ascii=False),
                        part.get("pivot_x"),
                        part.get("pivot_y"),
                        part.get("parent_id"),
                        part.get("z_index"),
                        None if part.get("enabled") is None else 1 if part["enabled"] else 0,
                        None if part.get("needs_completion") is None else 1 if part["needs_completion"] else 0,
                        updated_at,
                        part["id"],
                        rig_id,
                        workspace_id,
                    ),
                )
            connection.execute(
                "UPDATE character_rigs SET updated_at = ? WHERE id = ? AND workspace_id = ?",
                (updated_at, rig_id, workspace_id),
            )

    def update_character_part_assets(
        self,
        rig_id: str,
        part_id: str,
        workspace_id: str,
        *,
        part_asset_id: str,
        mask_asset_id: str,
        bbox: list[int],
        needs_completion: bool,
        updated_at: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE character_parts
                SET part_asset_id = ?,
                    mask_asset_id = ?,
                    bbox_json = ?,
                    needs_completion = ?,
                    updated_at = ?
                WHERE id = ?
                AND rig_id = ?
                AND EXISTS (
                    SELECT 1 FROM character_rigs
                    WHERE character_rigs.id = character_parts.rig_id
                    AND character_rigs.workspace_id = ?
                )
                """,
                (
                    part_asset_id,
                    mask_asset_id,
                    json.dumps(bbox, ensure_ascii=False),
                    1 if needs_completion else 0,
                    updated_at,
                    part_id,
                    rig_id,
                    workspace_id,
                ),
            )
            connection.execute(
                "UPDATE character_rigs SET updated_at = ? WHERE id = ? AND workspace_id = ?",
                (updated_at, rig_id, workspace_id),
            )

    def collect_character_rig_asset_ids(self, rig_id: str, workspace_id: str) -> list[str]:
        rig = self.get_character_rig_for_workspace(rig_id, workspace_id)
        if rig is None:
            return []
        asset_ids = [rig["source_asset_id"]]
        for part in self.list_character_parts(rig_id, workspace_id):
            for key in ("part_asset_id", "mask_asset_id"):
                value = part[key]
                if value and value not in asset_ids:
                    asset_ids.append(value)
        return asset_ids

    def collect_character_part_asset_ids(self, rig_id: str, workspace_id: str) -> list[str]:
        asset_ids: list[str] = []
        for part in self.list_character_parts(rig_id, workspace_id):
            for key in ("part_asset_id", "mask_asset_id"):
                value = part[key]
                if value and value not in asset_ids:
                    asset_ids.append(value)
        return asset_ids

    def delete_character_rig_for_workspace(self, rig_id: str, workspace_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM character_rigs WHERE id = ? AND workspace_id = ?", (rig_id, workspace_id))
            return cursor.rowcount > 0

    def list_settings(self) -> dict[str, str]:
        with self._connect() as connection:
            rows = connection.execute("SELECT key, value FROM system_settings ORDER BY key").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def table_columns(self, table_name: str) -> list[str]:
        # 测试通过真实 schema 检查字段，避免 Community 数据表重新混入账号字段。
        with self._connect() as connection:
            rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return [row["name"] for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _asset_from_row(row: sqlite3.Row) -> AssetRecord:
    data: dict[str, Any] = dict(row)
    return AssetRecord(**data)


def _job_from_row(row: sqlite3.Row) -> JobRecord:
    data: dict[str, Any] = dict(row)
    return JobRecord(**data)


def _job_page_filter(workspace_id: str, job_types: list[str] | None, status: str | None) -> tuple[str, list[Any]]:
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
    return " AND ".join(where), values
