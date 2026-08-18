from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class StableAudioService:
    # Community API queues generation through the internal HTTP service and never loads Stable Audio directly.
    # The main Web process holds no audio model or GPU state; installation, queue limits, and timeouts stay in the service boundary.
    def __init__(self, base_url: str, token: str = "", timeout_seconds: int = 900):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = max(1, int(timeout_seconds))

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    def install_status(self) -> dict[str, Any]:
        # Return a stable shape when unconfigured so Settings and job creation can branch directly on status.
        # Do not raise here, because Settings must remain available in a login-free Community startup.
        if not self.is_configured:
            return {
                "status": "unconfigured",
                "installed": False,
                "message": "Stable Audio 声效服务未配置。",
                "error": None,
            }
        try:
            return self._request_json("GET", "/models/status")
        except RuntimeError as exc:
            return {
                "status": "unavailable",
                "installed": False,
                "message": "Stable Audio 声效服务不可用。",
                "error": str(exc),
            }

    def start_install(self) -> dict[str, Any]:
        if not self.is_configured:
            raise RuntimeError("Stable Audio 声效服务未配置。")
        return self._request_json("POST", "/models/install")

    def generate_sound_effect(self, prompt: str, output_path: Path, parameters: dict[str, Any]) -> dict[str, Any]:
        if not self.is_configured:
            raise RuntimeError("Stable Audio 声效服务未配置。")

        payload = {
            "prompt": prompt,
            "duration_seconds": float(parameters.get("duration_seconds", 4)),
            "seed": parameters.get("seed"),
            "steps": int(parameters.get("steps", 100)),
            "cfg_scale": float(parameters.get("cfg_scale", 7.0)),
        }
        body, headers = self._request_bytes("POST", "/generate", payload)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(body)
        # The generation service reports device, queue time, and sample rate in headers; the API persists them in job results.
        # History can trace actual execution details without exposing internal worker state to public workflows.
        return {
            "model": headers.get("X-Stable-Audio-Model", ""),
            "device": headers.get("X-Stable-Audio-Device", ""),
            "sample_rate": _read_int_header(headers, "X-Stable-Audio-Sample-Rate"),
            "queue_wait_ms": _read_int_header(headers, "X-Stable-Audio-Queue-Wait-Ms"),
            "duration_ms": _read_int_header(headers, "X-Stable-Audio-Duration-Ms"),
        }

    def _request_json(self, method: str, path: str) -> dict[str, Any]:
        body, _ = self._request_bytes(method, path)
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("声效服务返回了无法解析的响应。") from exc
        if not isinstance(data, dict):
            raise RuntimeError("声效服务返回格式不正确。")
        return data

    def _request_bytes(self, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[bytes, Any]:
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if self.token:
            headers["X-GameKnife-Token"] = self.token

        request = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                return response.read(), response.headers
        except HTTPError as exc:
            raise RuntimeError(_read_error_detail(exc)) from exc
        except URLError as exc:
            raise RuntimeError(f"无法连接 Stable Audio 声效服务：{exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError("Stable Audio 声效服务请求超时。") from exc


def _read_error_detail(exc: HTTPError) -> str:
    fallback = f"Stable Audio 声效服务请求失败，状态码 {exc.code}。"
    try:
        body = exc.read().decode("utf-8")
        data = json.loads(body)
        if isinstance(data, dict) and isinstance(data.get("detail"), str):
            return data["detail"]
    except Exception:  # noqa: BLE001
        return fallback
    return fallback


def _read_int_header(headers: Any, name: str) -> int | None:
    value = headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
