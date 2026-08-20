from __future__ import annotations

from collections.abc import Callable

import pytest

from gameknife_core import JobRecord
from gameknife_jobs import (
    JOB_TYPE_REGISTRY,
    InProcessJobDispatcher,
    JobDeliveryRequirement,
    JobParameterValidationError,
    JobQueue,
    JobSubmissionResult,
    JobTypeRegistry,
    JobTypeSpec,
    TaskSubmission,
)


EXPECTED_JOB_TYPES = {
    "background_remove",
    "asset_board_region_detect",
    "asset_board_cutout",
    "asset_board_region_refine",
    "asset_board_export",
    "image_upscale",
    "sequence_clean",
    "sequence_generate_video",
    "sequence_video_to_frames",
    "sequence_export_frames",
    "sequence_export_spine",
    "sound_effect_generate",
}


def test_job_type_registry_covers_every_public_job_type_once() -> None:
    assert set(JOB_TYPE_REGISTRY) == EXPECTED_JOB_TYPES
    assert len(JOB_TYPE_REGISTRY) == len(EXPECTED_JOB_TYPES)
    assert len({spec.executor for spec in JOB_TYPE_REGISTRY.values()}) == len(EXPECTED_JOB_TYPES)


def test_job_type_registry_rejects_duplicate_job_types() -> None:
    spec = JobTypeSpec(
        job_type="duplicate",
        executor="duplicate",
        commercial_queue=JobQueue.CPU,
        delivery_requirement=JobDeliveryRequirement.RESULT,
        max_output_bytes_estimator=lambda _parameters: 0,
    )

    with pytest.raises(ValueError, match="Duplicate job type: duplicate"):
        JobTypeRegistry((spec, spec))


def test_registry_declares_execution_and_delivery_boundaries() -> None:
    assert JOB_TYPE_REGISTRY["background_remove"].commercial_queue is JobQueue.GPU
    assert JOB_TYPE_REGISTRY["background_remove"].delivery_requirement is JobDeliveryRequirement.OUTPUT_ASSET
    assert JOB_TYPE_REGISTRY["sequence_clean"].delivery_requirement is JobDeliveryRequirement.STATE_CHANGE
    assert JOB_TYPE_REGISTRY["asset_board_region_detect"].delivery_requirement is JobDeliveryRequirement.RESULT

    provider_spec = JOB_TYPE_REGISTRY["sequence_generate_video"]
    assert provider_spec.commercial_queue is JobQueue.EXTERNAL
    assert provider_spec.external_provider is True
    assert JOB_TYPE_REGISTRY["sound_effect_generate"].external_provider is False


def test_output_estimators_validate_parameters_and_return_byte_limits() -> None:
    generated_video = JOB_TYPE_REGISTRY["sequence_generate_video"]
    assert generated_video.estimate_max_output_bytes({"duration": 5, "resolution": "720P"}) == 36 * 1024 * 1024

    video_frames = JOB_TYPE_REGISTRY["sequence_video_to_frames"]
    assert video_frames.estimate_max_output_bytes({"max_frames": 2, "output_size": 128, "fps": 12}) == 4 * 512 * 512 * 4

    sound_effect = JOB_TYPE_REGISTRY["sound_effect_generate"]
    assert sound_effect.estimate_max_output_bytes({"duration_seconds": 1}) == 176_444

    sequence_clean = JOB_TYPE_REGISTRY["sequence_clean"]
    assert sequence_clean.estimate_max_output_bytes({"frame_count": 3, "canvas_width": 128, "canvas_height": 256}) == 393_216


