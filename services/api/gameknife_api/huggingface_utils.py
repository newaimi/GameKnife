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
    cache_dir: Path | None = None,
) -> bool:
    # Settings inspect the local cache without loading weights, so a status refresh cannot pull a model into memory.
    if not all(_cached_file_exists(model_id, filename, revision=revision, cache_dir=cache_dir) for filename in required_files):
        return False
    return any(_cached_file_exists(model_id, filename, revision=revision, cache_dir=cache_dir) for filename in weight_files)


def _cached_file_exists(model_id: str, filename: str, *, revision: str | None = None, cache_dir: Path | None = None) -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache
    except Exception:  # noqa: BLE001
        return False
    cached = try_to_load_from_cache(model_id, filename, revision=revision, cache_dir=cache_dir)
    return isinstance(cached, str) and Path(cached).is_file()


@contextmanager
def huggingface_model_io(local_files_only: bool) -> Iterator[None]:
    # Hugging Face offline mode is process-wide and must change serially so one task cannot disrupt another installation.
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
    # Some AutoProcessor implementations probe optional configuration files; offline execution blocks those implicit HEAD requests.
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
