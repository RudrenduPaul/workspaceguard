"""
Fail closed, never pass-through-unisolated -- the worst failure mode here is
a silent cross-workspace leak, so an unreachable backend must block, not
bypass, isolation. Ported from src/core/circuit-breaker.ts.

Opens after 3 consecutive failures. Once the cooldown has passed since
opening, the next call is let through as a half-open probe; success closes
the circuit, failure keeps it open and restarts the cooldown -- a real
circuit breaker with a path back to closed, not a one-way trip switch.
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, TypeVar

from .log import CircuitStateChangeEvent, Logger
from .types import BackendCircuitOpenError, BackendUnreachableError

T = TypeVar("T")

FAILURE_THRESHOLD = 3
CONNECT_TIMEOUT_MS = 3000
DEFAULT_OPEN_COOLDOWN_MS = 10_000


class CircuitBreaker:
    def __init__(self, backend_name: str, logger: Logger, open_cooldown_ms: int = DEFAULT_OPEN_COOLDOWN_MS) -> None:
        self._backend_name = backend_name
        self._logger = logger
        self._open_cooldown_ms = open_cooldown_ms
        self._consecutive_failures = 0
        self._open = False
        self._opened_at = 0.0

    def _probe_allowed(self) -> bool:
        return self._open and (time.monotonic() * 1000 - self._opened_at) >= self._open_cooldown_ms

    async def call(self, fn: Callable[[], Awaitable[T]]) -> T:
        if self._open and not self._probe_allowed():
            raise BackendCircuitOpenError(self._backend_name)
        try:
            result = await asyncio.wait_for(fn(), timeout=CONNECT_TIMEOUT_MS / 1000)
            self._consecutive_failures = 0
            self.on_health_check_success()
            return result
        except Exception:
            self._consecutive_failures += 1
            if self._consecutive_failures >= FAILURE_THRESHOLD:
                self._open_circuit()
            raise BackendUnreachableError(self._backend_name)

    def _open_circuit(self) -> None:
        was_open = self._open
        self._open = True
        self._opened_at = time.monotonic() * 1000
        if not was_open:
            self._logger.log(CircuitStateChangeEvent(backend=self._backend_name, state="open"))

    def on_health_check_success(self) -> None:
        """A health check success (or a successful half-open probe) closes the circuit again."""
        if self._open:
            self._open = False
            self._consecutive_failures = 0
            self._logger.log(CircuitStateChangeEvent(backend=self._backend_name, state="closed"))
