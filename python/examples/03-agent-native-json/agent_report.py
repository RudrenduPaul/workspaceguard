#!/usr/bin/env python3
"""
03 -- agent-native JSON + quota enforcement.

Demonstrates the use case workspaceguard is actually designed for: an
orchestrator or monitoring agent calling it in-process (no CLI subprocess,
no shelling out), serializing a structured usage report to JSON, and
handling QuotaExceededError as a normal control-flow exception rather than
parsing terminal output. Also demonstrates the fail-closed identity
resolution: a spoofed or missing identity header is rejected, never routed
to a default workspace.

Run:
    python3 examples/03-agent-native-json/agent_report.py
"""
import asyncio
import json
import tempfile

from workspaceguard import IdentityNotFoundError, MockAdapter, QuotaExceededError, create_workspace_guard


async def agent_native_usage_json(data_dir: str) -> None:
    """An agent framework's programmatic usage check, serialized straight to JSON."""
    guard = await create_workspace_guard(data_dir=data_dir, backend=MockAdapter())
    await guard.add_workspace("alex", "alex@example.com")
    await guard.set_cap("alex", 100)
    await guard.chat("alex@example.com", "hello from an agent")

    report = await guard.usage_report()
    payload = [
        {
            "workspaceId": r.workspace_id,
            "identity": r.identity,
            "monthlyMessageCap": r.monthly_message_cap,
            "percentUsed": r.percent_used,
            "messageCount": r.message_count,
        }
        for r in report
    ]
    print("--- agent-native usage report (JSON) ---")
    print(json.dumps(payload, indent=2))
    print()


async def quota_enforcement_as_control_flow(data_dir: str) -> None:
    """QuotaExceededError is a normal exception an orchestrator can catch and act on."""
    guard = await create_workspace_guard(data_dir=data_dir, backend=MockAdapter())
    await guard.add_workspace("alex", "alex@example.com")
    await guard.set_cap("alex", 1)

    await guard.chat("alex@example.com", "first message, under cap")
    print("--- quota enforcement ---")
    try:
        await guard.chat("alex@example.com", "second message, over cap")
        print("unexpected: second message should have been blocked")
    except QuotaExceededError as err:
        print(f"blocked as expected: workspace {err.workspace_id} is at its cap of {err.cap}")
    print()


async def fail_closed_identity(data_dir: str) -> None:
    """A spoofed or missing identity header is rejected, never routed to a default workspace."""
    guard = await create_workspace_guard(data_dir=data_dir, backend=MockAdapter())
    await guard.add_workspace("alex", "alex@example.com")

    print("--- fail-closed identity resolution ---")
    for label, identity in [("missing header", None), ("spoofed/unknown header", "nobody@example.com")]:
        try:
            await guard.chat(identity, "should never reach the backend")
            print(f"unexpected: {label} should have been rejected")
        except IdentityNotFoundError:
            print(f"rejected as expected: {label}")


async def main() -> None:
    with tempfile.TemporaryDirectory() as data_dir:
        await agent_native_usage_json(data_dir)
    with tempfile.TemporaryDirectory() as data_dir:
        await quota_enforcement_as_control_flow(data_dir)
    with tempfile.TemporaryDirectory() as data_dir:
        await fail_closed_identity(data_dir)


if __name__ == "__main__":
    asyncio.run(main())
