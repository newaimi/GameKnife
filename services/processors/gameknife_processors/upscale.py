from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from gameknife_core import ProcessResult

UPSCALE_STYLES = {"general", "anime", "noisy", "pixel"}
UPSCALE_SCALES = {2, 4, 8}
MAX_OUTPUT_PIXELS = 67_000_000


class UpscaleModelProvider(Protocol):
    device_label: str

    def is_installed(self) -> bool: ...

    def upscale_image(
        self,
        image: Image.Image,
        *,
        style: str,
        target_scale: int,
        denoise: int,
        tile_size: int,
    ) -> tuple[Image.Image, str, str, list[str]]: ...


class UpscaleProcessor:
    def process(
        self,
        input_path: Path,
        output_path: Path,
        parameters: dict[str, Any],
        model_service: UpscaleModelProvider | None = None,
    ) -> ProcessResult:
        started = time.perf_counter()
        style = _read_style(parameters)
        scale = _read_scale(parameters)
        denoise = _read_int(parameters, "denoise", default=0, minimum=0, maximum=3)
        tile_size = _read_int(parameters, "tile_size", default=384, minimum=128, maximum=1024)

        with Image.open(input_path) as source:
            image = source.convert("RGBA")
        _ensure_output_size_allowed(image.width, image.height, scale)

        if style == "pixel":
            output = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
            model_name = "nearest-neighbor"
            device = "CPU"
            warnings: list[str] = []
        elif model_service is None or not model_service.is_installed():
            # AI 超分必须在设置页显式安装模型后运行，任务阶段只读取本地模型，避免后台任务偷偷联网下载。
            raise RuntimeError("图片放大模型尚未下载安装，请先到设置页下载安装模型文件。")
        else:
            output, model_name, device, warnings = model_service.upscale_image(
                image,
                style=style,
                target_scale=scale,
                denoise=denoise,
                tile_size=tile_size,
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output.save(output_path, format="PNG")
        return ProcessResult(
            output_paths=[output_path],
            result={
                "input_size": [image.width, image.height],
                "output_size": [output.width, output.height],
                "scale": scale,
                "style": style,
                "denoise": denoise,
                "tile_size": tile_size,
                "model": model_name,
                "warnings": warnings,
            },
            duration_ms=int((time.perf_counter() - started) * 1000),
            device=device,
        )


def _read_style(parameters: dict[str, Any]) -> str:
    style = str(parameters.get("style") or "general")
    return style if style in UPSCALE_STYLES else "general"


def _read_scale(parameters: dict[str, Any]) -> int:
    try:
        scale = int(parameters.get("scale", 4))
    except (TypeError, ValueError):
        scale = 4
    return scale if scale in UPSCALE_SCALES else 4


def _read_int(parameters: dict[str, Any], key: str, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(parameters.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _ensure_output_size_allowed(width: int, height: int, scale: int) -> None:
    output_pixels = width * height * scale * scale
    if output_pixels <= MAX_OUTPUT_PIXELS:
        return
    raise RuntimeError("放大后的图片超过 67MP 上限，请降低倍率或先裁切图片。")
