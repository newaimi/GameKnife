from __future__ import annotations

import io
import json
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np
from PIL import Image

from gameknife_core import ProcessResult
from gameknife_processors.image_utils import apply_alpha, smooth_alpha


class AlphaPredictor(Protocol):
    device_label: str

    def predict_alpha(self, image: Image.Image) -> np.ndarray: ...


@dataclass(slots=True)
class SequenceFrameOutput:
    frame_id: str
    output_path: Path
    bbox: list[int]
    offset_x: int
    offset_y: int


@dataclass(slots=True)
class VideoFrameExtractionOutput:
    output_path: Path
    original_name: str
    width: int
    height: int
    bbox: list[int]
    duration_ms: int


class SequenceFrameProcessor:
    def extract_video_frames(
        self,
        video_path: Path,
        output_dir: Path,
        parameters: dict[str, Any],
        model: AlphaPredictor | None = None,
    ) -> tuple[ProcessResult, list[VideoFrameExtractionOutput]]:
        remove_background = bool(parameters.get("remove_background", False))
        if remove_background and model is None:
            # remove_background 是独立能力，处理器不能自己创建模型或触发下载。
            # 路由层负责安装状态检查，任务层必须显式传入已配置的本地模型服务。
            raise RuntimeError("BiRefNet 模型尚未下载安装，请先到设置页下载安装模型文件。")

        started = time.perf_counter()
        output_dir.mkdir(parents=True, exist_ok=True)
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise RuntimeError("视频文件无法读取。")

        try:
            source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0) or 24.0
            total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            target_fps = max(1, min(60, int(parameters.get("fps") or parameters.get("target_fps") or 12)))
            max_frames = max(1, min(300, int(parameters.get("max_frames") or 48)))
            output_size = max(64, int(parameters.get("output_size", 256)))
            max_edge = max(512, min(1024, output_size * 3))
            start_second = max(0.0, float(parameters.get("start_second") or 0))
            duration_seconds = parameters.get("duration_seconds")

            if total_frames > 0:
                video_duration = total_frames / source_fps
                clip_end_second = video_duration if duration_seconds is None else min(video_duration, start_second + float(duration_seconds))
                if clip_end_second <= start_second:
                    raise RuntimeError("视频裁切区间不正确，请让结束时间大于开始时间。")
                frame_count = max(1, min(max_frames, int(round((clip_end_second - start_second) * target_fps))))
                start_frame = min(total_frames - 1, int(round(start_second * source_fps)))
                end_frame = min(total_frames - 1, max(start_frame, int(round(clip_end_second * source_fps)) - 1))
                frame_indices = self._sample_indices(start_frame, end_frame, frame_count, bool(parameters.get("loop", True)))
                outputs = [
                    output
                    for output in (
                        self._extract_video_frame(capture, frame_index, index, target_fps, output_dir, max_edge, parameters, model if remove_background else None)
                        for index, frame_index in enumerate(frame_indices, start=1)
                    )
                    if output is not None
                ]
            else:
                start_frame = int(round(start_second * source_fps))
                end_frame = start_frame + max(1, int(round(float(duration_seconds) * source_fps))) if duration_seconds is not None else 2**31 - 1
                frame_step = max(1, int(round(source_fps / target_fps))) if source_fps > target_fps else 1
                capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

                outputs = []
                frame_number = start_frame
                while frame_number < end_frame and len(outputs) < max_frames:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    if (frame_number - start_frame) % frame_step == 0:
                        output = self._write_video_frame(frame, len(outputs) + 1, target_fps, output_dir, max_edge, parameters, model if remove_background else None)
                        outputs.append(output)
                    frame_number += 1
        finally:
            capture.release()

        if not outputs:
            raise RuntimeError("视频没有可抽取的画面。")

        return (
            ProcessResult(
                output_paths=[output.output_path for output in outputs],
                result={
                    "frame_count": len(outputs),
                    "fps": target_fps,
                    "source_fps": round(source_fps, 3),
                    "warnings": [],
                },
                duration_ms=int((time.perf_counter() - started) * 1000),
                device=model.device_label if remove_background and model is not None else "CPU",
            ),
            outputs,
        )

    def clean_frames(
        self,
        sequence: Any,
        frames: list[Any],
        output_dir: Path,
        parameters: dict[str, Any],
    ) -> tuple[ProcessResult, list[SequenceFrameOutput]]:
        if bool(parameters.get("remove_background", False)):
            # 序列帧清洗可以独立处理透明 PNG。只有视频抽帧这类显式请求才需要 AI 去背景。
            # 当前模型服务尚未迁完时直接失败，避免任务阶段隐式下载 BiRefNet。
            raise RuntimeError("BiRefNet 模型尚未下载安装，请先到设置页下载安装模型文件。")

        started = time.perf_counter()
        output_dir.mkdir(parents=True, exist_ok=True)
        prepared = [self._prepare_frame(frame, parameters) for frame in frames]
        self._fit_prepared_images(prepared, parameters)
        reference = self._resolve_reference_frame(prepared, parameters)
        self._apply_consistency_repairs(prepared, reference, sequence, parameters)
        canvas_width, canvas_height = self._resolve_canvas(sequence, prepared, parameters)
        outputs: list[SequenceFrameOutput] = []

        for index, item in enumerate(prepared, start=1):
            frame = item["frame"]
            cleaned = self._place_on_canvas(
                item["image"],
                canvas_width,
                canvas_height,
                str(sequence["anchor_mode"]),
                float(sequence["anchor_x"]),
                float(sequence["anchor_y"]),
                int(frame["offset_x"]) + int(item.get("stabilize_dx", 0)),
                int(frame["offset_y"]) + int(item.get("stabilize_dy", 0)),
            )
            output_path = output_dir / f"{Path(frame['original_name']).stem or 'frame'}_{index:03d}.png"
            cleaned.save(output_path, format="PNG")
            outputs.append(
                SequenceFrameOutput(
                    frame_id=frame["id"],
                    output_path=output_path,
                    bbox=item["bbox"],
                    offset_x=int(frame["offset_x"]),
                    offset_y=int(frame["offset_y"]),
                )
            )

        return (
            ProcessResult(
                output_paths=[output.output_path for output in outputs],
                result={
                    "sequence_id": sequence["id"],
                    "frame_count": len(outputs),
                    "canvas_size": [canvas_width, canvas_height],
                    "fps": int(sequence["fps"]),
                    "consistency_report": self._build_consistency_report(prepared, reference, parameters),
                    "warnings": self._build_sequence_warnings(prepared),
                },
                duration_ms=int((time.perf_counter() - started) * 1000),
                device="CPU",
            ),
            outputs,
        )

    def export_frames_zip(
        self,
        sequence: Any,
        frames: list[Any],
        output_path: Path,
        parameters: dict[str, Any],
    ) -> ProcessResult:
        started = time.perf_counter()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        enabled_frames = [frame for frame in frames if bool(frame["enabled"])]
        sheet, regions = self._build_sprite_sheet(enabled_frames)
        frame_width = sheet.width // max(1, len(enabled_frames)) if enabled_frames else 0
        frame_height = sheet.height if enabled_frames else 0

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for index, frame in enumerate(enabled_frames, start=1):
                image_path = Path(frame["processed_path"] or frame["source_path"])
                with Image.open(image_path) as opened:
                    image = opened.convert("RGBA")
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                archive.writestr(f"frames/{_safe_stem(sequence['name'])}_{index:03d}.png", buffer.getvalue())

            sheet_buffer = io.BytesIO()
            sheet.save(sheet_buffer, format="PNG")
            archive.writestr("spritesheet.png", sheet_buffer.getvalue())
            archive.writestr(
                "manifest.json",
                json.dumps(self._manifest(sequence, enabled_frames, parameters, regions, frame_width, frame_height), ensure_ascii=False, indent=2),
            )

        return ProcessResult(
            output_paths=[output_path],
            result={
                "sequence_id": sequence["id"],
                "frame_count": len(enabled_frames),
                "canvas_size": [int(sequence["canvas_width"]), int(sequence["canvas_height"])],
                "fps": int(sequence["fps"]),
                "warnings": [],
            },
            duration_ms=int((time.perf_counter() - started) * 1000),
            device="CPU",
        )

    def export_spine_zip(
        self,
        sequence: Any,
        frames: list[Any],
        output_path: Path,
        parameters: dict[str, Any],
    ) -> ProcessResult:
        started = time.perf_counter()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        enabled_frames = [frame for frame in frames if bool(frame["enabled"])]
        atlas_name = f"{_safe_stem(sequence['name'])}.png"
        atlas_text_name = f"{_safe_stem(sequence['name'])}.atlas"
        skeleton_name = f"{_safe_stem(sequence['name'])}.json"
        sheet, regions = self._build_sprite_sheet(enabled_frames)
        skeleton = self._build_spine_skeleton(sequence, regions, atlas_name)
        atlas_text = self._build_atlas_text(atlas_name, sheet.size, regions)

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            sheet_buffer = io.BytesIO()
            sheet.save(sheet_buffer, format="PNG")
            archive.writestr(atlas_name, sheet_buffer.getvalue())
            archive.writestr(atlas_text_name, atlas_text)
            archive.writestr(skeleton_name, json.dumps(skeleton, ensure_ascii=False, indent=2))

        return ProcessResult(
            output_paths=[output_path],
            result={
                "sequence_id": sequence["id"],
                "frame_count": len(enabled_frames),
                "canvas_size": [sheet.width, sheet.height],
                "fps": int(sequence["fps"]),
                "warnings": ["Spine 导出为逐帧切换附件，不包含骨骼绑定和蒙皮权重。"],
            },
            duration_ms=int((time.perf_counter() - started) * 1000),
            device="CPU",
        )

    def _prepare_frame(self, frame: Any, parameters: dict[str, Any]) -> dict[str, Any]:
        with Image.open(Path(frame["source_path"])) as opened:
            source = opened.convert("RGBA")
        alpha = np.asarray(source.getchannel("A"), dtype=np.uint8)
        alpha = self._clean_alpha(alpha, parameters)
        image = apply_alpha(source, alpha)
        bbox = self._alpha_bbox(alpha, int(parameters.get("alpha_threshold", 24)))
        padding = max(0, int(parameters.get("trim_padding", 6)))
        left = max(0, bbox[0] - padding)
        top = max(0, bbox[1] - padding)
        right = min(image.width, bbox[2] + padding)
        bottom = min(image.height, bbox[3] + padding)
        cropped = image.crop((left, top, right, bottom))
        cropped_alpha = np.asarray(cropped.getchannel("A"), dtype=np.uint8)
        return {
            "frame": frame,
            "image": cropped,
            "alpha": cropped_alpha,
            "bbox": [left, top, right - left, bottom - top],
            "color_stats": self._read_color_stats(cropped, cropped_alpha, int(parameters.get("alpha_threshold", 24))),
            "upper_center": self._read_upper_center(cropped_alpha),
            "stabilize_dx": 0,
            "stabilize_dy": 0,
        }

    def _extract_video_frame(
        self,
        capture: cv2.VideoCapture,
        frame_index: int,
        output_index: int,
        target_fps: int,
        output_dir: Path,
        max_edge: int,
        parameters: dict[str, Any],
        model: AlphaPredictor | None,
    ) -> VideoFrameExtractionOutput | None:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if not ok or frame is None:
            return None
        return self._write_video_frame(frame, output_index, target_fps, output_dir, max_edge, parameters, model)

    def _write_video_frame(
        self,
        frame: np.ndarray,
        output_index: int,
        target_fps: int,
        output_dir: Path,
        max_edge: int,
        parameters: dict[str, Any],
        model: AlphaPredictor | None,
    ) -> VideoFrameExtractionOutput:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb_frame, mode="RGB").convert("RGBA")
        image = self._resize_for_processing(image, max_edge)
        if model is not None:
            alpha = model.predict_alpha(image)
            alpha = smooth_alpha(alpha, int(parameters.get("alpha_smoothing", 0)))
            image = apply_alpha(image, alpha)
            left, top, right, bottom = self._alpha_bbox(alpha, int(parameters.get("alpha_threshold", 24)))
            bbox = [left, top, right - left, bottom - top]
        else:
            bbox = [0, 0, image.width, image.height]
        filename = f"video_frame_{output_index:03d}.png"
        output_path = output_dir / filename
        image.save(output_path, format="PNG")
        return VideoFrameExtractionOutput(
            output_path=output_path,
            original_name=filename,
            width=image.width,
            height=image.height,
            bbox=bbox,
            duration_ms=int(round(1000 / target_fps)),
        )

    def _sample_indices(self, start_frame: int, end_frame: int, frame_count: int, loop: bool) -> list[int]:
        if frame_count <= 1:
            return [start_frame]
        # 循环动画不取裁切段最后一帧，避免首尾重复导致游戏循环播放时停顿一帧。
        # 非循环动作保留结束帧，受击、死亡这类动作需要最后姿态。
        last = max(start_frame, end_frame - 1 if loop else end_frame)
        if last == start_frame:
            return [start_frame for _ in range(frame_count)]
        denominator = frame_count if loop else max(1, frame_count - 1)
        return [round(start_frame + index * (last - start_frame) / denominator) for index in range(frame_count)]

    def _resize_for_processing(self, image: Image.Image, max_edge: int) -> Image.Image:
        width, height = image.size
        current_max = max(width, height)
        if current_max <= max_edge:
            return image
        scale = max_edge / current_max
        return image.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)

    def _fit_prepared_images(self, prepared: list[dict[str, Any]], parameters: dict[str, Any]) -> None:
        if not bool(parameters.get("fit_canvas_size", False)) or not prepared:
            return
        target_width = int(parameters.get("canvas_width") or 0)
        target_height = int(parameters.get("canvas_height") or 0)
        if target_width <= 0 or target_height <= 0:
            return
        padding = max(0, int(parameters.get("canvas_padding", 0)))
        available_width = max(1, target_width - padding * 2)
        available_height = max(1, target_height - padding * 2)
        max_width = max((item["image"].width for item in prepared), default=1)
        max_height = max((item["image"].height for item in prepared), default=1)
        scale = min(1.0, available_width / max_width, available_height / max_height)
        if scale >= 1.0:
            return
        threshold = int(parameters.get("alpha_threshold", 24))
        for item in prepared:
            image = item["image"]
            next_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
            resized = image.resize(next_size, Image.Resampling.LANCZOS)
            alpha = np.asarray(resized.getchannel("A"), dtype=np.uint8)
            item["image"] = resized
            item["alpha"] = alpha
            item["bbox"] = [item["bbox"][0], item["bbox"][1], next_size[0], next_size[1]]
            item["color_stats"] = self._read_color_stats(resized, alpha, threshold)
            item["upper_center"] = self._read_upper_center(alpha)

    def _resolve_reference_frame(self, prepared: list[dict[str, Any]], parameters: dict[str, Any]) -> dict[str, Any] | None:
        reference_frame_id = str(parameters.get("reference_frame_id") or "")
        for item in prepared:
            if reference_frame_id and item["frame"]["id"] == reference_frame_id:
                return item
        return prepared[0] if prepared else None

    def _apply_consistency_repairs(
        self,
        prepared: list[dict[str, Any]],
        reference: dict[str, Any] | None,
        sequence: Any,
        parameters: dict[str, Any],
    ) -> None:
        if reference is None:
            return
        if bool(parameters.get("color_match", False)):
            for item in prepared:
                # 逐帧生成或抠图后的角色容易有亮度跳变，这里只做主体颜色统计匹配。
                # 不改变图像结构，避免把序列帧清洗变成不可控的生成式重绘。
                item["image"] = self._match_color_to_reference(
                    item["image"],
                    item["alpha"],
                    item["color_stats"],
                    reference["color_stats"],
                    int(parameters.get("alpha_threshold", 24)),
                )
        if bool(parameters.get("stabilize", False)):
            strength = max(0.0, min(1.0, float(parameters.get("stabilize_strength", 35)) / 100.0))
            reference_point = self._anchor_local_point(reference, str(sequence["anchor_mode"]))
            for item in prepared:
                current_point = self._anchor_local_point(item, str(sequence["anchor_mode"]))
                item["stabilize_dx"] = int(round((reference_point[0] - current_point[0]) * strength))
                item["stabilize_dy"] = int(round((reference_point[1] - current_point[1]) * strength))

    def _read_color_stats(self, image: Image.Image, alpha: np.ndarray, threshold: int) -> dict[str, np.ndarray]:
        pixels = np.asarray(image.convert("RGBA"), dtype=np.float32)
        mask = alpha >= threshold
        if not np.any(mask):
            mask = alpha > 0
        if not np.any(mask):
            return {"mean": np.array([0.0, 0.0, 0.0], dtype=np.float32), "std": np.array([1.0, 1.0, 1.0], dtype=np.float32)}
        rgb = pixels[:, :, :3][mask]
        return {"mean": rgb.mean(axis=0).astype(np.float32), "std": np.maximum(rgb.std(axis=0).astype(np.float32), 1.0)}

    def _match_color_to_reference(
        self,
        image: Image.Image,
        alpha: np.ndarray,
        current_stats: dict[str, np.ndarray],
        reference_stats: dict[str, np.ndarray],
        threshold: int,
    ) -> Image.Image:
        pixels = np.asarray(image.convert("RGBA"), dtype=np.float32).copy()
        mask = alpha >= threshold
        if not np.any(mask):
            return image
        scale = reference_stats["std"] / current_stats["std"]
        rgb = pixels[:, :, :3]
        matched = (rgb - current_stats["mean"]) * scale + reference_stats["mean"]
        # 只改主体可见区域的颜色，透明边缘仍交给 Alpha 清洗，避免边缘脏色被放大。
        rgb[mask] = np.clip(matched[mask], 0, 255)
        pixels[:, :, :3] = rgb
        return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), mode="RGBA")

    def _read_upper_center(self, alpha: np.ndarray) -> tuple[float, float]:
        if alpha.size == 0:
            return (0.0, 0.0)
        height = alpha.shape[0]
        upper_limit = max(1, int(height * 0.68))
        weighted = alpha[:upper_limit].astype(np.float32)
        total = float(weighted.sum())
        if total <= 0:
            return (alpha.shape[1] / 2.0, height / 2.0)
        ys, xs = np.indices(weighted.shape)
        return (float((xs * weighted).sum() / total), float((ys * weighted).sum() / total))

    def _anchor_local_point(self, item: dict[str, Any], anchor_mode: str) -> tuple[float, float]:
        image = item["image"]
        center_x, center_y = item["upper_center"]
        local_x = center_x - image.width / 2
        if anchor_mode == "center":
            local_y = center_y - image.height / 2
        else:
            local_y = center_y - image.height
        return (local_x, local_y)

    def _build_consistency_report(
        self,
        prepared: list[dict[str, Any]],
        reference: dict[str, Any] | None,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        widths = [item["image"].width for item in prepared]
        heights = [item["image"].height for item in prepared]
        offsets = [[int(item.get("stabilize_dx", 0)), int(item.get("stabilize_dy", 0))] for item in prepared]
        reference_id = reference["frame"]["id"] if reference is not None else None
        return {
            "reference_frame_id": reference_id,
            "color_match": bool(parameters.get("color_match", False)),
            "stabilize": bool(parameters.get("stabilize", False)),
            "stabilize_strength": int(parameters.get("stabilize_strength", 35)),
            "frame_count": len(prepared),
            "width_jitter_px": max(widths) - min(widths) if widths else 0,
            "height_jitter_px": max(heights) - min(heights) if heights else 0,
            "stabilize_offsets": offsets,
        }

    def _clean_alpha(self, alpha: np.ndarray, parameters: dict[str, Any]) -> np.ndarray:
        threshold = int(parameters.get("alpha_threshold", 24))
        binary = np.where(alpha >= threshold, alpha, 0).astype(np.uint8)
        if int(parameters.get("denoise", 0)):
            kernel = np.ones((3, 3), dtype=np.uint8)
            # 抽帧或模型输出常见孤立半透明噪点，开运算能先去掉小碎点再交给平滑处理。
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
        return smooth_alpha(binary, int(parameters.get("alpha_smoothing", 0)))

    def _alpha_bbox(self, alpha: np.ndarray, threshold: int) -> tuple[int, int, int, int]:
        ys, xs = np.where(alpha >= threshold)
        if len(xs) == 0 or len(ys) == 0:
            return (0, 0, alpha.shape[1], alpha.shape[0])
        return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)

    def _resolve_canvas(self, sequence: Any, prepared: list[dict[str, Any]], parameters: dict[str, Any]) -> tuple[int, int]:
        requested_width = int(parameters.get("canvas_width") or sequence["canvas_width"] or 0)
        requested_height = int(parameters.get("canvas_height") or sequence["canvas_height"] or 0)
        max_width = max((item["image"].width + abs(int(item.get("stabilize_dx", 0))) * 2 for item in prepared), default=1)
        max_height = max((item["image"].height + abs(int(item.get("stabilize_dy", 0))) * 2 for item in prepared), default=1)
        padding = max(0, int(parameters.get("canvas_padding", 4)))
        return max(requested_width, max_width + padding * 2), max(requested_height, max_height + padding * 2)

    def _place_on_canvas(
        self,
        image: Image.Image,
        canvas_width: int,
        canvas_height: int,
        anchor_mode: str,
        anchor_x: float,
        anchor_y: float,
        offset_x: int,
        offset_y: int,
    ) -> Image.Image:
        canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        if anchor_mode == "center":
            left = int(round(canvas_width * anchor_x - image.width / 2 + offset_x))
            top = int(round(canvas_height * anchor_y - image.height / 2 + offset_y))
        else:
            left = int(round(canvas_width * anchor_x - image.width / 2 + offset_x))
            top = int(round(canvas_height * anchor_y - image.height + offset_y))
        canvas.alpha_composite(image, (left, top))
        return canvas

    def _build_sequence_warnings(self, prepared: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        if len(prepared) < 6:
            warnings.append("序列帧数量偏少，走路循环可能缺少接触、交叉或过渡关键帧。")
        widths = [item["image"].width for item in prepared]
        heights = [item["image"].height for item in prepared]
        if widths and max(widths) - min(widths) > 8:
            warnings.append("主体宽度变化较大，播放时可能出现轮廓闪烁。")
        if heights and max(heights) - min(heights) > 6:
            warnings.append("主体高度变化较大，建议检查脚底基线和头部稳定性。")
        return warnings

    def _build_sprite_sheet(self, frames: list[Any]) -> tuple[Image.Image, list[dict[str, Any]]]:
        images: list[Image.Image] = []
        for frame in frames:
            with Image.open(Path(frame["processed_path"] or frame["source_path"])) as opened:
                images.append(opened.convert("RGBA"))
        max_width = max((image.width for image in images), default=1)
        max_height = max((image.height for image in images), default=1)
        sheet = Image.new("RGBA", (max_width * max(1, len(images)), max_height), (0, 0, 0, 0))
        regions: list[dict[str, Any]] = []
        for index, image in enumerate(images):
            x = index * max_width
            sheet.alpha_composite(image, (x, 0))
            regions.append({"name": f"frame_{index + 1:03d}", "x": x, "y": 0, "width": image.width, "height": image.height})
            image.close()
        return sheet, regions

    def _build_spine_skeleton(self, sequence: Any, regions: list[dict[str, Any]], atlas_name: str) -> dict[str, Any]:
        fps = max(1, int(sequence["fps"]))
        attachments = {
            "frame_slot": {
                region["name"]: {
                    "type": "region",
                    "path": region["name"],
                    "width": region["width"],
                    "height": region["height"],
                    "x": 0,
                    "y": region["height"] / 2,
                }
                for region in regions
            }
        }
        timeline = [{"time": index / fps, "name": region["name"]} for index, region in enumerate(regions)]
        if bool(sequence["loop"]) and regions:
            timeline.append({"time": len(regions) / fps, "name": regions[0]["name"]})
        return {
            "skeleton": {
                "hash": "",
                "spine": "4.1.00",
                "x": 0,
                "y": 0,
                "width": regions[0]["width"] if regions else 0,
                "height": regions[0]["height"] if regions else 0,
            },
            "bones": [{"name": "root"}],
            "slots": [{"name": "frame_slot", "bone": "root", "attachment": regions[0]["name"] if regions else None}],
            "skins": [{"name": "default", "attachments": attachments}],
            "animations": {str(sequence["name"] or "sequence"): {"slots": {"frame_slot": {"attachment": timeline}}}},
            "image": atlas_name,
        }

    def _build_atlas_text(self, atlas_name: str, sheet_size: tuple[int, int], regions: list[dict[str, Any]]) -> str:
        lines = [atlas_name, f"size: {sheet_size[0]},{sheet_size[1]}", "format: RGBA8888", "filter: Linear,Linear", "repeat: none"]
        for region in regions:
            lines.extend(
                [
                    region["name"],
                    "  rotate: false",
                    f"  xy: {region['x']}, {region['y']}",
                    f"  size: {region['width']}, {region['height']}",
                    f"  orig: {region['width']}, {region['height']}",
                    "  offset: 0, 0",
                    "  index: -1",
                ]
            )
        return "\n".join(lines) + "\n"

    def _manifest(
        self,
        sequence: Any,
        frames: list[Any],
        parameters: dict[str, Any],
        regions: list[dict[str, Any]],
        frame_width: int,
        frame_height: int,
    ) -> dict[str, Any]:
        return {
            "name": sequence["name"],
            "animation": sequence["name"],
            "fps": int(sequence["fps"]),
            "loop": bool(sequence["loop"]),
            "frame_count": len(frames),
            "frame_width": frame_width,
            "frame_height": frame_height,
            "spritesheet": "spritesheet.png",
            "pivot": {
                "x": round(frame_width * float(sequence["anchor_x"])),
                "y": round(frame_height * float(sequence["anchor_y"])),
            },
            "frames": [
                {
                    "index": index,
                    "source": frame["original_name"],
                    "file": f"frames/{_safe_stem(sequence['name'])}_{index + 1:03d}.png",
                    "enabled": bool(frame["enabled"]),
                    "generated": bool(frame["is_generated"]),
                    "sprite": regions[index] if index < len(regions) else None,
                }
                for index, frame in enumerate(frames)
            ],
            "parameters": parameters,
        }


def _safe_stem(value: str) -> str:
    stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    return stem or "sequence"
