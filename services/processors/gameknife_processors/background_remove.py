from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from gameknife_core import ProcessResult
from gameknife_processors.image_utils import apply_alpha, smooth_alpha


class AlphaPredictor(Protocol):
    @property
    def device_label(self) -> str: ...

    def predict_alpha(self, image: Image.Image): ...


class BackgroundRemoveProcessor:
    def process(self, input_path: Path, output_path: Path, parameters: dict[str, Any], service: AlphaPredictor) -> ProcessResult:
        started = time.perf_counter()
        source = Image.open(input_path).convert("RGBA")
        source.load()
        alpha = service.predict_alpha(source)
        alpha = smooth_alpha(alpha, int(parameters.get("alpha_smoothing", 0)))
        result = apply_alpha(source, alpha)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(output_path, format="PNG")
        return ProcessResult(
            output_paths=[output_path],
            result={"warnings": []},
            duration_ms=int((time.perf_counter() - started) * 1000),
            device=service.device_label,
        )
