from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

AlphaProvider = Callable[[Image.Image], np.ndarray]

BIREFNET_MODEL_ID = "ZhengPeng7/BiRefNet"
BIREFNET_MODEL_REVISION = "e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4"


class BiRefNetService:
    _model: Any = None
    _transform_image: Any = None
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

    def __init__(
        self,
        *,
        model_input_size: int = 1024,
        alpha_provider: AlphaProvider | None = None,
        model_cache_dir: Path | None = None,
    ) -> None:
        self.model_input_size = model_input_size
        self._alpha_provider = alpha_provider
        self.model_cache_dir = model_cache_dir

    @property
    def device_label(self) -> str:
        if self._alpha_provider is not None:
            return "CPU"
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
            loaded = self.is_loaded()
            installed = self.is_installed()
            if installed and self.__class__._install_status["status"] in {"idle", "running", "failed"}:
                self.__class__._install_status = {
                    "status": "success",
                    "progress": 100,
                    "message": "BiRefNet 模型文件已安装。" if not loaded else "BiRefNet 已安装并加载完成。",
                    "error": None,
                }
            status = dict(self.__class__._install_status)
            status["installed"] = installed
            status["loaded"] = loaded
            return status

    def is_installed(self) -> bool:
        if self._alpha_provider is not None:
            return True
        if self.is_loaded():
            return True
        try:
            from huggingface_hub import try_to_load_from_cache
        except Exception:  # noqa: BLE001
            return False
        required = ["config.json", "birefnet.py", "BiRefNet_config.py"]
        weights = ["model.safetensors", "pytorch_model.bin"]
        def cached_file_exists(filename: str) -> bool:
            cached = try_to_load_from_cache(BIREFNET_MODEL_ID, filename, revision=BIREFNET_MODEL_REVISION, cache_dir=self.model_cache_dir)
            return isinstance(cached, str) and Path(cached).is_file()

        has_required = all(cached_file_exists(filename) for filename in required)
        has_weight = any(cached_file_exists(filename) for filename in weights)
        return bool(has_required and has_weight)

    def is_loaded(self) -> bool:
        if self._alpha_provider is not None:
            return True
        return self.__class__._model is not None and self.__class__._transform_image is not None and self.__class__._device is not None

    def start_install(self) -> dict[str, Any]:
        with self._install_lock:
            if self.__class__._install_status["status"] == "running":
                return dict(self.__class__._install_status)
            self.__class__._install_status = {
                "status": "running",
                "progress": 1,
                "message": "准备安装 BiRefNet。",
                "error": None,
            }

        thread = threading.Thread(target=self._install_worker, name="birefnet-install", daemon=True)
        thread.start()
        return self.install_status()

    def predict_alpha(self, image: Image.Image) -> np.ndarray:
        if self._alpha_provider is not None:
            return self._normalize_alpha(self._alpha_provider(image), image.size)

        if not self.is_installed():
            # Inference forbids implicit downloads because large background transfers make jobs appear stalled.
            # A job can load from the local cache only after Settings completes an explicit installation.
            raise RuntimeError("BiRefNet 模型尚未下载安装，请先到设置页下载安装模型文件。")
        if not self.is_loaded():
            self._ensure_model_loaded(status_updates=False, local_files_only=True)
        model = self.__class__._model
        transform_image = self.__class__._transform_image
        device = self.__class__._device
        if model is None or transform_image is None or device is None:
            raise RuntimeError("BiRefNet 初始化失败，请重启服务后重试。")

        import torch
        from torchvision import transforms

        input_image = transform_image(image.convert("RGB")).unsqueeze(0).float().to(device)
        with self.infer_lock:
            with torch.no_grad():
                prediction = model(input_image)[-1].sigmoid().cpu()[0].squeeze()
        alpha_image = transforms.ToPILImage()(prediction).resize(image.size, Image.Resampling.LANCZOS)
        return np.asarray(alpha_image).astype(np.uint8)

    def _install_worker(self) -> None:
        try:
            self._set_install_status("running", 5, "检查 BiRefNet 依赖。")
            self._ensure_model_loaded(status_updates=True, local_files_only=False)
            self._set_install_status("success", 100, "BiRefNet 已安装并加载完成。")
        except Exception as exc:  # noqa: BLE001
            self._set_install_status("failed", 100, "BiRefNet 安装失败。", str(exc))

    def _ensure_model_loaded(self, *, status_updates: bool, local_files_only: bool) -> None:
        try:
            import torch
            from torchvision import transforms
            from transformers import AutoModelForImageSegmentation
        except ImportError as exc:
            raise RuntimeError("缺少 BiRefNet 依赖，请先安装 torch、torchvision、transformers、einops、kornia、timm 和 huggingface_hub。") from exc

        with self._load_lock:
            if self.__class__._model is not None:
                if status_updates:
                    self._set_install_status("running", 95, "模型已经在内存中，正在确认状态。")
                return

            device = "cuda" if torch.cuda.is_available() else "cpu"
            if status_updates:
                self._set_install_status("running", 15, f"开始下载并加载 {BIREFNET_MODEL_ID}。")
            transform_image = transforms.Compose(
                [
                    transforms.Resize((self.model_input_size, self.model_input_size)),
                    transforms.ToTensor(),
                    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
                ]
            )
            model = AutoModelForImageSegmentation.from_pretrained(
                BIREFNET_MODEL_ID,
                trust_remote_code=True,
                local_files_only=local_files_only,
                revision=BIREFNET_MODEL_REVISION,
                cache_dir=self.model_cache_dir,
            )
            if status_updates:
                self._set_install_status("running", 85, f"模型文件已就绪，正在迁移到 {device.upper()}。")
            self.__class__._model = model.eval().float().to(device)
            self.__class__._transform_image = transform_image
            self.__class__._device = device

    def _set_install_status(self, status: str, progress: int, message: str, error: str | None = None) -> None:
        with self._install_lock:
            self.__class__._install_status = {
                "status": status,
                "progress": max(0, min(100, int(progress))),
                "message": message,
                "error": error,
            }

    def _normalize_alpha(self, alpha: np.ndarray, image_size: tuple[int, int]) -> np.ndarray:
        alpha_array = np.asarray(alpha)
        if alpha_array.ndim == 3:
            alpha_array = alpha_array[:, :, 0]
        if alpha_array.shape[:2] != (image_size[1], image_size[0]):
            alpha_image = Image.fromarray(np.clip(alpha_array, 0, 255).astype(np.uint8), mode="L")
            alpha_array = np.asarray(alpha_image.resize(image_size, Image.Resampling.LANCZOS))
        return np.clip(alpha_array, 0, 255).astype(np.uint8)
