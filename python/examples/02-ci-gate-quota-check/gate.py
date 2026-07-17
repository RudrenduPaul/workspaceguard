#!/usr/bin/env python3
"""
02 -- CI-gate-style quota check.

Demonstrates using usage_report() as an actual CI gate script: reads a
warning threshold (percent of cap) from the command line, falling back to
90, and propagates a real process exit code -- exactly what you'd drop
into a scheduled CI job watching a shared deployment's usage (see
../../../docs/integrations/ci.md for the GitHub Actions version of this
same pattern). Uses a self-contained temp data dir with MockAdapter so it
runs standalone with zero external setup; against a real deployment you'd
point WORKSPACEGUARD_DATA_DIR at the shared data directory instead.

Run:
    python3 examples/02-ci-gate-quota-check/gate.py
    python3 examples/02-ci-gate-quota-check/gate.py 50
"""
import asyncio
import sys
import tempfile

from workspaceguard import MockAdapter, create_workspace_guard


async def main() -> int:
    threshold = int(sys.argv[1]) if len(sys.argv) > 1 else 90

    with tempfile.TemporaryDirectory() as data_dir:
        guard = await create_workspace_guard(data_dir=data_dir, backend=MockAdapter())
        await guard.add_workspace("alex", "alex@example.com")
        await guard.set_cap("alex", 10)
        # Simulate a workspace that's used most of its cap this period.
        for i in range(9):
            await guard.chat("alex@example.com", f"msg-{i}")

        report = await guard.usage_report()
        over_threshold = [r for r in report if r.percent_used is not None and r.percent_used >= threshold]

        if not over_threshold:
            print(f"PASS: no workspace at or above {threshold}% of its cap.")
            return 0

        print(f"FAIL: {len(over_threshold)} workspace(s) at or above {threshold}% of cap:", file=sys.stderr)
        for r in over_threshold:
            print(f"  {r.workspace_id}: {r.message_count}/{r.monthly_message_cap} ({r.percent_used}%)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
