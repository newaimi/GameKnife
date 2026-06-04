from __future__ import annotations

import shutil
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True, slots=True)
class UpscaleModelSpec:
    key: str
    name: str
    role: str
    filename: str
    url: str
    scale: int = 4


UPSCALE_MODEL_SPECS = [
    UpscaleModelSpec(
        key="general",
        name="RealESRGAN x4plus",
        role="通用、游戏素材、写实图片",
        filename="RealESRGAN_x4plus.pth",
        url="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
    ),
    UpscaleModelSpec(
        key="anime",
        name="RealESRGAN x4plus anime",
        role="动漫插画、线稿、卡通素材",
        filename="RealESRGAN_x4plus_anime_6B.pth",
        url="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
    ),
    UpscaleModelSpec(
        key="noisy",
        name="RealESRGAN general x4v3",
        role="噪点图、压缩图、低清素材",
        filename="realesr-general-x4v3.pth",
        url="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth",
    ),
]


class UpscaleModelService:
    # 模型对象、加载锁和推理锁放在类级别，是为了让同一个 Web 进程只持有一份权重，避免多请求重复加载占满显存。
    _models: dict[str, Any] = {}
    _device: str | None = None
    _load_lock = threading.Lock()
    _infer_lock = threading.Lock()
    _install_lock = threading.Lock()
    _install_status: dict[str, Any] = {
        "status": "idle",
        "progress": 0,
        "message": "尚未手动安装。",
        "error": None,
    }

    def __init__(self, model_root: Path):
        self.model_root = model_root

    @property
    def device_label(self) -> str:
        if self.__class__._device:
            return self.__class__._device.upper()
        try:
            import torch
        except Exception:  # noqa: BLE001
            return "未知"
        return ("cuda" if torch.cuda.is_available() else "cpu").upper()

    @property
    def infer_lock(self) -> threading.Lock:
        return self.__class__._infer_lock

    def install_status(self) -> dict[str, Any]:
        with self._install_lock:
            installed = self.is_installed()
            loaded = self.is_loaded()
            if installed and self.__class__._install_status["status"] in {"idle", "running", "failed"}:
                self.__class__._install_status = {
                    "status": "success",
                    "progress": 100,
                    "message": "图片放大模型文件已安装。" if not loaded else "图片放大模型已安装并加载完成。",
                    "error": None,
                }
            status = dict(self.__class__._install_status)
            status["installed"] = installed
            status["loaded"] = loaded
            return status

    def start_install(self) -> dict[str, Any]:
        with self._install_lock:
            if self.__class__._install_status["status"] == "running":
                return dict(self.__class__._install_status)
            # 下载只能由设置页显式触发；任务执行路径只读本地权重，避免用户提交任务后出现不可控联网行为。
            self.__class__._install_status = {
                "status": "running",
                "progress": 1,
                "message": "准备下载图片放大模型文件。",
                "error": None,
            }
        thread = threading.Thread(target=self._install_worker, name="upscale-model-install", daemon=True)
        thread.start()
        return self.install_status()

    def is_installed(self) -> bool:
        return all(self.model_path(spec.key).is_file() and self.model_path(spec.key).stat().st_size > 0 for spec in UPSCALE_MODEL_SPECS)

    def is_loaded(self) -> bool:
        return all(spec.key in self.__class__._models for spec in UPSCALE_MODEL_SPECS)

    def model_specs(self) -> list[dict[str, str]]:
        return [
            {"key": spec.key, "name": spec.name, "role": spec.role, "filename": spec.filename}
            for spec in UPSCALE_MODEL_SPECS
        ]

    def model_path(self, key: str) -> Path:
        return self.model_root / self._spec_for_key(key).filename

    def upscale_image(
        self,
        image: Image.Image,
        *,
        style: str,
        target_scale: int,
        denoise: int,
        tile_size: int,
    ) -> tuple[Image.Image, str, str, list[str]]:
        if not self.is_installed():
            raise RuntimeError("图片放大模型尚未下载安装，请先到设置页下载安装模型文件。")

        # 这里不再下载模型，只根据已存在的本地权重加载对应风格，保证创建任务时的安装检查和执行阶段行为一致。
        key = self._model_key_for_style(style)
        model = self._model_for_key(key)
        spec = self._spec_for_key(key)
        warnings: list[str] = []
        if target_scale == 8:
            warnings.append("8x 放大会先执行 4x AI 超分，再插值到目标尺寸。")

        rgb, alpha = _split_rgba_for_upscale(image)
        if denoise > 0:
            rgb = _denoise_rgb(rgb, denoise)

        first_pass = self._upscale_rgb_with_model(rgb, model, self.__class__._device or "cpu", spec.scale, tile_size)
        if target_scale == spec.scale:
            rgb_output = first_pass
        else:
            # 现有 Real-ESRGAN 权重都是原生 4x。8x 只跑一次模型再插值，避免 16x 中间图打爆内存。
            rgb_output = first_pass.resize((image.width * target_scale, image.height * target_scale), Image.Resampling.LANCZOS)

        alpha_output = alpha.resize(rgb_output.size, Image.Resampling.LANCZOS)
        output = rgb_output.convert("RGBA")
        output.putalpha(alpha_output)
        return output, spec.name, self.device_label, warnings

    def _install_worker(self) -> None:
        try:
            self.model_root.mkdir(parents=True, exist_ok=True)
            for index, spec in enumerate(UPSCALE_MODEL_SPECS):
                start = int(index / len(UPSCALE_MODEL_SPECS) * 92) + 3
                end = int((index + 1) / len(UPSCALE_MODEL_SPECS) * 92) + 3
                self._download_model(spec, start, end)
            self._set_install_status("success", 100, "图片放大模型文件已安装。")
        except Exception as exc:  # noqa: BLE001
            self._set_install_status("failed", 100, "图片放大模型安装失败。", str(exc))

    def _download_model(self, spec: UpscaleModelSpec, start_progress: int, end_progress: int) -> None:
        destination = self.model_path(spec.key)
        if destination.is_file() and destination.stat().st_size > 0:
            self._set_install_status("running", end_progress, f"{spec.name} 已存在。")
            return

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        self._set_install_status("running", start_progress, f"正在下载 {spec.name}。")
        try:
            with urllib.request.urlopen(spec.url, timeout=60) as response, temporary.open("wb") as output:  # noqa: S310
                total = int(response.headers.get("Content-Length") or 0)
                downloaded = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        ratio = min(1.0, downloaded / total)
                        progress = start_progress + int((end_progress - start_progress) * ratio)
                        self._set_install_status("running", progress, f"正在下载 {spec.name}。")
            shutil.move(str(temporary), destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _model_for_key(self, key: str) -> Any:
        if not self.model_path(key).is_file():
            raise RuntimeError("图片放大模型尚未下载安装，请先到设置页下载安装模型文件。")
        with self._load_lock:
            if key in self.__class__._models:
                return self.__class__._models[key]
            try:
                import torch
                from spandrel import ModelLoader
            except ImportError as exc:
                raise RuntimeError("缺少图片放大依赖，请安装 torch 和 spandrel。") from exc

            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = ModelLoader().load_from_file(str(self.model_path(key)))
            # 使用 spandrel 统一加载权重，避免旧 Real-ESRGAN 包和 torchvision 版本绑定影响 Web 进程。
            self.__class__._models[key] = model.eval().float().to(device)
            self.__class__._device = device
            return self.__class__._models[key]

    def _upscale_rgb_with_model(self, image: Image.Image, model: Any, device: str, native_scale: int, tile_size: int) -> Image.Image:
        if image.width <= tile_size and image.height <= tile_size:
            return self._run_model_tile(image, model, device, native_scale)

        tile_pad = 16
        output = np.zeros((image.height * native_scale, image.width * native_scale, 3), dtype=np.uint8)
        for top in range(0, image.height, tile_size):
            for left in range(0, image.width, tile_size):
                right = min(image.width, left + tile_size)
                bottom = min(image.height, top + tile_size)
                padded_left = max(0, left - tile_pad)
                padded_top = max(0, top - tile_pad)
                padded_right = min(image.width, right + tile_pad)
                padded_bottom = min(image.height, bottom + tile_pad)
                tile = image.crop((padded_left, padded_top, padded_right, padded_bottom))
                upscaled_tile = self._run_model_tile(tile, model, device, native_scale)
                crop_left = (left - padded_left) * native_scale
                crop_top = (top - padded_top) * native_scale
                crop_right = crop_left + (right - left) * native_scale
                crop_bottom = crop_top + (bottom - top) * native_scale
                cropped = upscaled_tile.crop((crop_left, crop_top, crop_right, crop_bottom))
                output[top * native_scale : bottom * native_scale, left * native_scale : right * native_scale] = np.asarray(cropped)
        return Image.fromarray(output, mode="RGB")

    def _run_model_tile(self, tile: Image.Image, model: Any, device: str, native_scale: int) -> Image.Image:
        import torch

        array = np.asarray(tile.convert("RGB")).astype(np.float32) / 255.0
        tensor = torch.from_numpy(array).permute(2, 0, 1).unsqueeze(0).to(device)
        # Real-ESRGAN 对显存峰值敏感，进程内串行能避免两个 tile 同时推理导致显存抖动。
        with self.infer_lock:
            with torch.inference_mode():
                output = model(tensor)
        if isinstance(output, (list, tuple)):
            output = output[0]
        output = output.detach().float().clamp(0, 1).squeeze(0).permute(1, 2, 0).cpu().numpy()
        output_array = np.clip(output * 255.0, 0, 255).astype(np.uint8)
        result = Image.fromarray(output_array, mode="RGB")
        expected_size = (tile.width * native_scale, tile.height * native_scale)
        if result.size != expected_size:
            result = result.resize(expected_size, Image.Resampling.LANCZOS)
        return result

    def _set_install_status(self, status: str, progress: int, message: str, error: str | None = None) -> None:
        with self._install_lock:
            self.__class__._install_status = {
                "status": status,
                "progress": max(0, min(100, int(progress))),
                "message": message,
                "error": error,
            }

    def _model_key_for_style(self, style: str) -> str:
        if style == "anime":
            return "anime"
        if style == "noisy":
            return "noisy"
        return "general"

    def _spec_for_key(self, key: str) -> UpscaleModelSpec:
        for spec in UPSCALE_MODEL_SPECS:
            if spec.key == key:
                return spec
        raise RuntimeError(f"未知图片放大模型：{key}")


def _split_rgba_for_upscale(image: Image.Image) -> tuple[Image.Image, Image.Image]:
    array = np.asarray(image.convert("RGBA"))
    rgb = array[:, :, :3].copy()
    alpha = array[:, :, 3]
    if 0 < int(np.count_nonzero(alpha > 0)) < alpha.size and int(np.count_nonzero(alpha == 0)) > 0:
        mask = np.where(alpha == 0, 255, 0).astype(np.uint8)
        # 透明区不会显示，但模型卷积会读到透明像素里的 RGB。先补邻近色，减少放大后的白边或黑边。
        rgb = cv2.cvtColor(cv2.inpaint(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), mask, 3, cv2.INPAINT_TELEA), cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb, mode="RGB"), Image.fromarray(alpha, mode="L")


def _denoise_rgb(image: Image.Image, level: int) -> Image.Image:
    array = np.asarray(image.convert("RGB"))
    strength = 3 + level * 3
    denoised = cv2.fastNlMeansDenoisingColored(cv2.cvtColor(array, cv2.COLOR_RGB2BGR), None, strength, strength, 7, 21)
    return Image.fromarray(cv2.cvtColor(denoised, cv2.COLOR_BGR2RGB), mode="RGB")
