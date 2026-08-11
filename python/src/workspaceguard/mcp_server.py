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

_FALLBACK_DESCRIPTION = (
    "Runs the workspaceguard CLI with the given argument list and returns its parsed JSON "
    "output. workspaceguard meters per-workspace usage and enforces fail-closed monthly "
    "message caps for a shared self-hosted AI assistant deployment. Commands: 'init', "
    "'add-workspace <id> --identity <value>', 'status', 'usage', 'set-cap <id> <count|none>', "
    "'rotate-key <id>', and 'scan'. All accept '--data-dir <path>'. Always pass '--json' so "
    "the output can be parsed as structured data, e.g. run(args=['usage', '--json']) or "
    "run(args=['status', '--json'])."
)


def _build_tool_description() -> str:
    """Builds the `run` tool's description from the real `workspaceguard --help` output at
    import time, so the description an agent sees always matches the installed CLI's
    actual subcommands. Falls back to a safe static description if the CLI can't be
    found on PATH or the subprocess call fails for any reason."""
    cli_path = shutil.which(_CLI_NAME)
    if cli_path is None:
        return _FALLBACK_DESCRIPTION

    try:
        result = subprocess.run(
            [cli_path, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return _FALLBACK_DESCRIPTION

    help_text = (result.stdout or result.stderr or "").strip()
    if not help_text:
        return _FALLBACK_DESCRIPTION

    return (
        "Runs the workspaceguard CLI with the given argument list and returns its parsed "
        f"JSON output. Always pass '--json' when the subcommand supports it. Real "
        f"`workspaceguard --help` output:\n\n{help_text}"
    )


_TOOL_DESCRIPTION = _build_tool_description()

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
