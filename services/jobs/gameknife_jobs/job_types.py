from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class JobQueue(StrEnum):
    """Commercial execution queues exposed without coupling public jobs to a broker."""

    CPU = "cpu"
    GPU = "gpu"
    EXTERNAL = "external"


class JobDeliveryRequirement(StrEnum):
    """Persisted outcome required before a job may enter the success state."""

    OUTPUT_ASSET = "output_asset"
    STATE_CHANGE = "state_change"
    RESULT = "result"


class JobParameterValidationError(ValueError):
    """Raised when output estimation cannot safely interpret submitted parameters."""

    pass


OutputSizeEstimator = Callable[[Mapping[str, Any]], int]


@dataclass(frozen=True, slots=True)
class JobTypeSpec:
    """Stable execution, delivery, and capacity metadata for one public job type."""

    job_type: str
    executor: str
    commercial_queue: JobQueue
    delivery_requirement: JobDeliveryRequirement
    max_output_bytes_estimator: OutputSizeEstimator
    external_provider: bool = False

    def __post_init__(self) -> None:
        if not self.job_type.strip():
            raise ValueError("job_type must not be empty")
        if not self.executor.strip():
            raise ValueError("executor must not be empty")

    def estimate_max_output_bytes(self, parameters: Mapping[str, Any]) -> int:
        if not isinstance(parameters, Mapping):
            raise JobParameterValidationError("Job parameters must be a mapping")
        estimated_bytes = self.max_output_bytes_estimator(parameters)
        if isinstance(estimated_bytes, bool) or not isinstance(estimated_bytes, int) or estimated_bytes < 0:
            raise RuntimeError(f"Invalid output-size estimate for job type {self.job_type}")
        return estimated_bytes


class JobTypeRegistry(Mapping[str, JobTypeSpec]):
    """Immutable job-type lookup that rejects duplicate registrations at startup."""

    def __init__(self, specs: Iterable[JobTypeSpec]) -> None:
        registered: dict[str, JobTypeSpec] = {}
        for spec in specs:
            if spec.job_type in registered:
                raise ValueError(f"Duplicate job type: {spec.job_type}")
            registered[spec.job_type] = spec
        self._specs = MappingProxyType(registered)

    def __getitem__(self, job_type: str) -> JobTypeSpec:
        return self._specs[job_type]

    def __iter__(self) -> Iterator[str]:
        return iter(self._specs)

    def __len__(self) -> int:
        return len(self._specs)

    def require(self, job_type: str) -> JobTypeSpec:
        try:
            return self._specs[job_type]
        except KeyError as exc:
            raise ValueError(f"Unsupported job type: {job_type}") from exc


_MIB = 1024 * 1024
_MAX_RGBA_IMAGE_BYTES = 67_000_000 * 4
_VIDEO_BYTES_PER_SECOND = {
    "480P": 2 * _MIB,
    "720P": 4 * _MIB,
    "1080P": 8 * _MIB,
}


def _fixed_output_size(max_bytes: int) -> OutputSizeEstimator:
    def estimate(_parameters: Mapping[str, Any]) -> int:
        return max_bytes

    return estimate


def _no_output(_parameters: Mapping[str, Any]) -> int:
    return 0


def _estimate_upscale_output(parameters: Mapping[str, Any]) -> int:
    _read_int(parameters, "scale", default=4, minimum=2, maximum=8, allowed={2, 4, 8})
    return _MAX_RGBA_IMAGE_BYTES


def _estimate_sequence_clean_output(parameters: Mapping[str, Any]) -> int:
    frame_count = _read_int(parameters, "frame_count", minimum=1, maximum=300)
    canvas_width = _read_int(parameters, "canvas_width", minimum=1, maximum=4096)
    canvas_height = _read_int(parameters, "canvas_height", minimum=1, maximum=4096)
    return frame_count * canvas_width * canvas_height * 4


def _estimate_generated_video_output(parameters: Mapping[str, Any]) -> int:
    duration = _read_int(parameters, "duration", default=5, minimum=2, maximum=15)
    resolution = str(parameters.get("resolution") or "720P").upper()
    try:
        bytes_per_second = _VIDEO_BYTES_PER_SECOND[resolution]
    except KeyError as exc:
        raise JobParameterValidationError("resolution must be one of 480P, 720P, or 1080P") from exc
    return duration * bytes_per_second + 16 * _MIB


