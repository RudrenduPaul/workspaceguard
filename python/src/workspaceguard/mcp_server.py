"""MCP server for workspaceguard-cli: a generic subprocess-wrapper tool that shells out to
the installed `workspaceguard` CLI and returns its parsed JSON output.

Requires the `mcp` extra (`pip install "workspaceguard-cli[mcp]"`). Started via the
`workspaceguard-mcp` console script (stdio transport), so any MCP-compatible agent runtime
can call `run` directly instead of shelling out to the CLI itself and parsing text.

Uses `mcp.server.MCPServer`, the official SDK's current high-level server class (`mcp`
2.0.0+). Earlier `mcp` 1.x releases exposed the same `.tool()`/`.run()` pattern under
`mcp.server.fastmcp.FastMCP` -- that module was removed in the 2.0.0 release. If a future
`mcp` major version renames this again, this is the one file that needs to change.

Note: the `mcp` package itself requires Python >=3.10, while this project's own floor
(`requires-python` in pyproject.toml) is >=3.9 for the base install. That's fine -- the
`mcp` extra simply isn't installable on 3.9, the same as any other optional dependency with
a narrower Python requirement than the base package.

The `run` tool never raises: every subprocess failure mode (the CLI missing from PATH, a
launch-level OSError, a timeout, a non-zero exit, unparseable stdout) is caught and returned
as a `{"error": ...}` dict instead of propagating.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from mcp.server import MCPServer

_CLI_NAME = "workspaceguard"
_TIMEOUT_SECONDS = 30

_TOOL_DESCRIPTION = (
    "Executes one workspaceguard subcommand against the local encrypted vault and usage "
    "store, and returns its parsed JSON output. Call this to check or manage per-workspace "
    "message quotas for a shared self-hosted AI assistant deployment: see who is close to "
    "their monthly cap, register a new workspace, change a cap, rotate a compromised vault "
    "key, or audit isolation config for misconfigurations. Do not call it for anything "
    "outside workspaceguard's own domain (it has no knowledge of the assistant backend "
    "itself, only of the sidecar's quota/vault state).\n\n"
    "Prerequisites: the `workspaceguard` binary must be on PATH (bundled with this package); "
    "no API key is required. The data directory (config, vault, usage counters) defaults to "
    "$WORKSPACEGUARD_DATA_DIR or ~/.workspaceguard, and must already exist -- run "
    "run(args=['init']) once per deployment before any other command, or every call will "
    "report an uninitialized store.\n\n"
    "Side effects and mutation: 'status', 'usage', and 'scan' are read-only and safe to call "
    "at any frequency. 'init', 'add-workspace', 'set-cap', and 'rotate-key' write to the data "
    "directory on disk -- 'add-workspace' is idempotent (repeat calls for the same id are a "
    "no-op), but 'rotate-key' permanently re-encrypts a workspace's secrets under a new key "
    "and invalidates the old ciphertext, so it cannot be undone by calling it again. No "
    "network calls are made; everything is local disk I/O. This tool never raises -- a "
    "missing binary, launch failure, timeout, non-zero exit, or unparseable stdout is always "
    "returned as {\"error\": ...} instead of an exception.\n\n"
    "Parameter `args` is the literal argv you would type after `workspaceguard` on the "
    "command line, as a list of strings (flags and values as separate elements). Real "
    "examples: run(args=[\"usage\", \"--json\"]) for per-workspace message counts, caps, and "
    "percent-used this period; run(args=[\"add-workspace\", \"alex\", \"--identity\", "
    "\"alex@example.com\"]) to register a workspace (the identity value must immediately "
    "follow the id, not stand alone as a flag); run(args=[\"set-cap\", \"alex\", \"1000\"]) or "
    "run(args=[\"set-cap\", \"alex\", \"none\"]) to set or clear a monthly cap; "
    "run(args=[\"rotate-key\", \"alex\"]) to rotate a vault key; run(args=[\"scan\", "
    "\"--json\"]) to check isolation config for misconfigurations. Append '--data-dir <path>' "
    "to any call to target a non-default data directory, and pass '--json' whenever the "
    "subcommand supports it (all except 'add-workspace', 'set-cap', and 'rotate-key', which "
    "only print a short confirmation line either way).\n\n"
    "Returns a dict parsed from the CLI's stdout JSON on success (shape varies by "
    "subcommand, e.g. {\"ok\": true, \"usage\": [{\"id\": ..., \"count\": ..., \"cap\": "
    "...}, ...]} for 'usage'), or {\"returncode\", \"stdout\", \"stderr\"} if stdout wasn't "
    "valid JSON, or {\"error\": ...} on failure. Pass run(args=[\"--help\"]) or "
    "run(args=[\"<subcommand>\", \"--help\"]) to fetch the CLI's own current help text for "
    "any detail not covered here."
)

mcp = MCPServer("workspaceguard-cli")


@mcp.tool(description=_TOOL_DESCRIPTION)
def run(args: list[str]) -> dict[str, Any]:
    """Shells out to the installed `workspaceguard` CLI with `args` and returns its parsed
    JSON output.

    Example: run(args=["usage", "--json"]) returns per-workspace message counts, caps, and
    percent-used for the current period.

    Every failure mode is caught here -- a missing CLI, a launch-level OSError, a timeout, a
    non-zero exit code, or unparseable stdout -- and returned as {"error": ...} instead of
    raising, so this tool handler can never crash the server.
    """
    cli_path = shutil.which(_CLI_NAME)
    if cli_path is None:
        return {"error": f"'{_CLI_NAME}' was not found on PATH. Is workspaceguard-cli installed?"}

    try:
        result = subprocess.run(
            [cli_path, *args],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except OSError as exc:
        return {"error": f"failed to launch '{_CLI_NAME}': {exc}"}
    except subprocess.TimeoutExpired:
        return {
            "error": (
                f"'{_CLI_NAME} {' '.join(args)}' timed out after {_TIMEOUT_SECONDS}s"
            )
        }

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    if result.returncode != 0:
        return {
            "error": stderr or stdout or f"'{_CLI_NAME}' exited with code {result.returncode}",
            "returncode": result.returncode,
        }

    if not stdout:
        return {"returncode": result.returncode, "stdout": "", "stderr": stderr}

    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return {"returncode": result.returncode, "stdout": stdout, "stderr": stderr}

    if isinstance(parsed, dict):
        return parsed
    return {"result": parsed}


def main() -> None:
    """Starts the MCP server on stdio transport. Console-script entry point for
    `workspaceguard-mcp`."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
