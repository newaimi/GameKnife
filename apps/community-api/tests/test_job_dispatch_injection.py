from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from community_api.main import create_app
from fastapi.testclient import TestClient
from gameknife_api.deps import (
    CommunitySettings,
    get_job_dispatcher,
    get_job_submission_replay,
    get_task_submission,
)
from gameknife_core import JobRecord
from gameknife_jobs import (
    JOB_TYPE_REGISTRY,
    InProcessJobDispatcher,
    JobSubmissionResult,
    TaskSubmission,
    bind_task_submission_request,
)
from PIL import Image

JOB_CREATION_PATHS = {
    "/api/jobs/background-remove",
    "/api/jobs/upscale",
    "/api/jobs/sound-effect",
    "/api/jobs/asset-board/regions",
    "/api/jobs/asset-board/cutout",
    "/api/jobs/asset-board/refine",
    "/api/jobs/asset-board/export",
    "/api/sequences/{sequence_id}/clean",
    "/api/sequences/generate-from-image",
    "/api/sequences/from-video",
    "/api/sequences/{sequence_id}/export/frames",
    "/api/sequences/{sequence_id}/export/spine",
}


class RecordingJobDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def dispatch(self, job_id: str, workspace_id: str) -> None:
        self.calls.append((job_id, workspace_id))


