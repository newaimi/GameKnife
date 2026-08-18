from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np
from PIL import Image

from gameknife_core import ComponentCandidate, ProcessResult
from gameknife_processors.image_utils import apply_alpha, connected_components, contract_alpha, decontaminate_edge_colors, smooth_alpha


class AlphaPredictor(Protocol):
    @property
    def device_label(self) -> str: ...

    def predict_alpha(self, image: Image.Image): ...


class AssetBoardSplitProcessor:
    def detect_source_regions(self, input_path: Path, parameters: dict[str, Any]) -> ProcessResult:
        started = time.perf_counter()
        source = Image.open(input_path).convert("RGBA")
        source.load()
        region_alpha = self._build_source_region_alpha(source, parameters)
        components = self._extract_components(region_alpha, parameters)
        component_payloads = self._component_payloads(components)

        return ProcessResult(
            output_paths=[],
            result={
                "image_size": list(source.size),
                "source_components": component_payloads,
                "components": component_payloads,
                "component_count": len(component_payloads),
                "component_revision": int(parameters.get("component_revision", 0) or 0),
            },
            duration_ms=int((time.perf_counter() - started) * 1000),
            device="CPU",
        )

    def cutout(self, input_path: Path, output_path: Path, parameters: dict[str, Any], service: AlphaPredictor) -> ProcessResult:
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
            result={
                "image_size": list(source.size),
                "component_revision": int(parameters.get("component_revision", 0) or 0),
            },
            duration_ms=int((time.perf_counter() - started) * 1000),
            device=service.device_label,
        )

    def refine_cutout_regions(self, cutout_path: Path, parameters: dict[str, Any]) -> ProcessResult:
        started = time.perf_counter()
        cutout = Image.open(cutout_path).convert("RGBA")
        cutout.load()
        alpha = np.asarray(cutout.getchannel("A"), dtype=np.uint8)
        components = self._extract_components(alpha, parameters)
        component_payloads = self._component_payloads(components)
        return ProcessResult(
            output_paths=[],
            result={
                "image_size": list(cutout.size),
                "cutout_components": component_payloads,
                "components": component_payloads,
                "component_count": len(component_payloads),
                "component_revision": int(parameters.get("component_revision", 0) or 0),
            },
            duration_ms=int((time.perf_counter() - started) * 1000),
            device="CPU",
        )

    def export_components(
        self,
        cutout_path: Path,
        output_path: Path,
        selected_component_ids: list[int],
        parameters: dict[str, Any],
        component_payloads: list[dict[str, Any]] | None = None,
    ) -> ProcessResult:
        started = time.perf_counter()
        cutout = Image.open(cutout_path).convert("RGBA")
        cutout.load()
        components = self._components_from_payloads(component_payloads or [])
        if not components:
            alpha = np.asarray(cutout.getchannel("A"), dtype=np.uint8)
            components = [component for component, _ in self._extract_components(alpha, parameters)]
        selected_ids = set(selected_component_ids) if selected_component_ids else {component.id for component in components}

        output_path.parent.mkdir(parents=True, exist_ok=True)
        export_index = 1
        export_name_stem = str(parameters.get("export_name_stem") or cutout_path.stem)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for component in components:
                if component.id not in selected_ids:
                    continue
                component_image = self._crop_cutout_component(cutout, component, parameters)
                # ZIP names retain the user's asset stem so game projects can map exports back to the source board.
                filename = f"{export_name_stem}_component_{export_index:03d}.png"
                buffer = io.BytesIO()
                component_image.save(buffer, format="PNG")
                archive.writestr(filename, buffer.getvalue())
                export_index += 1

        return ProcessResult(
            output_paths=[output_path],
            result={"component_count": len(components), "selected_count": export_index - 1},
            duration_ms=int((time.perf_counter() - started) * 1000),
            device="CPU",
        )

    def _extract_components(
        self,
        alpha: np.ndarray,
        parameters: dict[str, Any],
    ) -> list[tuple[ComponentCandidate, np.ndarray]]:
        threshold = int(parameters.get("alpha_threshold", 16))
        min_area = int(parameters.get("min_component_area", 500))
        raw_components = connected_components(alpha, threshold=threshold, min_area=min_area)
        components: list[tuple[ComponentCandidate, np.ndarray]] = []
        for component_id, (_, bbox, area, mask) in enumerate(raw_components, start=1):
            components.append((ComponentCandidate(id=component_id, bbox=bbox, area=area), mask))
        return components

    def _build_source_region_alpha(self, source: Image.Image, parameters: dict[str, Any]) -> np.ndarray:
        alpha = np.asarray(source.getchannel("A"), dtype=np.uint8)
        if int(alpha.min()) < 250:
            return alpha

        rgb = np.asarray(source.convert("RGB"), dtype=np.int16)
        height, width = rgb.shape[:2]
        border_width = max(1, min(width, height) // 80)
        border_pixels = np.concatenate(
            [
                rgb[:border_width, :, :].reshape(-1, 3),
                rgb[-border_width:, :, :].reshape(-1, 3),
                rgb[:, :border_width, :].reshape(-1, 3),
                rgb[:, -border_width:, :].reshape(-1, 3),
            ],
            axis=0,
        )
        background = np.median(border_pixels, axis=0)
        distance = np.linalg.norm(rgb - background, axis=2)
        threshold = max(8, int(parameters.get("alpha_threshold", 16)))
        mask = (distance > threshold).astype(np.uint8) * 255
        kernel_size = max(3, (min(width, height) // 180) | 1)
        kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
        # Close small gaps before removing edge noise; direct connected components can split one asset on common light backgrounds.
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        return mask.astype(np.uint8)

    def _component_payloads(self, components: list[tuple[ComponentCandidate, np.ndarray]]) -> list[dict[str, Any]]:
        return [
            {
                "id": component.id,
                "bbox": list(component.bbox),
                "area": component.area,
                "selected": component.selected,
                "preview_asset_id": None,
            }
            for component, _ in components
        ]

    def _components_from_payloads(self, payloads: list[dict[str, Any]]) -> list[ComponentCandidate]:
        components: list[ComponentCandidate] = []
        for payload in payloads:
            bbox = payload.get("bbox")
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            components.append(
                ComponentCandidate(
                    id=int(payload.get("id", len(components) + 1)),
                    bbox=(int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])),
                    area=int(payload.get("area", int(bbox[2]) * int(bbox[3]))),
                    selected=bool(payload.get("selected", True)),
                )
            )
        components.sort(key=lambda component: component.id)
        return components

    def _crop_cutout_component(
        self,
        cutout: Image.Image,
        component: ComponentCandidate,
        parameters: dict[str, Any],
    ) -> Image.Image:
        x, y, width, height = component.bbox
        padding = max(0, int(parameters.get("export_padding", 8)))
        left = max(0, x - padding)
        top = max(0, y - padding)
        right = min(cutout.width, x + width + padding)
        bottom = min(cutout.height, y + height + padding)
        cropped = cutout.crop((left, top, right, bottom)).convert("RGBA")
        alpha_smoothing = int(parameters.get("alpha_smoothing", 0))
        alpha_contract = float(parameters.get("alpha_contract", 0) or 0)
        alpha_feather = float(parameters.get("alpha_feather", 0) or 0)
        alpha_defringe = int(parameters.get("alpha_defringe", 0) or 0)
        if alpha_smoothing <= 0 and alpha_contract <= 0 and alpha_feather <= 0 and alpha_defringe <= 0:
            return cropped
        local_alpha = np.asarray(cropped.getchannel("A"), dtype=np.uint8)
        # Single-asset export performs only CPU post-processing and does not re-enter the GPU extraction queue.
        if alpha_smoothing > 0:
            local_alpha = smooth_alpha(local_alpha, alpha_smoothing)
        if alpha_contract > 0 or alpha_feather > 0:
            local_alpha = contract_alpha(local_alpha, alpha_contract, threshold=int(parameters.get("alpha_threshold", 16)), feather=alpha_feather)
        if alpha_defringe > 0:
            return decontaminate_edge_colors(cropped, local_alpha, alpha_defringe, threshold=int(parameters.get("alpha_threshold", 16)))
        return apply_alpha(cropped, local_alpha)
