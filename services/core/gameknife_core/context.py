from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class Principal:
    # Community 使用匿名主体，是为了让公共工作流始终拿到明确的操作者。
    # 这样业务代码不需要散落 `None` 用户判断，商用版也能替换成真实用户主体。
    id: str
    kind: Literal["anonymous", "user"]
    display_name: str


@dataclass(frozen=True, slots=True)
class Workspace:
    # Community 固定写入本地工作区，Commercial 会注入项目工作区。
    # 公共处理链只认 workspace_id，避免直接依赖团队、项目等商用表结构。
    id: str
    kind: Literal["local", "project"]
    name: str


class PermissionChecker(Protocol):
    # 公共工作流只调用权限接口，不关心权限来自匿名放行还是商用 RBAC。
    # 这条边界用于保证开源核心不会反向导入商用用户和角色模块。
    def require(self, action: str, resource: object | None = None) -> None:
        ...

    def can(self, action: str, resource: object | None = None) -> bool:
        ...


class StorageProvider(Protocol):
    root: Path

    def resolve_asset_path(self, relative_path: str) -> Path:
        ...


@dataclass(frozen=True, slots=True)
class CapabilitySet:
    edition: Literal["community", "commercial"]
    features: frozenset[str]


@dataclass(frozen=True, slots=True)
class RequestContext:
    # RequestContext 是公共 API 和公共工作流之间的边界。
    # API 层负责注入主体、工作区、权限和存储，工作流只使用这些抽象完成业务。
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
