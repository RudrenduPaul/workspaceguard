"""
CLI end-to-end tests. Not a direct TS port (src/cli/index.ts has no
dedicated test file in the TypeScript suite) but exercises the same command
surface: init, add-workspace, status, usage, set-cap, rotate-key, scan, and
the --json toggle on each, run against a real temp data directory.
"""
from __future__ import annotations

import base64
import json
import os
import tempfile

from workspaceguard.cli import _run
from workspaceguard.paths import default_data_dir


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


# --- --data-dir flag, default location, and overwrite protection ---
# Regression coverage: `init` used to silently default to the bare cwd with
# no flag/env override, and would generate a key with no distinction
# between "no key yet" and "the existing key file looks wrong."


async def _run_plain(*args: str) -> tuple:
    """Runs the CLI without pre-seeding WORKSPACEGUARD_DATA_DIR, so --data-dir
    (or the real default) is exercised as a real caller would hit it.
    Mirrors main()'s top-level try/except -- _run() itself can raise (e.g.
    a corrupted master key), and only main() converts that into exit code 1."""
    import contextlib
    import io

    argv = ["workspaceguard", *args]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = await _run(argv)
        return code, buf.getvalue()
    except Exception:
        return 1, buf.getvalue()


def test_default_data_dir_resolves_under_home_not_cwd():
    resolved = default_data_dir()
    assert resolved == os.path.join(os.path.expanduser("~"), ".workspaceguard")
    assert resolved != os.getcwd()


async def test_init_writes_into_the_resolved_data_dir_flag_not_cwd():
    old_env = os.environ.pop("WORKSPACEGUARD_DATA_DIR", None)
    cwd_before = os.getcwd()
    try:
        with tempfile.TemporaryDirectory() as data_dir:
            code, output = await _run_plain("init", "--data-dir", data_dir, "--json")
            assert code == 0
            payload = json.loads(output)
            assert payload["ok"] is True
            assert payload["dataDir"] == data_dir

            key_path = os.path.join(data_dir, ".workspaceguard", "master.key")
            with open(key_path, "r", encoding="utf-8") as fh:
                raw = fh.read().strip()
            assert len(base64.b64decode(raw)) == 32

            assert os.getcwd() == cwd_before
            assert not os.path.exists(os.path.join(cwd_before, ".workspaceguard", "master.key"))
    finally:
        if old_env is not None:
            os.environ["WORKSPACEGUARD_DATA_DIR"] = old_env


async def test_data_dir_flag_takes_precedence_over_env_var():
    old_env = os.environ.get("WORKSPACEGUARD_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory() as env_dir, tempfile.TemporaryDirectory() as flag_dir:
            os.environ["WORKSPACEGUARD_DATA_DIR"] = env_dir
            code, output = await _run_plain("init", "--data-dir", flag_dir, "--json")
            assert code == 0
            payload = json.loads(output)
            assert payload["dataDir"] == flag_dir
            assert not os.path.exists(os.path.join(env_dir, ".workspaceguard", "master.key"))
            assert os.path.exists(os.path.join(flag_dir, ".workspaceguard", "master.key"))
    finally:
        if old_env is None:
            os.environ.pop("WORKSPACEGUARD_DATA_DIR", None)
        else:
            os.environ["WORKSPACEGUARD_DATA_DIR"] = old_env


async def test_init_refuses_to_silently_regenerate_a_corrupted_master_key_without_force():
    with tempfile.TemporaryDirectory() as data_dir:
        key_dir = os.path.join(data_dir, ".workspaceguard")
        os.makedirs(key_dir, exist_ok=True)
        key_path = os.path.join(key_dir, "master.key")
        with open(key_path, "w", encoding="utf-8") as fh:
            fh.write("not-a-valid-key")

        code, _ = await _run_plain("init", "--data-dir", data_dir, "--json")
        assert code == 1

        with open(key_path, "r", encoding="utf-8") as fh:
            still_raw = fh.read()
        assert still_raw == "not-a-valid-key"


async def test_init_force_regenerates_over_a_corrupted_master_key():
    with tempfile.TemporaryDirectory() as data_dir:
        key_dir = os.path.join(data_dir, ".workspaceguard")
        os.makedirs(key_dir, exist_ok=True)
        key_path = os.path.join(key_dir, "master.key")
        with open(key_path, "w", encoding="utf-8") as fh:
            fh.write("not-a-valid-key")

        code, _ = await _run_plain("init", "--data-dir", data_dir, "--force", "--json")
        assert code == 0

        with open(key_path, "r", encoding="utf-8") as fh:
            raw = fh.read().strip()
        assert raw != "not-a-valid-key"
        assert len(base64.b64decode(raw)) == 32
