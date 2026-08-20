from __future__ import annotations

import base64
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from gameknife_jobs import GameKnifeRepository
from PIL import Image

VIDEO_GENERATION_SETTING_KEY = "video_generation_config"

DEFAULT_VIDEO_GENERATION_CONFIG: dict[str, Any] = {
    "provider": "aliyun_dashscope",
    "base_url": "https://dashscope.aliyuncs.com",
    "api_key": "",
    "api_key_header": "Authorization",
    "api_key_prefix": "Bearer ",
    "model": "happyhorse-1.0-i2v",
    "submit_path": "/api/v1/services/aigc/video-generation/video-synthesis",
    "query_path": "/api/v1/tasks/{task_id}",
    "poll_interval_seconds": 15,
    "timeout_seconds": 900,
    "task_id_path": "output.task_id",
    "status_path": "output.task_status",
    "video_url_path": "output.video_url",
    "success_status": "SUCCEEDED",
    "failed_status": "FAILED",
    "pending_statuses": ["PENDING", "RUNNING"],
}

PROVIDER_DEFAULTS: dict[str, dict[str, Any]] = {
    "aliyun_dashscope": {
        "base_url": "https://dashscope.aliyuncs.com",
        "model": "happyhorse-1.0-i2v",
        "submit_path": "/api/v1/services/aigc/video-generation/video-synthesis",
        "query_path": "/api/v1/tasks/{task_id}",
        "task_id_path": "output.task_id",
        "status_path": "output.task_status",
        "video_url_path": "output.video_url",
        "success_status": "SUCCEEDED",
        "failed_status": "FAILED",
        "pending_statuses": ["PENDING", "RUNNING"],
    },
    "seedance": {
        "base_url": "https://ark.cn-beijing.volces.com",
        "model": "doubao-seedance-1-0-pro-250528",
        "submit_path": "/api/v3/contents/generations/tasks",
        "query_path": "/api/v3/contents/generations/tasks/{task_id}",
        "task_id_path": "id",
        "status_path": "status",
        "video_url_path": "content.video_url",
        "success_status": "succeeded",
        "failed_status": "failed",
        "pending_statuses": ["queued", "running", "pending"],
    },
}


@dataclass(slots=True)
class VideoGenerationResult:
    external_task_id: str
    video_url: str
    output_path: Path
    provider: str
    final_response: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VideoGenerationSubmission:
    external_task_id: str
    provider: str
    response: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VideoGenerationPollResult:
    state: Literal["pending", "succeeded", "failed", "unknown"]
    provider_status: str
    video_url: str | None
    message: str | None
    response: dict[str, Any]


