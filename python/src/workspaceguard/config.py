"""
Load/save `workspaceguard.config.yaml` and the pure config-mutation helpers
(add a workspace, set a cap, resolve an identity to a workspace id). Ported
from src/core/config.ts. YAML keys are camelCase (backend, identityHeader,
workspaces: [{workspaceId, identity, monthlyMessageCap}]) to stay
file-compatible with the npm package's own config file.
"""
from __future__ import annotations

import os
from typing import Optional

import yaml

from .types import WorkspaceEntry, WorkspaceGuardConfig, WorkspaceNotFoundError

DEFAULT_IDENTITY_HEADER = "cf-access-authenticated-user-email"


def _default_config() -> WorkspaceGuardConfig:
    return WorkspaceGuardConfig(backend="odysseus", identity_header=DEFAULT_IDENTITY_HEADER, workspaces=[])


def load_config(config_path: str) -> WorkspaceGuardConfig:
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        parsed = yaml.safe_load(raw) or {}
        workspaces = [
            WorkspaceEntry(
                workspace_id=w["workspaceId"],
                identity=w["identity"],
                monthly_message_cap=w.get("monthlyMessageCap"),
            )
            for w in parsed.get("workspaces", [])
        ]
        return WorkspaceGuardConfig(
            backend=parsed.get("backend") or "odysseus",
            identity_header=parsed.get("identityHeader") or DEFAULT_IDENTITY_HEADER,
            workspaces=workspaces,
        )
    except Exception:
        return _default_config()


def save_config(config_path: str, config: WorkspaceGuardConfig) -> None:
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    payload = {
        "backend": config.backend,
        "identityHeader": config.identity_header,
        "workspaces": [
            {
                "workspaceId": w.workspace_id,
                "identity": w.identity,
                **({"monthlyMessageCap": w.monthly_message_cap} if w.monthly_message_cap is not None else {}),
            }
            for w in config.workspaces
        ],
    }
    with open(config_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, sort_keys=False)


class DuplicateIdentityError(Exception):
    def __init__(self, identity: str, existing_workspace_id: str) -> None:
        super().__init__(f'identity "{identity}" is already assigned to workspace "{existing_workspace_id}"')
        self.identity = identity
        self.existing_workspace_id = existing_workspace_id


def upsert_workspace(config: WorkspaceGuardConfig, workspace_id: str, identity: str) -> WorkspaceGuardConfig:
    """
    add-workspace on an existing id is idempotent -- returns the existing
    config unchanged, never overwrites. Rejects loudly if the identity is
    already claimed by a DIFFERENT workspace id: without this check, two
    workspace ids could silently share one identity, and resolve_workspace_id
    would deterministically route to whichever was added first, merging two
    workspaces from the routing layer's perspective without either operator
    being told.
    """
    for w in config.workspaces:
        if w.workspace_id == workspace_id:
            return config
    for w in config.workspaces:
        if w.identity == identity:
            raise DuplicateIdentityError(identity, w.workspace_id)
    return WorkspaceGuardConfig(
        backend=config.backend,
        identity_header=config.identity_header,
        workspaces=[*config.workspaces, WorkspaceEntry(workspace_id=workspace_id, identity=identity)],
    )


def set_workspace_cap(
    config: WorkspaceGuardConfig, workspace_id: str, cap: Optional[int]
) -> WorkspaceGuardConfig:
    """
    Sets (or clears, with cap=None) a workspace's monthly message cap.
    Rejects loudly on an unknown workspace id rather than silently
    no-op'ing, matching upsert_workspace's fail-loud-on-ambiguity precedent.
    """
    index = next((i for i, w in enumerate(config.workspaces) if w.workspace_id == workspace_id), None)
    if index is None:
        raise WorkspaceNotFoundError(workspace_id)
    workspaces = list(config.workspaces)
    existing = workspaces[index]
    workspaces[index] = WorkspaceEntry(
        workspace_id=existing.workspace_id, identity=existing.identity, monthly_message_cap=cap
    )
    return WorkspaceGuardConfig(backend=config.backend, identity_header=config.identity_header, workspaces=workspaces)


def resolve_workspace_id(config: WorkspaceGuardConfig, identity_header_value: Optional[str]) -> Optional[str]:
    if not identity_header_value:
        return None
    for w in config.workspaces:
        if w.identity == identity_header_value:
            return w.workspace_id
    return None
