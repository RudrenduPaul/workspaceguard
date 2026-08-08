# Getting started

WorkspaceGuard adds per-workspace usage metering and quota caps to one
shared self-hosted AI assistant deployment (Odysseus and compatible
backends): per-workspace message counts, optional monthly caps that fail
closed, and a CLI report an admin (or another agent) can read. It ships as
two packages built from the same design: an npm package (`workspaceguard-cli`,
TypeScript, repo root -- built, CI green, and published, see
"Package status" below) and a PyPI package (`workspaceguard-cli`, Python,
`python/`, a genuine independent port, also published).

## Package status

| Distribution | Status |
| --- | --- |
| npm (`workspaceguard-cli`) | Built, tested, CI green, and published. `npm install -g workspaceguard-cli` works today. |
| PyPI (`workspaceguard-cli`) | Built, tested, packaged, and published. `pip install workspaceguard-cli` works today -- see [pypi.org/project/workspaceguard-cli](https://pypi.org/project/workspaceguard-cli/) for current live status. |

This page uses the Python CLI for every runnable example below.

## Install

```bash
pip install workspaceguard-cli
```

or with [uv](https://docs.astral.sh/uv/):

```bash
uv add workspaceguard-cli
```

## Your first run

```bash
# Register the workspaces sharing one deployment. Identity is the header
# value your reverse proxy sets after authenticating (e.g. Cloudflare
# Access) -- see "Trust boundary" below.
workspaceguard add-workspace alex --identity alex@example.com
workspaceguard add-workspace jordan --identity jordan@example.com

# Optional: cap alex at 1000 messages/month. Omit for unlimited (the default).
workspaceguard set-cap alex 1000

# See usage for every workspace.
workspaceguard status
workspaceguard usage
```

Real output:

```
-> alex [isolated] identity: alex@example.com
-> jordan [isolated] identity: jordan@example.com
No cross-workspace leaks detected.
-> alex [alex@example.com]: 0 messages this period, cap 1000 (0%)
-> jordan [jordan@example.com]: 0 messages this period, cap unlimited
```

Every command accepts `--json` for a structured, agent-native output shape:

```bash
$ workspaceguard usage --json
{"ok": true, "usage": [{"workspaceId": "alex", "identity": "alex@example.com", "monthlyMessageCap": 1000, "percentUsed": 0, "period": "2026-07", "messageCount": 0, "estimatedBytes": 0}]}
```

By default the CLI reads/writes its config, vault, and usage data under
`~/.workspaceguard` (the current user's home directory), not the current
working directory -- this used to default to the cwd, which could silently
drop a live encryption key into whatever directory the command happened to
be run from. Override the location with, in order of precedence:

1. `--data-dir <path>` on the command itself, e.g. `workspaceguard init --data-dir ./data`.
2. The `WORKSPACEGUARD_DATA_DIR` environment variable.
3. The `~/.workspaceguard` default, if neither of the above is set.

`init` also refuses to silently regenerate the master key if an existing
key file at the resolved location looks corrupted or truncated -- pass
`--force` to explicitly accept overwriting it (this permanently
invalidates anything already encrypted under the old key).

## Using the library instead of the CLI

The `chat()` entry point -- resolve workspace -> check quota -> call
backend -> record usage -- is library-only; it is not exposed as a CLI
command, since it's meant to be called from your own request-handling code
(a reverse-proxy sidecar, an orchestrator), not run interactively.

```python
import asyncio
from workspaceguard import create_workspace_guard, MockAdapter, QuotaExceededError

async def main():
    guard = await create_workspace_guard(data_dir="./data", backend=MockAdapter())
    await guard.add_workspace("alex", "alex@example.com")
    await guard.set_cap("alex", 1000)

    try:
        response = await guard.chat("alex@example.com", "hello")
    except QuotaExceededError:
        print("alex is over their monthly cap")

    report = await guard.usage_report()

asyncio.run(main())
```

`MockAdapter` is an in-memory stand-in for a real backend, useful for
testing and local experimentation. There is no real Odysseus HTTP adapter
yet -- see [concepts.md](./concepts.md#backend-adapters) and
[integrations/backends.md](./integrations/backends.md) for what that
actually means and how to bring your own adapter today.

## Next steps

- [concepts.md](./concepts.md) -- the isolation + metering pipeline, the
  vault's encryption model, and what each module actually does.
- [integrations/ci.md](./integrations/ci.md) -- wiring WorkspaceGuard's
  usage report into a CI-gate-style check.
- [integrations/backends.md](./integrations/backends.md) -- what "Odysseus
  and compatible backends" means concretely, and how to point WorkspaceGuard
  at one via `BackendAdapter`.
- The [project README](../README.md) for the full story on why this
  project pivoted from per-user isolation to usage metering.
