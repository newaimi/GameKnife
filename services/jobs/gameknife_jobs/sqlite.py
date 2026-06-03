from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

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
