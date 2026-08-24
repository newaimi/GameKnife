from __future__ import annotations

import base64
import io
import json
import subprocess
import struct
from pathlib import Path

import numpy as np
import gameknife_processors.model_quality as model_quality
from gameknife_processors import check_glb_asset, run_gltf_validator
from PIL import Image


def test_glb_quality_reports_geometry_topology_pbr_and_bounds(tmp_path: Path) -> None:
    model_path = tmp_path / "triangle.glb"
    model_path.write_bytes(_glb_bytes())

    result = check_glb_asset(model_path, max_triangles=100)

    assert result.status == "passed"
    assert result.rules_version == "model-3d-v1"
    payload = json.loads(result.checks_json())
    assert payload["parameters"] == {
        "check_type": "model_3d",
        "format": "glb",
        "max_triangles": 100,
        "require_uv": True,
        "require_pbr": True,
        "gltf_validator": False,
    }
    geometry = next(
        item for item in payload["checks"] if item["code"] == "MODEL_GEOMETRY"
    )
    assert geometry["metrics"]["vertex_count"] == 3
    assert geometry["metrics"]["triangle_count"] == 1
    topology = next(
        item for item in payload["checks"] if item["code"] == "MODEL_TOPOLOGY"
    )
    assert topology["status"] == "passed"
    assert topology["metrics"]["boundary_edges"] == 3
    material = next(
        item
        for item in payload["checks"]
        if item["code"] == "MODEL_MATERIAL_TEXTURE"
    )
    assert material["metrics"]["pbr_complete_materials"] == 1
    assert material["metrics"]["maximum_texture_width"] == 2


def test_glb_quality_fails_degenerate_or_external_delivery(tmp_path: Path) -> None:
    degenerate_path = tmp_path / "degenerate.glb"
    degenerate_path.write_bytes(_glb_bytes(indices=(0, 0, 1)))
    degenerate = check_glb_asset(degenerate_path)

    assert degenerate.status == "failed"
    assert next(
        item for item in degenerate.checks if item.code == "MODEL_TOPOLOGY"
    ).status == "failed"

    external_path = tmp_path / "external.glb"
    external_path.write_bytes(_glb_bytes(external_image=True))
    external = check_glb_asset(external_path)

    assert external.status == "failed"
    assert next(
        item
        for item in external.checks
        if item.code == "MODEL_MATERIAL_TEXTURE"
    ).status == "failed"


