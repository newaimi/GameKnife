from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class Principal:
    # Community uses an anonymous principal so public workflows always receive an explicit actor.
    # This avoids scattered None checks while allowing other callers to inject an identified user principal.
    id: str
    kind: Literal["anonymous", "user"]
    display_name: str


@dataclass(frozen=True, slots=True)
class Workspace:
    # Community writes to the local workspace, while other callers may inject a project workspace through RequestContext.
    # Public processing depends only on workspace_id and remains independent of workspace origin and persistence layout.
    id: str
    kind: Literal["local", "project"]
    name: str


class PermissionChecker(Protocol):
    # Public workflows use only this interface, regardless of whether the caller allows actions or enforces authorization rules.
    # This boundary prevents the core layer from importing account and role implementations.
    def require(self, action: str, resource: object | None = None) -> None:
        ...

    def can(self, action: str, resource: object | None = None) -> bool:
        ...


class StorageProvider(Protocol):
    root: Path

    def write_asset(self, asset_id: str, original_name: str, content: bytes) -> str:
        ...

    def remove_asset_file(self, relative_path: str) -> None:
        ...

    def resolve_asset_path(self, relative_path: str) -> Path:
        ...


@dataclass(frozen=True, slots=True)
class CapabilitySet:
    edition: Literal["community", "commercial"]
    features: frozenset[str]


@dataclass(frozen=True, slots=True)
class RequestContext:
    # RequestContext is the boundary between the public API and public workflows.
    # The API layer injects the principal, workspace, permissions, and storage; workflows operate only through these abstractions.
    principal: Principal
    workspace: Workspace
    permissions: PermissionChecker
    capabilities: CapabilitySet
    storage: StorageProvider


class AllowAllPermissionChecker:
    def require(self, action: str, resource: object | None = None) -> None:
        return None

    def can(self, action: str, resource: object | None = None) -> bool:
        return True