@pytest.mark.parametrize(
    ("job_type", "parameters", "message"),
    (
        ("sequence_generate_video", {"duration": 16, "resolution": "720P"}, "duration must be between 2 and 15"),
        ("sequence_generate_video", {"duration": 5, "resolution": "4K"}, "resolution must be one of"),
        ("sequence_video_to_frames", {"max_frames": 0}, "max_frames must be between 1 and 300"),
        ("image_upscale", {"scale": 3}, "scale must be one of 2, 4, 8"),
        ("sequence_clean", {"frame_count": 3, "canvas_width": 128}, "canvas_height is required"),
        ("sound_effect_generate", {"duration_seconds": True}, "duration_seconds must be a number"),
    ),
)
def test_output_estimators_reject_invalid_parameters(job_type: str, parameters: dict[str, object], message: str) -> None:
    with pytest.raises(JobParameterValidationError, match=message):
        JOB_TYPE_REGISTRY[job_type].estimate_max_output_bytes(parameters)


def test_output_estimator_rejects_non_mapping_parameters() -> None:
    with pytest.raises(JobParameterValidationError, match="Job parameters must be a mapping"):
        JOB_TYPE_REGISTRY["background_remove"].estimate_max_output_bytes(None)  # type: ignore[arg-type]


def test_task_submission_normalizes_optional_identifiers() -> None:
    submission = TaskSubmission(idempotency_key=" request-1 ", quote_id=" quote-1 ")

    assert submission.idempotency_key == "request-1"
    assert submission.quote_id == "quote-1"
    assert TaskSubmission() == TaskSubmission(idempotency_key=None, quote_id=None)


@pytest.mark.parametrize("field_name", ("idempotency_key", "quote_id"))
def test_task_submission_rejects_blank_identifiers(field_name: str) -> None:
    with pytest.raises(ValueError, match=f"{field_name} must not be empty"):
        TaskSubmission(**{field_name: "  "})


def test_job_submission_result_reports_idempotent_replay() -> None:
    job = _job("background_remove")

    assert JobSubmissionResult(job=job).replayed is False
    assert JobSubmissionResult(job=job, replayed=True).job is job


def test_in_process_dispatcher_schedules_explicit_handler_with_stable_ids() -> None:
    calls: list[tuple[str, str]] = []
    scheduled: list[Callable[[], None]] = []
    job = _job("background_remove")
    dispatcher = InProcessJobDispatcher(
        lambda job_id, workspace_id: job if (job_id, workspace_id) == (job.id, job.workspace_id) else None,
        {"background_remove": lambda job_id, workspace_id: calls.append((job_id, workspace_id))},
        scheduler=scheduled.append,
    )

    dispatcher.dispatch(job.id, job.workspace_id)

    assert calls == []
    assert len(scheduled) == 1
    scheduled[0]()
    assert calls == [("job-1", "local")]


def test_in_process_dispatcher_rejects_unknown_or_missing_executors() -> None:
    background_job = _job("background_remove")
    with pytest.raises(ValueError, match="Unknown job executors: arbitrary.module.function"):
        InProcessJobDispatcher(
            lambda _job_id, _workspace_id: background_job,
            {"arbitrary.module.function": lambda _job_id, _workspace_id: None},
        )

    dispatcher = InProcessJobDispatcher(lambda _job_id, _workspace_id: background_job, {})
    with pytest.raises(RuntimeError, match="No in-process handler registered for executor: background_remove"):
        dispatcher.dispatch(background_job.id, background_job.workspace_id)

    unknown_job = _job("unknown")
    unknown_dispatcher = InProcessJobDispatcher(lambda _job_id, _workspace_id: unknown_job, {})
    with pytest.raises(ValueError, match="Unsupported job type: unknown"):
        unknown_dispatcher.dispatch(unknown_job.id, unknown_job.workspace_id)

    missing_dispatcher = InProcessJobDispatcher(lambda _job_id, _workspace_id: None, {})
    with pytest.raises(RuntimeError, match="Cannot dispatch missing job: missing"):
        missing_dispatcher.dispatch("missing", "local")


def _job(job_type: str) -> JobRecord:
    return JobRecord(
        id="job-1",
        workspace_id="local",
        created_by="anonymous",
        job_type=job_type,
        status="pending",
        input_asset_id="asset-1",
        parameters_json="{}",
        result_json="{}",
        device=None,
        duration_ms=0,
        error_message=None,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
