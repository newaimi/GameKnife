from __future__ import annotations

import inspect
import os
import threading
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from gameknife_api.huggingface_utils import huggingface_model_io, model_files_cached
from gameknife_processors.character_part_catalog import OPTIONAL_PART_KEYS, normalize_part_key, part_keys_from_text, read_part_spec
from gameknife_processors.character_rig import CharacterRigDetection, CharacterRigHints

REQUIRED_TRANSFORMERS_VERSION = "4.57.3"
DEFAULT_FLORENCE_MODEL_ID = "microsoft/Florence-2-large"
DEFAULT_GROUNDING_DINO_MODEL_ID = "IDEA-Research/grounding-dino-base"
DEFAULT_SAM_MODEL_ID = "facebook/sam2.1-hiera-large"
FLORENCE_MODEL_ID = os.getenv("GAMEKNIFE_FLORENCE_MODEL_ID", DEFAULT_FLORENCE_MODEL_ID)
GROUNDING_DINO_MODEL_ID = os.getenv("GAMEKNIFE_GROUNDING_DINO_MODEL_ID", DEFAULT_GROUNDING_DINO_MODEL_ID)
SAM_MODEL_ID = os.getenv("GAMEKNIFE_SAM_MODEL_ID", DEFAULT_SAM_MODEL_ID)


def _resolve_model_revision(env_name: str, model_id: str, default_model_id: str, default_revision: str) -> str:
    configured = os.getenv(env_name)
    if configured:
        return configured
    if model_id == default_model_id:
        return default_revision
    return "main"


# 默认 revision 固定到旧工程已验证的快照。模型仓库 main 更新很容易破坏 processor 或后处理接口。
FLORENCE_MODEL_REVISION = _resolve_model_revision(
    "GAMEKNIFE_FLORENCE_MODEL_REVISION",
    FLORENCE_MODEL_ID,
    DEFAULT_FLORENCE_MODEL_ID,
    "21a599d414c4d928c9032694c424fb94458e3594",
)
GROUNDING_DINO_MODEL_REVISION = _resolve_model_revision(
    "GAMEKNIFE_GROUNDING_DINO_MODEL_REVISION",
    GROUNDING_DINO_MODEL_ID,
    DEFAULT_GROUNDING_DINO_MODEL_ID,
    "12bdfa3120f3e7ec7b434d90674b3396eccf88eb",
)
SAM_MODEL_REVISION = _resolve_model_revision(
    "GAMEKNIFE_SAM_MODEL_REVISION",
    SAM_MODEL_ID,
    DEFAULT_SAM_MODEL_ID,
    "665f8e2ad61cf5f53d65644ff27c8ee525124610",
)
FLORENCE_ATTN_IMPLEMENTATION = "eager"
FLORENCE_REMOTE_CODE_FILES = [
    "configuration_florence2.py",
    "modeling_florence2.py",
    "processing_florence2.py",
]
FLORENCE_MODEL_FILES = [
    "config.json",
    "preprocessor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    *FLORENCE_REMOTE_CODE_FILES,
]
GROUNDING_DINO_MODEL_FILES = ["config.json", "preprocessor_config.json", "tokenizer.json", "tokenizer_config.json"]
SAM_MODEL_FILES = ["config.json", "preprocessor_config.json", "processor_config.json"]
WEIGHT_FILES = ["model.safetensors", "pytorch_model.bin"]

CHARACTER_RIG_MODEL_SPECS = [
    {
        "key": "florence",
        "name": "Florence-2",
        "role": "生成素材描述和候选部件词",
        "model_id": FLORENCE_MODEL_ID,
    },
    {
        "key": "grounding_dino",
        "name": "Grounding DINO",
        "role": "根据部件词检测候选框",
        "model_id": GROUNDING_DINO_MODEL_ID,
    },
    {
        "key": "sam",
        "name": "SAM 2",
        "role": "精修部件 mask 边缘",
        "model_id": SAM_MODEL_ID,
    },
]


