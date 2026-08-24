from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import wave
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
from PIL import Image, UnidentifiedImageError

QualityItemStatus = Literal["passed", "warning", "failed", "not_checked"]
QualityStatus = Literal["unchecked", "passed", "warning", "failed"]
OcrRunner = Callable[[Path], tuple[bool, int, float | None]]

IMAGE_QUALITY_RULES_VERSION = "image-v1"
UI_COMPONENT_QUALITY_RULES_VERSION = "ui-components-v1"
AUDIO_QUALITY_RULES_VERSION = "audio-v1"


@dataclass(frozen=True, slots=True)
class QualityCheckItem:
    code: str
    status: QualityItemStatus
    message: str
    metrics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AssetQualityResult:
    status: QualityStatus
    rules_version: str
    content_sha256: str
    checks: tuple[QualityCheckItem, ...]
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def checks_json(self) -> str:
        return json.dumps(
            {
                "parameters": dict(self.parameters),
                "checks": [
                    {
                        "code": item.code,
                        "status": item.status,
                        "message": item.message,
                        "metrics": item.metrics,
                    }
                    for item in self.checks
                ]
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


def check_generated_images(
    paths: Sequence[Path],
    *,
    expected_size: str,
    palette: Sequence[str] = (),
    expect_no_text: bool = False,
    expect_transparency: bool = False,
    expect_seamless: bool = False,
    ocr_runner: OcrRunner | None = None,
) -> list[AssetQualityResult]:
    """Check a candidate set while keeping every result bound to its own file hash.

    Pairwise duplicate detection runs after individual parsing so one unreadable candidate does not prevent the
    remaining outputs from receiving measurable results. OCR is required only for explicit no-text UI output; a
    missing OCR runtime leaves that candidate unchecked instead of claiming that it passed.
    """

    parsed = [_read_image_metrics(path) for path in paths]
    duplicate_warnings = _duplicate_candidates(parsed)
    check_parameters = {
        "check_type": "image",
        "expected_size": expected_size.upper(),
        "palette": [str(value) for value in palette],
        "expect_no_text": expect_no_text,
        "expect_transparency": expect_transparency,
        "expect_seamless": expect_seamless,
    }
    results: list[AssetQualityResult] = []
    for index, (path, metrics) in enumerate(zip(paths, parsed, strict=True)):
        checks: list[QualityCheckItem] = []
        if metrics is None:
            checks.append(
                QualityCheckItem(
                    code="IMAGE_DECODE",
                    status="failed",
                    message="图片文件无法解析。",
                    metrics={},
                )
            )
            results.append(
                AssetQualityResult(
                    status="failed",
                    rules_version=IMAGE_QUALITY_RULES_VERSION,
                    content_sha256=_sha256(path),
                    checks=tuple(checks),
                    parameters=check_parameters,
                )
            )
            continue
        checks.append(
            QualityCheckItem(
                code="IMAGE_DECODE",
                status="passed",
                message="图片文件可解析。",
                metrics={
                    "width": metrics["width"],
                    "height": metrics["height"],
                    "format": metrics["format"],
                },
            )
        )
        checks.append(_format_and_aspect_check(metrics))
        checks.append(_dimension_check(metrics, expected_size))
        checks.append(_blank_check(metrics))
        if expect_transparency or bool(metrics["has_transparency"]):
            checks.append(
                _transparency_check(
                    metrics,
                    required=expect_transparency,
                )
            )
        if expect_seamless:
            checks.append(_seam_check(metrics))
        if index in duplicate_warnings:
            checks.append(
                QualityCheckItem(
                    code="IMAGE_NEAR_DUPLICATE",
                    status="warning",
                    message="候选图与同次任务中的其他结果高度相似。",
                    metrics={"other_candidate": duplicate_warnings[index]},
                )
            )
        else:
            checks.append(
                QualityCheckItem(
                    code="IMAGE_NEAR_DUPLICATE",
                    status="passed",
                    message="未发现高度相似的候选图。",
                    metrics={},
                )
            )
        if palette:
            checks.append(_palette_check(metrics, palette))
        if expect_no_text:
            checks.append(_ocr_check(path, ocr_runner or run_tesseract_ocr))
        results.append(
            AssetQualityResult(
                status=_overall_status(checks, require_complete=expect_no_text),
                rules_version=IMAGE_QUALITY_RULES_VERSION,
                content_sha256=str(metrics["content_sha256"]),
                checks=tuple(checks),
                parameters=check_parameters,
            )
        )
    return results


def check_component_archive(path: Path) -> AssetQualityResult:
    checks: list[QualityCheckItem] = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            unsafe_names = [
                name
                for name in names
                if name.startswith(("/", "\\")) or ".." in Path(name).parts
            ]
            if unsafe_names:
                raise ValueError("组件包包含不安全路径。")
            manifest = json.loads(archive.read("component-manifest.json"))
            components = manifest.get("components")
            if not isinstance(components, list) or not components:
                raise ValueError("组件清单为空。")
            for component in components:
                _validate_component_manifest_entry(component, names)
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        checks.append(
            QualityCheckItem(
                code="UI_COMPONENT_MANIFEST",
                status="failed",
                message=str(exc) or "组件包无法解析。",
                metrics={},
            )
        )
    else:
        checks.append(
            QualityCheckItem(
                code="UI_COMPONENT_MANIFEST",
                status="passed",
                message="组件清单、图片和九宫格边界有效。",
                metrics={"component_count": len(components)},
            )
        )
    return AssetQualityResult(
        status=_overall_status(checks),
        rules_version=UI_COMPONENT_QUALITY_RULES_VERSION,
        content_sha256=_sha256(path),
        checks=tuple(checks),
        parameters={"check_type": "ui_components"},
    )


def check_audio_asset(
    path: Path,
    *,
    expected_duration_seconds: float | None = None,
    expect_loop: bool = False,
    asset_type: str = "sound_effect",
) -> AssetQualityResult:
    """Check one PCM WAV asset without claiming to judge artistic quality.

    The current sound workflow always delivers PCM WAV. Keeping this checker on that
    explicit boundary makes bit depth, channels, peak, silence, and loop measurements
    reproducible without silently accepting compressed formats that need a decoder.
    """

    parameters = {
        "check_type": "audio",
        "asset_type": asset_type,
        "expected_duration_seconds": expected_duration_seconds,
        "expect_loop": expect_loop,
    }
    try:
        metrics = _read_wav_metrics(path)
    except (OSError, ValueError, wave.Error):
        return AssetQualityResult(
            status="failed",
            rules_version=AUDIO_QUALITY_RULES_VERSION,
            content_sha256=_sha256(path),
            checks=(
                QualityCheckItem(
                    code="AUDIO_DECODE",
                    status="failed",
                    message="音频文件不是可解析的 PCM WAV。",
                    metrics={},
                ),
            ),
            parameters=parameters,
        )

    checks = [
        QualityCheckItem(
            code="AUDIO_DECODE",
            status="passed",
            message="音频文件可解析。",
            metrics={"encoding": "PCM WAV"},
        ),
        _audio_format_check(metrics),
        _audio_duration_check(
            metrics,
            expected_duration_seconds=expected_duration_seconds,
            asset_type=asset_type,
        ),
        _audio_peak_check(metrics),
        _audio_level_check(metrics),
    ]
    if expect_loop:
        checks.append(_audio_loop_check(metrics))
    return AssetQualityResult(
        status=_overall_status(checks),
        rules_version=AUDIO_QUALITY_RULES_VERSION,
        content_sha256=str(metrics["content_sha256"]),
        checks=tuple(checks),
        parameters=parameters,
    )


def unavailable_quality_result(
    path: Path,
    *,
    rules_version: str,
    parameters: Mapping[str, Any],
) -> AssetQualityResult:
    """Persist an unchecked fact when the checker itself cannot produce a material verdict."""

    return AssetQualityResult(
        status="unchecked",
        rules_version=rules_version,
        content_sha256=_sha256(path),
        checks=(
            QualityCheckItem(
                code="QUALITY_CHECK_UNAVAILABLE",
                status="not_checked",
                message="自动质量检查暂时不可用，请重试。",
                metrics={},
            ),
        ),
        parameters=dict(parameters),
    )


def _read_wav_metrics(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getcomptype() != "NONE":
            raise ValueError("Compressed WAV is not supported")
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
        if channels <= 0 or sample_rate <= 0 or frame_count <= 0:
            raise ValueError("Invalid WAV metadata")
        window_frames = max(1, round(sample_rate * 0.02))
        seam_frames = min(frame_count // 2, window_frames)
        total_frames = 0
        sample_count = 0
        square_sum = 0.0
        peak = 0.0
        clipped_samples = 0
        silent_windows = 0
        window_count = 0
        first_frames: np.ndarray | None = None
        last_frames = np.empty((0, channels), dtype=np.float64)
        while total_frames < frame_count:
            raw_frames = wav_file.readframes(
                min(window_frames, frame_count - total_frames)
            )
            if not raw_frames:
                break
            samples = _decode_pcm_samples(raw_frames, sample_width)
            if samples.size % channels:
                raise ValueError("Incomplete WAV frames")
            channel_samples = samples.reshape(-1, channels)
            read_frames = int(channel_samples.shape[0])
            total_frames += read_frames
            sample_count += int(channel_samples.size)
            square_sum += float(np.sum(np.square(channel_samples)))
            peak = max(peak, float(np.max(np.abs(channel_samples))))
            clipped_samples += int(np.count_nonzero(np.abs(channel_samples) >= 0.999))
            window_level = float(np.sqrt(np.mean(np.square(channel_samples))))
            silent_windows += int(window_level < 0.001)
            window_count += 1
            if first_frames is None:
                first_frames = channel_samples[:seam_frames].copy()
            if seam_frames:
                last_frames = np.concatenate((last_frames, channel_samples))[
                    -seam_frames:
                ].copy()
    if total_frames != frame_count or sample_count <= 0 or first_frames is None:
        raise ValueError("Incomplete WAV frames")
    rms = math.sqrt(square_sum / sample_count)
    clipping_ratio = clipped_samples / sample_count
    level_dbfs = 20 * math.log10(max(rms, 1e-12))
    silence_ratio = silent_windows / window_count
    if seam_frames:
        value_jump = float(
            np.sqrt(np.mean(np.square(first_frames[0] - last_frames[-1])))
        )
        slope_jump = (
            float(
                np.sqrt(
                    np.mean(
                        np.square(
                            (first_frames[1] - first_frames[0])
                            - (last_frames[-1] - last_frames[-2])
                        )
                    )
                )
            )
            if seam_frames > 1
            else 0.0
        )
        loop_seam_rms = max(value_jump, slope_jump)
    else:
        value_jump = 0.0
        slope_jump = 0.0
        loop_seam_rms = 0.0
    return {
        "content_sha256": _sha256(path),
        "duration_seconds": frame_count / sample_rate,
        "sample_rate": sample_rate,
        "bit_depth": sample_width * 8,
        "channels": channels,
        "peak": peak,
        "clipping_ratio": clipping_ratio,
        "level_dbfs": level_dbfs,
        "silence_ratio": silence_ratio,
        "loop_seam_rms": loop_seam_rms,
        "loop_value_jump_rms": value_jump,
        "loop_slope_jump_rms": slope_jump,
    }


def _decode_pcm_samples(raw_frames: bytes, sample_width: int) -> np.ndarray:
    if sample_width == 1:
        return (np.frombuffer(raw_frames, dtype=np.uint8).astype(np.float64) - 128) / 128
    if sample_width == 2:
        return np.frombuffer(raw_frames, dtype="<i2").astype(np.float64) / 32768
    if sample_width == 3:
        packed = np.frombuffer(raw_frames, dtype=np.uint8)
        if packed.size % 3:
            raise ValueError("Invalid 24-bit PCM payload")
        triples = packed.reshape(-1, 3).astype(np.int32)
        values = triples[:, 0] | (triples[:, 1] << 8) | (triples[:, 2] << 16)
        signed = (values ^ 0x800000) - 0x800000
        return signed.astype(np.float64) / 8_388_608
    if sample_width == 4:
        return np.frombuffer(raw_frames, dtype="<i4").astype(np.float64) / 2_147_483_648
    raise ValueError("Unsupported PCM bit depth")


def _audio_format_check(metrics: Mapping[str, Any]) -> QualityCheckItem:
    sample_rate = int(metrics["sample_rate"])
    bit_depth = int(metrics["bit_depth"])
    channels = int(metrics["channels"])
    supported = (
        sample_rate in {44_100, 48_000}
        and bit_depth in {16, 24, 32}
        and channels in {1, 2}
    )
    return QualityCheckItem(
        code="AUDIO_FORMAT",
        status="passed" if supported else "warning",
        message=(
            "采样率、位深和声道符合交付规格。"
            if supported
            else "采样率、位深或声道需要人工确认。"
        ),
        metrics={
            "sample_rate": sample_rate,
            "bit_depth": bit_depth,
            "channels": channels,
        },
    )


def _audio_duration_check(
    metrics: Mapping[str, Any],
    *,
    expected_duration_seconds: float | None,
    asset_type: str,
) -> QualityCheckItem:
    duration = float(metrics["duration_seconds"])
    if expected_duration_seconds is not None:
        expected = float(expected_duration_seconds)
        difference = abs(duration - expected)
        pass_tolerance = max(0.1, expected * 0.03)
        warning_tolerance = max(0.5, expected * 0.15)
        status: QualityItemStatus = (
            "passed"
            if difference <= pass_tolerance
            else "warning"
            if difference <= warning_tolerance
            else "failed"
        )
    else:
        expected = None
        status = "warning" if asset_type == "sound_effect" and duration > 30 else "passed"
    return QualityCheckItem(
        code="AUDIO_DURATION",
        status=status,
        message=(
            "音频时长符合任务参数。"
            if status == "passed"
            else "音频时长与任务参数存在偏差。"
            if expected is not None
            else "声效时长超过当前单次任务范围。"
        ),
        metrics={
            "duration_seconds": round(duration, 4),
            "expected_duration_seconds": expected,
        },
    )


def _audio_peak_check(metrics: Mapping[str, Any]) -> QualityCheckItem:
    peak = float(metrics["peak"])
    clipping_ratio = float(metrics["clipping_ratio"])
    status: QualityItemStatus = (
        "failed"
        if clipping_ratio >= 0.01
        else "warning"
        if clipping_ratio > 0 or peak >= 0.999
        else "passed"
    )
    return QualityCheckItem(
        code="AUDIO_PEAK_CLIPPING",
        status=status,
        message=(
            "峰值正常，未发现削波。"
            if status == "passed"
            else "检测到少量满幅采样，请试听确认。"
            if status == "warning"
            else "检测到明显削波。"
        ),
        metrics={
            "peak": round(peak, 6),
            "clipping_ratio": round(clipping_ratio, 6),
        },
    )


def _audio_level_check(metrics: Mapping[str, Any]) -> QualityCheckItem:
    level_dbfs = float(metrics["level_dbfs"])
    silence_ratio = float(metrics["silence_ratio"])
    status: QualityItemStatus = (
        "failed"
        if level_dbfs <= -55 or silence_ratio >= 0.98
        else "warning"
        if level_dbfs <= -35 or silence_ratio >= 0.8
        else "passed"
    )
    return QualityCheckItem(
        code="AUDIO_LEVEL_SILENCE",
        status=status,
        message=(
            "音频电平和静音比例正常。"
            if status == "passed"
            else "音频整体偏安静或包含较多静音。"
            if status == "warning"
            else "音频接近静音。"
        ),
        metrics={
            "rms_dbfs": round(level_dbfs, 3),
            "silent_window_ratio": round(silence_ratio, 4),
        },
    )


def _audio_loop_check(metrics: Mapping[str, Any]) -> QualityCheckItem:
    seam_rms = float(metrics["loop_seam_rms"])
    status: QualityItemStatus = (
        "failed" if seam_rms >= 0.2 else "warning" if seam_rms >= 0.08 else "passed"
    )
    return QualityCheckItem(
        code="AUDIO_LOOP_SEAM",
        status=status,
        message=(
            "首尾接缝平滑。"
            if status == "passed"
            else "首尾接缝可能产生跳变，请试听确认。"
            if status == "warning"
            else "首尾接缝存在明显跳变。"
        ),
        metrics={
            "seam_rms": round(seam_rms, 6),
            "value_jump_rms": round(float(metrics["loop_value_jump_rms"]), 6),
            "slope_jump_rms": round(float(metrics["loop_slope_jump_rms"]), 6),
        },
    )


def run_tesseract_ocr(path: Path) -> tuple[bool, int, float | None]:
    executable = shutil.which("tesseract")
    if executable is None:
        return False, 0, None
    try:
        completed = subprocess.run(
            [
                executable,
                str(path),
                "stdout",
                "-l",
                "eng+chi_sim",
                "--psm",
                "11",
                "tsv",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False, 0, None
    if completed.returncode != 0:
        return False, 0, None
    confidences: list[float] = []
    for line in completed.stdout.splitlines()[1:]:
        columns = line.split("\t")
        if len(columns) < 12 or not columns[11].strip():
            continue
        try:
            confidence = float(columns[10])
        except ValueError:
            continue
        if confidence >= 60:
            confidences.append(confidence)
    return True, len(confidences), max(confidences, default=None)


def _read_image_metrics(path: Path) -> dict[str, Any] | None:
    try:
        with Image.open(path) as image:
            image.load()
            rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
            full_grayscale = np.asarray(image.convert("L"), dtype=np.uint8)
            grayscale = np.asarray(image.convert("L").resize((9, 8)), dtype=np.uint8)
            sampled = np.asarray(image.convert("RGBA").resize((64, 64)), dtype=np.float32)
            image_format = str(image.format or "").upper()
    except (OSError, UnidentifiedImageError):
        return None
    visible = rgba[:, :, 3] > 4
    alpha = rgba[:, :, 3]
    border_alpha = np.concatenate(
        (alpha[0, :], alpha[-1, :], alpha[:, 0], alpha[:, -1])
    )
    visible_luma = full_grayscale[visible]
    luma_std = float(np.std(visible_luma)) if visible_luma.size else 0.0
    normalized_rgba = rgba.astype(np.float32) / 255.0
    horizontal_seam_error = float(
        np.mean(np.abs(normalized_rgba[:, 0, :] - normalized_rgba[:, -1, :]))
    )
    vertical_seam_error = float(
        np.mean(np.abs(normalized_rgba[0, :, :] - normalized_rgba[-1, :, :]))
    )
    return {
        "content_sha256": _sha256(path),
        "width": int(rgba.shape[1]),
        "height": int(rgba.shape[0]),
        "format": image_format,
        "transparent_ratio": float(np.mean(~visible)),
        "semi_transparent_ratio": float(np.mean((alpha > 4) & (alpha < 250))),
        "border_visible_ratio": float(np.mean(border_alpha > 4)),
        "has_transparency": bool(np.any(alpha < 250)),
        "horizontal_seam_error": horizontal_seam_error,
        "vertical_seam_error": vertical_seam_error,
        "luma_std": luma_std,
        "dhash": tuple(bool(value) for value in (grayscale[:, 1:] > grayscale[:, :-1]).flat),
        "sampled_rgb": sampled[:, :, :3][sampled[:, :, 3] > 4],
    }


def _format_and_aspect_check(metrics: dict[str, Any]) -> QualityCheckItem:
    image_format = str(metrics["format"])
    width = int(metrics["width"])
    height = int(metrics["height"])
    aspect_ratio = width / max(height, 1)
    if image_format not in {"PNG", "JPEG"}:
        status: QualityItemStatus = "failed"
        message = "图片格式不属于生成任务允许的 PNG 或 JPEG。"
    elif aspect_ratio < 0.2 or aspect_ratio > 5.0:
        status = "warning"
        message = "图片宽高比异常，请确认是否符合任务预期。"
    else:
        status = "passed"
        message = "图片格式和宽高比有效。"
    return QualityCheckItem(
        code="IMAGE_FORMAT_ASPECT",
        status=status,
        message=message,
        metrics={
            "format": image_format,
            "aspect_ratio": round(aspect_ratio, 4),
        },
    )


def _dimension_check(metrics: dict[str, Any], expected_size: str) -> QualityCheckItem:
    minimum_long_edge = {"2K": 1536, "3K": 2560, "4K": 3584}.get(
        expected_size.upper(),
        1,
    )
    long_edge = max(int(metrics["width"]), int(metrics["height"]))
    status: QualityItemStatus = "passed" if long_edge >= minimum_long_edge else "warning"
    return QualityCheckItem(
        code="IMAGE_DIMENSIONS",
        status=status,
        message="图片尺寸符合任务档位。" if status == "passed" else "图片长边低于任务档位。",
        metrics={"long_edge": long_edge, "minimum_long_edge": minimum_long_edge},
    )


def _blank_check(metrics: dict[str, Any]) -> QualityCheckItem:
    luma_std = float(metrics["luma_std"])
    status: QualityItemStatus = "failed" if luma_std < 2.0 else "passed"
    return QualityCheckItem(
        code="IMAGE_BLANK",
        status=status,
        message="图片包含可用视觉内容。" if status == "passed" else "图片接近空白或纯色。",
        metrics={
            "luma_std": round(luma_std, 3),
            "transparent_ratio": round(float(metrics["transparent_ratio"]), 4),
        },
    )


def _transparency_check(
    metrics: dict[str, Any],
    *,
    required: bool,
) -> QualityCheckItem:
    transparent_ratio = float(metrics["transparent_ratio"])
    semi_transparent_ratio = float(metrics["semi_transparent_ratio"])
    border_visible_ratio = float(metrics["border_visible_ratio"])
    if required and transparent_ratio < 0.01:
        status: QualityItemStatus = "warning"
        message = "任务要求透明背景，但图片没有形成可用透明区域。"
    elif transparent_ratio > 0 and border_visible_ratio > 0.75:
        status = "warning"
        message = "透明图片边界仍有大面积可见像素，请检查背景残留。"
    elif semi_transparent_ratio > 0.35:
        status = "warning"
        message = "图片包含大面积半透明区域，请检查边缘残留。"
    else:
        status = "passed"
        message = "透明区域和画布边界未发现明显残留。"
    return QualityCheckItem(
        code="IMAGE_TRANSPARENCY",
        status=status,
        message=message,
        metrics={
            "transparent_ratio": round(transparent_ratio, 4),
            "semi_transparent_ratio": round(semi_transparent_ratio, 4),
            "border_visible_ratio": round(border_visible_ratio, 4),
            "required": required,
        },
    )


def _seam_check(metrics: dict[str, Any]) -> QualityCheckItem:
    horizontal_error = float(metrics["horizontal_seam_error"])
    vertical_error = float(metrics["vertical_seam_error"])
    maximum_error = max(horizontal_error, vertical_error)
    status: QualityItemStatus = "warning" if maximum_error > 0.12 else "passed"
    return QualityCheckItem(
        code="IMAGE_SEAM",
        status=status,
        message="图片首尾边缘差异较大。" if status == "warning" else "图片首尾边缘连续。",
        metrics={
            "horizontal_error": round(horizontal_error, 4),
            "vertical_error": round(vertical_error, 4),
            "maximum_error": round(maximum_error, 4),
        },
    )


def _duplicate_candidates(parsed: Sequence[dict[str, Any] | None]) -> dict[int, int]:
    warnings: dict[int, int] = {}
    for index, current in enumerate(parsed):
        if current is None:
            continue
        for other_index in range(index):
            other = parsed[other_index]
            if other is None:
                continue
            distance = sum(
                left != right
                for left, right in zip(current["dhash"], other["dhash"], strict=True)
            )
            if distance <= 4:
                warnings[index] = other_index + 1
                break
    return warnings


def _palette_check(metrics: dict[str, Any], palette: Sequence[str]) -> QualityCheckItem:
    colors = [_parse_hex_color(value) for value in palette]
    valid_colors = np.asarray([color for color in colors if color is not None], dtype=np.float32)
    if not valid_colors.size:
        return QualityCheckItem(
            code="IMAGE_PALETTE",
            status="not_checked",
            message="风格档案没有可解析的色板。",
            metrics={},
        )
    pixels = metrics["sampled_rgb"]
    if not pixels.size:
        return QualityCheckItem(
            code="IMAGE_PALETTE",
            status="warning",
            message="图片没有可比较的可见颜色。",
            metrics={},
        )
    distances = np.linalg.norm(
        pixels[:, None, :] - valid_colors[None, :, :],
        axis=2,
    )
    deviation = float(np.mean(np.min(distances, axis=1)) / 441.67295593)
    status: QualityItemStatus = "warning" if deviation > 0.28 else "passed"
    return QualityCheckItem(
        code="IMAGE_PALETTE",
        status=status,
        message="图片颜色偏离项目色板。" if status == "warning" else "图片颜色接近项目色板。",
        metrics={"mean_deviation": round(deviation, 4)},
    )


def _ocr_check(path: Path, runner: OcrRunner) -> QualityCheckItem:
    available, detected_count, max_confidence = runner(path)
    if not available:
        return QualityCheckItem(
            code="UI_UNEXPECTED_TEXT",
            status="not_checked",
            message="OCR 服务不可用，未检查文字。",
            metrics={},
        )
    status: QualityItemStatus = "warning" if detected_count else "passed"
    return QualityCheckItem(
        code="UI_UNEXPECTED_TEXT",
        status=status,
        message="无文字输出中检测到文字。" if detected_count else "未检测到文字。",
        metrics={
            "detected_regions": detected_count,
            "max_confidence": max_confidence,
        },
    )


def _validate_component_manifest_entry(component: object, names: list[str]) -> None:
    if not isinstance(component, dict):
        raise ValueError("组件清单条目无效。")
    filename = str(component.get("file") or "")
    if not filename or filename not in names:
        raise ValueError("组件清单引用的图片不存在。")
    width = int(component.get("width") or 0)
    height = int(component.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ValueError("组件尺寸无效。")
    nine_slice = component.get("nine_slice")
    if nine_slice is None:
        return
    if not isinstance(nine_slice, dict):
        raise ValueError("九宫格边界无效。")
    left = int(nine_slice.get("left", -1))
    top = int(nine_slice.get("top", -1))
    right = int(nine_slice.get("right", -1))
    bottom = int(nine_slice.get("bottom", -1))
    if min(left, top, right, bottom) < 0 or left + right >= width or top + bottom >= height:
        raise ValueError("九宫格边界没有保留可拉伸中心区域。")


def _overall_status(
    checks: Sequence[QualityCheckItem],
    *,
    require_complete: bool = False,
) -> QualityStatus:
    if any(item.status == "failed" for item in checks):
        return "failed"
    if require_complete and any(item.status == "not_checked" for item in checks):
        return "unchecked"
    if any(item.status == "warning" for item in checks):
        return "warning"
    return "passed"


def _parse_hex_color(value: str) -> tuple[int, int, int] | None:
    normalized = str(value or "").strip().lstrip("#")
    if len(normalized) == 3:
        normalized = "".join(character * 2 for character in normalized)
    if len(normalized) != 6:
        return None
    try:
        return tuple(int(normalized[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
