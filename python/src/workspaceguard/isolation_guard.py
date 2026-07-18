"""
Core isolation + metering logic. Ported from src/core/isolation-guard.ts.
Never imports a specific backend directly -- all backend-specific behavior
goes through the BackendAdapter interface, a fixed architectural boundary.
The CLI and the library export are both thin wrappers around this class;
there is exactly one implementation of the isolation/metering logic.
"""
from __future__ import annotations

import asyncio
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import DefaultDict, List, Optional

from .circuit_breaker import CircuitBreaker
from .config import load_config, resolve_workspace_id, save_config, set_workspace_cap, upsert_workspace
from .log import ConsoleLogger, FailClosedEvent, Logger
from .namespace import ensure_workspace_dirs
from .types import BackendAdapter, IdentityNotFoundError, WorkspaceGuardConfig
from .usage import UsageMeter, WorkspaceUsage
from .vault import Vault


@dataclass
class WorkspaceUsageReport:
    workspace_id: str
    identity: str
    monthly_message_cap: Optional[int]
    percent_used: Optional[int]
    period: str
    message_count: int
    estimated_bytes: int


class IsolationGuard:
    def __init__(
        self,
        data_dir: str,
        backend: BackendAdapter,
        logger: Optional[Logger] = None,
        circuit_open_cooldown_ms: Optional[int] = None,
    ) -> None:
        self._data_dir = data_dir
        self._backend = backend
        self._logger = logger or ConsoleLogger()
        self._vault = Vault(os.path.join(self._data_dir, ".workspaceguard", "master.key"))
        kwargs = {} if circuit_open_cooldown_ms is None else {"open_cooldown_ms": circuit_open_cooldown_ms}
        self._circuit = CircuitBreaker(backend.name, self._logger, **kwargs)
        self._usage = UsageMeter(self._data_dir)
        self._config = WorkspaceGuardConfig(backend="odysseus", identity_header="", workspaces=[])
        # Per-workspace lock so a concurrent quota check-then-record can't
        # race across two calls to chat() for the same workspace (in-process
        # only, matching this project's documented single-sidecar-process
        # deployment model -- see usage.py).
        self._workspace_locks: DefaultDict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @property
    def _config_path(self) -> str:
        return os.path.join(self._data_dir, "workspaceguard.config.yaml")

    async def init(self) -> None:
        await self._vault.init()
        self._config = load_config(self._config_path)

    async def add_workspace(self, workspace_id: str, identity: str) -> None:
        self._config = upsert_workspace(self._config, workspace_id, identity)
        save_config(self._config_path, self._config)
        await ensure_workspace_dirs(self._data_dir, workspace_id)

    async def set_secret(self, workspace_id: str, secret: str) -> None:
        await self._vault.write_secret(self._data_dir, workspace_id, secret)

    async def rotate_key(self, workspace_id: str) -> None:
        await self._vault.rotate(self._data_dir, workspace_id)

    def resolve_workspace(self, identity_header_value: Optional[str]) -> str:
        """
        Resolves a workspace from an untrusted identity header value. Fails
        closed on any miss -- never falls back to a default workspace. This
        is the single choke point every request-handling path must go
        through.
        """
        workspace_id = resolve_workspace_id(self._config, identity_header_value)
        if not workspace_id:
            self._logger.log(
                FailClosedEvent(
                    reason="identity_not_found",
                    detail={"identityHeaderValue": identity_header_value},
                )
            )
            raise IdentityNotFoundError(identity_header_value)
        return workspace_id

    async def chat(self, identity_header_value: Optional[str], message: str) -> str:
        """
        The quota check, backend call, and usage record are wrapped in a
        single per-workspace lock so two concurrent chat() calls for the
        same workspace can never both pass the same pre-cap quota check
        (regression: previously unlocked, letting N concurrent requests at
        cap-1 all read the same count and all proceed, and letting
        concurrent record() calls lose updates to each other). Different
        workspaces never contend with each other.
        """
        workspace_id = self.resolve_workspace(identity_header_value)
        entry = next((w for w in self._config.workspaces if w.workspace_id == workspace_id), None)
        cap = entry.monthly_message_cap if entry is not None else None

        async with self._workspace_locks[workspace_id]:
            await self._usage.check_quota(workspace_id, cap)

            async def _call() -> str:
                return await self._backend.forward_chat(workspace_id, message)

            response = await self._circuit.call(_call)
            await self._usage.record(workspace_id, message)
            return response

    async def status(self) -> List[dict]:
        return [{"workspaceId": w.workspace_id, "identity": w.identity} for w in self._config.workspaces]

    async def set_cap(self, workspace_id: str, cap: Optional[int]) -> None:
        self._config = set_workspace_cap(self._config, workspace_id, cap)
        save_config(self._config_path, self._config)

    async def usage_report(self) -> List[WorkspaceUsageReport]:
        """
        The admin-visibility surface this project actually ships (the OSS
        free tier) -- a hosted billing dashboard on top of this data is a
        separate, closed-source product, never built in this repo.
        """
        ids = [w.workspace_id for w in self._config.workspaces]
        usage_by_id = await self._usage.get_all(ids)
        reports: List[WorkspaceUsageReport] = []
        for w in self._config.workspaces:
            usage = usage_by_id.get(w.workspace_id) or WorkspaceUsage(period="", message_count=0, estimated_bytes=0)
            percent_used: Optional[int] = None
            if w.monthly_message_cap is not None and w.monthly_message_cap > 0:
                # math.floor(x + 0.5), not the builtin round(): Python's
                # round() uses banker's rounding (round-half-to-even) while
                # the TS original's Math.round() rounds half-up -- this
                # kept percentUsed diverging between the two --json outputs
                # for exact-half cases (e.g. 12.5% -> 12 vs 13) despite both
                # READMEs documenting the outputs as identical.
                percent_used = math.floor((usage.message_count / w.monthly_message_cap) * 100 + 0.5)
            reports.append(
                WorkspaceUsageReport(
                    workspace_id=w.workspace_id,
                    identity=w.identity,
                    monthly_message_cap=w.monthly_message_cap,
                    percent_used=percent_used,
                    period=usage.period,
                    message_count=usage.message_count,
                    estimated_bytes=usage.estimated_bytes,
                )
            )
        return reports
