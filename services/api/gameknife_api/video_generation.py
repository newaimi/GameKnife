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
from typing import Any

from PIL import Image

from gameknife_jobs import GameKnifeRepository

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
        self._ensure_configured(config)
        # 测试配置只检查字段完整性。真实视频 API 通常按调用扣费，
        # 不能因为管理员在设置页测试配置就直接发起外部生成请求。
        return {"ok": True, "message": "视频生成 API 配置字段完整。"}

    def ensure_configured(self) -> None:
        self._ensure_configured(self.read_config(include_secret=True))

    def generate_video(self, image_path: Path, output_path: Path, parameters: dict[str, Any]) -> VideoGenerationResult:
        config = self.read_config(include_secret=True)
        self._ensure_configured(config)

        data_url = self._image_to_data_url(image_path)
        submit_body = self._build_submit_body(config, data_url, parameters)
        submit_response = self._request_json("POST", self._join_url(config["base_url"], config["submit_path"]), config, submit_body)
        external_task_id = str(self._read_json_path(submit_response, str(config["task_id_path"])) or "")
        if not external_task_id:
            raise RuntimeError("视频生成接口没有返回任务 ID。")

        final_response = self._poll_result(config, external_task_id)
        video_url = str(self._read_json_path(final_response, str(config["video_url_path"])) or "")
        if not video_url:
            raise RuntimeError("视频生成成功，但接口没有返回视频地址。")

        self._download_video(video_url, output_path)
        return VideoGenerationResult(
            external_task_id=external_task_id,
            video_url=video_url,
            output_path=output_path,
            provider=str(config["provider"]),
            final_response=final_response,
        )

    def _poll_result(self, config: dict[str, Any], task_id: str) -> dict[str, Any]:
        started = time.monotonic()
        timeout_seconds = int(config["timeout_seconds"])
        poll_interval = int(config["poll_interval_seconds"])
        success_status = str(config["success_status"]).upper()
        failed_status = str(config["failed_status"]).upper()
        pending_statuses = {str(status).upper() for status in config.get("pending_statuses", [])}

        while True:
            query_path = str(config["query_path"]).replace("{task_id}", urllib.parse.quote(task_id))
            payload = self._request_json("GET", self._join_url(config["base_url"], query_path), config, None)
            status = str(self._read_json_path(payload, str(config["status_path"])) or "").upper()
            if status == success_status:
                return payload
            if status == failed_status:
                message = self._read_json_path(payload, "output.message") or self._read_json_path(payload, "message") or "视频生成失败。"
                raise RuntimeError(str(message))
            if status and status not in pending_statuses:
                raise RuntimeError(f"视频生成接口返回未知状态：{status}。")
            if time.monotonic() - started > timeout_seconds:
                raise RuntimeError("视频生成超时，请稍后在任务记录中重试。")
            time.sleep(poll_interval)

    def _build_submit_body(self, config: dict[str, Any], image_data_url: str, parameters: dict[str, Any]) -> dict[str, Any]:
        values = {
            "model": config["model"],
            "prompt": self._build_prompt(parameters),
            "negative_prompt": str(parameters.get("negative_prompt") or ""),
            "image_data_url": image_data_url,
            "duration": int(parameters.get("duration", 5)),
            "resolution": str(parameters.get("resolution") or "720P"),
            "action": str(parameters.get("action") or "idle"),
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
            # 外部视频 API 读取首帧图片。这里传 data URL，避免把本地受保护文件地址暴露给外部服务。
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

    def _build_prompt(self, parameters: dict[str, Any]) -> str:
        prompt = str(parameters.get("prompt") or "").strip()
        action = str(parameters.get("action") or "idle").strip()
        default_prompt = (
            "A clean 2D game character animation, the character performs "
            f"{action}, fixed camera, no camera movement, centered subject, stable size, simple background, smooth loop."
        )
        return prompt or default_prompt

    def _request_json(self, method: str, url: str, config: dict[str, Any], body: dict[str, Any] | None) -> dict[str, Any]:
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method)
        for key, value in self._build_headers(config).items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"视频生成接口请求失败：HTTP {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"视频生成接口连接失败：{exc.reason}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("视频生成接口返回内容不是 JSON 对象。")
        return payload

    def _download_video(self, video_url: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(video_url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=120) as response, output_path.open("wb") as output:  # noqa: S310
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
        except urllib.error.URLError as exc:
            raise RuntimeError(f"生成视频下载失败：{exc.reason}") from exc
        if output_path.stat().st_size <= 0:
            raise RuntimeError("生成视频下载后为空文件。")

    def _build_headers(self, config: dict[str, Any]) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = str(config.get("api_key") or "")
        if api_key:
            headers[str(config["api_key_header"])] = f"{config['api_key_prefix']}{api_key}"
        if config["provider"] == "aliyun_dashscope":
            headers["X-DashScope-Async"] = "enable"
        return headers

    def _image_to_data_url(self, image_path: Path) -> str:
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
                # 外部视频模型会接收 base64 图片。限制最长边可以降低请求体大小，
                # 也减少过大原图导致供应商接口拒绝的概率，游戏序列帧生成不需要原图级像素。
                scale = 1600 / max_edge
                background = background.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            background.save(buffer, format="JPEG", quality=92)
        return f"data:image/jpeg;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"

    def _ensure_configured(self, config: dict[str, Any]) -> None:
        if not str(config.get("base_url") or "").strip():
            raise RuntimeError("视频生成 API 缺少 Base URL。")
        if not str(config.get("api_key") or "").strip():
            raise RuntimeError("视频生成 API 缺少 API Key。")
        if not str(config.get("model") or "").strip():
            raise RuntimeError("视频生成 API 缺少模型名称。")
        for key in ("submit_path", "query_path", "task_id_path", "status_path", "video_url_path"):
            if not str(config.get(key) or "").strip():
                raise RuntimeError(f"视频生成 API 缺少 {key} 配置。")

    def _normalize_config(self, config: dict[str, Any]) -> dict[str, Any]:
        provider = str(config.get("provider") or DEFAULT_VIDEO_GENERATION_CONFIG["provider"])
        if provider not in PROVIDER_DEFAULTS:
            provider = "aliyun_dashscope"

        # 设置页只暴露供应商、Base URL 和密钥。其他字段来自供应商默认值，
        # 这样管理员不用理解各家接口的任务字段，同时避免旧配置残留影响请求格式。
        normalized = {**DEFAULT_VIDEO_GENERATION_CONFIG, **self._provider_defaults(provider)}
        normalized["provider"] = provider
        normalized["base_url"] = str(config.get("base_url") or normalized["base_url"]).rstrip("/")
        normalized["api_key"] = str(config.get("api_key") or "")
        normalized["api_key_header"] = str(normalized.get("api_key_header") or "Authorization")
        normalized["api_key_prefix"] = str(normalized.get("api_key_prefix") or "")
        normalized["model"] = str(normalized.get("model") or DEFAULT_VIDEO_GENERATION_CONFIG["model"])
        normalized["submit_path"] = self._normalize_path(str(normalized.get("submit_path") or ""))
        normalized["query_path"] = self._normalize_path(str(normalized.get("query_path") or ""))
        normalized["poll_interval_seconds"] = max(1, min(120, int(normalized.get("poll_interval_seconds") or 15)))
        normalized["timeout_seconds"] = max(30, min(7200, int(normalized.get("timeout_seconds") or 900)))
        normalized["pending_statuses"] = [str(status) for status in normalized.get("pending_statuses") or ["PENDING", "RUNNING"]]
        return normalized

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

    def _normalize_path(self, value: str) -> str:
        value = value.strip()
        if not value:
            return value
        return value if value.startswith("/") else f"/{value}"

    def _join_url(self, base_url: str, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    def _read_json_path(self, payload: dict[str, Any], path: str) -> Any:
        current: Any = payload
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                current = current[int(part)]
            else:
                return None
        return current
