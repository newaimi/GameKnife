from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import pytest

from gameknife_core import AssetRecord, JobOutputAssetRecord, JobRecord
from gameknife_jobs import (
    SQLITE_SCHEMA_VERSION,
    InvalidJobStateTransitionError,
    JobDeliveryRequirementError,
    ResourceReferenceError,
    SequenceActiveJobError,
    SQLiteGameKnifeRepository,
    TaskSubmission,
    init_sqlite_schema,
)


LEGACY_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
CREATE TABLE assets (
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
CREATE TABLE jobs (
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
CREATE TABLE sequences (
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
CREATE TABLE sequence_frames (
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
CREATE TABLE system_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def test_new_schema_is_versioned_and_uses_restrict_for_asset_references(tmp_path: Path) -> None:
    database_path = tmp_path / "gameknife.sqlite3"
    init_sqlite_schema(database_path)

    with sqlite3.connect(database_path) as connection:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        output_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(job_output_assets)")}
        sequence_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(sequences)")}
        job_foreign_keys = connection.execute("PRAGMA foreign_key_list(jobs)").fetchall()
        frame_foreign_keys = connection.execute("PRAGMA foreign_key_list(sequence_frames)").fetchall()
        output_foreign_keys = connection.execute("PRAGMA foreign_key_list(job_output_assets)").fetchall()

    assert version == SQLITE_SCHEMA_VERSION
    assert {"workspace_id", "created_by"} <= output_columns
    assert {"active_job_id", "revision"} <= sequence_columns
    assert _delete_action(job_foreign_keys, "input_asset_id") == "RESTRICT"
    assert _delete_action(frame_foreign_keys, "source_asset_id") == "RESTRICT"
    assert _delete_action(frame_foreign_keys, "processed_asset_id") == "RESTRICT"
    assert _delete_action(output_foreign_keys, "asset_id") == "RESTRICT"


def test_legacy_schema_migration_preserves_rows_and_backfills_job_outputs(tmp_path: Path) -> None:
    database_path = tmp_path / "gameknife.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(LEGACY_SCHEMA_SQL)
        for asset_id in ("input", "output", "processed"):
            _insert_legacy_asset(connection, asset_id)
        connection.execute(
            """
            INSERT INTO jobs VALUES (
                ?, 'local', 'anonymous', 'background_remove', 'success', ?, '{}', ?,
                'CPU', 5, NULL, ?, ?
            )
            """,
            (
                "job-1",
                "input",
                json.dumps({"output_assets": [{"id": "output", "url": "/api/assets/output"}]}),
                _timestamp(),
                _timestamp(),
            ),
        )
        connection.execute(
            """
            INSERT INTO sequences VALUES (
                'sequence-1', 'local', 'anonymous', 'walk', 12, 1, 16, 16,
                'bottom_center', 0.5, 1.0, '{}', 'ready', ?, ?
            )
            """,
            (_timestamp(), _timestamp()),
        )
        connection.execute(
            """
            INSERT INTO sequence_frames VALUES (
                'frame-1', 'sequence-1', 'input', 'processed', 0, 'frame.png', 16, 16,
                '[0, 0, 16, 16]', 0, 0, 0, 1, 0, ?, ?
            )
            """,
            (_timestamp(), _timestamp()),
        )
        connection.execute("INSERT INTO system_settings VALUES ('theme', 'dark', ?)", (_timestamp(),))

    init_sqlite_schema(database_path)

    repository = SQLiteGameKnifeRepository(database_path)
    job = repository.get_job_for_workspace("job-1", "local")
    frames = repository.list_sequence_frames("sequence-1", "local")
    outputs = repository.list_job_output_assets_for_workspace("job-1", "local")
    with sqlite3.connect(database_path) as connection:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()

    assert version == SQLITE_SCHEMA_VERSION
    assert violations == []
    assert job is not None and job.status == "success"
    assert frames[0]["processed_asset_id"] == "processed"
    assert frames[0]["sequence_id"] == "sequence-1"
    migrated_sequence = repository.get_sequence_for_workspace("sequence-1", "local")
    assert migrated_sequence is not None
    assert migrated_sequence["active_job_id"] is None
    assert migrated_sequence["revision"] == 0
    assert [output.asset_id for output in outputs] == ["output"]
    assert repository.read_setting("theme") == "dark"


def test_asset_references_block_job_deletion_but_sequence_deletion_preserves_shared_assets(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    source = _create_asset(repository, "source")
    output = _create_asset(repository, "output")
    _create_job(repository, "producer", source.id)
    repository.create_job_output_asset(
        JobOutputAssetRecord(
            id="producer-output",
            workspace_id="local",
            created_by="anonymous",
            job_id="producer",
            asset_id=output.id,
            created_at=_timestamp(),
        )
    )
    repository.update_job("producer", "local", status="running", updated_at="2026-01-01T00:00:01+00:00")
    repository.update_job("producer", "local", status="success", updated_at="2026-01-01T00:00:02+00:00")
    _create_job(repository, "consumer", output.id, status="pending", result_json="{}")
    sequence = repository.create_sequence_with_frames(
        workspace_id="local",
        created_by="anonymous",
        name="walk",
        fps=12,
        loop=True,
        clean_parameters={},
        frames=[
            {
                "source_asset_id": output.id,
                "original_name": "output.png",
                "width": 16,
                "height": 16,
                "bbox": [0, 0, 16, 16],
            }
        ],
        created_at=_timestamp(),
    )

    summaries = repository.get_asset_reference_summaries([output.id], "local")
    assert summaries[0].input_job_ids == ("consumer",)
    assert summaries[0].output_job_ids == ("producer",)
    assert len(summaries[0].source_sequence_frame_ids) == 1

    with pytest.raises(ResourceReferenceError) as asset_error:
        repository.delete_assets_for_workspace([output.id], "local")
    assert asset_error.value.resource_kind == "asset"

    with pytest.raises(ResourceReferenceError) as job_error:
        repository.delete_job_for_workspace("producer", "local")
    assert job_error.value.resource_kind == "job"

    detached_assets = repository.delete_sequence_for_workspace(str(sequence["id"]), "local")
    assert detached_assets == []
    assert repository.get_sequence_for_workspace(str(sequence["id"]), "local") is None
    assert repository.get_job_for_workspace("consumer", "local") is not None
    assert repository.get_asset_for_workspace(output.id, "local") is not None


def test_sequence_delete_removes_unreferenced_frame_assets_in_the_same_transaction(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    source = _create_asset(repository, "sequence-only-source")
    sequence = _create_sequence(repository, source.id)

    removed_assets = repository.delete_sequence_for_workspace(str(sequence["id"]), "local")

    assert removed_assets is not None
    assert [asset.id for asset in removed_assets] == [source.id]
    assert repository.get_sequence_for_workspace(str(sequence["id"]), "local") is None
    assert repository.get_asset_for_workspace(source.id, "local") is None


def test_failed_legacy_migration_rolls_back_every_schema_change(tmp_path: Path) -> None:
    database_path = tmp_path / "gameknife.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(LEGACY_SCHEMA_SQL)
        _insert_legacy_asset(connection, "input")
        connection.execute(
            """
            INSERT INTO jobs VALUES (
                'job-1', 'local', 'anonymous', 'background_remove', 'cancelled', 'input',
                '{}', '{}', NULL, 0, NULL, ?, ?
            )
            """,
            (_timestamp(), _timestamp()),
        )

    with pytest.raises(sqlite3.IntegrityError):
        init_sqlite_schema(database_path)

    with sqlite3.connect(database_path) as connection:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        stored_status = str(connection.execute("SELECT status FROM jobs WHERE id = 'job-1'").fetchone()[0])
        job_foreign_keys = connection.execute("PRAGMA foreign_key_list(jobs)").fetchall()
        output_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'job_output_assets'"
        ).fetchone()

    assert version == 0
    assert stored_status == "cancelled"
    assert _delete_action(job_foreign_keys, "input_asset_id") == "CASCADE"
    assert output_table is None


def test_job_state_transitions_are_monotonic_and_same_terminal_update_is_idempotent(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    asset = _create_asset(repository, "input")
    _create_job(repository, "job-1", asset.id, job_type="asset_board_region_detect")

    repository.update_job("job-1", "local", status="running", updated_at="2026-01-01T00:00:01+00:00")
    repository.update_job(
        "job-1",
        "local",
        status="success",
        result_json='{"version": 1}',
        updated_at="2026-01-01T00:00:02+00:00",
    )
    repository.update_job(
        "job-1",
        "local",
        status="success",
        result_json='{"version": 2}',
        updated_at="2026-01-01T00:00:03+00:00",
    )
    repository.update_job(
        "job-1",
        "local",
        result_json='{"version": 3}',
        updated_at="2026-01-01T00:00:04+00:00",
    )

    stored = repository.get_job_for_workspace("job-1", "local")
    assert stored is not None
    assert stored.status == "success"
    assert stored.result_json == '{"version": 1}'
    assert stored.updated_at == "2026-01-01T00:00:02+00:00"

    with pytest.raises(InvalidJobStateTransitionError):
        repository.update_job("job-1", "local", status="failed", updated_at="2026-01-01T00:00:05+00:00")


def test_new_jobs_require_registered_type_and_pending_initial_state(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    asset = _create_asset(repository, "input")
    template = _create_job(repository, "template", asset.id)

    with pytest.raises(ValueError, match="Unsupported job type: unknown"):
        repository.create_job(
            replace(template, id="unknown-job", job_type="unknown")
        )

    with pytest.raises(ValueError, match="must start in the pending state"):
        repository.create_job(
            replace(template, id="running-job", status="running")
        )


def test_community_job_submission_returns_the_persisted_job(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    asset = _create_asset(repository, "input")
    job = _job_record("job-1", asset.id)

    submitted = repository.create_job(
        job,
        TaskSubmission(idempotency_key="community-request", quote_id="community-quote"),
    )

    assert submitted.job == job
    assert submitted.replayed is False
    assert repository.get_job_for_workspace(job.id, "local") == job


def test_result_job_requires_non_empty_json_delivery(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    asset = _create_asset(repository, "input")
    _create_job(repository, "job-1", asset.id, job_type="asset_board_region_detect")
    assert repository.claim_job_for_workspace(
        "job-1",
        "local",
        updated_at="2026-01-01T00:00:01+00:00",
    ) is True

    with pytest.raises(JobDeliveryRequirementError):
        repository.update_job("job-1", "local", status="success", updated_at="2026-01-01T00:00:02+00:00")
    with pytest.raises(JobDeliveryRequirementError):
        repository.update_job(
            "job-1",
            "local",
            status="success",
            result_json="not-json",
            updated_at="2026-01-01T00:00:03+00:00",
        )

    repository.update_job(
        "job-1",
        "local",
        status="success",
        result_json='{"component_count": 1}',
        updated_at="2026-01-01T00:00:04+00:00",
    )
    stored = repository.get_job_for_workspace("job-1", "local")
    assert stored is not None and stored.status == "success"


def test_concurrent_job_claim_allows_only_one_runner(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    asset = _create_asset(repository, "input")
    _create_job(repository, "job-1", asset.id)
    barrier = Barrier(2)

    def claim(index: int) -> bool:
        barrier.wait()
        return repository.claim_job_for_workspace(
            "job-1",
            "local",
            updated_at=f"2026-01-01T00:00:0{index}+00:00",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, (1, 2)))

    assert sorted(claims) == [False, True]
    stored = repository.get_job_for_workspace("job-1", "local")
    assert stored is not None and stored.status == "running"


def test_concurrent_sequence_claim_allows_one_clean_job_and_blocks_user_updates(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    asset = _create_asset(repository, "input")
    sequence = _create_sequence(repository, asset.id)
    _create_job(repository, "clean-1", asset.id, job_type="sequence_clean")
    _create_job(repository, "clean-2", asset.id, job_type="sequence_clean")
    assert repository.claim_job_for_workspace("clean-1", "local", updated_at=_timestamp()) is True
    assert repository.claim_job_for_workspace("clean-2", "local", updated_at=_timestamp()) is True
    barrier = Barrier(2)

    def claim(job_id: str) -> tuple[str, int | None]:
        barrier.wait()
        revision = repository.claim_sequence_for_job(
            str(sequence["id"]),
            "local",
            job_id,
            0,
            updated_at=_timestamp(),
        )
        return job_id, revision

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, ("clean-1", "clean-2")))

    winners = [job_id for job_id, revision in claims if revision == 0]
    assert len(winners) == 1
    claimed = repository.get_sequence_for_workspace_including_processing(str(sequence["id"]), "local")
    assert claimed is not None
    assert claimed["active_job_id"] == winners[0]
    assert claimed["status"] == "cleaning"

    with pytest.raises(SequenceActiveJobError):
        repository.update_sequence(str(sequence["id"]), "local", name="blocked", updated_at=_timestamp())
    with pytest.raises(SequenceActiveJobError):
        repository.update_sequence_frames(str(sequence["id"]), "local", [], updated_at=_timestamp())
    with pytest.raises(SequenceActiveJobError):
        repository.delete_sequence_for_workspace(str(sequence["id"]), "local")

    assert repository.fail_sequence_clean_job(
        str(sequence["id"]),
        "local",
        winners[0],
        0,
        error_message="processor failed",
        updated_at=_timestamp(),
    ) == []
    released = repository.get_sequence_for_workspace(str(sequence["id"]), "local")
    failed_job = repository.get_job_for_workspace(winners[0], "local")
    assert released is not None
    assert released["active_job_id"] is None
    assert released["revision"] == 0
    assert failed_job is not None and failed_job.status == "failed"


def test_sequence_failure_finalizer_releases_claim_after_job_is_already_failed(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    source = _create_asset(repository, "source")
    temporary = _create_asset(repository, "temporary")
    sequence = _create_sequence(repository, source.id)
    _create_job(repository, "clean-job", source.id, job_type="sequence_clean")
    assert repository.claim_job_for_workspace("clean-job", "local", updated_at=_timestamp()) is True
    assert repository.claim_sequence_for_job(
        str(sequence["id"]),
        "local",
        "clean-job",
        0,
        updated_at=_timestamp(),
    ) == 0
    repository.create_job_output_asset(
        JobOutputAssetRecord(
            id="temporary-output",
            workspace_id="local",
            created_by="anonymous",
            job_id="clean-job",
            asset_id=temporary.id,
            created_at=_timestamp(),
        )
    )
    repository.update_job(
        "clean-job",
        "local",
        status="failed",
        error_message="dispatcher failed",
        updated_at=_timestamp(),
    )

    cleanup_assets = repository.fail_sequence_clean_job(
        str(sequence["id"]),
        "local",
        "clean-job",
        0,
        error_message="runner failed",
        updated_at=_timestamp(),
    )

    released = repository.get_sequence_for_workspace(str(sequence["id"]), "local")
    assert released is not None and released["active_job_id"] is None
    assert [asset.id for asset in cleanup_assets] == [temporary.id]
    assert repository.get_asset_for_workspace(temporary.id, "local") is None


def test_sequence_clean_finalize_is_atomic_and_rolls_back_invalid_delivery(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    asset = _create_asset(repository, "input")
    processed = _create_asset(repository, "processed")
    sequence = _create_sequence(repository, asset.id)
    frame = repository.list_sequence_frames(str(sequence["id"]), "local")[0]
    _create_job(repository, "clean-1", asset.id, job_type="sequence_clean")
    repository.create_job_output_asset(
        JobOutputAssetRecord(
            id="clean-output",
            workspace_id="local",
            created_by="anonymous",
            job_id="clean-1",
            asset_id=processed.id,
            created_at=_timestamp(),
        )
    )
    assert repository.claim_job_for_workspace("clean-1", "local", updated_at=_timestamp()) is True
    assert repository.claim_sequence_for_job(
        str(sequence["id"]),
        "local",
        "clean-1",
        0,
        updated_at=_timestamp(),
    ) == 0
    with pytest.raises(JobDeliveryRequirementError):
        repository.finalize_sequence_clean_job(
            str(sequence["id"]),
            "local",
            "clean-1",
            0,
            processed_assets_by_frame={str(frame["id"]): processed.id},
            canvas_width=32,
            canvas_height=32,
            clean_parameters={"alpha_threshold": 32},
            result_json=json.dumps({"sequence_id": sequence["id"], "sequence_revision": 2}),
            device=None,
            duration_ms=10,
            updated_at=_timestamp(),
        )

    unchanged_job = repository.get_job_for_workspace("clean-1", "local")
    unchanged_sequence = repository.get_sequence_for_workspace_including_processing(str(sequence["id"]), "local")
    unchanged_frame = repository.list_sequence_frames(str(sequence["id"]), "local")[0]
    assert unchanged_job is not None and unchanged_job.status == "running"
    assert unchanged_sequence is not None and unchanged_sequence["active_job_id"] == "clean-1"
    assert unchanged_sequence["revision"] == 0
    assert unchanged_frame["processed_asset_id"] is None
    assert [output.asset_id for output in repository.list_job_output_assets_for_workspace("clean-1", "local")] == [
        processed.id
    ]

    completed_revision = repository.finalize_sequence_clean_job(
        str(sequence["id"]),
        "local",
        "clean-1",
        0,
        processed_assets_by_frame={str(frame["id"]): processed.id},
        canvas_width=32,
        canvas_height=32,
        clean_parameters={"alpha_threshold": 32},
        result_json=json.dumps({"sequence_id": sequence["id"], "sequence_revision": 1}),
        device=None,
        duration_ms=10,
        updated_at=_timestamp(),
    )
    assert completed_revision == 1
    stored_job = repository.get_job_for_workspace("clean-1", "local")
    delivered_sequence = repository.get_sequence_for_workspace(str(sequence["id"]), "local")
    delivered_frame = repository.list_sequence_frames(str(sequence["id"]), "local")[0]
    assert stored_job is not None and stored_job.status == "success"
    assert delivered_sequence is not None
    assert delivered_sequence["active_job_id"] is None
    assert delivered_sequence["status"] == "ready"
    assert delivered_sequence["revision"] == 1
    assert delivered_frame["processed_asset_id"] == processed.id
    assert repository.list_job_output_assets_for_workspace("clean-1", "local") == []


def test_video_sequence_stays_hidden_and_locked_until_atomic_finalize(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    video = _create_asset(repository, "video")
    source = _create_asset(repository, "frame-source")
    processed = _create_asset(repository, "frame-processed")
    _create_job(repository, "video-job", video.id, job_type="sequence_video_to_frames")
    assert repository.claim_job_for_workspace("video-job", "local", updated_at=_timestamp()) is True
    for relationship_id, asset_id in (("source-output", source.id), ("processed-output", processed.id)):
        repository.create_job_output_asset(
            JobOutputAssetRecord(
                id=relationship_id,
                workspace_id="local",
                created_by="anonymous",
                job_id="video-job",
                asset_id=asset_id,
                created_at=_timestamp(),
            )
        )
    processing = repository.create_sequence_with_frames_for_job(
        workspace_id="local",
        created_by="anonymous",
        job_id="video-job",
        name="walk",
        fps=12,
        loop=True,
        clean_parameters={"alpha_threshold": 24},
        frames=[
            {
                "source_asset_id": source.id,
                "original_name": "frame-source.png",
                "width": 16,
                "height": 16,
                "bbox": [0, 0, 16, 16],
            }
        ],
        created_at=_timestamp(),
    )
    sequence_id = str(processing["id"])
    frame = repository.list_sequence_frames(sequence_id, "local")[0]

    assert processing["status"] == "processing"
    assert processing["active_job_id"] == "video-job"
    assert repository.get_sequence_for_workspace(sequence_id, "local") is None
    assert repository.list_sequences_for_workspace("local") == []
    with pytest.raises(SequenceActiveJobError):
        repository.delete_sequence_for_workspace(sequence_id, "local")

    revision = repository.finalize_sequence_from_video_job(
        sequence_id,
        "local",
        "video-job",
        processed_assets_by_frame={str(frame["id"]): processed.id},
        canvas_width=32,
        canvas_height=32,
        clean_parameters={"alpha_threshold": 24},
        result_json=json.dumps({"sequence_id": sequence_id, "frame_count": 1}),
        device=None,
        duration_ms=25,
        updated_at=_timestamp(),
    )

    delivered = repository.get_sequence_for_workspace(sequence_id, "local")
    delivered_frame = repository.list_sequence_frames(sequence_id, "local")[0]
    delivered_job = repository.get_job_for_workspace("video-job", "local")
    assert revision == 1
    assert delivered is not None
    assert delivered["status"] == "ready"
    assert delivered["active_job_id"] is None
    assert delivered_frame["processed_asset_id"] == processed.id
    assert delivered_job is not None and delivered_job.status == "success"
    detached_assets = repository.delete_sequence_for_workspace(sequence_id, "local")
    assert detached_assets == []
    assert repository.get_asset_for_workspace(source.id, "local") is not None
    assert repository.get_asset_for_workspace(processed.id, "local") is not None


def test_startup_recovery_fails_incomplete_jobs_and_preserves_shared_success_assets(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    input_asset = _create_asset(repository, "input")
    shared_success = _create_asset(repository, "shared-success")
    clean_temporary = _create_asset(repository, "clean-temporary")
    video_source = _create_asset(repository, "video-source")
    video_processed = _create_asset(repository, "video-processed")

    _create_job(repository, "success-job", input_asset.id)
    repository.create_job_output_asset(
        JobOutputAssetRecord(
            id="success-output",
            workspace_id="local",
            created_by="anonymous",
            job_id="success-job",
            asset_id=shared_success.id,
            created_at=_timestamp(),
        )
    )
    assert repository.claim_job_for_workspace("success-job", "local", updated_at=_timestamp()) is True
    repository.update_job("success-job", "local", status="success", updated_at=_timestamp())

    sequence = _create_sequence(repository, input_asset.id)
    _create_job(repository, "clean-job", input_asset.id, job_type="sequence_clean")
    assert repository.claim_job_for_workspace("clean-job", "local", updated_at=_timestamp()) is True
    assert repository.claim_sequence_for_job(
        str(sequence["id"]), "local", "clean-job", 0, updated_at=_timestamp()
    ) == 0
    for relationship_id, asset_id in (
        ("clean-temporary-output", clean_temporary.id),
        ("clean-shared-output", shared_success.id),
    ):
        repository.create_job_output_asset(
            JobOutputAssetRecord(
                id=relationship_id,
                workspace_id="local",
                created_by="anonymous",
                job_id="clean-job",
                asset_id=asset_id,
                created_at=_timestamp(),
            )
        )

    _create_job(repository, "video-job", input_asset.id, job_type="sequence_video_to_frames")
    assert repository.claim_job_for_workspace("video-job", "local", updated_at=_timestamp()) is True
    for relationship_id, asset_id in (
        ("video-source-output", video_source.id),
        ("video-processed-output", video_processed.id),
    ):
        repository.create_job_output_asset(
            JobOutputAssetRecord(
                id=relationship_id,
                workspace_id="local",
                created_by="anonymous",
                job_id="video-job",
                asset_id=asset_id,
                created_at=_timestamp(),
            )
        )
    processing = repository.create_sequence_with_frames_for_job(
        workspace_id="local",
        created_by="anonymous",
        job_id="video-job",
        name="interrupted",
        fps=12,
        loop=True,
        clean_parameters={},
        frames=[
            {
                "source_asset_id": video_source.id,
                "original_name": "video-source.png",
                "width": 16,
                "height": 16,
                "bbox": [0, 0, 16, 16],
            }
        ],
        created_at=_timestamp(),
    )

    cleanup_assets = repository.recover_incomplete_jobs(
        error_message="service restarted",
        updated_at="2026-01-01T00:00:10+00:00",
    )

    assert {asset.id for asset in cleanup_assets} == {
        clean_temporary.id,
        video_source.id,
        video_processed.id,
    }
    assert repository.get_job_for_workspace("clean-job", "local").status == "failed"  # type: ignore[union-attr]
    assert repository.get_job_for_workspace("video-job", "local").status == "failed"  # type: ignore[union-attr]
    assert repository.get_job_for_workspace("success-job", "local").status == "success"  # type: ignore[union-attr]
    recovered_sequence = repository.get_sequence_for_workspace(str(sequence["id"]), "local")
    assert recovered_sequence is not None and recovered_sequence["active_job_id"] is None
    assert repository.get_sequence_for_workspace_including_processing(str(processing["id"]), "local") is None
    assert repository.get_asset_for_workspace(shared_success.id, "local") is not None
    assert repository.get_asset_for_workspace(clean_temporary.id, "local") is None
    assert repository.get_asset_for_workspace(video_source.id, "local") is None
    assert repository.get_asset_for_workspace(video_processed.id, "local") is None


def test_job_output_cleanup_is_scoped_and_keeps_assets_with_other_references(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    source = _create_asset(repository, "source")
    first_output = _create_asset(repository, "first-output")
    second_output = _create_asset(repository, "second-output")
    _create_job(repository, "job-1", source.id)
    _create_job(repository, "job-2", source.id)
    for relationship_id, job_id, asset_id in (
        ("rel-1", "job-1", first_output.id),
        ("rel-2", "job-1", second_output.id),
        ("rel-3", "job-2", first_output.id),
    ):
        repository.create_job_output_asset(
            JobOutputAssetRecord(
                id=relationship_id,
                workspace_id="local",
                created_by="anonymous",
                job_id=job_id,
                asset_id=asset_id,
                created_at=_timestamp(),
            )
        )

    assert repository.cleanup_job_output_assets_for_workspace("job-1", "local", []) == []
    assert len(repository.list_job_output_assets_for_workspace("job-1", "local")) == 2

    assert repository.cleanup_job_output_assets_for_workspace("job-1", "local", [first_output.id]) == []
    assert [row.asset_id for row in repository.list_job_output_assets_for_workspace("job-1", "local")] == [
        second_output.id
    ]
    assert [row.asset_id for row in repository.list_job_output_assets_for_workspace("job-2", "local")] == [
        first_output.id
    ]
    assert repository.get_asset_for_workspace(first_output.id, "local") is not None

    removed = repository.cleanup_job_output_assets_for_workspace("job-1", "local", [second_output.id])
    assert [asset.id for asset in removed] == [second_output.id]
    assert repository.list_job_output_assets_for_workspace("job-1", "local") == []
    assert len(repository.list_job_output_assets_for_workspace("job-2", "local")) == 1
    assert repository.get_asset_for_workspace(second_output.id, "local") is None


def test_job_output_cleanup_rolls_back_relationship_when_asset_delete_fails(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    source = _create_asset(repository, "source")
    output = _create_asset(repository, "output")
    _create_job(repository, "job-1", source.id)
    repository.create_job_output_asset(
        JobOutputAssetRecord(
            id="rel-1",
            workspace_id="local",
            created_by="anonymous",
            job_id="job-1",
            asset_id=output.id,
            created_at=_timestamp(),
        )
    )
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_output_asset_delete
            BEFORE DELETE ON assets
            WHEN OLD.id = 'output'
            BEGIN
                SELECT RAISE(ABORT, 'delete rejected');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="delete rejected"):
        repository.cleanup_job_output_assets_for_workspace("job-1", "local", [output.id])

    assert repository.get_asset_for_workspace(output.id, "local") is not None
    assert [row.asset_id for row in repository.list_job_output_assets_for_workspace("job-1", "local")] == [
        output.id
    ]


def test_competing_terminal_updates_store_exactly_one_terminal_result(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    asset = _create_asset(repository, "input")
    _create_job(repository, "job-1", asset.id, job_type="asset_board_region_detect")
    repository.update_job("job-1", "local", status="running", updated_at="2026-01-01T00:00:01+00:00")
    barrier = Barrier(2)

    def finish(status: str) -> str:
        barrier.wait()
        try:
            repository.update_job(
                "job-1",
                "local",
                status=status,
                result_json=json.dumps({"terminal": status}),
                error_message="failed" if status == "failed" else None,
                updated_at=f"2026-01-01T00:00:0{2 if status == 'success' else 3}+00:00",
            )
        except InvalidJobStateTransitionError:
            return "rejected"
        return "stored"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(finish, ("success", "failed")))

    stored = repository.get_job_for_workspace("job-1", "local")
    assert stored is not None
    assert sorted(outcomes) == ["rejected", "stored"]
    assert stored.status in {"success", "failed"}
    assert json.loads(stored.result_json)["terminal"] == stored.status


def test_output_job_cannot_succeed_before_an_output_relationship_is_persisted(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    source = _create_asset(repository, "source")
    output = _create_asset(repository, "output")
    _create_job(repository, "job-1", source.id)

    with pytest.raises(InvalidJobStateTransitionError):
        repository.update_job("job-1", "local", status="success", updated_at="2026-01-01T00:00:00+00:00")

    repository.update_job("job-1", "local", status="running", updated_at="2026-01-01T00:00:01+00:00")

    with pytest.raises(JobDeliveryRequirementError):
        repository.update_job("job-1", "local", status="success", updated_at="2026-01-01T00:00:02+00:00")

    repository.create_job_output_asset(
        JobOutputAssetRecord(
            id="job-output",
            workspace_id="local",
            created_by="anonymous",
            job_id="job-1",
            asset_id=output.id,
            created_at=_timestamp(),
        )
    )
    repository.update_job("job-1", "local", status="success", updated_at="2026-01-01T00:00:03+00:00")

    stored = repository.get_job_for_workspace("job-1", "local")
    assert stored is not None and stored.status == "success"


def _repository(tmp_path: Path) -> SQLiteGameKnifeRepository:
    database_path = tmp_path / "gameknife.sqlite3"
    init_sqlite_schema(database_path)
    return SQLiteGameKnifeRepository(database_path)


def _create_asset(repository: SQLiteGameKnifeRepository, asset_id: str) -> AssetRecord:
    asset = AssetRecord(
        id=asset_id,
        workspace_id="local",
        created_by="anonymous",
        kind="image",
        original_name=f"{asset_id}.png",
        path=f"uploads/{asset_id}.png",
        mime_type="image/png",
        size_bytes=1,
        created_at=_timestamp(),
        updated_at=_timestamp(),
    )
    repository.create_asset(asset)
    return asset


def _create_job(
    repository: SQLiteGameKnifeRepository,
    job_id: str,
    input_asset_id: str,
    *,
    status: str = "pending",
    result_json: str = "{}",
    job_type: str = "background_remove",
) -> JobRecord:
    job = _job_record(
        job_id,
        input_asset_id,
        status=status,
        result_json=result_json,
        job_type=job_type,
    )
    repository.create_job(job)
    return job


def _job_record(
    job_id: str,
    input_asset_id: str,
    *,
    status: str = "pending",
    result_json: str = "{}",
    job_type: str = "background_remove",
) -> JobRecord:
    return JobRecord(
        id=job_id,
        workspace_id="local",
        created_by="anonymous",
        job_type=job_type,
        status=status,
        input_asset_id=input_asset_id,
        parameters_json="{}",
        result_json=result_json,
        device=None,
        duration_ms=0,
        error_message=None,
        created_at=_timestamp(),
        updated_at=_timestamp(),
    )


def _create_sequence(repository: SQLiteGameKnifeRepository, asset_id: str) -> sqlite3.Row:
    return repository.create_sequence_with_frames(
        workspace_id="local",
        created_by="anonymous",
        name="idle",
        fps=12,
        loop=True,
        clean_parameters={"alpha_threshold": 24},
        frames=[
            {
                "source_asset_id": asset_id,
                "original_name": "input.png",
                "width": 16,
                "height": 16,
                "bbox": [0, 0, 16, 16],
            }
        ],
        created_at=_timestamp(),
    )


def _insert_legacy_asset(connection: sqlite3.Connection, asset_id: str) -> None:
    connection.execute(
        """
        INSERT INTO assets VALUES (?, 'local', 'anonymous', 'image', ?, ?, 'image/png', 1, ?, ?)
        """,
        (asset_id, f"{asset_id}.png", f"uploads/{asset_id}.png", _timestamp(), _timestamp()),
    )


def _delete_action(rows: list[tuple[object, ...]], from_column: str) -> str:
    return str(next(row[6] for row in rows if row[3] == from_column))


def _timestamp() -> str:
    return "2026-01-01T00:00:00+00:00"