def _estimate_video_frames_output(parameters: Mapping[str, Any]) -> int:
    max_frames = _read_int(parameters, "max_frames", default=48, minimum=1, maximum=300)
    output_size = _read_int(parameters, "output_size", default=256, minimum=64, maximum=1024)
    _read_int(parameters, "fps", default=12, minimum=1, maximum=60)
    max_edge = max(512, min(1024, output_size * 3))
    # Extraction persists source and processed PNG assets for every selected frame.
    return max_frames * max_edge * max_edge * 4 * 2


def _estimate_sound_effect_output(parameters: Mapping[str, Any]) -> int:
    duration_seconds = _read_float(parameters, "duration_seconds", default=4.0, minimum=0.5, maximum=30.0)
    # Stable Audio currently returns stereo, 44.1 kHz, 16-bit PCM WAV files.
    return math.ceil(duration_seconds * 44_100 * 2 * 2) + 44


def _estimate_project_export_output(parameters: Mapping[str, Any]) -> int:
    canonical = canonical_project_export_parameters(
        asset_ids=parameters.get("asset_ids"),
        preset=parameters.get("preset"),
        package_name=parameters.get("package_name"),
        input_total_bytes=parameters.get("input_total_bytes"),
    )
    input_total_bytes = int(canonical["input_total_bytes"])
    # Deflate can expand already-compressed media slightly. The fixed headroom also covers central-directory
    # records and the manifest without making capacity depend on archive implementation details.
    return input_total_bytes + max(16 * _MIB, math.ceil(input_total_bytes * 0.05))


def canonical_project_export_parameters(
    *,
    asset_ids: object,
    preset: object,
    package_name: object,
    input_total_bytes: object,
) -> dict[str, Any]:
    if not isinstance(asset_ids, list):
        raise JobParameterValidationError("asset_ids must be a list")
    normalized_ids = list(dict.fromkeys(str(item).strip() for item in asset_ids if str(item).strip()))
    if not 1 <= len(normalized_ids) <= 100:
        raise JobParameterValidationError("asset_ids must contain between 1 and 100 items")
    normalized_preset = str(preset or "").strip().lower()
    if normalized_preset not in {"generic", "unity", "godot"}:
        raise JobParameterValidationError("preset must be generic, unity, or godot")
    total_bytes = _read_int(
        {"input_total_bytes": input_total_bytes},
        "input_total_bytes",
        minimum=1,
        maximum=10 * 1024 * 1024 * 1024,
    )
    raw_name = str(package_name or "").strip()
    stem = raw_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0]
    safe_name = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in stem)
    return {
        "asset_ids": normalized_ids,
        "preset": normalized_preset,
        "package_name": safe_name[:80] or "gameknife-export",
        "input_total_bytes": total_bytes,
    }


def _read_int(
    parameters: Mapping[str, Any],
    key: str,
    *,
    default: int | None = None,
    minimum: int,
    maximum: int,
    allowed: set[int] | None = None,
) -> int:
    raw_value = parameters.get(key, default)
    if raw_value is None:
        raise JobParameterValidationError(f"{key} is required")
    if isinstance(raw_value, bool):
        raise JobParameterValidationError(f"{key} must be an integer")
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise JobParameterValidationError(f"{key} must be an integer") from exc
    if isinstance(raw_value, float) and not raw_value.is_integer():
        raise JobParameterValidationError(f"{key} must be an integer")
    if value < minimum or value > maximum:
        raise JobParameterValidationError(f"{key} must be between {minimum} and {maximum}")
    if allowed is not None and value not in allowed:
        allowed_values = ", ".join(str(item) for item in sorted(allowed))
        raise JobParameterValidationError(f"{key} must be one of {allowed_values}")
    return value


