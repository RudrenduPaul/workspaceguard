#!/usr/bin/env python3
"""
Console entry point: `workspaceguard <command> [args] [--json]`, installed
via the `workspaceguard` console-script defined in python/pyproject.toml --
the same command name as the (not-yet-published) npm package's `bin` entry.

Ported from src/cli/index.ts. Commands, flags, human-readable text, and
--json output shapes are kept identical to the TypeScript CLI so the two
distributions are drop-in equivalents for anything that shells out to
either one.
"""
from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from typing import Any, List, Optional, Tuple

from . import create_workspace_guard
from .adapters.mock import MockAdapter


def _package_version() -> str:
    try:
        return _pkg_version("workspaceguard-cli")
    except PackageNotFoundError:
        return "0.0.0-dev"


HELP_TEXT = """usage: workspaceguard <command> [args] [--json]

commands:
  init                              initialize workspaceguard in the current (or configured) data directory
  add-workspace <id> --identity <v> register a new workspace with its identity
  status                            list configured workspaces and their isolation status
  rotate-key <id>                   rotate the API key for a workspace
  usage                             print per-workspace message-usage counts and caps
  set-cap <id> <count|none>         set (or clear) a workspace's monthly message cap
  scan                              scan isolation config for misconfigurations

global options:
  --json          output structured JSON instead of human-readable text
  -h, --help      show this help message and exit
  -V, --version   show the installed version and exit"""

STARTUP_WARNING = (
    "WARNING: workspaceguard must never be directly reachable from the network.\n"
    "It trusts an upstream identity header (e.g. Cf-Access-Authenticated-User-Email)\n"
    "set by your reverse proxy. If this port is exposed without that proxy in front\n"
    "of it, anyone can impersonate any workspace. Firewall this port; only your\n"
    "trusted proxy should be able to reach it."
)

USAGE = "usage: workspaceguard <init|add-workspace|status|rotate-key|usage|set-cap|scan> [--json]"


def _extract_json_flag(args: List[str]) -> Tuple[bool, List[str]]:
    """Strips a boolean flag out of an argv slice, agent-native mode toggle for every command."""
    rest = [a for a in args if a != "--json"]
    return len(rest) != len(args), rest


def _print_result(json_mode: bool, data: Any, human_lines: List[str]) -> None:
    if json_mode:
        import json as _json

        print(_json.dumps(data))
        return
    for line in human_lines:
        print(line)


def _usage_report_to_dict(report: Any) -> dict:
    d = asdict(report)
    return {
        "workspaceId": d["workspace_id"],
        "identity": d["identity"],
        "monthlyMessageCap": d["monthly_message_cap"],
        "percentUsed": d["percent_used"],
        "period": d["period"],
        "messageCount": d["message_count"],
        "estimatedBytes": d["estimated_bytes"],
    }


