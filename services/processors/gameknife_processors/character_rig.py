from __future__ import annotations

import io
import json
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from PIL import Image

from gameknife_core import ProcessResult
from gameknife_processors.character_part_catalog import CORE_PART_KEYS, OPTIONAL_PART_KEYS, normalize_part_key, read_part_spec
from gameknife_processors.image_utils import apply_alpha, connected_components


@dataclass(slots=True)
class CharacterPartOutput:
    name: str
    semantic_type: str
    bbox: list[int]
    pivot_x: float
    pivot_y: float
    parent_id: str | None
    z_index: int
    needs_completion: bool
    part_path: Path
    mask_path: Path


@dataclass(slots=True)
class CharacterRigHints:
    description: str
    candidate_keys: list[str]


@dataclass(slots=True)
class CharacterRigDetection:
    key: str
    label: str
    bbox: list[int]
    score: float


class CharacterRigModelProvider(Protocol):
    device_label: str

    def is_installed(self) -> bool: ...

    def describe_parts(self, image: Image.Image, parameters: dict[str, Any]) -> CharacterRigHints: ...

    def detect_parts(self, image: Image.Image, candidate_keys: list[str], parameters: dict[str, Any]) -> list[CharacterRigDetection]: ...

    def refine_bbox(self, image: Image.Image, bbox: list[int], alpha: np.ndarray, parameters: dict[str, Any]) -> np.ndarray: ...

    def model_report(self) -> dict[str, str]: ...


