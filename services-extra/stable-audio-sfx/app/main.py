from __future__ import annotations

import io
import os
import queue
import threading
import time
import wave
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, Field


MODEL_ID = os.getenv("GAMEKNIFE_STABLE_AUDIO_MODEL_ID", "stabilityai/stable-audio-open-1.0")
SERVICE_TOKEN = os.getenv("GAMEKNIFE_STABLE_AUDIO_TOKEN", "")
QUEUE_SIZE = max(1, int(os.getenv("GAMEKNIFE_STABLE_AUDIO_QUEUE_SIZE", "12")))
GENERATION_TIMEOUT_SECONDS = max(60, int(os.getenv("GAMEKNIFE_STABLE_AUDIO_GENERATION_TIMEOUT_SECONDS", "900")))


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1500)
    duration_seconds: float = Field(default=4, ge=0.5, le=30)
    seed: int | None = Field(default=None, ge=-1)
    steps: int = Field(default=100, ge=10, le=250)
    cfg_scale: float = Field(default=7.0, ge=1, le=20)


@dataclass(slots=True)
class AudioJob:
    request: GenerateRequest
    created_at: float
    done: threading.Event = field(default_factory=threading.Event)
    audio: bytes | None = None
    headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None


@dataclass(slots=True)
class WorkerState:
    device: str
    label: str
    loaded: bool = False
    busy: bool = False
    current_prompt: str = ""
    last_error: str | None = None


class InstallState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status: dict[str, Any] = {
            "status": "idle",
            "progress": 0,
            "message": "尚未手动安装。",
            "error": None,
        }

    def read(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def write(self, status_name: str, progress: int, message: str, error: str | None = None) -> None:
        with self._lock:
            self._status = {
                "status": status_name,
                "progress": max(0, min(100, int(progress))),
                "message": message,
                "error": error,
            }


class StableAudioWorkerPool:
    def __init__(self) -> None:
        self.jobs: queue.Queue[AudioJob] = queue.Queue(maxsize=QUEUE_SIZE)
        self.states = [WorkerState(device=device, label=label) for device, label in _resolve_worker_devices()]
        self._models: dict[str, tuple[Any, dict[str, Any]]] = {}
        self._model_lock = threading.Lock()
        for state in self.states:
            thread = threading.Thread(target=self._worker_loop, args=(state,), name=f"gameknife-stable-audio-{state.label}", daemon=True)
            thread.start()

    def status(self) -> dict[str, Any]:
        installed = model_files_cached()
        loaded = any(state.loaded for state in self.states)
        status_data = install_state.read()
        if installed and status_data["status"] in {"idle", "running", "failed"}:
            status_data = {
                "status": "success",
                "progress": 100,
                "message": "Stable Audio Open 模型文件已安装。",
                "error": None,
            }
        return {
            **status_data,
            "installed": installed,
            "loaded": loaded,
            "model_id": MODEL_ID,
            "queue_size": QUEUE_SIZE,
            "queued": self.jobs.qsize(),
            "workers": [
                {
                    "device": state.label,
                    "runtime_device": state.device,
                    "loaded": state.loaded,
                    "busy": state.busy,
                    "last_error": state.last_error,
                }
                for state in self.states
            ],
        }

    def submit(self, request: GenerateRequest) -> AudioJob:
        job = AudioJob(request=request, created_at=time.monotonic())
        try:
            self.jobs.put_nowait(job)
        except queue.Full as exc:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="声效生成队列已满，请稍后再试。") from exc
        if not job.done.wait(GENERATION_TIMEOUT_SECONDS):
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="声效生成超时，请缩短时长或稍后重试。")
        if job.error:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=job.error)
        return job

    def install_model(self) -> None:
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise RuntimeError("缺少 huggingface_hub，请确认 stable-audio-tools 已安装。") from exc
        snapshot_download(MODEL_ID, repo_type="model")

    def _worker_loop(self, state: WorkerState) -> None:
        while True:
            job = self.jobs.get()
            state.busy = True
            state.current_prompt = job.request.prompt
            started = time.monotonic()
            try:
                audio, metadata = self._generate(state, job.request)
                job.audio = audio
                job.headers = {
                    "X-Stable-Audio-Model": MODEL_ID,
                    "X-Stable-Audio-Device": state.label,
                    "X-Stable-Audio-Sample-Rate": str(metadata["sample_rate"]),
                    "X-Stable-Audio-Queue-Wait-Ms": str(round((started - job.created_at) * 1000)),
                    "X-Stable-Audio-Duration-Ms": str(round((time.monotonic() - started) * 1000)),
                }
                state.last_error = None
            except Exception as exc:  # noqa: BLE001
                state.last_error = str(exc)
                job.error = str(exc)
            finally:
                state.busy = False
                state.current_prompt = ""
                job.done.set()
                self.jobs.task_done()

    def _generate(self, state: WorkerState, request: GenerateRequest) -> tuple[bytes, dict[str, int]]:
        import torch
        from einops import rearrange
        from stable_audio_tools.inference.generation import generate_diffusion_cond

        model, model_config = self._load_model(state)
        sample_rate = int(model_config["sample_rate"])
        configured_sample_size = int(model_config["sample_size"])
        requested_samples = int(request.duration_seconds * sample_rate)
        sample_size = min(configured_sample_size, max(1, requested_samples))
        seed = int(time.time()) if request.seed is None or request.seed < 0 else int(request.seed)
        conditioning = [{"prompt": request.prompt, "seconds_start": 0, "seconds_total": float(request.duration_seconds)}]

        # 声效推理由独立服务 worker 串行消费，Community API 只负责排队和持久化任务。
        # 这样 GPU 占用、排队时间和失败原因都集中在服务边界内，不会阻塞主 Web 进程。
        with torch.no_grad():
            audio = generate_diffusion_cond(
                model,
                steps=int(request.steps),
                cfg_scale=float(request.cfg_scale),
                conditioning=conditioning,
                sample_size=sample_size,
                sigma_min=0.3,
                sigma_max=500,
                sampler_type="dpmpp-3m-sde",
                device=state.device,
                seed=seed,
            )
        audio = audio[:, :, :requested_samples]
        audio = rearrange(audio, "b d n -> d (b n)")
        audio = audio.to(torch.float32).clamp(-1, 1).mul(32767).to(torch.int16).cpu()
        return encode_wav_pcm16(audio, sample_rate), {"sample_rate": sample_rate}

    def _load_model(self, state: WorkerState) -> tuple[Any, dict[str, Any]]:
        with self._model_lock:
            cached = self._models.get(state.device)
            if cached is not None:
                return cached
            try:
                from stable_audio_tools import get_pretrained_model
            except ImportError as exc:
                raise RuntimeError("缺少 stable-audio-tools，请先安装声效服务依赖。") from exc
            with huggingface_offline_mode():
                model, model_config = get_pretrained_model(MODEL_ID)
            try:
                import torch

                model = model.eval().to(state.device)
                if os.getenv("GAMEKNIFE_STABLE_AUDIO_MODEL_HALF", "1") == "1" and state.device.startswith("cuda"):
                    model = model.half()
                if state.device.startswith("cuda"):
                    torch.cuda.set_device(state.device)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Stable Audio 模型迁移到 {state.label} 失败：{exc}") from exc
            state.loaded = True
            self._models[state.device] = (model, model_config)
            return model, model_config


