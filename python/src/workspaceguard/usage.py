"""
Per-workspace usage metering -- the wedge this project ships instead of
per-user isolation (already native in the target platform, see README).
Ported from src/core/usage.ts. Reads/writes are not lock-guarded against
concurrent processes, the same accepted tradeoff config.py already makes for
`workspaceguard.config.yaml` (single-sidecar-process deployment model).

The usage.json file uses camelCase keys (period, messageCount,
estimatedBytes) to stay wire-compatible with the npm package's own store.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

UsageStore = Dict[str, "WorkspaceUsage"]


@dataclass
class WorkspaceUsage:
    period: str
    message_count: int
    estimated_bytes: int


class QuotaExceededError(Exception):
    def __init__(self, workspace_id: str, cap: int) -> None:
        super().__init__(f"workspace {workspace_id} has reached its monthly cap of {cap} messages")
        self.workspace_id = workspace_id
        self.cap = cap


def _current_period() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year}-{now.month:02d}"


def usage_path(data_dir: str) -> str:
    return os.path.join(data_dir, ".workspaceguard", "usage.json")


def _load_usage_raw(data_dir: str) -> Dict[str, dict]:
    """
    Only a missing file (no workspace has recorded usage yet) is a
    legitimate empty store. Every other failure (permission error, disk
    error, a corrupted/truncated JSON file) must propagate so a caller like
    check_quota() fails closed instead of silently reading every
    workspace's usage as zero -- a catch-everything here used to let any
    I/O hiccup or a race-corrupted usage.json lift every quota in the
    store.
    """
    try:
        with open(usage_path(data_dir), "r", encoding="utf-8") as fh:
            raw = fh.read()
    except FileNotFoundError:
        return {}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as err:
        raise ValueError(f"usage store at {usage_path(data_dir)} is corrupted and could not be parsed: {err}") from err
    if not isinstance(parsed, dict):
        raise ValueError(f"usage store at {usage_path(data_dir)} has an unexpected shape (expected a JSON object)")
    return parsed


def load_usage(data_dir: str) -> UsageStore:
    raw = _load_usage_raw(data_dir)
    store: UsageStore = {}
    for workspace_id, entry in raw.items():
        try:
            store[workspace_id] = WorkspaceUsage(
                period=entry["period"],
                message_count=entry["messageCount"],
                estimated_bytes=entry["estimatedBytes"],
            )
        except (KeyError, TypeError):
            continue
    return store


def save_usage(data_dir: str, store: UsageStore) -> None:
    path = usage_path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        workspace_id: {
            "period": usage.period,
            "messageCount": usage.message_count,
            "estimatedBytes": usage.estimated_bytes,
        }
        for workspace_id, usage in store.items()
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def current_usage_for(store: UsageStore, workspace_id: str) -> WorkspaceUsage:
    """
    Rolls a workspace's counter over to a fresh period on read -- a stale
    count from last month must never inflate this month's total or trip a
    cap that shouldn't apply yet (no cron/scheduler needed, since every real
    read/write already knows what period it is).
    """
    existing = store.get(workspace_id)
    period = _current_period()
    if existing is None or existing.period != period:
        return WorkspaceUsage(period=period, message_count=0, estimated_bytes=0)
    return existing


class UsageMeter:
    def __init__(self, data_dir: str) -> None:
        self.data_dir = data_dir

    async def record(self, workspace_id: str, message: str) -> WorkspaceUsage:
        store = load_usage(self.data_dir)
        usage = current_usage_for(store, workspace_id)
        usage = WorkspaceUsage(
            period=usage.period,
            message_count=usage.message_count + 1,
            estimated_bytes=usage.estimated_bytes + len(message.encode("utf-8")),
        )
        store[workspace_id] = usage
        save_usage(self.data_dir, store)
        return usage

    async def get(self, workspace_id: str) -> WorkspaceUsage:
        store = load_usage(self.data_dir)
        return current_usage_for(store, workspace_id)

    async def get_all(self, workspace_ids: List[str]) -> Dict[str, WorkspaceUsage]:
        store = load_usage(self.data_dir)
        return {workspace_id: current_usage_for(store, workspace_id) for workspace_id in workspace_ids}

    async def check_quota(self, workspace_id: str, cap: Optional[int]) -> None:
        """
        Raises QuotaExceededError once a workspace has reached its
        configured cap. cap=None means unlimited -- never blocks a
        workspace that has no cap set, so this stays free/OSS-safe by
        default.
        """
        if cap is None:
            return
        usage = await self.get(workspace_id)
        if usage.message_count >= cap:
            raise QuotaExceededError(workspace_id, cap)