class CharacterRigProcessor:
    def analyze(
        self,
        input_path: Path,
        output_dir: Path,
        parameters: dict[str, Any],
        model_service: CharacterRigModelProvider | None = None,
    ) -> tuple[ProcessResult, list[CharacterPartOutput]]:
        with Image.open(input_path) as opened:
            source = opened.convert("RGBA")
            source.load()
        alpha = np.asarray(source.getchannel("A"), dtype=np.uint8)
        if _has_transparency(alpha):
            return self.analyze_transparent_source(input_path, output_dir, parameters)
        if model_service is None or not model_service.is_installed():
            # 不透明角色图需要真实检测和分割模型。这里不做本地启发式兜底，避免用户以为得到了可用于绑定的模型结果。
            raise RuntimeError("骨骼拆分模型尚未下载安装，请先到设置页下载安装模型文件。")
        return self._analyze_with_models(source, output_dir, parameters, model_service)

    def analyze_transparent_source(
        self,
        input_path: Path,
        output_dir: Path,
        parameters: dict[str, Any],
    ) -> tuple[ProcessResult, list[CharacterPartOutput]]:
        started = time.perf_counter()
        output_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(input_path) as opened:
            source = opened.convert("RGBA")

        alpha = np.asarray(source.getchannel("A"), dtype=np.uint8)
        if not _has_transparency(alpha):
            raise RuntimeError("骨骼拆分模型尚未下载安装，请先到设置页下载安装模型文件。")

        threshold = int(parameters.get("alpha_threshold", 16))
        min_area = int(parameters.get("min_component_area", 12))
        padding = max(0, int(parameters.get("padding", 2)))
        outputs: list[CharacterPartOutput] = []
        for index, (_, bbox, _, component_alpha) in enumerate(
            connected_components(alpha, threshold=threshold, min_area=min_area),
            start=1,
        ):
            x, y, width, height = _pad_bbox(bbox, padding, source.width, source.height)
            part_alpha = component_alpha[y : y + height, x : x + width]
            part_image = source.crop((x, y, x + width, y + height))
            part_image.putalpha(Image.fromarray(part_alpha, mode="L"))
            mask_image = Image.fromarray(part_alpha, mode="L")

            part_name = f"part_{index:03d}"
            part_path = output_dir / "parts" / f"{part_name}.png"
            mask_path = output_dir / "masks" / f"{part_name}_mask.png"
            part_path.parent.mkdir(parents=True, exist_ok=True)
            mask_path.parent.mkdir(parents=True, exist_ok=True)
            part_image.save(part_path, format="PNG")
            mask_image.save(mask_path, format="PNG")
            outputs.append(
                CharacterPartOutput(
                    name=f"部件 {index}",
                    semantic_type=part_name,
                    bbox=[x, y, width, height],
                    pivot_x=0.5,
                    pivot_y=0.5,
                    parent_id=None,
                    z_index=index - 1,
                    needs_completion=False,
                    part_path=part_path,
                    mask_path=mask_path,
                )
            )

        if not outputs:
            raise RuntimeError("没有识别到可拆分的透明部件。")

        return (
            ProcessResult(
                result={
                    "part_count": len(outputs),
                    "canvas_size": [source.width, source.height],
                    "warnings": ["透明 PNG 已按连通区域生成初始部件。"],
                },
                duration_ms=int((time.perf_counter() - started) * 1000),
                device="CPU",
            ),
            outputs,
        )

    def _analyze_with_models(
        self,
        source: Image.Image,
        output_dir: Path,
        parameters: dict[str, Any],
        model_service: CharacterRigModelProvider,
    ) -> tuple[ProcessResult, list[CharacterPartOutput]]:
        started = time.perf_counter()
        output_dir.mkdir(parents=True, exist_ok=True)
        alpha = np.asarray(source.getchannel("A"), dtype=np.uint8)
        if not _has_transparency(alpha):
            alpha = np.full((source.height, source.width), 255, dtype=np.uint8)
        cutout = apply_alpha(source, alpha)
        hints = model_service.describe_parts(cutout, parameters)
        candidate_keys = _read_candidate_keys(parameters, hints.candidate_keys)
        detections = model_service.detect_parts(cutout, candidate_keys, parameters)
        filtered, warnings = _filter_detections(detections, alpha, parameters, source.size)

        outputs: list[CharacterPartOutput] = []
        for detection in filtered:
            refined_mask = model_service.refine_bbox(cutout, detection.bbox, alpha, parameters)
            bbox = _mask_bbox(refined_mask)
            if bbox is None:
                continue
            part_image, mask_image, bbox_list = _crop_part(cutout, refined_mask, bbox, parameters)
            spec = read_part_spec(detection.key)
            safe_name = _safe_name(detection.key)
            part_path = output_dir / f"{safe_name}.png"
            mask_path = output_dir / f"{safe_name}_mask.png"
            part_path.parent.mkdir(parents=True, exist_ok=True)
            mask_path.parent.mkdir(parents=True, exist_ok=True)
            part_image.save(part_path, format="PNG")
            mask_image.save(mask_path, format="PNG")
            outputs.append(
                CharacterPartOutput(
                    name=spec.name,
                    semantic_type=detection.key,
                    bbox=bbox_list,
                    pivot_x=spec.pivot[0],
                    pivot_y=spec.pivot[1],
                    parent_id=None,
                    z_index=spec.z_index,
                    needs_completion=spec.needs_completion or detection.score < 0.35,
                    part_path=part_path,
                    mask_path=mask_path,
                )
            )

        if not outputs:
            warnings.append("没有识别到可拆分部件，请尝试补充候选词或手动框选后精修。")
        missing_core = [read_part_spec(key).name for key in ("head", "torso") if key not in {output.semantic_type for output in outputs}]
        if missing_core:
            warnings.append(f"关键部件未识别：{'、'.join(missing_core)}，需要手动补框或重新调整候选词。")
        if outputs and any(output.needs_completion for output in outputs):
            warnings.append("部分部件来自低置信度或特殊道具候选，已标记为需要确认。")

        return (
            ProcessResult(
                result={
                    "part_count": len(outputs),
                    "canvas_size": [source.width, source.height],
                    "warnings": warnings,
                    "description": hints.description,
                    "candidate_keys": candidate_keys,
                    "models": model_service.model_report(),
                },
                duration_ms=int((time.perf_counter() - started) * 1000),
                device=model_service.device_label,
            ),
            outputs,
        )

    def refine_part(
        self,
        input_path: Path,
        part: Any,
        output_dir: Path,
        parameters: dict[str, Any],
        model_service: CharacterRigModelProvider | None = None,
    ) -> tuple[ProcessResult, CharacterPartOutput]:
        started = time.perf_counter()
        output_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(input_path) as opened:
            source = opened.convert("RGBA")

        alpha = np.asarray(source.getchannel("A"), dtype=np.uint8)
        bbox = json.loads(part["bbox_json"])
        padding = max(0, int(parameters.get("padding", 2)))
        x, y, width, height = _pad_bbox((int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])), padding, source.width, source.height)
        if _has_transparency(alpha):
            part_alpha = alpha[y : y + height, x : x + width]
        elif model_service is None or not model_service.is_installed():
            raise RuntimeError("骨骼拆分模型尚未下载安装，请先到设置页下载安装模型文件。")
        else:
            refined = model_service.refine_bbox(source, [x, y, width, height], np.full((source.height, source.width), 255, dtype=np.uint8), parameters)
            refined_bbox = _mask_bbox(refined) or (x, y, x + width, y + height)
            x, y, width, height = _pad_bbox(
                (int(refined_bbox[0]), int(refined_bbox[1]), int(refined_bbox[2] - refined_bbox[0]), int(refined_bbox[3] - refined_bbox[1])),
                padding,
                source.width,
                source.height,
            )
            part_alpha = refined[y : y + height, x : x + width]
        part_image = source.crop((x, y, x + width, y + height))
        part_image.putalpha(Image.fromarray(part_alpha, mode="L"))
        mask_image = Image.fromarray(part_alpha, mode="L")

        stem = _safe_name(str(part["semantic_type"] or part["name"] or "part"))
        part_path = output_dir / f"{stem}.png"
        mask_path = output_dir / f"{stem}_mask.png"
        part_image.save(part_path, format="PNG")
        mask_image.save(mask_path, format="PNG")
        output = CharacterPartOutput(
            name=str(part["name"]),
            semantic_type=str(part["semantic_type"]),
            bbox=[x, y, width, height],
            pivot_x=float(part["pivot_x"]),
            pivot_y=float(part["pivot_y"]),
            parent_id=part["parent_id"],
            z_index=int(part["z_index"]),
            needs_completion=False,
            part_path=part_path,
            mask_path=mask_path,
        )
        return (
            ProcessResult(
                result={"part_id": part["id"], "bbox": output.bbox, "warnings": ["部件已基于当前素材重新生成。"]},
                duration_ms=int((time.perf_counter() - started) * 1000),
                device="CPU" if _has_transparency(alpha) or model_service is None else model_service.device_label,
            ),
            output,
        )

    def export_spine_zip(self, rig: Any, parts: list[Any], output_path: Path, parameters: dict[str, Any]) -> ProcessResult:
        started = time.perf_counter()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        enabled_parts = [part for part in parts if bool(part["enabled"]) and part["part_path"]]
        safe_name = _safe_name(str(rig["name"]))
        skeleton = _spine_skeleton(rig, enabled_parts)
        atlas_text = _atlas_text(enabled_parts)
        manifest = _manifest(rig, enabled_parts, parameters, "spine")

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            _write_part_images(archive, enabled_parts)
            archive.writestr(f"{safe_name}.json", json.dumps(skeleton, ensure_ascii=False, indent=2))
            archive.writestr(f"{safe_name}.atlas", atlas_text)
            archive.writestr("rig_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        return ProcessResult(
            output_paths=[output_path],
            result={
                "rig_id": rig["id"],
                "part_count": len(enabled_parts),
                "warnings": ["Spine 导出包含部件散图和基础骨骼 JSON，需要在 Spine 中继续绑定权重。"],
            },
            duration_ms=int((time.perf_counter() - started) * 1000),
            device="CPU",
        )

    def export_dragonbones_zip(self, rig: Any, parts: list[Any], output_path: Path, parameters: dict[str, Any]) -> ProcessResult:
        started = time.perf_counter()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        enabled_parts = [part for part in parts if bool(part["enabled"]) and part["part_path"]]
        safe_name = _safe_name(str(rig["name"]))
        texture = _dragonbones_texture(enabled_parts)
        skeleton = _dragonbones_skeleton(rig, enabled_parts)
        manifest = _manifest(rig, enabled_parts, parameters, "dragonbones")

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            _write_part_images(archive, enabled_parts)
            archive.writestr(f"{safe_name}_ske.json", json.dumps(skeleton, ensure_ascii=False, indent=2))
            archive.writestr(f"{safe_name}_tex.json", json.dumps(texture, ensure_ascii=False, indent=2))
            archive.writestr("rig_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        return ProcessResult(
            output_paths=[output_path],
            result={
                "rig_id": rig["id"],
                "part_count": len(enabled_parts),
                "warnings": ["DragonBones 导出包含部件散图和基础骨骼 JSON，需要在 DragonBones 中继续绑定权重。"],
            },
            duration_ms=int((time.perf_counter() - started) * 1000),
            device="CPU",
        )