class VideoGenerationProviderAdapter:
    """Single-request adapter shared by in-process and durable task runners.

    The adapter owns only one provider interaction at a time. Callers decide whether
    polling happens in a local loop or across durable worker messages.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = normalize_video_generation_config(config)
        _ensure_configured(self.config)

    @property
    def provider(self) -> str:
        return str(self.config["provider"])

    @property
    def poll_interval_seconds(self) -> int:
        return int(self.config["poll_interval_seconds"])

    @property
    def timeout_seconds(self) -> int:
        return int(self.config["timeout_seconds"])

    def submit(self, image_path: Path, parameters: dict[str, Any]) -> VideoGenerationSubmission:
        image_data_url = _image_to_data_url(image_path)
        body = _build_submit_body(self.config, image_data_url, parameters)
        response = _request_json(
            "POST",
            _join_url(str(self.config["base_url"]), str(self.config["submit_path"])),
            self.config,
            body,
        )
        external_task_id = str(_read_json_path(response, str(self.config["task_id_path"])) or "")
        if not external_task_id:
            raise RuntimeError("视频生成接口没有返回任务 ID。")
        return VideoGenerationSubmission(
            external_task_id=external_task_id,
            provider=self.provider,
            response=response,
        )

    def poll_once(self, external_task_id: str) -> VideoGenerationPollResult:
        query_path = str(self.config["query_path"]).replace("{task_id}", urllib.parse.quote(external_task_id))
        response = _request_json(
            "GET",
            _join_url(str(self.config["base_url"]), query_path),
            self.config,
            None,
        )
        provider_status = str(_read_json_path(response, str(self.config["status_path"])) or "")
        normalized_status = provider_status.upper()
        if normalized_status == str(self.config["success_status"]).upper():
            video_url = str(_read_json_path(response, str(self.config["video_url_path"])) or "") or None
            return VideoGenerationPollResult("succeeded", provider_status, video_url, None, response)
        if normalized_status == str(self.config["failed_status"]).upper():
            message = _read_json_path(response, "output.message") or _read_json_path(response, "message") or "视频生成失败。"
            return VideoGenerationPollResult("failed", provider_status, None, str(message), response)
        pending_statuses = {str(status).upper() for status in self.config.get("pending_statuses", [])}
        if normalized_status and normalized_status not in pending_statuses:
            return VideoGenerationPollResult(
                "unknown",
                provider_status,
                None,
                f"视频生成接口返回未知状态：{normalized_status}。",
                response,
            )
        return VideoGenerationPollResult("pending", provider_status, None, None, response)

    def download(self, video_url: str, output_path: Path) -> Path:
        _download_video(video_url, output_path)
        return output_path


class VideoGenerationClient:
    def __init__(self, repository: GameKnifeRepository):
        self.repository = repository

    def read_config(self, *, include_secret: bool = False) -> dict[str, Any]:
        raw = self.repository.read_setting(VIDEO_GENERATION_SETTING_KEY, json.dumps(DEFAULT_VIDEO_GENERATION_CONFIG, ensure_ascii=False))
        try:
            stored = json.loads(raw)
        except json.JSONDecodeError:
            stored = {}

        config = self._normalize_config({**DEFAULT_VIDEO_GENERATION_CONFIG, **stored})
        return config if include_secret else self._sanitize_config(config)

    def save_config(self, patch: dict[str, Any], *, updated_at: str) -> dict[str, Any]:
        patch = {key: patch[key] for key in ("provider", "base_url", "api_key") if key in patch and patch[key] is not None}
        current = self.read_config(include_secret=True)
        provider = str(patch.get("provider") or current.get("provider"))
        next_config = {**current, **self._provider_defaults(provider), **patch}
        if "api_key" not in patch:
            next_config["api_key"] = current.get("api_key", "")
        next_config = self._normalize_config(next_config)
        self.repository.write_setting(VIDEO_GENERATION_SETTING_KEY, json.dumps(next_config, ensure_ascii=False), updated_at=updated_at)
        return self._sanitize_config(next_config)

    def test_config(self, patch: dict[str, Any] | None = None) -> dict[str, Any]:
        patch = {key: patch[key] for key in ("provider", "base_url", "api_key") if patch and key in patch and patch[key] is not None}
        current = self.read_config(include_secret=True)
        provider = str((patch or {}).get("provider") or current.get("provider"))
        config = self._normalize_config({**current, **self._provider_defaults(provider), **(patch or {})})
        _ensure_configured(config)
        # 测试配置只检查字段完整性。真实视频 API 通常按调用扣费，
        # 不能因为管理员在设置页测试配置就直接发起外部生成请求。
        return {"ok": True, "message": "视频生成 API 配置字段完整。"}

    def ensure_configured(self) -> None:
        _ensure_configured(self.read_config(include_secret=True))

    def generate_video(self, image_path: Path, output_path: Path, parameters: dict[str, Any]) -> VideoGenerationResult:
        config = self.read_config(include_secret=True)
        adapter = VideoGenerationProviderAdapter(config)
        submission = adapter.submit(image_path, parameters)
        started = time.monotonic()
        while True:
            polled = adapter.poll_once(submission.external_task_id)
            if polled.state == "succeeded":
                if not polled.video_url:
                    raise RuntimeError("视频生成成功，但接口没有返回视频地址。")
                adapter.download(polled.video_url, output_path)
                break
            if polled.state == "failed":
                raise RuntimeError(polled.message or "视频生成失败。")
            if polled.state == "unknown":
                raise RuntimeError(polled.message or "视频生成接口返回未知状态。")
            if time.monotonic() - started > adapter.timeout_seconds:
                raise RuntimeError("视频生成超时，请稍后在任务记录中重试。")
            time.sleep(adapter.poll_interval_seconds)

        return VideoGenerationResult(
            external_task_id=submission.external_task_id,
            video_url=polled.video_url,
            output_path=output_path,
            provider=submission.provider,
            final_response=polled.response,
        )

    def _normalize_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return normalize_video_generation_config(config)

    def _sanitize_config(self, config: dict[str, Any]) -> dict[str, Any]:
        api_key = str(config.get("api_key") or "")
        return {
            "provider": config["provider"],
            "base_url": config["base_url"],
            "api_key_configured": bool(api_key),
            "masked_api_key": self._mask_secret(api_key),
        }

    def _provider_defaults(self, provider: str) -> dict[str, Any]:
        return dict(PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["aliyun_dashscope"]))

    def _mask_secret(self, value: str) -> str | None:
        if not value:
            return None
        if len(value) <= 8:
            return "****"
        return f"{value[:4]}****{value[-4:]}"

def normalize_video_generation_config(config: dict[str, Any]) -> dict[str, Any]:
    provider = str(config.get("provider") or DEFAULT_VIDEO_GENERATION_CONFIG["provider"])
    if provider not in PROVIDER_DEFAULTS:
        provider = "aliyun_dashscope"
    normalized = {**DEFAULT_VIDEO_GENERATION_CONFIG, **PROVIDER_DEFAULTS[provider]}
    normalized["provider"] = provider
    normalized["base_url"] = str(config.get("base_url") or normalized["base_url"]).rstrip("/")
    normalized["api_key"] = str(config.get("api_key") or "")
    normalized["api_key_header"] = str(normalized.get("api_key_header") or "Authorization")
    normalized["api_key_prefix"] = str(normalized.get("api_key_prefix") or "")
    normalized["model"] = str(config.get("model") or normalized["model"])
    normalized["submit_path"] = _normalize_path(str(normalized.get("submit_path") or ""))
    normalized["query_path"] = _normalize_path(str(normalized.get("query_path") or ""))
    normalized["poll_interval_seconds"] = max(1, min(120, int(config.get("poll_interval_seconds") or normalized["poll_interval_seconds"])))
    normalized["timeout_seconds"] = max(30, min(7200, int(config.get("timeout_seconds") or normalized["timeout_seconds"])))
    normalized["pending_statuses"] = [str(status) for status in normalized.get("pending_statuses") or ["PENDING", "RUNNING"]]
    return normalized


def _ensure_configured(config: dict[str, Any]) -> None:
    if not str(config.get("base_url") or "").strip():
        raise RuntimeError("视频生成 API 缺少 Base URL。")
    if not str(config.get("api_key") or "").strip():
        raise RuntimeError("视频生成 API 缺少 API Key。")
    if not str(config.get("model") or "").strip():
        raise RuntimeError("视频生成 API 缺少模型名称。")
    for key in ("submit_path", "query_path", "task_id_path", "status_path", "video_url_path"):
        if not str(config.get(key) or "").strip():
            raise RuntimeError(f"视频生成 API 缺少 {key} 配置。")


def _build_submit_body(config: dict[str, Any], image_data_url: str, parameters: dict[str, Any]) -> dict[str, Any]:
    values = {
        "model": config["model"],
        "prompt": _build_prompt(parameters),
        "negative_prompt": str(parameters.get("negative_prompt") or ""),
        "duration": int(parameters.get("duration", 5)),
        "resolution": str(parameters.get("resolution") or "720P"),
    }
    if config["provider"] == "seedance":
        return {
            "model": values["model"],
            "content": [
                {"type": "text", "text": values["prompt"]},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
            "duration": values["duration"],
            "resolution": values["resolution"],
        }
    input_payload: dict[str, Any] = {
        "prompt": values["prompt"],
        "media": [{"type": "first_frame", "url": image_data_url}],
    }
    if values["negative_prompt"]:
        input_payload["negative_prompt"] = values["negative_prompt"]
    return {
        "model": values["model"],
        "input": input_payload,
        "parameters": {
            "resolution": values["resolution"],
            "duration": values["duration"],
            "prompt_extend": False,
        },
    }


def _build_prompt(parameters: dict[str, Any]) -> str:
    prompt = str(parameters.get("prompt") or "").strip()
    action = str(parameters.get("action") or "idle").strip()
    default_prompt = (
        "A clean 2D game character animation, the character performs "
        f"{action}, fixed camera, no camera movement, centered subject, stable size, simple background, smooth loop."
    )
    return prompt or default_prompt


def _request_json(method: str, url: str, config: dict[str, Any], body: dict[str, Any] | None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    for key, value in _build_headers(config).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"视频生成接口请求失败：HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"视频生成接口连接失败：{exc.reason}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("视频生成接口返回内容不是 JSON 对象。")  # noqa: TRY004
    return payload


def _download_video(video_url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(video_url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=120) as response, output_path.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"生成视频下载失败：{exc.reason}") from exc
    if output_path.stat().st_size <= 0:
        raise RuntimeError("生成视频下载后为空文件。")


def _build_headers(config: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = str(config.get("api_key") or "")
    if api_key:
        headers[str(config["api_key_header"])] = f"{config['api_key_prefix']}{api_key}"
    if config["provider"] == "aliyun_dashscope":
        headers["X-DashScope-Async"] = "enable"
    return headers


def _image_to_data_url(image_path: Path) -> str:
    with Image.open(image_path) as image:
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image.convert("RGB"), mask=image.getchannel("A"))
        width, height = background.size
        min_edge = min(width, height)
        max_edge = max(width, height)
        if min_edge < 240:
            scale = 240 / max(1, min_edge)
            background = background.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)
        elif max_edge > 1600:
            scale = 1600 / max_edge
            background = background.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        background.save(buffer, format="JPEG", quality=92)
    return f"data:image/jpeg;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"


def _normalize_path(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    return value if value.startswith("/") else f"/{value}"


def _join_url(base_url: str, path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _read_json_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
    return current
