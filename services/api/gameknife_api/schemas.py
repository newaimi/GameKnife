from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AssetResponse(BaseModel):
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    url: str


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

    edition: Literal["community"]
    workspace_id: str
    storage: Literal["local_file_storage"]
    models: dict[str, Any]
