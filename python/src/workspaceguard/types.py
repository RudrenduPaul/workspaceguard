"""
Shared types for WorkspaceGuard's isolation and metering pipeline. Used by
both the CLI (workspaceguard/cli.py) and the programmatic library API
(workspaceguard/__init__.py).

This is a Python port of the TypeScript original's src/core/types.ts. Field
names follow Python (snake_case) convention; the config/usage persistence
layer (workspaceguard/config.py, workspaceguard/usage.py) re-serializes to
the same camelCase keys the npm package's YAML/JSON files use, so a
`workspaceguard.config.yaml` or `usage.json` written by one distribution
stays readable by the other.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class WorkspaceEntry:
    workspace_id: str
    identity: str
    monthly_message_cap: Optional[int] = None
    """Monthly message cap for usage metering. None = unlimited (free-tier default)."""


@dataclass
class WorkspaceGuardConfig:
    backend: str = "odysseus"
    identity_header: str = ""
    workspaces: List[WorkspaceEntry] = field(default_factory=list)


class BackendAdapter(ABC):
    """
    Fixed architectural boundary: all backend-specific behavior goes through
    this interface. Core isolation/metering logic never imports a specific
    backend directly.
    """

    name: str

    @abstractmethod
    async def health_check(self) -> bool: ...

    @abstractmethod
    async def forward_chat(self, workspace_id: str, message: str) -> str: ...


class IdentityNotFoundError(Exception):
    def __init__(self, header_value: Optional[str]) -> None:
        super().__init__("no workspace configured for this identity")
        self.header_value = header_value


class VaultDecryptionError(Exception):
    def __init__(self, workspace_id: str) -> None:
        super().__init__(f"could not decrypt vault for workspace {workspace_id}")
        self.workspace_id = workspace_id


class BackendUnreachableError(Exception):
    def __init__(self, backend: str) -> None:
        super().__init__(f"backend {backend} did not respond")
        self.backend = backend


class BackendCircuitOpenError(Exception):
    def __init__(self, backend: str) -> None:
        super().__init__(f"backend {backend} circuit is open, refusing calls")
        self.backend = backend


class WorkspaceNotFoundError(Exception):
    def __init__(self, workspace_id: str) -> None:
        super().__init__(f'no workspace configured with id "{workspace_id}"')
        self.workspace_id = workspace_id