def _has_transparency(alpha: np.ndarray) -> bool:
    # 透明图可以在本地用 alpha 连通域拆出草稿部件；不透明图需要真实模型先做前景分割。
    # 这里在任务创建和处理阶段都保留同一判断，防止外部调用绕过路由后进入隐式降级。
    return bool(np.any(alpha < 250))


def _read_candidate_keys(parameters: dict[str, Any], florence_keys: list[str]) -> list[str]:
    requested = parameters.get("enabled_part_keys")
    if isinstance(requested, list) and requested:
        keys = [key for key in (normalize_part_key(str(value)) for value in requested) if key]
    else:
        keys = list(CORE_PART_KEYS)
    for key in florence_keys:
        if key not in keys:
            keys.append(key)
    extra_prompts = parameters.get("extra_prompts", "")
    if isinstance(extra_prompts, str):
        raw_values = [value for chunk in extra_prompts.split("\n") for value in chunk.split(",")]
    elif isinstance(extra_prompts, list):
        raw_values = [str(value) for value in extra_prompts]
    else:
        raw_values = []
    for value in raw_values:
        key = normalize_part_key(value)
        if key and key not in keys and (key in OPTIONAL_PART_KEYS or requested):
            keys.append(key)
    return keys


def _filter_detections(
    detections: list[CharacterRigDetection],
    alpha: np.ndarray,
    parameters: dict[str, Any],
    image_size: tuple[int, int],
) -> tuple[list[CharacterRigDetection], list[str]]:
    min_area = int(parameters.get("min_mask_area", 96))
    max_candidates = int(parameters.get("max_candidates", 16))
    alpha_threshold = int(parameters.get("alpha_threshold", 24))
    warnings: list[str] = []
    filtered: list[CharacterRigDetection] = []
    for detection in sorted(detections, key=lambda item: item.score, reverse=True):
        bbox = _clip_bbox(detection.bbox, image_size)
        area = bbox[2] * bbox[3]
        if area < min_area:
            warnings.append(f"{read_part_spec(detection.key).name} 候选面积过小，已过滤。")
            continue
        x, y, width, height = bbox
        crop_alpha = alpha[y : y + height, x : x + width]
        if crop_alpha.size == 0:
            continue
        alpha_overlap = float(np.count_nonzero(crop_alpha >= alpha_threshold)) / float(crop_alpha.size)
        if alpha_overlap < 0.08:
            warnings.append(f"{read_part_spec(detection.key).name} 与角色前景重叠过低，已过滤。")
            continue
        if any(existing.key == detection.key for existing in filtered):
            warnings.append(f"{read_part_spec(detection.key).name} 出现重复候选，只保留置信度最高的一个。")
            continue
        if any(_bbox_iou(bbox, existing.bbox) > 0.72 for existing in filtered):
            warnings.append(f"{read_part_spec(detection.key).name} 与已有候选重叠过高，已过滤。")
            continue
        filtered.append(CharacterRigDetection(key=detection.key, label=detection.label, bbox=bbox, score=detection.score))
        if len(filtered) >= max_candidates:
            break
    return filtered, warnings


