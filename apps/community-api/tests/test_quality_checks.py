from __future__ import annotations

import io
import json
import wave
import zipfile
from pathlib import Path

import numpy as np
from gameknife_processors import (
    check_audio_asset,
    check_component_archive,
    check_generated_images,
    unavailable_quality_result,
)
from PIL import Image


def test_generated_image_quality_detects_duplicates_palette_and_unavailable_ocr(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    pixels = np.zeros((960, 1600, 4), dtype=np.uint8)
    pixels[:, :, 0] = np.linspace(64, 255, 1600, dtype=np.uint8)
    pixels[:, :, 1] = 32
    pixels[:, :, 3] = 255
    Image.fromarray(pixels, "RGBA").save(first)
    Image.fromarray(pixels, "RGBA").save(second)

    results = check_generated_images(
        [first, second],
        expected_size="2K",
        palette=["#ff2020", "#402020"],
        expect_no_text=True,
        expect_transparency=True,
        ocr_runner=lambda _path: (False, 0, None),
    )

    assert results[0].status == "unchecked"
    assert results[1].status == "unchecked"
    assert results[0].content_sha256 == results[1].content_sha256
    assert next(
        item for item in results[1].checks if item.code == "IMAGE_NEAR_DUPLICATE"
    ).status == "warning"
    assert next(
        item for item in results[0].checks if item.code == "UI_UNEXPECTED_TEXT"
    ).status == "not_checked"
    transparency = next(
        item for item in results[0].checks if item.code == "IMAGE_TRANSPARENCY"
    )
    assert transparency.status == "warning"
    assert transparency.metrics["required"] is True


def test_no_text_ocr_detection_produces_warning_without_persisting_text(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "ui.png"
    image = Image.new("RGB", (1600, 900), (20, 30, 40))
    for x in range(100, 1500):
        image.putpixel((x, x % 800 + 50), (220, 180, 60))
    image.save(image_path)

    result = check_generated_images(
        [image_path],
        expected_size="2K",
        expect_no_text=True,
        ocr_runner=lambda _path: (True, 2, 91.0),
    )[0]

    assert result.status == "warning"
    payload = json.loads(result.checks_json())
    assert payload["parameters"] == {
        "check_type": "image",
        "expected_size": "2K",
        "palette": [],
        "expect_no_text": True,
        "expect_transparency": False,
        "expect_seamless": False,
    }
    ocr = next(item for item in payload["checks"] if item["code"] == "UI_UNEXPECTED_TEXT")
    assert ocr["metrics"] == {"detected_regions": 2, "max_confidence": 91.0}
    assert "recognized" not in result.checks_json().lower()


def test_generated_image_quality_checks_transparency_and_seam_boundaries(
    tmp_path: Path,
) -> None:
    cutout_path = tmp_path / "cutout.png"
    cutout = np.zeros((960, 1600, 4), dtype=np.uint8)
    cutout[120:840, 240:1360, 0] = np.linspace(
        32,
        224,
        1120,
        dtype=np.uint8,
    )
    cutout[120:840, 240:1360, 1] = 96
    cutout[120:840, 240:1360, 3] = 255
    Image.fromarray(cutout, "RGBA").save(cutout_path)

    cutout_result = check_generated_images(
        [cutout_path],
        expected_size="2K",
        expect_transparency=True,
    )[0]

    transparency = next(
        item for item in cutout_result.checks if item.code == "IMAGE_TRANSPARENCY"
    )
    assert transparency.status == "passed"
    assert transparency.metrics["transparent_ratio"] > 0.4
    assert transparency.metrics["border_visible_ratio"] == 0.0

    texture_path = tmp_path / "texture.png"
    texture = np.zeros((960, 1600, 3), dtype=np.uint8)
    texture[:, :, 0] = np.linspace(0, 255, 1600, dtype=np.uint8)
    texture[:, :, 1] = np.arange(960, dtype=np.uint8)[:, None]
    Image.fromarray(texture, "RGB").save(texture_path)

    texture_result = check_generated_images(
        [texture_path],
        expected_size="2K",
        expect_seamless=True,
    )[0]
    seam = next(item for item in texture_result.checks if item.code == "IMAGE_SEAM")
    assert seam.status == "warning"
    assert seam.metrics["maximum_error"] > 0.12


def test_component_archive_quality_validates_manifest_and_nine_slice(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "components.zip"
    buffer = io.BytesIO()
    Image.new("RGBA", (24, 18), (255, 0, 0, 255)).save(buffer, format="PNG")
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("hud_button.png", buffer.getvalue())
        archive.writestr(
            "component-manifest.json",
            json.dumps(
                {
                    "components": [
                        {
                            "file": "hud_button.png",
                            "width": 24,
                            "height": 18,
                            "nine_slice": {
                                "left": 6,
                                "top": 4,
                                "right": 6,
                                "bottom": 4,
                            },
                        }
                    ]
                }
            ),
        )

    valid = check_component_archive(archive_path)

    assert valid.status == "passed"
    assert valid.rules_version == "ui-components-v1"

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("component-manifest.json", '{"components": []}')
    invalid = check_component_archive(archive_path)
    assert invalid.status == "failed"


def test_unavailable_quality_result_keeps_retry_parameters_and_no_material_verdict(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "input.png"
    Image.new("RGB", (32, 32), (20, 40, 80)).save(image_path)

    result = unavailable_quality_result(
        image_path,
        rules_version="image-v1",
        parameters={"check_type": "image", "expected_size": "2K"},
    )

    assert result.status == "unchecked"
    payload = json.loads(result.checks_json())
    assert payload["parameters"] == {"check_type": "image", "expected_size": "2K"}
    assert payload["checks"] == [
        {
            "code": "QUALITY_CHECK_UNAVAILABLE",
            "status": "not_checked",
            "message": "Automatic quality checks are temporarily unavailable. Try again.",
            "metrics": {},
        }
    ]


def test_audio_quality_checks_pcm_format_duration_level_and_hash(
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "effect.wav"
    timeline = np.arange(44_100, dtype=np.float64) / 44_100
    mono = 0.5 * np.sin(2 * np.pi * 440 * timeline)
    _write_pcm16_wav(audio_path, np.column_stack((mono, mono)))

    result = check_audio_asset(
        audio_path,
        expected_duration_seconds=1.0,
        asset_type="sound_effect",
    )

    assert result.status == "passed"
    assert result.rules_version == "audio-v1"
    payload = json.loads(result.checks_json())
    assert payload["parameters"] == {
        "check_type": "audio",
        "asset_type": "sound_effect",
        "expected_duration_seconds": 1.0,
        "expect_loop": False,
    }
    audio_format = next(
        item for item in payload["checks"] if item["code"] == "AUDIO_FORMAT"
    )
    assert audio_format["metrics"] == {
        "sample_rate": 44_100,
        "bit_depth": 16,
        "channels": 2,
    }


def test_audio_quality_detects_clipping_silence_and_loop_jump(tmp_path: Path) -> None:
    clipped_path = tmp_path / "clipped.wav"
    clipped = np.zeros((44_100, 2), dtype=np.float64)
    clipped[:4_410] = 1.0
    _write_pcm16_wav(clipped_path, clipped)
    clipped_result = check_audio_asset(clipped_path)
    assert next(
        item
        for item in clipped_result.checks
        if item.code == "AUDIO_PEAK_CLIPPING"
    ).status == "failed"

    silent_path = tmp_path / "silent.wav"
    _write_pcm16_wav(silent_path, np.zeros((44_100, 2), dtype=np.float64))
    silent_result = check_audio_asset(silent_path)
    assert silent_result.status == "failed"
    assert next(
        item
        for item in silent_result.checks
        if item.code == "AUDIO_LEVEL_SILENCE"
    ).status == "failed"

    loop_path = tmp_path / "loop.wav"
    ramp = np.linspace(-0.7, 0.7, 44_100, dtype=np.float64)
    _write_pcm16_wav(loop_path, np.column_stack((ramp, ramp)))
    loop_result = check_audio_asset(loop_path, expect_loop=True)
    assert next(
        item for item in loop_result.checks if item.code == "AUDIO_LOOP_SEAM"
    ).status == "failed"


def _write_pcm16_wav(path: Path, samples: np.ndarray) -> None:
    pcm = np.rint(np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(int(samples.shape[1]))
        wav_file.setsampwidth(2)
        wav_file.setframerate(44_100)
        wav_file.writeframes(np.asarray(pcm, dtype="<i2").tobytes())