class CharacterRigModelService:
    _florence_processor: Any = None
    _florence_model: Any = None
    _grounding_processor: Any = None
    _grounding_model: Any = None
    _sam_processor: Any = None
    _sam_model: Any = None
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

    def __init__(self, *, model_cache_dir: Path | None = None) -> None:
        self.model_cache_dir = model_cache_dir

    @property
    def device_label(self) -> str:
        if self.__class__._device:
            return self.__class__._device.upper()
        try:
            import torch
        except Exception:  # noqa: BLE001
            return "未知"
        return self._resolve_device(torch).upper()

    def model_specs(self) -> list[dict[str, str]]:
        return [dict(spec) for spec in CHARACTER_RIG_MODEL_SPECS]

    def install_status(self) -> dict[str, Any]:
        with self._install_lock:
            loaded = self._all_models_loaded()
            installed = self.is_installed()
            if installed and self.__class__._install_status["status"] in {"idle", "running", "failed"}:
                self.__class__._install_status = {
                    "status": "success",
                    "progress": 100,
                    "message": "骨骼拆分模型文件已安装。" if not loaded else "骨骼拆分真实模型已安装并加载完成。",
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
            # 只有设置页会调用安装入口。任务执行阶段只允许 local_files_only=True 的缓存加载。
            self.__class__._install_status = {
                "status": "running",
                "progress": 1,
                "message": "准备安装骨骼拆分真实模型。",
                "error": None,
            }

        thread = threading.Thread(target=self._install_worker, name="character-rig-model-install", daemon=True)
        thread.start()
        return self.install_status()

    def is_installed(self) -> bool:
        return self.florence_installed() and self.grounding_dino_installed() and self.sam_installed()

    def florence_installed(self) -> bool:
        if self.florence_ready():
            return True
        return model_files_cached(
            FLORENCE_MODEL_ID,
            FLORENCE_MODEL_FILES,
            WEIGHT_FILES,
            revision=FLORENCE_MODEL_REVISION,
            cache_dir=self.model_cache_dir,
        )

    def grounding_dino_installed(self) -> bool:
        if self.grounding_dino_ready():
            return True
        return model_files_cached(
            GROUNDING_DINO_MODEL_ID,
            GROUNDING_DINO_MODEL_FILES,
            WEIGHT_FILES,
            revision=GROUNDING_DINO_MODEL_REVISION,
            cache_dir=self.model_cache_dir,
        )

    def sam_installed(self) -> bool:
        if self.sam_ready():
            return True
        return model_files_cached(SAM_MODEL_ID, SAM_MODEL_FILES, WEIGHT_FILES, revision=SAM_MODEL_REVISION, cache_dir=self.model_cache_dir)

    def florence_ready(self) -> bool:
        return self.__class__._florence_processor is not None and self.__class__._florence_model is not None

    def grounding_dino_ready(self) -> bool:
        return self.__class__._grounding_processor is not None and self.__class__._grounding_model is not None

    def sam_ready(self) -> bool:
        return self.__class__._sam_processor is not None and self.__class__._sam_model is not None

    def describe_parts(self, image: Image.Image, parameters: dict[str, Any]) -> CharacterRigHints:
        if not self.florence_ready() and not self.florence_installed():
            raise RuntimeError("Florence-2 模型尚未安装，请先在设置页安装骨骼拆分真实模型。")
        try:
            description = self._describe_with_florence(image)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Florence-2 模型执行失败：{exc}") from exc
        # Florence 只补充候选词，最终部件仍要经过固定词表、检测框和 mask 精修，避免描述文本直接污染结果。
        candidate_keys = [key for key in part_keys_from_text(description) if key in OPTIONAL_PART_KEYS]
        return CharacterRigHints(description=description, candidate_keys=candidate_keys)

    def detect_parts(self, image: Image.Image, candidate_keys: list[str], parameters: dict[str, Any]) -> list[CharacterRigDetection]:
        if not candidate_keys:
            return []
        if not self.grounding_dino_ready() and not self.grounding_dino_installed():
            raise RuntimeError("Grounding DINO 模型尚未安装，请先在设置页安装骨骼拆分真实模型。")
        try:
            return self._detect_with_grounding_dino(image, candidate_keys, parameters)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Grounding DINO 模型执行失败：{exc}") from exc

    def refine_bbox(self, image: Image.Image, bbox: list[int], alpha: np.ndarray, parameters: dict[str, Any]) -> np.ndarray:
        if not self.sam_ready() and not self.sam_installed():
            raise RuntimeError("SAM 2 模型尚未安装，请先在设置页安装骨骼拆分真实模型。")
        try:
            base_mask = _bbox_mask(image.size, bbox)
            refined = self._refine_with_sam(image, base_mask)
            threshold = int(parameters.get("alpha_threshold", 24))
            return np.where(alpha >= threshold, refined, 0).astype(np.uint8)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"SAM 2 模型执行失败：{exc}") from exc

    def model_report(self) -> dict[str, str]:
        return {
            "florence": FLORENCE_MODEL_ID if self.florence_ready() else "not-loaded",
            "grounding_dino": GROUNDING_DINO_MODEL_ID if self.grounding_dino_ready() else "not-loaded",
            "sam": SAM_MODEL_ID if self.sam_ready() else "not-loaded",
        }

    def _install_worker(self) -> None:
        try:
            self._set_install_status("running", 5, "检查 PyTorch 和 Transformers 依赖。")
            self._ensure_florence_loaded(status_updates=True, local_files_only=False)
            self._ensure_grounding_dino_loaded(status_updates=True, local_files_only=False)
            self._ensure_sam_loaded(status_updates=True, local_files_only=False)
            self._set_install_status("success", 100, "骨骼拆分真实模型已安装并加载完成。")
        except Exception as exc:  # noqa: BLE001
            self._set_install_status("failed", 100, "骨骼拆分真实模型安装失败。", str(exc))

    def _describe_with_florence(self, image: Image.Image) -> str:
        import torch

        task_prompt = "<MORE_DETAILED_CAPTION>"
        processor, model, device = self._florence_components()
        inputs = processor(text=task_prompt, images=image.convert("RGB"), return_tensors="pt")
        if hasattr(inputs, "to"):
            inputs = inputs.to(device)
        with self._infer_lock:
            with torch.no_grad():
                generated_ids = model.generate(
                    input_ids=inputs["input_ids"],
                    pixel_values=inputs["pixel_values"],
                    max_new_tokens=96,
                    num_beams=3,
                    do_sample=False,
                    # Florence 生成缓存在部分 Transformers 版本下会收到 None，关闭缓存能避免安装成功后任务失败。
                    use_cache=False,
                )
        generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        parsed = processor.post_process_generation(generated_text, task=task_prompt, image_size=(image.width, image.height))
        description = parsed.get(task_prompt) if isinstance(parsed, dict) else None
        return str(description or generated_text).strip()

    def _detect_with_grounding_dino(self, image: Image.Image, candidate_keys: list[str], parameters: dict[str, Any]) -> list[CharacterRigDetection]:
        import torch

        labels = [read_part_spec(key).prompt for key in candidate_keys]
        text_prompt = ". ".join(labels) + "."
        box_threshold = float(parameters.get("box_threshold", 0.25))
        text_threshold = float(parameters.get("text_threshold", 0.25))
        processor, model, device = self._grounding_dino_components()
        inputs = processor(images=image.convert("RGB"), text=text_prompt, return_tensors="pt")
        if hasattr(inputs, "to"):
            inputs = inputs.to(device)
        with self._infer_lock:
            with torch.no_grad():
                outputs = model(**inputs)
        results = processor.post_process_grounded_object_detection(
            outputs,
            inputs.get("input_ids"),
            threshold=box_threshold,
            text_threshold=text_threshold,
            target_sizes=[(image.height, image.width)],
        )
        if not results:
            return []
        boxes = results[0].get("boxes", [])
        scores = results[0].get("scores", [])
        labels = results[0].get("labels", [])
        detections: list[CharacterRigDetection] = []
        for box, score, label in zip(boxes, scores, labels, strict=False):
            key = normalize_part_key(str(label))
            if key is None:
                continue
            values = box.detach().cpu().tolist() if hasattr(box, "detach") else list(box)
            left, top, right, bottom = [float(value) for value in values]
            bbox = _clip_xyxy(left, top, right, bottom, image.width, image.height)
            if bbox[2] <= 0 or bbox[3] <= 0:
                continue
            detections.append(CharacterRigDetection(key=key, label=str(label), bbox=bbox, score=float(score)))
        return detections

    def _refine_with_sam(self, image: Image.Image, base_mask: np.ndarray) -> np.ndarray:
        import torch

        ys, xs = np.where(base_mask > 0)
        if len(xs) == 0 or len(ys) == 0:
            return base_mask.astype(np.uint8)
        left, top, right, bottom = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        center_x = float(xs.mean())
        center_y = float(ys.mean())
        processor, model, device = self._sam_components()
        inputs = processor(
            images=image.convert("RGB"),
            input_boxes=[[[float(left), float(top), float(right), float(bottom)]]],
            input_points=[[[[center_x, center_y]]]],
            input_labels=[[[1]]],
            return_tensors="pt",
        )
        if hasattr(inputs, "to"):
            inputs = inputs.to(device)
        with self._infer_lock:
            with torch.no_grad():
                outputs = model(**inputs, multimask_output=True)

        processed_masks = _post_process_sam_masks(processor, outputs.pred_masks, inputs)
        mask_tensor = processed_masks[0]
        if mask_tensor.ndim == 4:
            mask_tensor = mask_tensor[0]
        if mask_tensor.ndim == 3:
            scores = getattr(outputs, "iou_scores", None)
            if scores is not None:
                score_array = scores.detach().cpu().reshape(-1).numpy()
                mask_tensor = mask_tensor[int(score_array.argmax())]
            else:
                mask_tensor = mask_tensor[0]
        mask = mask_tensor.numpy()
        # SAM 的提示框可能带到相邻部件。裁剪回原始 bbox，保持“精修当前候选”的业务边界。
        clipped = np.zeros_like(base_mask, dtype=np.uint8)
        clipped[top:bottom, left:right] = np.where(mask[top:bottom, left:right] > 0, 255, 0).astype(np.uint8)
        return clipped

    def _florence_components(self) -> tuple[Any, Any, str]:
        if not self.florence_ready():
            if not self.florence_installed():
                raise RuntimeError("Florence-2 模型尚未安装，请先在设置页安装骨骼拆分真实模型。")
            self._ensure_florence_loaded(status_updates=False, local_files_only=True)
        return self.__class__._florence_processor, self.__class__._florence_model, self.__class__._device or "cpu"

    def _grounding_dino_components(self) -> tuple[Any, Any, str]:
        if not self.grounding_dino_ready():
            if not self.grounding_dino_installed():
                raise RuntimeError("Grounding DINO 模型尚未安装，请先在设置页安装骨骼拆分真实模型。")
            self._ensure_grounding_dino_loaded(status_updates=False, local_files_only=True)
        return self.__class__._grounding_processor, self.__class__._grounding_model, self.__class__._device or "cpu"

    def _sam_components(self) -> tuple[Any, Any, str]:
        if not self.sam_ready():
            if not self.sam_installed():
                raise RuntimeError("SAM 2 模型尚未安装，请先在设置页安装骨骼拆分真实模型。")
            self._ensure_sam_loaded(status_updates=False, local_files_only=True)
        return self.__class__._sam_processor, self.__class__._sam_model, self.__class__._device or "cpu"

    def _ensure_florence_loaded(self, *, status_updates: bool, local_files_only: bool) -> None:
        try:
            import torch
            import transformers
            from transformers import AutoModelForCausalLM, AutoProcessor
        except ImportError as exc:
            raise RuntimeError("缺少 Florence-2 依赖，请先安装支持 AutoProcessor 的 transformers。") from exc

        _ensure_transformers_version(transformers.__version__)
        with self._load_lock:
            device = self._ensure_device(torch)
            if self.__class__._florence_model is not None:
                if status_updates:
                    self._set_install_status("running", 30, "Florence-2 模型已经在内存中。")
                return
            if status_updates:
                self._set_install_status("running", 12, f"开始下载并加载 {FLORENCE_MODEL_ID}。")
            with huggingface_model_io(local_files_only):
                _refresh_florence_remote_code_cache(local_files_only, self.model_cache_dir)
                processor = AutoProcessor.from_pretrained(
                    FLORENCE_MODEL_ID,
                    trust_remote_code=True,
                    local_files_only=local_files_only,
                    revision=FLORENCE_MODEL_REVISION,
                    cache_dir=self.model_cache_dir,
                )
                model = AutoModelForCausalLM.from_pretrained(
                    FLORENCE_MODEL_ID,
                    trust_remote_code=True,
                    local_files_only=local_files_only,
                    revision=FLORENCE_MODEL_REVISION,
                    attn_implementation=FLORENCE_ATTN_IMPLEMENTATION,
                    cache_dir=self.model_cache_dir,
                )
            self.__class__._florence_processor = processor
            self.__class__._florence_model = model.eval().float().to(device)
            if status_updates:
                self._set_install_status("running", 35, "Florence-2 模型已就绪。")

    def _ensure_grounding_dino_loaded(self, *, status_updates: bool, local_files_only: bool) -> None:
        try:
            import torch
            import transformers
            from transformers import GroundingDinoForObjectDetection, GroundingDinoProcessor
        except ImportError as exc:
            raise RuntimeError("缺少 Grounding DINO 依赖，请先安装支持 GroundingDino 的 transformers。") from exc

        _ensure_transformers_version(transformers.__version__)
        with self._load_lock:
            device = self._ensure_device(torch)
            if self.__class__._grounding_model is not None:
                if status_updates:
                    self._set_install_status("running", 62, "Grounding DINO 模型已经在内存中。")
                return
            if status_updates:
                self._set_install_status("running", 42, f"开始下载并加载 {GROUNDING_DINO_MODEL_ID}。")
            with huggingface_model_io(local_files_only):
                processor = GroundingDinoProcessor.from_pretrained(
                    GROUNDING_DINO_MODEL_ID,
                    local_files_only=local_files_only,
                    revision=GROUNDING_DINO_MODEL_REVISION,
                    cache_dir=self.model_cache_dir,
                )
                model = GroundingDinoForObjectDetection.from_pretrained(
                    GROUNDING_DINO_MODEL_ID,
                    local_files_only=local_files_only,
                    revision=GROUNDING_DINO_MODEL_REVISION,
                    cache_dir=self.model_cache_dir,
                )
            self.__class__._grounding_processor = processor
            self.__class__._grounding_model = model.eval().float().to(device)
            if status_updates:
                self._set_install_status("running", 68, "Grounding DINO 模型已就绪。")

    def _ensure_sam_loaded(self, *, status_updates: bool, local_files_only: bool) -> None:
        try:
            import torch
            import transformers
            from transformers import Sam2Model, Sam2Processor
        except ImportError as exc:
            raise RuntimeError("缺少 SAM 2 依赖，请先安装支持 Sam2Model 的 transformers。") from exc

        _ensure_transformers_version(transformers.__version__)
        with self._load_lock:
            device = self._ensure_device(torch)
            if self.__class__._sam_model is not None:
                if status_updates:
                    self._set_install_status("running", 90, "SAM 2 模型已经在内存中。")
                return
            if status_updates:
                self._set_install_status("running", 76, f"开始下载并加载 {SAM_MODEL_ID}。")
            with huggingface_model_io(local_files_only):
                processor = Sam2Processor.from_pretrained(
                    SAM_MODEL_ID,
                    local_files_only=local_files_only,
                    revision=SAM_MODEL_REVISION,
                    cache_dir=self.model_cache_dir,
                )
                model = Sam2Model.from_pretrained(
                    SAM_MODEL_ID,
                    local_files_only=local_files_only,
                    revision=SAM_MODEL_REVISION,
                    cache_dir=self.model_cache_dir,
                )
            self.__class__._sam_processor = processor
            self.__class__._sam_model = model.eval().float().to(device)
            if status_updates:
                self._set_install_status("running", 94, "SAM 2 模型已就绪。")

    def _set_install_status(self, status: str, progress: int, message: str, error: str | None = None) -> None:
        with self._install_lock:
            self.__class__._install_status = {
                "status": status,
                "progress": max(0, min(100, int(progress))),
                "message": message,
                "error": error,
            }

    def _all_models_loaded(self) -> bool:
        return self.florence_ready() and self.grounding_dino_ready() and self.sam_ready()

    def _ensure_device(self, torch: Any) -> str:
        device = self._resolve_device(torch)
        self.__class__._device = device
        return device

    def _resolve_device(self, torch: Any) -> str:
        if torch.cuda.is_available():
            return "cuda"
        # 质量优先模型在 MPS 上容易受算子覆盖影响，CPU 慢但行为更可预测。
        return "cpu"


