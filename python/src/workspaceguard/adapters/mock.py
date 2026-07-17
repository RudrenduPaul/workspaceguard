"""
In-memory mock backend, used for the scaffold-stage isolation tests only.
Ported from src/adapters/mock.ts. The real Odysseus adapter is blocked on a
feasibility spike: does Odysseus's HTTP API expose clean interception
points, or does it read/write some of this directly from disk/DB in a way
an HTTP-level proxy can't see? See docs/integrations/backends.md.
"""
from __future__ import annotations

from typing import Dict, List

from ..types import BackendAdapter


class MockAdapter(BackendAdapter):
    name = "mock"

    def __init__(self) -> None:
        self._messages_by_workspace: Dict[str, List[str]] = {}
        self._failures_remaining = 0

    async def health_check(self) -> bool:
        return True

    async def forward_chat(self, workspace_id: str, message: str) -> str:
        if self._failures_remaining > 0:
            self._failures_remaining -= 1
            raise RuntimeError("simulated backend failure")
        existing = self._messages_by_workspace.setdefault(workspace_id, [])
        existing.append(message)
        return f"echo: {message}"

    def _fail_next_calls(self, n: int) -> None:
        """Test-only: makes the next N forward_chat calls fail, to exercise the circuit breaker."""
        self._failures_remaining = n

    def _messages_for(self, workspace_id: str) -> List[str]:
        """Test-only inspection point -- never exposed through the public adapter interface."""
        return self._messages_by_workspace.get(workspace_id, [])
