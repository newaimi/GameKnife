from __future__ import annotations

import io
import json
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from gameknife_core import ProcessResult
from gameknife_processors.image_utils import apply_alpha, smooth_alpha


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
    ) -> tuple[ProcessResult, list[VideoFrameExtractionOutput]]:
        if bool(parameters.get("remove_background", False)):
            # 视频抽帧本身是本地能力，去背景属于额外模型能力。
            # 在真实 BiRefNet 链路迁完前直接失败，避免抽帧任务偷偷联网下载模型。
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
            start_second = max(0.0, float(parameters.get("start_second") or 0))
            duration_seconds = parameters.get("duration_seconds")
            start_frame = int(round(start_second * source_fps))
            if duration_seconds is None:
                end_frame = total_frames if total_frames > 0 else 2**31 - 1
            else:
                end_frame = start_frame + max(1, int(round(float(duration_seconds) * source_fps)))
                if total_frames > 0:
                    end_frame = min(end_frame, total_frames)
            frame_step = max(1, int(round(source_fps / target_fps))) if source_fps > target_fps else 1
            capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

            outputs: list[VideoFrameExtractionOutput] = []
            frame_number = start_frame
            while frame_number < end_frame and len(outputs) < max_frames:
                ok, frame = capture.read()
                if not ok:
                    break
                if (frame_number - start_frame) % frame_step == 0:
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    image = Image.fromarray(rgb_frame, mode="RGB").convert("RGBA")
                    filename = f"video_frame_{len(outputs) + 1:03d}.png"
                    output_path = output_dir / filename
                    image.save(output_path, format="PNG")
                    outputs.append(
                        VideoFrameExtractionOutput(
                            output_path=output_path,
                            original_name=filename,
                            width=image.width,
                            height=image.height,
                            bbox=[0, 0, image.width, image.height],
                            duration_ms=int(round(1000 / target_fps)),
                        )
                    )
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
                device="CPU",
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
                int(frame["offset_x"]),
                int(frame["offset_y"]),
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
        return {
            "frame": frame,
            "image": cropped,
            "bbox": [left, top, right - left, bottom - top],
        }

    def _clean_alpha(self, alpha: np.ndarray, parameters: dict[str, Any]) -> np.ndarray:
        threshold = int(parameters.get("alpha_threshold", 24))
        binary = np.where(alpha >= threshold, alpha, 0).astype(np.uint8)
        return smooth_alpha(binary, int(parameters.get("alpha_smoothing", 0)))

    def _alpha_bbox(self, alpha: np.ndarray, threshold: int) -> tuple[int, int, int, int]:
        ys, xs = np.where(alpha >= threshold)
        if len(xs) == 0 or len(ys) == 0:
            return (0, 0, alpha.shape[1], alpha.shape[0])
        return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)

    def _resolve_canvas(self, sequence: Any, prepared: list[dict[str, Any]], parameters: dict[str, Any]) -> tuple[int, int]:
        requested_width = int(parameters.get("canvas_width") or sequence["canvas_width"] or 0)
        requested_height = int(parameters.get("canvas_height") or sequence["canvas_height"] or 0)
        max_width = max((item["image"].width for item in prepared), default=1)
        max_height = max((item["image"].height for item in prepared), default=1)
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