def _bbox_mask(image_size: tuple[int, int], bbox: list[int]) -> np.ndarray:
    image_width, image_height = image_size
    x, y, width, height = [int(value) for value in bbox]
    base_mask = np.zeros((image_height, image_width), dtype=np.uint8)
    left = max(0, x)
    top = max(0, y)
    right = min(image_width, x + width)
    bottom = min(image_height, y + height)
    if right > left and bottom > top:
        base_mask[top:bottom, left:right] = 255
    return base_mask


def _clip_xyxy(left: float, top: float, right: float, bottom: float, width: int, height: int) -> list[int]:
    x1 = max(0, min(width, round(left)))
    y1 = max(0, min(height, round(top)))
    x2 = max(0, min(width, round(right)))
    y2 = max(0, min(height, round(bottom)))
    return [x1, y1, max(0, x2 - x1), max(0, y2 - y1)]


def _post_process_sam_masks(processor: Any, masks: Any, inputs: Any) -> list[Any]:
    mask_tensor = masks.detach().cpu()
    original_sizes = inputs["original_sizes"].detach().cpu()
    signature = inspect.signature(processor.post_process_masks)
    # Transformers 的 SAM 2 后处理接口存在版本差异，按运行时签名适配，避免把接口变化误报为模型损坏。
    if "reshaped_input_sizes" in signature.parameters and "reshaped_input_sizes" in inputs:
        return processor.post_process_masks(mask_tensor, original_sizes, inputs["reshaped_input_sizes"].detach().cpu())
    return processor.post_process_masks(mask_tensor, original_sizes)


def _refresh_florence_remote_code_cache(local_files_only: bool, cache_dir: Path | None) -> None:
    if local_files_only:
        return
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("缺少 Hugging Face 依赖，请先安装 huggingface_hub。") from exc
    # 只刷新 Florence-2 远程代码，不强制重下权重。旧缓存缺少新版 Transformers 需要的属性时会导致加载失败。
    snapshot_download(
        FLORENCE_MODEL_ID,
        revision=FLORENCE_MODEL_REVISION,
        allow_patterns=FLORENCE_REMOTE_CODE_FILES,
        force_download=True,
        cache_dir=cache_dir,
    )


def _ensure_transformers_version(version: str) -> None:
    # 三个模型共享同一个 Transformers 包，固定到已验证版本可以避免安装页成功、任务页失败的组合问题。
    if version == REQUIRED_TRANSFORMERS_VERSION:
        return
    raise RuntimeError(
        f"当前 transformers 版本 {version}，骨骼拆分链路只验证过 {REQUIRED_TRANSFORMERS_VERSION}，"
        '请在 Community API 环境执行 pip install -e ".[dev]" 重新安装项目依赖。'
    )
