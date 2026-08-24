from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import subprocess
import struct
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError

from .quality import (
    AssetQualityResult,
    QualityCheckItem,
    QualityItemStatus,
    QualityStatus,
)

MODEL_3D_QUALITY_RULES_VERSION = "model-3d-v1"
GLB_MAGIC = b"glTF"
GLB_JSON_CHUNK = 0x4E4F534A
GLB_BINARY_CHUNK = 0x004E4942
MAX_GLTF_JSON_BYTES = 16 * 1024 * 1024
MAX_TOPOLOGY_VERTICES = 1_000_000
MAX_TOPOLOGY_INDICES = 3_000_000
COMPONENT_DTYPES = {
    5120: np.dtype("i1"),
    5121: np.dtype("u1"),
    5122: np.dtype("<i2"),
    5123: np.dtype("<u2"),
    5125: np.dtype("<u4"),
    5126: np.dtype("<f4"),
}
ACCESSOR_COMPONENTS = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}
GltfValidatorRunner = Callable[[Path], Mapping[str, Any]]


def check_glb_asset(
    path: Path,
    *,
    max_triangles: int | None = None,
    require_uv: bool = True,
    require_pbr: bool = True,
    validator_runner: GltfValidatorRunner | None = None,
) -> AssetQualityResult:
    """Inspect one self-contained GLB and report measurable game-asset constraints."""

    if (
        max_triangles is not None
        and (
            isinstance(max_triangles, bool)
            or not isinstance(max_triangles, int)
            or max_triangles <= 0
        )
    ):
        raise ValueError("max_triangles must be a positive integer")
    if not isinstance(require_uv, bool) or not isinstance(require_pbr, bool):
        raise ValueError("model quality flags must be booleans")

    parameters = {
        "check_type": "model_3d",
        "format": "glb",
        "max_triangles": max_triangles,
        "require_uv": require_uv,
        "require_pbr": require_pbr,
        "gltf_validator": validator_runner is not None,
    }
    try:
        document, binary_offset, binary_length = _read_glb_document(path)
        metrics = _model_metrics(
            path,
            document,
            binary_offset=binary_offset,
            binary_length=binary_length,
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        checks = [
            QualityCheckItem(
                code="MODEL_GLTF_PARSE",
                status="failed",
                message="GLB 文件无法解析或结构不完整。",
                metrics={},
            )
        ]
        if validator_runner is not None:
            # The official report remains useful when the lightweight reader
            # rejects a container, so malformed deliveries still retain both
            # pieces of evidence.
            checks.append(_gltf_validator_check(path, validator_runner))
        return AssetQualityResult(
            status=_overall_model_status(checks),
            rules_version=MODEL_3D_QUALITY_RULES_VERSION,
            content_sha256=_sha256(path),
            checks=tuple(checks),
            parameters=parameters,
        )

    checks = [
        QualityCheckItem(
            code="MODEL_GLTF_PARSE",
            status="passed",
            message="GLB 2.0 文件可解析。",
            metrics={
                "generator": metrics["generator"],
                "size_bytes": path.stat().st_size,
            },
        ),
        _geometry_check(metrics, max_triangles=max_triangles),
        _topology_check(metrics),
        _normal_uv_check(metrics, require_uv=require_uv),
        _material_texture_check(metrics, require_pbr=require_pbr),
        _bounds_check(metrics),
        QualityCheckItem(
            code="MODEL_RIG_ANIMATION",
            status="passed",
            message="已记录骨骼和动画数量。",
            metrics={
                "skin_count": metrics["skin_count"],
                "animation_count": metrics["animation_count"],
            },
        ),
    ]
    if validator_runner is not None:
        checks.append(_gltf_validator_check(path, validator_runner))
    return AssetQualityResult(
        status=_overall_model_status(checks),
        rules_version=MODEL_3D_QUALITY_RULES_VERSION,
        content_sha256=_sha256(path),
        checks=tuple(checks),
        parameters=parameters,
    )


def _read_glb_document(path: Path) -> tuple[dict[str, Any], int, int]:
    file_size = path.stat().st_size
    with path.open("rb") as source:
        header = source.read(12)
        if len(header) != 12:
            raise ValueError("Incomplete GLB header")
        magic, version, declared_length = struct.unpack("<4sII", header)
        if magic != GLB_MAGIC or version != 2 or declared_length != file_size:
            raise ValueError("Invalid GLB header")
        json_document: dict[str, Any] | None = None
        binary_offset = 0
        binary_length = 0
        while source.tell() < declared_length:
            chunk_header = source.read(8)
            if len(chunk_header) != 8:
                raise ValueError("Incomplete GLB chunk header")
            chunk_length, chunk_type = struct.unpack("<II", chunk_header)
            if chunk_length % 4 or source.tell() + chunk_length > declared_length:
                raise ValueError("Invalid GLB chunk length")
            if chunk_type == GLB_JSON_CHUNK:
                if json_document is not None or chunk_length > MAX_GLTF_JSON_BYTES:
                    raise ValueError("Invalid GLB JSON chunk")
                payload = source.read(chunk_length).rstrip(b" \t\r\n\x00")
                decoded = json.loads(payload.decode("utf-8"))
                if not isinstance(decoded, dict):
                    raise ValueError("Invalid GLB document")
                json_document = decoded
            elif chunk_type == GLB_BINARY_CHUNK:
                if binary_length:
                    raise ValueError("Multiple GLB binary chunks")
                binary_offset = source.tell()
                binary_length = chunk_length
                source.seek(chunk_length, 1)
            else:
                source.seek(chunk_length, 1)
        if source.tell() != declared_length or json_document is None:
            raise ValueError("Incomplete GLB document")
    asset = json_document.get("asset")
    if not isinstance(asset, dict) or not str(asset.get("version") or "").startswith("2"):
        raise ValueError("Unsupported glTF version")
    return json_document, binary_offset, binary_length


def _model_metrics(
    path: Path,
    document: Mapping[str, Any],
    *,
    binary_offset: int,
    binary_length: int,
) -> dict[str, Any]:
    accessors = _object_list(document.get("accessors"))
    buffer_views = _object_list(document.get("bufferViews"))
    buffers = _object_list(document.get("buffers"))
    meshes = _object_list(document.get("meshes"))
    materials = _object_list(document.get("materials"))
    images = _object_list(document.get("images"))
    textures = _object_list(document.get("textures"))
    if len(buffers) != 1 or binary_length <= 0:
        raise ValueError("GLB binary buffer missing")
    if any(buffer.get("uri") for buffer in buffers):
        raise ValueError("GLB references external buffers")
    _validate_texture_references(materials, textures, images)
    declared_buffer_length = int(buffers[0].get("byteLength") or 0)
    if declared_buffer_length <= 0 or declared_buffer_length > binary_length:
        raise ValueError("GLB binary buffer length mismatch")

    primitive_records: list[dict[str, Any]] = []
    total_vertices = 0
    total_triangles = 0
    bounds_min: list[list[float]] = []
    bounds_max: list[list[float]] = []
    for mesh in meshes:
        for primitive in _object_list(mesh.get("primitives")):
            attributes = primitive.get("attributes")
            if not isinstance(attributes, dict) or "POSITION" not in attributes:
                raise ValueError("Mesh primitive has no POSITION accessor")
            position_index = _index(attributes["POSITION"], accessors)
            position_accessor = accessors[position_index]
            vertex_count = _positive_int(position_accessor.get("count"))
            triangles = _triangle_count(primitive, accessors, vertex_count)
            total_vertices += vertex_count
            total_triangles += triangles
            minimum = position_accessor.get("min")
            maximum = position_accessor.get("max")
            if _vec3(minimum) is not None and _vec3(maximum) is not None:
                bounds_min.append(_vec3(minimum) or [])
                bounds_max.append(_vec3(maximum) or [])
            primitive_records.append(
                {
                    "primitive": primitive,
                    "position_accessor": position_index,
                    "vertex_count": vertex_count,
                    "triangle_count": triangles,
                    "has_normal": "NORMAL" in attributes,
                    "has_uv": "TEXCOORD_0" in attributes,
                }
            )
    if not primitive_records:
        raise ValueError("GLB contains no mesh primitives")

    topology = _topology_metrics(
        path,
        primitive_records,
        accessors=accessors,
        buffer_views=buffer_views,
        binary_offset=binary_offset,
        binary_length=binary_length,
    )
    external_images = [
        str(image.get("uri"))
        for image in images
        if image.get("uri") and not str(image.get("uri")).startswith("data:")
    ]
    texture_dimensions, invalid_images = _texture_dimensions(
        path,
        images,
        buffer_views=buffer_views,
        binary_offset=binary_offset,
        binary_length=binary_length,
    )
    pbr_complete = sum(_material_has_pbr_textures(material) for material in materials)
    asset = document.get("asset") if isinstance(document.get("asset"), dict) else {}
    return {
        "generator": str(asset.get("generator") or ""),
        "mesh_count": len(meshes),
        "primitive_count": len(primitive_records),
        "vertex_count": total_vertices,
        "triangle_count": total_triangles,
        "all_normals": all(record["has_normal"] for record in primitive_records),
        "all_uv": all(record["has_uv"] for record in primitive_records),
        "bounds_min": _global_min(bounds_min),
        "bounds_max": _global_max(bounds_max),
        "material_count": len(materials),
        "texture_count": len(textures),
        "image_count": len(images),
        "pbr_complete_materials": pbr_complete,
        "external_images": external_images,
        "invalid_images": invalid_images,
        "maximum_texture_width": max((width for width, _height in texture_dimensions), default=0),
        "maximum_texture_height": max((height for _width, height in texture_dimensions), default=0),
        "skin_count": len(_object_list(document.get("skins"))),
        "animation_count": len(_object_list(document.get("animations"))),
        **topology,
    }


def _topology_metrics(
    path: Path,
    primitive_records: Sequence[Mapping[str, Any]],
    *,
    accessors: Sequence[Mapping[str, Any]],
    buffer_views: Sequence[Mapping[str, Any]],
    binary_offset: int,
    binary_length: int,
) -> dict[str, Any]:
    if (
        sum(int(record["vertex_count"]) for record in primitive_records)
        > MAX_TOPOLOGY_VERTICES
        or sum(int(record["triangle_count"]) * 3 for record in primitive_records)
        > MAX_TOPOLOGY_INDICES
    ):
        return _unchecked_topology_metrics()
    degenerate = 0
    non_manifold = 0
    boundaries = 0
    isolated = 0
    for record in primitive_records:
        primitive = record["primitive"]
        if not isinstance(primitive, Mapping) or int(primitive.get("mode", 4)) != 4:
            return _unchecked_topology_metrics()
        position_accessor = accessors[int(record["position_accessor"])]
        if (
            int(position_accessor.get("componentType") or 0) != 5126
            or position_accessor.get("sparse") is not None
            or _primitive_uses_draco(primitive)
            or _accessor_uses_meshopt(
                position_accessor,
                buffer_views=buffer_views,
            )
        ):
            # Provider GLBs may use Meshopt, Draco, or quantized POSITION data.
            # The official validator still checks those encodings; this local
            # reader leaves topology unchecked instead of reading compressed
            # bytes as vertices.
            return _unchecked_topology_metrics()
        positions = _read_accessor(
            path,
            int(record["position_accessor"]),
            accessors=accessors,
            buffer_views=buffer_views,
            binary_offset=binary_offset,
            binary_length=binary_length,
        )
        if positions.shape[1:] != (3,) or positions.dtype.kind != "f":
            raise ValueError("POSITION accessor must be floating VEC3")
        indices_value = primitive.get("indices")
        if indices_value is None:
            indices = np.arange(int(record["vertex_count"]), dtype=np.uint32)
        else:
            index_accessor = accessors[_index(indices_value, accessors)]
            if str(index_accessor.get("type") or "") != "SCALAR":
                raise ValueError("Index accessor must be scalar")
            if _accessor_uses_meshopt(index_accessor, buffer_views=buffer_views):
                return _unchecked_topology_metrics()
            indices = _read_accessor(
                path,
                _index(indices_value, accessors),
                accessors=accessors,
                buffer_views=buffer_views,
                binary_offset=binary_offset,
                binary_length=binary_length,
            ).reshape(-1)
            if indices.dtype.kind not in {"u", "i"}:
                raise ValueError("Index accessor is not integral")
        if indices.size % 3 or np.any(indices < 0) or np.any(indices >= positions.shape[0]):
            raise ValueError("Triangle indices are invalid")
        triangles = indices.astype(np.int64).reshape(-1, 3)
        duplicate_vertices = (
            (triangles[:, 0] == triangles[:, 1])
            | (triangles[:, 1] == triangles[:, 2])
            | (triangles[:, 0] == triangles[:, 2])
        )
        first = positions[triangles[:, 1]] - positions[triangles[:, 0]]
        second = positions[triangles[:, 2]] - positions[triangles[:, 0]]
        zero_area = np.linalg.norm(np.cross(first, second), axis=1) <= 1e-12
        degenerate += int(np.count_nonzero(duplicate_vertices | zero_area))
        used_vertices = np.unique(triangles)
        isolated += int(positions.shape[0] - used_vertices.size)
        edge_counts = Counter(
            tuple(sorted((int(left), int(right))))
            for triangle in triangles
            for left, right in (
                (triangle[0], triangle[1]),
                (triangle[1], triangle[2]),
                (triangle[2], triangle[0]),
            )
        )
        non_manifold += sum(count > 2 for count in edge_counts.values())
        boundaries += sum(count == 1 for count in edge_counts.values())
    return {
        "topology_checked": True,
        "degenerate_triangles": degenerate,
        "non_manifold_edges": non_manifold,
        "boundary_edges": boundaries,
        "isolated_vertices": isolated,
    }


def _unchecked_topology_metrics() -> dict[str, Any]:
    return {
        "topology_checked": False,
        "degenerate_triangles": None,
        "non_manifold_edges": None,
        "boundary_edges": None,
        "isolated_vertices": None,
    }


def _primitive_uses_draco(primitive: Mapping[str, Any]) -> bool:
    extensions = primitive.get("extensions")
    return isinstance(extensions, Mapping) and isinstance(
        extensions.get("KHR_draco_mesh_compression"),
        Mapping,
    )


def _accessor_uses_meshopt(
    accessor: Mapping[str, Any],
    *,
    buffer_views: Sequence[Mapping[str, Any]],
) -> bool:
    if accessor.get("bufferView") is None:
        return False
    view = buffer_views[_index(accessor["bufferView"], buffer_views)]
    extensions = view.get("extensions")
    return isinstance(extensions, Mapping) and isinstance(
        extensions.get("EXT_meshopt_compression"),
        Mapping,
    )


def _read_accessor(
    path: Path,
    accessor_index: int,
    *,
    accessors: Sequence[Mapping[str, Any]],
    buffer_views: Sequence[Mapping[str, Any]],
    binary_offset: int,
    binary_length: int,
) -> np.ndarray:
    accessor = accessors[accessor_index]
    if accessor.get("sparse") is not None or accessor.get("bufferView") is None:
        raise ValueError("Sparse or missing accessor buffer view")
    view = buffer_views[_index(accessor["bufferView"], buffer_views)]
    if int(view.get("buffer", 0)) != 0:
        raise ValueError("External GLB buffer")
    dtype = COMPONENT_DTYPES.get(int(accessor.get("componentType") or 0))
    components = ACCESSOR_COMPONENTS.get(str(accessor.get("type") or ""))
    count = _positive_int(accessor.get("count"))
    if dtype is None or components is None:
        raise ValueError("Unsupported accessor type")
    item_size = dtype.itemsize * components
    stride = int(view.get("byteStride") or item_size)
    if stride < item_size or stride % dtype.itemsize:
        raise ValueError("Invalid accessor stride")
    view_offset = int(view.get("byteOffset") or 0)
    view_length = _positive_int(view.get("byteLength"))
    accessor_offset = int(accessor.get("byteOffset") or 0)
    relative_offset = view_offset + accessor_offset
    read_length = stride * (count - 1) + item_size
    if (
        view_offset < 0
        or accessor_offset < 0
        or accessor_offset + read_length > view_length
        or relative_offset + read_length > binary_length
    ):
        raise ValueError("Accessor exceeds GLB buffer")
    with path.open("rb") as source:
        source.seek(binary_offset + relative_offset)
        payload = source.read(read_length)
    if len(payload) != read_length:
        raise ValueError("Accessor data is incomplete")
    values = np.ndarray(
        shape=(count, components),
        dtype=dtype,
        buffer=payload,
        strides=(stride, dtype.itemsize),
    )
    return values.copy()


def _texture_dimensions(
    path: Path,
    images: Sequence[Mapping[str, Any]],
    *,
    buffer_views: Sequence[Mapping[str, Any]],
    binary_offset: int,
    binary_length: int,
) -> tuple[list[tuple[int, int]], int]:
    dimensions: list[tuple[int, int]] = []
    invalid = 0
    for image in images:
        try:
            if image.get("bufferView") is not None:
                view = buffer_views[_index(image["bufferView"], buffer_views)]
                payload = _read_buffer_view(
                    path,
                    view,
                    binary_offset=binary_offset,
                    binary_length=binary_length,
                )
            elif str(image.get("uri") or "").startswith("data:"):
                payload = _decode_data_uri(str(image["uri"]))
            else:
                continue
            with Image.open(io.BytesIO(payload)) as decoded:
                dimensions.append((int(decoded.width), int(decoded.height)))
                decoded.verify()
        except (OSError, ValueError, UnidentifiedImageError):
            invalid += 1
    return dimensions, invalid


def _read_buffer_view(
    path: Path,
    view: Mapping[str, Any],
    *,
    binary_offset: int,
    binary_length: int,
) -> bytes:
    if int(view.get("buffer", 0)) != 0:
        raise ValueError("External GLB buffer")
    offset = int(view.get("byteOffset") or 0)
    length = _positive_int(view.get("byteLength"))
    if offset < 0 or offset + length > binary_length:
        raise ValueError("Buffer view exceeds GLB buffer")
    with path.open("rb") as source:
        source.seek(binary_offset + offset)
        payload = source.read(length)
    if len(payload) != length:
        raise ValueError("Buffer view data is incomplete")
    return payload


def _geometry_check(
    metrics: Mapping[str, Any],
    *,
    max_triangles: int | None,
) -> QualityCheckItem:
    triangles = int(metrics["triangle_count"])
    status: QualityItemStatus = (
        "failed"
        if triangles <= 0 or int(metrics["vertex_count"]) <= 0
        else "warning"
        if max_triangles is not None and triangles > max_triangles
        else "passed"
    )
    return QualityCheckItem(
        code="MODEL_GEOMETRY",
        status=status,
        message=(
            "网格包含有效顶点和三角面。"
            if status == "passed"
            else "三角面数超过目标上限。"
            if status == "warning"
            else "网格没有可用几何体。"
        ),
        metrics={
            "mesh_count": metrics["mesh_count"],
            "primitive_count": metrics["primitive_count"],
            "vertex_count": metrics["vertex_count"],
            "triangle_count": triangles,
            "maximum_triangles": max_triangles,
        },
    )


def _topology_check(metrics: Mapping[str, Any]) -> QualityCheckItem:
    if not metrics["topology_checked"]:
        return QualityCheckItem(
            code="MODEL_TOPOLOGY",
            status="not_checked",
            message="网格过大或使用了暂不支持的拓扑编码，需要引擎复核。",
            metrics={},
        )
    degenerate = int(metrics["degenerate_triangles"])
    non_manifold = int(metrics["non_manifold_edges"])
    isolated = int(metrics["isolated_vertices"])
    status: QualityItemStatus = (
        "failed" if degenerate or non_manifold else "warning" if isolated else "passed"
    )
    return QualityCheckItem(
        code="MODEL_TOPOLOGY",
        status=status,
        message=(
            "未发现退化三角形、非流形边或孤立顶点。"
            if status == "passed"
            else "网格包含孤立顶点。"
            if status == "warning"
            else "网格包含退化三角形或非流形边。"
        ),
        metrics={
            "degenerate_triangles": degenerate,
            "non_manifold_edges": non_manifold,
            "boundary_edges": metrics["boundary_edges"],
            "isolated_vertices": isolated,
        },
    )


def _normal_uv_check(
    metrics: Mapping[str, Any],
    *,
    require_uv: bool,
) -> QualityCheckItem:
    normals = bool(metrics["all_normals"])
    uv = bool(metrics["all_uv"])
    status: QualityItemStatus = "passed" if normals and (uv or not require_uv) else "warning"
    return QualityCheckItem(
        code="MODEL_NORMAL_UV",
        status=status,
        message=(
            "所有网格基元包含法线和所需 UV。"
            if status == "passed"
            else "部分网格基元缺少法线或 UV。"
        ),
        metrics={"all_normals": normals, "all_uv": uv, "uv_required": require_uv},
    )


def _material_texture_check(
    metrics: Mapping[str, Any],
    *,
    require_pbr: bool,
) -> QualityCheckItem:
    material_count = int(metrics["material_count"])
    complete = int(metrics["pbr_complete_materials"])
    invalid = int(metrics["invalid_images"])
    external = list(metrics["external_images"])
    if external or invalid:
        status: QualityItemStatus = "failed"
    elif require_pbr and (material_count == 0 or complete != material_count):
        status = "warning"
    else:
        status = "passed"
    return QualityCheckItem(
        code="MODEL_MATERIAL_TEXTURE",
        status=status,
        message=(
            "材质和 PBR 纹理已包含在 GLB 中。"
            if status == "passed"
            else "部分材质缺少完整 PBR 纹理。"
            if status == "warning"
            else "GLB 包含外部或无法解析的纹理。"
        ),
        metrics={
            "material_count": material_count,
            "texture_count": metrics["texture_count"],
            "image_count": metrics["image_count"],
            "pbr_complete_materials": complete,
            "maximum_texture_width": metrics["maximum_texture_width"],
            "maximum_texture_height": metrics["maximum_texture_height"],
            "external_image_count": len(external),
            "invalid_image_count": invalid,
            "pbr_required": require_pbr,
        },
    )


def _bounds_check(metrics: Mapping[str, Any]) -> QualityCheckItem:
    minimum = metrics["bounds_min"]
    maximum = metrics["bounds_max"]
    valid = (
        isinstance(minimum, list)
        and isinstance(maximum, list)
        and len(minimum) == 3
        and len(maximum) == 3
        and all(math.isfinite(float(value)) for value in [*minimum, *maximum])
        and all(float(low) <= float(high) for low, high in zip(minimum, maximum))
    )
    return QualityCheckItem(
        code="MODEL_BOUNDS_COORDINATES",
        status="passed" if valid else "warning",
        message=(
            "包围盒有效；glTF 坐标按米制、Y 轴向上解释。"
            if valid
            else "POSITION accessor 缺少有效包围盒，需要引擎复核。"
        ),
        metrics={
            "minimum": minimum,
            "maximum": maximum,
            "unit": "meter",
            "up_axis": "Y",
        },
    )


def run_gltf_validator(path: Path, executable: Path) -> Mapping[str, Any]:
    """Run the official validator without installing or downloading it implicitly."""

    resolved = executable.expanduser().resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ValueError("glTF Validator executable is unavailable")
    completed = subprocess.run(
        [str(resolved), "--stdout", str(path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("glTF Validator did not return JSON") from exc
    if not isinstance(report, dict):
        raise ValueError("glTF Validator report is invalid")
    # The validator exits non-zero when the report contains model errors. The
    # report remains authoritative in that case, so only missing JSON is treated
    # as an unavailable tool result.
    return report


def _gltf_validator_check(
    path: Path,
    runner: GltfValidatorRunner,
) -> QualityCheckItem:
    try:
        report = runner(path)
        issues = report.get("issues")
        if not isinstance(issues, Mapping):
            raise ValueError("glTF Validator report has no issues summary")
        errors = _non_negative_int(issues.get("numErrors"))
        warnings = _non_negative_int(issues.get("numWarnings"))
        infos = _non_negative_int(issues.get("numInfos"))
        hints = _non_negative_int(issues.get("numHints"))
    except (OSError, subprocess.SubprocessError, TypeError, ValueError):
        return QualityCheckItem(
            code="MODEL_GLTF_VALIDATOR",
            status="not_checked",
            message="glTF Validator 未能完成检查。",
            metrics={},
        )
    status: QualityItemStatus = (
        "failed" if errors else "warning" if warnings else "passed"
    )
    return QualityCheckItem(
        code="MODEL_GLTF_VALIDATOR",
        status=status,
        message=(
            "glTF Validator 未发现规范错误或警告。"
            if status == "passed"
            else "glTF Validator 发现规范警告。"
            if status == "warning"
            else "glTF Validator 发现规范错误。"
        ),
        metrics={
            "validator_version": str(report.get("validatorVersion") or ""),
            "errors": errors,
            "warnings": warnings,
            "infos": infos,
            "hints": hints,
            "truncated": bool(issues.get("truncated", False)),
        },
    )


def _triangle_count(
    primitive: Mapping[str, Any],
    accessors: Sequence[Mapping[str, Any]],
    vertex_count: int,
) -> int:
    mode = int(primitive.get("mode", 4))
    count = (
        _positive_int(accessors[_index(primitive["indices"], accessors)].get("count"))
        if primitive.get("indices") is not None
        else vertex_count
    )
    if mode == 4:
        if count % 3:
            raise ValueError("Triangle index count is not divisible by three")
        return count // 3
    if mode in {5, 6}:
        return max(0, count - 2)
    return 0


def _material_has_pbr_textures(material: Mapping[str, Any]) -> bool:
    pbr = material.get("pbrMetallicRoughness")
    return bool(
        isinstance(pbr, dict)
        and isinstance(pbr.get("baseColorTexture"), dict)
        and isinstance(pbr.get("metallicRoughnessTexture"), dict)
        and isinstance(material.get("normalTexture"), dict)
    )


def _validate_texture_references(
    materials: Sequence[Mapping[str, Any]],
    textures: Sequence[Mapping[str, Any]],
    images: Sequence[Mapping[str, Any]],
) -> None:
    for texture in textures:
        if texture.get("source") is not None:
            _index(texture["source"], images)
    for material in materials:
        pbr = material.get("pbrMetallicRoughness")
        texture_infos = [
            pbr.get("baseColorTexture") if isinstance(pbr, dict) else None,
            pbr.get("metallicRoughnessTexture") if isinstance(pbr, dict) else None,
            material.get("normalTexture"),
            material.get("occlusionTexture"),
            material.get("emissiveTexture"),
        ]
        for info in texture_infos:
            if info is None:
                continue
            if not isinstance(info, dict) or info.get("index") is None:
                raise ValueError("Material texture reference is invalid")
            _index(info["index"], textures)


def _decode_data_uri(value: str) -> bytes:
    header, separator, encoded = value.partition(",")
    if not separator or ";base64" not in header.lower():
        raise ValueError("Image data URI is invalid")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Image data URI is invalid") from exc
    if not payload:
        raise ValueError("Image data URI is empty")
    return payload


def _object_list(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("glTF collection is invalid")
    return list(value)


def _index(value: object, rows: Sequence[object]) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < len(rows):
        raise ValueError("glTF index is invalid")
    return value


def _positive_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("glTF count is invalid")
    return value


def _non_negative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("glTF Validator issue count is invalid")
    return value


def _vec3(value: object) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 3:
        return None
    try:
        parsed = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    return parsed if all(math.isfinite(item) for item in parsed) else None


def _global_min(values: Sequence[Sequence[float]]) -> list[float] | None:
    return [min(item[index] for item in values) for index in range(3)] if values else None


def _global_max(values: Sequence[Sequence[float]]) -> list[float] | None:
    return [max(item[index] for item in values) for index in range(3)] if values else None


def _overall_model_status(checks: Sequence[QualityCheckItem]) -> QualityStatus:
    if any(item.status == "failed" for item in checks):
        return "failed"
    if any(item.status == "not_checked" for item in checks):
        return "unchecked"
    if any(item.status == "warning" for item in checks):
        return "warning"
    return "passed"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