def test_glb_quality_rejects_malformed_container_and_invalid_policy(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "broken.glb"
    model_path.write_bytes(b"not-a-glb")

    result = check_glb_asset(model_path)

    assert result.status == "failed"
    assert result.checks[0].code == "MODEL_GLTF_PARSE"
    try:
        check_glb_asset(model_path, max_triangles=0)
    except ValueError as exc:
        assert "max_triangles" in str(exc)
    else:
        raise AssertionError("Invalid triangle limits must be rejected before parsing.")

    validated = check_glb_asset(
        model_path,
        validator_runner=lambda _path: {
            "validatorVersion": "2.0.0-test",
            "issues": {
                "numErrors": 1,
                "numWarnings": 0,
                "numInfos": 0,
                "numHints": 0,
            },
        },
    )
    assert [item.code for item in validated.checks] == [
        "MODEL_GLTF_PARSE",
        "MODEL_GLTF_VALIDATOR",
    ]


def test_glb_quality_supports_data_uri_textures_and_validator_report(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "data-uri.glb"
    model_path.write_bytes(_glb_bytes(data_uri_image=True))

    result = check_glb_asset(
        model_path,
        validator_runner=lambda _path: {
            "validatorVersion": "2.0.0-test",
            "issues": {
                "numErrors": 0,
                "numWarnings": 0,
                "numInfos": 1,
                "numHints": 0,
                "truncated": False,
            },
        },
    )

    assert result.status == "passed"
    validator = next(
        item for item in result.checks if item.code == "MODEL_GLTF_VALIDATOR"
    )
    assert validator.status == "passed"
    assert validator.metrics["validator_version"] == "2.0.0-test"


def test_glb_quality_rejects_invalid_texture_references(tmp_path: Path) -> None:
    model_path = tmp_path / "invalid-texture.glb"
    model_path.write_bytes(_glb_bytes(invalid_texture_reference=True))

    result = check_glb_asset(model_path)

    assert result.status == "failed"
    assert result.checks[0].code == "MODEL_GLTF_PARSE"


def test_glb_quality_does_not_read_meshopt_bytes_as_raw_topology(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "meshopt.glb"
    model_path.write_bytes(_glb_bytes(meshopt_position=True))

    result = check_glb_asset(model_path)

    assert result.status == "unchecked"
    topology = next(
        item for item in result.checks if item.code == "MODEL_TOPOLOGY"
    )
    assert topology.status == "not_checked"


def test_gltf_validator_adapter_keeps_nonzero_validation_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    executable = tmp_path / "gltf_validator"
    executable.write_text("test executable", encoding="utf-8")
    executable.chmod(0o755)
    model_path = tmp_path / "model.glb"
    model_path.write_bytes(_glb_bytes())
    calls = []

    def fake_run(arguments, **options):
        calls.append((arguments, options))
        return subprocess.CompletedProcess(
            arguments,
            returncode=1,
            stdout=json.dumps(
                {
                    "validatorVersion": "2.0.0-test",
                    "issues": {"numErrors": 1},
                }
            ),
            stderr="validation error",
        )

    monkeypatch.setattr(model_quality.subprocess, "run", fake_run)

    report = run_gltf_validator(model_path, executable)

    assert report["issues"]["numErrors"] == 1
    assert calls[0][0] == [str(executable), "--stdout", str(model_path)]
    assert calls[0][1]["check"] is False
    assert calls[0][1]["timeout"] == 120


def _glb_bytes(
    *,
    indices: tuple[int, int, int] = (0, 1, 2),
    external_image: bool = False,
    data_uri_image: bool = False,
    invalid_texture_reference: bool = False,
    meshopt_position: bool = False,
) -> bytes:
    positions = np.asarray(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        dtype="<f4",
    ).tobytes()
    normals = np.asarray(((0.0, 0.0, 1.0),) * 3, dtype="<f4").tobytes()
    uv = np.asarray(((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)), dtype="<f4").tobytes()
    index_bytes = np.asarray(indices, dtype="<u2").tobytes()
    texture = _png_bytes()
    binary = bytearray()
    views: list[dict[str, int]] = []
    for payload in (positions, normals, uv, index_bytes, texture):
        while len(binary) % 4:
            binary.append(0)
        views.append(
            {
                "buffer": 0,
                "byteOffset": len(binary),
                "byteLength": len(payload),
            }
        )
        binary.extend(payload)
    while len(binary) % 4:
        binary.append(0)
    if meshopt_position:
        views[0]["extensions"] = {"EXT_meshopt_compression": {}}
    if external_image:
        image = {"uri": "https://example.test/texture.png", "mimeType": "image/png"}
    elif data_uri_image:
        image = {
            "uri": "data:image/png;base64,"
            + base64.b64encode(texture).decode("ascii")
        }
    else:
        image = {"bufferView": 4, "mimeType": "image/png"}
    document = {
        "asset": {"version": "2.0", "generator": "GameKnife test"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": views,
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [0, 0, 0],
                "max": [1, 1, 0],
            },
            {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": 3, "type": "VEC2"},
            {"bufferView": 3, "componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
        "images": [image],
        "textures": [{"source": 9 if invalid_texture_reference else 0}],
        "materials": [
            {
                "pbrMetallicRoughness": {
                    "baseColorTexture": {"index": 0},
                    "metallicRoughnessTexture": {"index": 0},
                },
                "normalTexture": {"index": 0},
            }
        ],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
                        "indices": 3,
                        "material": 0,
                    }
                ]
            }
        ],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    json_payload = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_payload += b" " * (-len(json_payload) % 4)
    binary_payload = bytes(binary)
    total_length = 12 + 8 + len(json_payload) + 8 + len(binary_payload)
    return b"".join(
        (
            struct.pack("<4sII", b"glTF", 2, total_length),
            struct.pack("<II", len(json_payload), 0x4E4F534A),
            json_payload,
            struct.pack("<II", len(binary_payload), 0x004E4942),
            binary_payload,
        )
    )


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), (128, 64, 32)).save(buffer, format="PNG")
    return buffer.getvalue()
