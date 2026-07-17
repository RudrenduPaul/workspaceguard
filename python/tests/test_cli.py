"""
CLI end-to-end tests. Not a direct TS port (src/cli/index.ts has no
dedicated test file in the TypeScript suite) but exercises the same command
surface: init, add-workspace, status, usage, set-cap, rotate-key, scan, and
the --json toggle on each, run against a real temp data directory.
"""
from __future__ import annotations

import json
import tempfile

from workspaceguard.cli import _run


async def _run_in(data_dir: str, *args: str) -> tuple:
    import io
    import contextlib

    argv = ["workspaceguard", *args]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        import os

        old = os.environ.get("WORKSPACEGUARD_DATA_DIR")
        os.environ["WORKSPACEGUARD_DATA_DIR"] = data_dir
        try:
            code = await _run(argv)
        finally:
            if old is None:
                os.environ.pop("WORKSPACEGUARD_DATA_DIR", None)
            else:
                os.environ["WORKSPACEGUARD_DATA_DIR"] = old
    return code, buf.getvalue()


async def test_init_creates_data_dir_and_reports_ok():
    with tempfile.TemporaryDirectory() as data_dir:
        code, output = await _run_in(data_dir, "init", "--json")
        assert code == 0
        payload = json.loads(output)
        assert payload["ok"] is True
        assert payload["workspaces"] == []


async def test_add_workspace_then_status_json():
    with tempfile.TemporaryDirectory() as data_dir:
        code, _ = await _run_in(data_dir, "add-workspace", "alex", "--identity", "alex@example.com", "--json")
        assert code == 0

        code, output = await _run_in(data_dir, "status", "--json")
        assert code == 0
        payload = json.loads(output)
        assert payload["ok"] is True
        assert payload["workspaces"] == [{"workspaceId": "alex", "identity": "alex@example.com"}]


async def test_add_workspace_missing_identity_fails_with_usage_message():
    with tempfile.TemporaryDirectory() as data_dir:
        code, output = await _run_in(data_dir, "add-workspace", "alex", "--json")
        assert code == 1
        payload = json.loads(output)
        assert payload["ok"] is False


async def test_set_cap_and_usage_json_round_trip():
    with tempfile.TemporaryDirectory() as data_dir:
        await _run_in(data_dir, "add-workspace", "alex", "--identity", "alex@example.com", "--json")
        code, output = await _run_in(data_dir, "set-cap", "alex", "1000", "--json")
        assert code == 0
        payload = json.loads(output)
        assert payload == {"ok": True, "workspaceId": "alex", "cap": 1000}

        code, output = await _run_in(data_dir, "usage", "--json")
        assert code == 0
        payload = json.loads(output)
        assert payload["ok"] is True
        assert len(payload["usage"]) == 1
        entry = payload["usage"][0]
        assert entry["workspaceId"] == "alex"
        assert entry["monthlyMessageCap"] == 1000
        assert entry["messageCount"] == 0
        assert entry["percentUsed"] == 0


async def test_set_cap_invalid_value_fails():
    with tempfile.TemporaryDirectory() as data_dir:
        await _run_in(data_dir, "add-workspace", "alex", "--identity", "alex@example.com", "--json")
        code, output = await _run_in(data_dir, "set-cap", "alex", "not-a-number", "--json")
        assert code == 1
        payload = json.loads(output)
        assert payload["ok"] is False


async def test_set_cap_none_clears_cap():
    with tempfile.TemporaryDirectory() as data_dir:
        await _run_in(data_dir, "add-workspace", "alex", "--identity", "alex@example.com", "--json")
        await _run_in(data_dir, "set-cap", "alex", "5", "--json")
        code, output = await _run_in(data_dir, "set-cap", "alex", "none", "--json")
        assert code == 0
        payload = json.loads(output)
        assert payload["cap"] is None


async def test_rotate_key_without_workspace_id_fails():
    with tempfile.TemporaryDirectory() as data_dir:
        code, output = await _run_in(data_dir, "rotate-key", "--json")
        assert code == 1
        payload = json.loads(output)
        assert payload["ok"] is False


async def test_rotate_key_succeeds_for_existing_workspace():
    with tempfile.TemporaryDirectory() as data_dir:
        await _run_in(data_dir, "add-workspace", "alex", "--identity", "alex@example.com", "--json")
        code, output = await _run_in(data_dir, "rotate-key", "alex", "--json")
        assert code == 0
        payload = json.loads(output)
        assert payload == {"ok": True, "workspaceId": "alex"}


async def test_scan_stub_returns_empty_findings():
    with tempfile.TemporaryDirectory() as data_dir:
        code, output = await _run_in(data_dir, "scan", "--json")
        assert code == 0
        payload = json.loads(output)
        assert payload == {"ok": True, "findings": []}


async def test_unknown_command_prints_usage_and_fails():
    with tempfile.TemporaryDirectory() as data_dir:
        code, output = await _run_in(data_dir, "bogus-command", "--json")
        assert code == 1
        payload = json.loads(output)
        assert payload["ok"] is False
        assert "usage:" in payload["error"]


async def test_human_output_for_status_with_no_workspaces():
    with tempfile.TemporaryDirectory() as data_dir:
        code, output = await _run_in(data_dir, "status")
        assert code == 0
        assert "no workspaces configured" in output


async def test_human_output_for_usage_with_cap_shows_percent():
    with tempfile.TemporaryDirectory() as data_dir:
        await _run_in(data_dir, "add-workspace", "alex", "--identity", "alex@example.com", "--json")
        await _run_in(data_dir, "set-cap", "alex", "10", "--json")
        code, output = await _run_in(data_dir, "usage")
        assert code == 0
        assert "cap 10" in output
        assert "(0%)" in output
