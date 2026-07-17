#!/usr/bin/env python3
"""
01 -- basic usage report.

The simplest possible use of the workspaceguard library: create a guard
backed by MockAdapter, register two workspaces, set a cap on one, send a
few chat messages, then read back the usage report. Runs standalone with
no setup beyond `pip install -e .` (or `pip install workspaceguard-cli`)
from the python/ directory -- everything happens in a temp directory, no
real backend needed.

Run:
    python3 examples/01-basic-usage-report/report.py
"""
import asyncio
import tempfile

from workspaceguard import MockAdapter, create_workspace_guard


async def main() -> None:
    with tempfile.TemporaryDirectory() as data_dir:
        guard = await create_workspace_guard(data_dir=data_dir, backend=MockAdapter())

        await guard.add_workspace("alex", "alex@example.com")
        await guard.add_workspace("jordan", "jordan@example.com")
        await guard.set_cap("alex", 5)  # jordan stays unlimited (the default)

        for i in range(3):
            await guard.chat("alex@example.com", f"message {i} from alex")
        await guard.chat("jordan@example.com", "one message from jordan")

        report = await guard.usage_report()

        print("--- usage report ---")
        for entry in report:
            cap = entry.monthly_message_cap if entry.monthly_message_cap is not None else "unlimited"
            pct = f" ({entry.percent_used}%)" if entry.percent_used is not None else ""
            print(
                f"{entry.workspace_id} [{entry.identity}]: "
                f"{entry.message_count} messages this period, cap {cap}{pct}"
            )


if __name__ == "__main__":
    asyncio.run(main())