def _clip_bbox(bbox: list[int], image_size: tuple[int, int]) -> list[int]:
    image_width, image_height = image_size
    x, y, width, height = [int(value) for value in bbox]
    left = max(0, min(image_width, x))
    top = max(0, min(image_height, y))
    right = max(0, min(image_width, x + width))
    bottom = max(0, min(image_height, y + height))
    return [left, top, max(0, right - left), max(0, bottom - top)]


def _bbox_iou(first: list[int], second: list[int]) -> float:
    first_left, first_top, first_width, first_height = first
    second_left, second_top, second_width, second_height = second
    inter_left = max(first_left, second_left)
    inter_top = max(first_top, second_top)
    inter_right = min(first_left + first_width, second_left + second_width)
    inter_bottom = min(first_top + first_height, second_top + second_height)
    inter_area = max(0, inter_right - inter_left) * max(0, inter_bottom - inter_top)
    union_area = first_width * first_height + second_width * second_height - inter_area
    return inter_area / union_area if union_area > 0 else 0.0


def _mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0 or len(ys) == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _crop_part(
    source: Image.Image,
    mask: np.ndarray,
    bbox: tuple[int, int, int, int],
    parameters: dict[str, Any],
) -> tuple[Image.Image, Image.Image, list[int]]:
    overlap = max(0, int(parameters.get("overlap_padding", 8)))
    left = max(0, bbox[0] - overlap)
    top = max(0, bbox[1] - overlap)
    right = min(source.width, bbox[2] + overlap)
    bottom = min(source.height, bbox[3] + overlap)
    local_alpha = mask[top:bottom, left:right]
    cropped = source.crop((left, top, right, bottom)).convert("RGBA")
    part_image = apply_alpha(cropped, local_alpha)
    mask_image = Image.fromarray(local_alpha.astype(np.uint8), mode="L")
    return part_image, mask_image, [left, top, right - left, bottom - top]