def _read_float(
    parameters: Mapping[str, Any],
    key: str,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    raw_value = parameters.get(key, default)
    if isinstance(raw_value, bool):
        raise JobParameterValidationError(f"{key} must be a number")
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise JobParameterValidationError(f"{key} must be a number") from exc
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise JobParameterValidationError(f"{key} must be between {minimum} and {maximum}")
    return value


JOB_TYPE_REGISTRY = JobTypeRegistry(
    (
        JobTypeSpec(
            job_type="background_remove",
            executor="background_remove",
            commercial_queue=JobQueue.GPU,
            delivery_requirement=JobDeliveryRequirement.OUTPUT_ASSET,
            max_output_bytes_estimator=_fixed_output_size(_MAX_RGBA_IMAGE_BYTES),
        ),
        JobTypeSpec(
            job_type="asset_board_region_detect",
            executor="asset_board_region_detect",
            commercial_queue=JobQueue.CPU,
            delivery_requirement=JobDeliveryRequirement.RESULT,
            max_output_bytes_estimator=_no_output,
        ),
        JobTypeSpec(
            job_type="asset_board_cutout",
            executor="asset_board_cutout",
            commercial_queue=JobQueue.GPU,
            delivery_requirement=JobDeliveryRequirement.OUTPUT_ASSET,
            max_output_bytes_estimator=_fixed_output_size(_MAX_RGBA_IMAGE_BYTES),
        ),
        JobTypeSpec(
            job_type="asset_board_region_refine",
            executor="asset_board_region_refine",
            commercial_queue=JobQueue.CPU,
            delivery_requirement=JobDeliveryRequirement.RESULT,
            max_output_bytes_estimator=_no_output,
        ),
        JobTypeSpec(
            job_type="asset_board_export",
            executor="asset_board_export",
            commercial_queue=JobQueue.CPU,
            delivery_requirement=JobDeliveryRequirement.OUTPUT_ASSET,
            max_output_bytes_estimator=_fixed_output_size(512 * _MIB),
        ),
        JobTypeSpec(
            job_type="image_upscale",
            executor="image_upscale",
            commercial_queue=JobQueue.GPU,
            delivery_requirement=JobDeliveryRequirement.OUTPUT_ASSET,
            max_output_bytes_estimator=_estimate_upscale_output,
        ),
        JobTypeSpec(
            job_type="sequence_clean",
            executor="sequence_clean",
            commercial_queue=JobQueue.CPU,
            delivery_requirement=JobDeliveryRequirement.STATE_CHANGE,
            max_output_bytes_estimator=_estimate_sequence_clean_output,
        ),
        JobTypeSpec(
            job_type="sequence_generate_video",
            executor="sequence_generate_video",
            commercial_queue=JobQueue.EXTERNAL,
            delivery_requirement=JobDeliveryRequirement.OUTPUT_ASSET,
            max_output_bytes_estimator=_estimate_generated_video_output,
            external_provider=True,
        ),
        JobTypeSpec(
            job_type="sequence_video_to_frames",
            executor="sequence_video_to_frames",
            commercial_queue=JobQueue.GPU,
            delivery_requirement=JobDeliveryRequirement.OUTPUT_ASSET,
            max_output_bytes_estimator=_estimate_video_frames_output,
        ),
        JobTypeSpec(
            job_type="sequence_export_frames",
            executor="sequence_export_frames",
            commercial_queue=JobQueue.CPU,
            delivery_requirement=JobDeliveryRequirement.OUTPUT_ASSET,
            max_output_bytes_estimator=_fixed_output_size(4 * 1024 * _MIB),
        ),
        JobTypeSpec(
            job_type="sequence_export_spine",
            executor="sequence_export_spine",
            commercial_queue=JobQueue.CPU,
            delivery_requirement=JobDeliveryRequirement.OUTPUT_ASSET,
            max_output_bytes_estimator=_fixed_output_size(4 * 1024 * _MIB),
        ),
        JobTypeSpec(
            job_type="sound_effect_generate",
            executor="sound_effect_generate",
            commercial_queue=JobQueue.EXTERNAL,
            delivery_requirement=JobDeliveryRequirement.OUTPUT_ASSET,
            max_output_bytes_estimator=_estimate_sound_effect_output,
        ),
        JobTypeSpec(
            job_type="project_export_package",
            executor="project_export_package",
            commercial_queue=JobQueue.CPU,
            delivery_requirement=JobDeliveryRequirement.OUTPUT_ASSET,
            max_output_bytes_estimator=_estimate_project_export_output,
        ),
    )
)
