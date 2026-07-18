"""
Programmatic / agent-native entry point.

    from workspaceguard import create_workspace_guard, MockAdapter

    guard = await create_workspace_guard(data_dir="./data", backend=MockAdapter())
    await guard.add_workspace("alex", "alex@example.com")
    await guard.set_cap("alex", 1000)
    report = await guard.usage_report()

Same core isolation/metering logic as the `workspaceguard` CLI;
workspaceguard/cli.py is a thin argument-parsing wrapper over this class.

This is the Python port of the workspaceguard-cli npm package
(https://www.npmjs.com/package/workspaceguard-cli, not yet published as of
this port -- see README for current npm status). See
https://github.com/RudrenduPaul/workspaceguard for the canonical
documentation and the original TypeScript source.
"""
from __future__ import annotations

from typing import Optional

from .adapters.mock import MockAdapter
from .config import DuplicateIdentityError, InvalidWorkspaceIdError
from .isolation_guard import IsolationGuard, WorkspaceUsageReport
from .types import (
    BackendAdapter,
    BackendCircuitOpenError,
    BackendUnreachableError,
    IdentityNotFoundError,
    VaultDecryptionError,
    WorkspaceNotFoundError,
)
from .usage import QuotaExceededError, WorkspaceUsage

__version__ = "0.1.1"


async def create_workspace_guard(
    data_dir: str,
    backend: BackendAdapter,
    circuit_open_cooldown_ms: Optional[int] = None,
) -> IsolationGuard:
    """
    The library entry point -- the "agent-native" surface. An orchestrator
    process can call this directly instead of shelling out to the CLI. No
    default backend -- a caller must be explicit about which adapter it
    wants (the real Odysseus adapter ships once the feasibility spike
    confirms clean HTTP interception; MockAdapter is exported for tests and
    local experimentation).
    """
    guard = IsolationGuard(
        data_dir=data_dir,
        backend=backend,
        circuit_open_cooldown_ms=circuit_open_cooldown_ms,
    )
    await guard.init()
    return guard


__all__ = [
    "create_workspace_guard",
    "IsolationGuard",
    "WorkspaceUsageReport",
    "BackendAdapter",
    "MockAdapter",
    "IdentityNotFoundError",
    "VaultDecryptionError",
    "BackendUnreachableError",
    "BackendCircuitOpenError",
    "WorkspaceNotFoundError",
    "DuplicateIdentityError",
    "InvalidWorkspaceIdError",
    "QuotaExceededError",
    "WorkspaceUsage",
    "__version__",
]
