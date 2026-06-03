from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from PIL import Image

from gameknife_core import ProcessResult

UPSCALE_STYLES = {"general", "anime", "noisy", "pixel"}
UPSCALE_SCALES = {2, 4, 8}
MAX_OUTPUT_PIXELS = 67_000_000


class UpscaleProcessor:
    def process(self, input_path: Path, output_path: Path, parameters: dict[str, Any]) -> ProcessResult:
        started = time.perf_counter()
        style = _read_style(parameters)
        scale = _read_scale(parameters)

        with Image.open(input_path) as source:
            image = source.convert("RGBA")
        _ensure_output_size_allowed(image.width, image.height, scale)

        if style != "pixel":
            # Real-ESRGAN 需要设置页显式安装模型后才能运行。
            # 当前 Community 骨架尚未接入模型安装服务，先在创建任务阶段拒绝非像素风请求。
            raise RuntimeError("图片放大模型尚未下载安装，请先到设置页下载安装模型文件。")

        output = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output.save(output_path, format="PNG")
        return ProcessResult(
            output_paths=[output_path],
            result={
                "input_size": [image.width, image.height],
                "output_size": [output.width, output.height],
                "scale": scale,
                "style": style,
                "model": "nearest-neighbor",
                "warnings": [],
            },
            duration_ms=int((time.perf_counter() - started) * 1000),
            device="CPU",
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


def _ensure_output_size_allowed(width: int, height: int, scale: int) -> None:
    output_pixels = width * height * scale * scale
    if output_pixels <= MAX_OUTPUT_PIXELS:
        return
    raise RuntimeError("放大后的图片超过 67MP 上限，请降低倍率或先裁切图片。")
