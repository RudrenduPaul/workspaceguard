"""
Chat history and memory get a directory boundary per workspace, not a
shared table/file with a workspace column -- easier to verify by inspection
than a query filter. Ported from src/core/namespace.ts.
"""
from __future__ import annotations

import os


def chat_history_dir(data_dir: str, workspace_id: str) -> str:
    return os.path.join(data_dir, "workspaces", workspace_id, "chat")


def memory_dir(data_dir: str, workspace_id: str) -> str:
    return os.path.join(data_dir, "workspaces", workspace_id, "memory")


async def ensure_workspace_dirs(data_dir: str, workspace_id: str) -> None:
    os.makedirs(chat_history_dir(data_dir, workspace_id), exist_ok=True)
    os.makedirs(memory_dir(data_dir, workspace_id), exist_ok=True)