def _pad_bbox(bbox: tuple[int, int, int, int], padding: int, width_limit: int, height_limit: int) -> tuple[int, int, int, int]:
    x, y, width, height = bbox
    left = max(0, x - padding)
    top = max(0, y - padding)
    right = min(width_limit, x + width + padding)
    bottom = min(height_limit, y + height + padding)
    return left, top, max(1, right - left), max(1, bottom - top)


def _write_part_images(archive: zipfile.ZipFile, parts: list[Any]) -> None:
    for part in parts:
        part_name = _safe_name(str(part["semantic_type"] or part["name"] or "part"))
        with Image.open(Path(part["part_path"])) as opened:
            image = opened.convert("RGBA")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        archive.writestr(f"parts/{part_name}.png", buffer.getvalue())


def _spine_skeleton(rig: Any, parts: list[Any]) -> dict[str, Any]:
    bones = [{"name": "root"}]
    slots: list[dict[str, Any]] = []
    attachments: dict[str, dict[str, Any]] = {}
    for part in parts:
        name = _safe_name(str(part["semantic_type"] or part["name"] or "part"))
        bone_name = f"{name}_bone"
        parent_name = "root"
        bones.append({"name": bone_name, "parent": parent_name, "x": int(part["bbox"][0]), "y": int(part["bbox"][1])})
        slots.append({"name": f"{name}_slot", "bone": bone_name, "attachment": name})
        attachments[f"{name}_slot"] = {
            name: {
                "type": "region",
                "path": f"parts/{name}.png",
                "width": int(part["bbox"][2]),
                "height": int(part["bbox"][3]),
                "x": int(part["bbox"][2]) * float(part["pivot_x"]),
                "y": int(part["bbox"][3]) * (1 - float(part["pivot_y"])),
            }
        }
    return {
        "skeleton": {
            "hash": "",
            "spine": "4.1.00",
            "x": 0,
            "y": 0,
            "width": int(rig["canvas_width"]),
            "height": int(rig["canvas_height"]),
        },
        "bones": bones,
        "slots": slots,
        "skins": [{"name": "default", "attachments": attachments}],
        "animations": {"idle": {}},
    }