def model_files_cached() -> bool:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return False
    try:
        snapshot_download(MODEL_ID, repo_type="model", local_files_only=True)
        return True
    except Exception:  # noqa: BLE001
        return False


def encode_wav_pcm16(audio: Any, sample_rate: int) -> bytes:
    if len(audio.shape) != 2:
        raise RuntimeError("声效输出格式不正确，无法写入 WAV。")
    channels = int(audio.shape[0])
    if channels <= 0:
        raise RuntimeError("声效输出没有可写入的声道。")

    # 生成阶段已经裁剪到 int16 PCM。这里直接用标准库写 WAV，
    # 避免 torchaudio 在不同系统和 conda 后端里对 BytesIO 支持不一致。
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    interleaved = audio.transpose(1, 0).copy().tobytes()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(sample_rate))
        wav_file.writeframes(interleaved)
    return buffer.getvalue()


def _resolve_worker_devices() -> list[tuple[str, str]]:
    raw_devices = [item.strip() for item in os.getenv("GAMEKNIFE_STABLE_AUDIO_VISIBLE_GPUS", "").split(",") if item.strip()]
    try:
        import torch

        if torch.cuda.is_available():
            count = torch.cuda.device_count()
            if raw_devices:
                resolved: list[tuple[str, str]] = []
                for raw_device in raw_devices:
                    if not raw_device.isdigit():
                        continue
                    device_index = int(raw_device)
                    if 0 <= device_index < count:
                        resolved.append((f"cuda:{device_index}", f"cuda:{device_index}"))
                if resolved:
                    return resolved
            return [(f"cuda:{index}", f"cuda:{index}") for index in range(count)]
    except Exception:  # noqa: BLE001
        pass
    return [("cpu", "cpu")]


@contextmanager
def huggingface_offline_mode():
    previous = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous


install_state = InstallState()
worker_pool = StableAudioWorkerPool()
app = FastAPI(title="GameKnife Stable Audio SFX", version="0.1.0")


def verify_token(x_gameknife_token: str | None = Header(default=None)) -> None:
    if SERVICE_TOKEN and x_gameknife_token != SERVICE_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="声效服务内部 token 不正确。")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "gameknife-stable-audio-sfx"}


@app.get("/models/status", dependencies=[Depends(verify_token)])
def model_status() -> dict[str, Any]:
    return worker_pool.status()


@app.post("/models/install", dependencies=[Depends(verify_token)])
def install_model() -> dict[str, Any]:
    current = install_state.read()
    if current["status"] == "running":
        return worker_pool.status()
    install_state.write("running", 1, "准备安装 Stable Audio Open。")
    thread = threading.Thread(target=_install_worker, name="gameknife-stable-audio-install", daemon=True)
    thread.start()
    return worker_pool.status()


@app.post("/generate", dependencies=[Depends(verify_token)])
def generate_sound_effect(payload: GenerateRequest) -> Response:
    if not model_files_cached():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stable Audio Open 模型尚未安装，请先调用安装接口。")
    job = worker_pool.submit(payload)
    if job.audio is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="声效生成没有返回音频。")
    return Response(content=job.audio, media_type="audio/wav", headers=job.headers)


def _install_worker() -> None:
    try:
        install_state.write("running", 10, f"正在下载 {MODEL_ID}。")
        worker_pool.install_model()
        install_state.write("success", 100, "Stable Audio Open 模型文件已安装。")
    except Exception as exc:  # noqa: BLE001
        install_state.write("failed", 100, "Stable Audio Open 安装失败。", str(exc))
