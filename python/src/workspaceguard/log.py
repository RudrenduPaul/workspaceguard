"""
Structured event logging. Ported from src/core/log.ts. Every fail-closed
decision and every circuit-breaker state change gets one JSON line -- the
only way the "zero cross-workspace leaks" claim is verifiable outside of
tests.
"""
from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional


@dataclass
class FailClosedEvent:
    reason: str
    detail: Dict[str, Any]
    type: Literal["fail_closed"] = "fail_closed"


@dataclass
class CircuitStateChangeEvent:
    backend: str
    state: Literal["open", "closed"]
    type: Literal["circuit_state_change"] = "circuit_state_change"


LogEvent = Any  # FailClosedEvent | CircuitStateChangeEvent


class Logger(ABC):
    @abstractmethod
    def log(self, event: LogEvent) -> None: ...


class ConsoleLogger(Logger):
    def log(self, event: LogEvent) -> None:
        line: Dict[str, Any] = {"ts": datetime.now(timezone.utc).isoformat()}
        line.update(vars(event))
        print(json.dumps(line), file=sys.stdout)
