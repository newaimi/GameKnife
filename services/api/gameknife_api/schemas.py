from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


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
