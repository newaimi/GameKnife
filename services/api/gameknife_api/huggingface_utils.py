from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


_MODEL_IO_LOCK = threading.RLock()


def model_files_cached(
    model_id: str,
    required_files: list[str],
    weight_files: list[str],
    *,
    revision: str | None = None,
) -> bool:
    # 设置页只检查本地缓存，不加载权重；这样状态刷新不会把模型意外拉进内存。
    if not all(_cached_file_exists(model_id, filename, revision=revision) for filename in required_files):
        return False
    return any(_cached_file_exists(model_id, filename, revision=revision) for filename in weight_files)


def _cached_file_exists(model_id: str, filename: str, *, revision: str | None = None) -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache
    except Exception:  # noqa: BLE001
        return False
    cached = try_to_load_from_cache(model_id, filename, revision=revision)
    return isinstance(cached, str) and Path(cached).is_file()


@contextmanager
def huggingface_model_io(local_files_only: bool) -> Iterator[None]:
    # Hugging Face 的离线开关是进程级状态，必须串行修改，避免一个任务切离线时影响另一个模型安装。
    with _MODEL_IO_LOCK:
        if not local_files_only:
            yield
            return
        with _huggingface_offline_mode():
            yield


@contextmanager
def _huggingface_offline_mode() -> Iterator[None]:
    previous = os.environ.get("HF_HUB_OFFLINE")
    transformers_hub = None
    hf_constants = None
    previous_transformers_offline = None
    previous_hf_offline = None
    try:
        import huggingface_hub.constants as hf_constants
        import transformers.utils.hub as transformers_hub

        previous_hf_offline = hf_constants.HF_HUB_OFFLINE
        previous_transformers_offline = transformers_hub._is_offline_mode
        hf_constants.HF_HUB_OFFLINE = True
        transformers_hub._is_offline_mode = True
    except Exception:  # noqa: BLE001
        transformers_hub = None
        hf_constants = None
    # 部分 AutoProcessor 会探测可选配置文件。任务阶段打开离线模式，可以拦住这些隐式 HEAD 请求。
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        yield
    finally:
        if hf_constants is not None and previous_hf_offline is not None:
            hf_constants.HF_HUB_OFFLINE = previous_hf_offline
        if transformers_hub is not None and previous_transformers_offline is not None:
            transformers_hub._is_offline_mode = previous_transformers_offline
        if previous is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous
