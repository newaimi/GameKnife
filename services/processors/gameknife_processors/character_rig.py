from __future__ import annotations

import io
import json
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from gameknife_core import ProcessResult
from gameknife_processors.image_utils import connected_components


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


class CharacterRigProcessor:
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

    def refine_part(
        self,
        input_path: Path,
        part: Any,
        output_dir: Path,
        parameters: dict[str, Any],
    ) -> tuple[ProcessResult, CharacterPartOutput]:
        started = time.perf_counter()
        output_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(input_path) as opened:
            source = opened.convert("RGBA")

        alpha = np.asarray(source.getchannel("A"), dtype=np.uint8)
        if not _has_transparency(alpha):
            raise RuntimeError("骨骼拆分模型尚未下载安装，请先到设置页下载安装模型文件。")

        bbox = json.loads(part["bbox_json"])
        padding = max(0, int(parameters.get("padding", 2)))
        x, y, width, height = _pad_bbox((int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])), padding, source.width, source.height)
        part_alpha = alpha[y : y + height, x : x + width]
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
                result={"part_id": part["id"], "bbox": output.bbox, "warnings": ["部件已基于当前透明区域重新生成。"]},
                duration_ms=int((time.perf_counter() - started) * 1000),
                device="CPU",
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