def test_community_runtime_registers_every_public_executor(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    with TestClient(app):
        handlers = app.state.job_execution_handlers

    assert set(handlers) == {spec.executor for spec in JOB_TYPE_REGISTRY.values()}
    assert len(handlers) == 12


def test_every_public_job_creation_route_injects_dispatcher(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    job_routes = {route.path: route for route in app.routes if getattr(route, "path", None) in JOB_CREATION_PATHS}

    assert set(job_routes) == JOB_CREATION_PATHS
    for route in job_routes.values():
        dependencies = {dependency.call for dependency in route.dependant.dependencies}
        assert get_job_dispatcher in dependencies
        assert get_task_submission in dependencies
        assert get_job_submission_replay in dependencies


def test_job_creation_route_calls_injected_dispatcher_with_persisted_ids(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    dispatcher = RecordingJobDispatcher()
    app.dependency_overrides[get_job_dispatcher] = lambda: dispatcher

    submissions: list[TaskSubmission | None] = []

    with TestClient(app) as client:
        original_create_job = app.state.repository.create_job

        def record_create_job(job: JobRecord, submission: TaskSubmission | None = None) -> JobSubmissionResult:
            submissions.append(submission)
            return original_create_job(job, submission)

        app.state.repository.create_job = record_create_job
        uploaded = client.post(
            "/api/assets/images",
            files={"file": ("sheet.png", _png_bytes(), "image/png")},
        )
        created = client.post(
            "/api/jobs/asset-board/regions",
            json={"input_asset_id": uploaded.json()["id"], "parameters": {"min_component_area": 1}},
        )
        stored = client.get(f"/api/jobs/{created.json()['id']}")

    assert created.status_code == 200
    assert stored.json()["status"] == "pending"
    assert dispatcher.calls == [(created.json()["id"], "local")]
    assert len(submissions) == 1
    assert submissions[0] is not None
    assert submissions[0].idempotency_key is None
    assert submissions[0].quote_id is None
    assert submissions[0].request_digest is not None


def test_replayed_workflow_submission_is_not_dispatched_again(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    dispatcher = RecordingJobDispatcher()
    app.dependency_overrides[get_job_dispatcher] = lambda: dispatcher

    with TestClient(app) as client:
        uploaded = client.post(
            "/api/assets/images",
            files={"file": ("sheet.png", _png_bytes(), "image/png")},
        )
        headers = {"Idempotency-Key": "request-1", "X-GameKnife-Quote-Id": "quote-1"}
        first = client.post(
            "/api/jobs/asset-board/regions",
            headers=headers,
            json={"input_asset_id": uploaded.json()["id"], "parameters": {"min_component_area": 1}},
        )
        accepted = app.state.repository.get_job_for_workspace(first.json()["id"], "local")
        assert accepted is not None

        expected_submission = bind_task_submission_request(
            TaskSubmission(idempotency_key="request-1", quote_id="quote-1"),
            method="POST",
            path="/api/jobs/asset-board/regions",
            body=(
                '{"input_asset_id":"'
                + uploaded.json()["id"]
                + '","parameters":{"min_component_area":1}}'
            ).encode(),
        )

        def replay_create_job(_job: JobRecord, submission: TaskSubmission | None = None) -> JobSubmissionResult:
            assert submission == expected_submission
            return JobSubmissionResult(job=accepted, replayed=True)

        app.state.repository.create_job = replay_create_job
        replay = client.post(
            "/api/jobs/asset-board/regions",
            headers=headers,
            json={"input_asset_id": uploaded.json()["id"], "parameters": {"min_component_area": 1}},
        )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert dispatcher.calls == [(first.json()["id"], "local")]


def test_replayed_direct_sequence_submission_is_not_dispatched_again(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    dispatcher = RecordingJobDispatcher()
    app.dependency_overrides[get_job_dispatcher] = lambda: dispatcher

    with TestClient(app) as client:
        imported = client.post(
            "/api/sequences/import",
            data={"name": "replay", "fps": "8"},
            files=[("files", ("replay_001.png", _png_bytes(), "image/png"))],
        )
        sequence_id = imported.json()["id"]
        headers = {"Idempotency-Key": "sequence-request-1", "X-GameKnife-Quote-Id": "quote-2"}
        first = client.post(
            f"/api/sequences/{sequence_id}/clean",
            headers=headers,
            json={"parameters": {}},
        )
        accepted = app.state.repository.get_job_for_workspace(first.json()["id"], "local")
        assert accepted is not None

        expected_submission = bind_task_submission_request(
            TaskSubmission(idempotency_key="sequence-request-1", quote_id="quote-2"),
            method="POST",
            path=f"/api/sequences/{sequence_id}/clean",
            body=b'{"parameters":{}}',
        )

        def replay_create_job(_job: JobRecord, submission: TaskSubmission | None = None) -> JobSubmissionResult:
            assert submission == expected_submission
            return JobSubmissionResult(job=accepted, replayed=True)

        app.state.repository.create_job = replay_create_job
        replay = client.post(
            f"/api/sequences/{sequence_id}/clean",
            headers=headers,
            json={"parameters": {}},
        )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert dispatcher.calls == [(first.json()["id"], "local")]


def test_prevalidation_replay_skips_mutable_sequence_checks(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    dispatcher = RecordingJobDispatcher()
    app.dependency_overrides[get_job_dispatcher] = lambda: dispatcher
    accepted = JobRecord(
        id="accepted-sequence-clean",
        workspace_id="local",
        created_by="anonymous",
        job_type="sequence_clean",
        status="success",
        input_asset_id="deleted-input",
        parameters_json='{"sequence_id":"deleted-sequence"}',
        result_json='{"sequence_id":"deleted-sequence","sequence_revision":1}',
        device="cpu",
        duration_ms=10,
        error_message=None,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:01+00:00",
    )
    app.dependency_overrides[get_job_submission_replay] = lambda: JobSubmissionResult(
        job=accepted,
        replayed=True,
    )

    with TestClient(app) as client:
        replay = client.post(
            "/api/sequences/deleted-sequence/clean",
            headers={
                "Idempotency-Key": "accepted-request",
                "X-GameKnife-Quote-Id": "accepted-quote",
            },
            json={"parameters": {}},
        )

    assert replay.status_code == 200
    assert replay.json()["id"] == accepted.id
    assert replay.json()["status"] == "success"
    assert dispatcher.calls == []


def test_malformed_persisted_parameters_fail_without_escaping_scheduler(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    with TestClient(app) as client:
        uploaded = client.post(
            "/api/assets/images",
            files={"file": ("frame.png", _png_bytes(), "image/png")},
        ).json()
        now = datetime.now(UTC).isoformat()
        job = JobRecord(
            id="malformed-parameters-job",
            workspace_id="local",
            created_by="anonymous",
            job_type="sequence_clean",
            status="pending",
            input_asset_id=uploaded["id"],
            parameters_json="{",
            result_json="{}",
            device=None,
            duration_ms=0,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        app.state.repository.create_job(job)
        dispatcher = InProcessJobDispatcher(
            app.state.repository.get_job_for_workspace,
            app.state.job_execution_handlers,
        )

        dispatcher.dispatch(job.id, job.workspace_id)

        stored = app.state.repository.get_job_for_workspace(job.id, job.workspace_id)

    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_message == f"Invalid parameters for job {job.id}"


def _settings(tmp_path: Path) -> CommunitySettings:
    return CommunitySettings(
        storage_root=tmp_path / "storage",
        database_path=tmp_path / "storage" / "gameknife.sqlite3",
        cors_origins=["*"],
    )


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(buffer, format="PNG")
    return buffer.getvalue()