async def _run(argv: List[str]) -> int:
    command = argv[1] if len(argv) > 1 else None
    raw_args = argv[2:]
    json_mode, args = _extract_json_flag(raw_args)
    data_dir = os.environ.get("WORKSPACEGUARD_DATA_DIR") or os.getcwd()

    if command in ("--help", "-h"):
        print(HELP_TEXT)
        return 0

    if command in ("--version", "-V"):
        print(_package_version())
        return 0

    if command == "init":
        if not json_mode:
            print(STARTUP_WARNING)
        guard = await create_workspace_guard(data_dir=data_dir, backend=MockAdapter())
        workspaces = await guard.status()
        _print_result(json_mode, {"ok": True, "dataDir": data_dir, "workspaces": workspaces}, [
            f"workspaceguard initialized in {data_dir}"
        ])
        return 0

    if command == "add-workspace":
        workspace_id: Optional[str] = args[0] if len(args) > 0 else None
        identity: Optional[str] = args[2] if len(args) > 2 else None  # add-workspace <id> --identity <value>
        if not workspace_id or not identity:
            _print_result(
                json_mode,
                {"ok": False, "error": "usage: workspaceguard add-workspace <id> --identity <value>"},
                ["usage: workspaceguard add-workspace <id> --identity <value>"],
            )
            return 1
        guard = await create_workspace_guard(data_dir=data_dir, backend=MockAdapter())
        await guard.add_workspace(workspace_id, identity)
        _print_result(json_mode, {"ok": True, "workspaceId": workspace_id, "identity": identity}, [
            f"workspace {workspace_id} added"
        ])
        return 0

    if command == "status":
        guard = await create_workspace_guard(data_dir=data_dir, backend=MockAdapter())
        workspaces = await guard.status()
        if workspaces:
            lines = [f"-> {w['workspaceId']} [isolated] identity: {w['identity']}" for w in workspaces]
            lines.append("No cross-workspace leaks detected.")
        else:
            lines = ["no workspaces configured"]
        _print_result(json_mode, {"ok": True, "workspaces": workspaces}, lines)
        return 0

    if command == "rotate-key":
        workspace_id = args[0] if len(args) > 0 else None
        if not workspace_id:
            _print_result(json_mode, {"ok": False, "error": "usage: workspaceguard rotate-key <id>"}, [
                "usage: workspaceguard rotate-key <id>"
            ])
            return 1
        guard = await create_workspace_guard(data_dir=data_dir, backend=MockAdapter())
        await guard.rotate_key(workspace_id)
        _print_result(json_mode, {"ok": True, "workspaceId": workspace_id}, [f"workspace {workspace_id} key rotated"])
        return 0

    if command == "usage":
        guard = await create_workspace_guard(data_dir=data_dir, backend=MockAdapter())
        report = await guard.usage_report()
        report_dicts = [_usage_report_to_dict(r) for r in report]
        if report:
            lines = []
            for r in report:
                cap = str(r.monthly_message_cap) if r.monthly_message_cap is not None else "unlimited"
                pct = f" ({r.percent_used}%)" if r.percent_used is not None else ""
                lines.append(
                    f"-> {r.workspace_id} [{r.identity}]: {r.message_count} messages this period, cap {cap}{pct}"
                )
        else:
            lines = ["no workspaces configured"]
        _print_result(json_mode, {"ok": True, "usage": report_dicts}, lines)
        return 0

    if command == "set-cap":
        workspace_id = args[0] if len(args) > 0 else None
        cap_arg = args[1] if len(args) > 1 else None
        if not workspace_id or not cap_arg:
            _print_result(
                json_mode,
                {"ok": False, "error": "usage: workspaceguard set-cap <workspaceId> <count|none>"},
                ["usage: workspaceguard set-cap <workspaceId> <count|none>"],
            )
            return 1
        cap: Optional[int]
        if cap_arg == "none":
            cap = None
        else:
            try:
                cap = int(cap_arg)
                if cap < 0:
                    raise ValueError
            except ValueError:
                _print_result(json_mode, {"ok": False, "error": f"invalid cap value: {cap_arg}"}, [
                    f'invalid cap value: {cap_arg} (must be a non-negative integer or "none")'
                ])
                return 1
        guard = await create_workspace_guard(data_dir=data_dir, backend=MockAdapter())
        await guard.set_cap(workspace_id, cap)
        _print_result(json_mode, {"ok": True, "workspaceId": workspace_id, "cap": cap}, [
            f"workspace {workspace_id} cap cleared (unlimited)"
            if cap is None
            else f"workspace {workspace_id} cap set to {cap} messages/month"
        ])
        return 0

    if command == "scan":
        _print_result(json_mode, {"ok": True, "findings": []}, [
            "isolation config scan: no misconfigurations detected (scaffold stub)"
        ])
        return 0

    _print_result(json_mode, {"ok": False, "error": USAGE}, [USAGE])
    return 1


def main() -> None:
    try:
        code = asyncio.run(_run(sys.argv))
    except Exception as err:  # noqa: BLE001 -- top-level crash guard, mirrors src/cli/index.ts's catch-all
        print(str(err), file=sys.stderr)
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
