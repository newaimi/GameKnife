from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AssetResponse(BaseModel):
    id: str
    filename: str
    kind: str
    mime_type: str
    size_bytes: int
    storage_state: str
    created_by: str
    created_at: str
    updated_at: str
    url: str


class AssetActionResponse(BaseModel):
    id: str
    label: str
    route: str


class AssetRelationResponse(BaseModel):
    direction: Literal["source", "derived"]
    relation_type: str
    job_id: str | None = None
    asset: AssetResponse


class AssetDetailResponse(AssetResponse):
    relations: list[AssetRelationResponse] = Field(default_factory=list)
    available_actions: list[AssetActionResponse] = Field(default_factory=list)


class AssetPageResponse(BaseModel):
    items: list[AssetResponse]
    total: int
    page: int
    page_size: int


class JobResponse(BaseModel):
    id: str
    type: str
    status: Literal["pending", "running", "success", "failed"]
    input_asset_id: str
    input_filename: str | None = None
    input_mime_type: str | None = None
    input_size_bytes: int | None = None
    parameters: dict[str, Any]
    result: dict[str, Any]
    device: str | None = None
    duration_ms: int = 0
    error_message: str | None = None
    error_code: str | None = None
    created_at: str
    updated_at: str


class JobPageResponse(BaseModel):
    items: list[JobResponse]
    total: int
    page: int
    page_size: int


class AssetJobRequest(BaseModel):
    input_asset_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ProjectExportRequest(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=100)
    preset: Literal["generic", "unity", "godot"] = "generic"
    package_name: str = Field(default="gameknife-export", min_length=1, max_length=120)


class AssetBoardRefineRequest(BaseModel):
    cutout_asset_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class AssetBoardExportRequest(BaseModel):
    cutout_asset_id: str
    selected_component_ids: list[int] = Field(default_factory=list)
    components: list[dict[str, Any]] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)


class SoundEffectRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1500)
    duration_seconds: float = Field(default=4, ge=0.5, le=30)
    seed: int | None = Field(default=None, ge=-1)
    steps: int = Field(default=100, ge=10, le=250)
    cfg_scale: float = Field(default=7.0, ge=1, le=20)


class SequenceFrameResponse(BaseModel):
    id: str
    sequence_id: str
    source_asset_id: str
    processed_asset_id: str | None = None
    frame_index: int
    original_name: str
    width: int
    height: int
    bbox: list[int]
    offset_x: int = 0
    offset_y: int = 0
    duration_ms: int = 0
    enabled: bool = True
    is_generated: bool = False
    source_url: str
    preview_url: str
    created_at: str
    updated_at: str


class SequenceResponse(BaseModel):
    id: str
    name: str
    fps: int
    loop: bool
    canvas_width: int
    canvas_height: int
    anchor_mode: str
    anchor_x: float
    anchor_y: float
    clean_parameters: dict[str, Any]
    status: str
    frame_count: int
    enabled_frame_count: int
    frames: list[SequenceFrameResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class SequenceUpdateRequest(BaseModel):
    name: str | None = None
    fps: int | None = Field(default=None, ge=1, le=60)
    loop: bool | None = None
    canvas_width: int | None = Field(default=None, ge=0, le=4096)
    canvas_height: int | None = Field(default=None, ge=0, le=4096)
    anchor_mode: str | None = None
    anchor_x: float | None = Field(default=None, ge=0, le=1)
    anchor_y: float | None = Field(default=None, ge=0, le=1)
    clean_parameters: dict[str, Any] | None = None


class SequenceFramePatch(BaseModel):
    id: str
    frame_index: int | None = Field(default=None, ge=0)
    offset_x: int | None = Field(default=None, ge=-4096, le=4096)
    offset_y: int | None = Field(default=None, ge=-4096, le=4096)
    duration_ms: int | None = Field(default=None, ge=0, le=10000)
    enabled: bool | None = None


class SequenceFramesUpdateRequest(BaseModel):
    frames: list[SequenceFramePatch]


class SequenceTaskRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)


class VideoToSequenceRequest(BaseModel):
    video_asset_id: str
    name: str | None = None
    fps: int = Field(default=12, ge=1, le=60)
    max_frames: int = Field(default=48, ge=1, le=300)
    start_second: float = Field(default=0, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0.1, le=3600)
    remove_background: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)


class VideoSequenceGenerateRequest(BaseModel):
    input_asset_id: str
    action: str = Field(default="walk_down", max_length=64)
    prompt: str = Field(default="", max_length=1500)
    negative_prompt: str = Field(default="", max_length=500)
    duration: int = Field(default=5, ge=2, le=15)
    resolution: str = Field(default="720P", max_length=32)
    confirmed_external_api: bool = False


class VideoGenerationConfigRequest(BaseModel):
    provider: Literal["aliyun_dashscope", "seedance"] = "aliyun_dashscope"
    base_url: str = ""
    api_key: str | None = None


class VideoGenerationConfigResponse(BaseModel):
    provider: Literal["aliyun_dashscope", "seedance"]
    base_url: str
    api_key_configured: bool
    masked_api_key: str | None = None


class PrincipalResponse(BaseModel):
    id: str
    kind: Literal["anonymous", "user"]
    displayName: str


class WorkspaceResponse(BaseModel):
    id: str
    kind: Literal["local", "project"]
    name: str


class CapabilityResponse(BaseModel):
    edition: Literal["community", "commercial"]
    features: list[str]


class ContextResponse(BaseModel):
    principal: PrincipalResponse
    workspace: WorkspaceResponse
    capabilities: CapabilityResponse


class SettingsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    edition: Literal["community", "commercial"]
    workspace_id: str
    storage: Literal["local_file_storage", "enterprise_storage"]
    system: dict[str, Any]
    runtime: dict[str, Any]
    birefnet: dict[str, Any]
    upscale_models: dict[str, Any]
    stable_audio: dict[str, Any]
    video_generation: VideoGenerationConfigResponse