def _atlas_text(parts: list[Any]) -> str:
    lines = ["parts", "size: 1,1", "format: RGBA8888", "filter: Linear,Linear", "repeat: none"]
    for part in parts:
        name = _safe_name(str(part["semantic_type"] or part["name"] or "part"))
        lines.extend(
            [
                name,
                "  rotate: false",
                "  xy: 0, 0",
                f"  size: {int(part['bbox'][2])}, {int(part['bbox'][3])}",
                f"  orig: {int(part['bbox'][2])}, {int(part['bbox'][3])}",
                "  offset: 0, 0",
                "  index: -1",
            ]
        )
    return "\n".join(lines) + "\n"


def _dragonbones_skeleton(rig: Any, parts: list[Any]) -> dict[str, Any]:
    armature_parts = []
    for part in parts:
        name = _safe_name(str(part["semantic_type"] or part["name"] or "part"))
        armature_parts.append(
            {
                "name": name,
                "parent": "root",
                "transform": {"x": int(part["bbox"][0]), "y": int(part["bbox"][1])},
            }
        )
    return {
        "name": rig["name"],
        "frameRate": 24,
        "version": "5.5",
        "compatibleVersion": "5.5",
        "armature": [
            {
                "name": rig["name"],
                "type": "Armature",
                "bone": [{"name": "root"}, *armature_parts],
                "slot": [{"name": f"{_safe_name(str(part['semantic_type']))}_slot", "parent": _safe_name(str(part["semantic_type"]))} for part in parts],
                "skin": [
                    {
                        "name": "default",
                        "slot": [
                            {
                                "name": f"{_safe_name(str(part['semantic_type']))}_slot",
                                "display": [{"name": _safe_name(str(part["semantic_type"])), "path": f"parts/{_safe_name(str(part['semantic_type']))}.png"}],
                            }
                            for part in parts
                        ],
                    }
                ],
            }
        ],
    }


def _dragonbones_texture(parts: list[Any]) -> dict[str, Any]:
    return {
        "name": "parts",
        "imagePath": "parts",
        "SubTexture": [
            {
                "name": _safe_name(str(part["semantic_type"] or part["name"] or "part")),
                "x": 0,
                "y": 0,
                "width": int(part["bbox"][2]),
                "height": int(part["bbox"][3]),
            }
            for part in parts
        ],
    }


def _manifest(rig: Any, parts: list[Any], parameters: dict[str, Any], export_format: str) -> dict[str, Any]:
    return {
        "id": rig["id"],
        "name": rig["name"],
        "format": export_format,
        "canvas": {"width": int(rig["canvas_width"]), "height": int(rig["canvas_height"])},
        "part_count": len(parts),
        "parameters": parameters,
        "parts": [
            {
                "id": part["id"],
                "name": part["name"],
                "semantic_type": part["semantic_type"],
                "bbox": part["bbox"],
                "pivot": {"x": float(part["pivot_x"]), "y": float(part["pivot_y"])},
                "parent_id": part["parent_id"],
                "z_index": int(part["z_index"]),
            }
            for part in parts
        ],
    }


def _safe_name(value: str) -> str:
    stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    return stem or "part"
