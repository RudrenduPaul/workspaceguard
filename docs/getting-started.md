# Getting started

WorkspaceGuard adds per-workspace usage metering and quota caps to one
shared self-hosted AI assistant deployment (Odysseus and compatible
backends): per-workspace message counts, optional monthly caps that fail
closed, and a CLI report an admin (or another agent) can read. It ships as
two packages built from the same design: an npm package (`workspaceguard-cli`,
TypeScript, repo root -- built, CI green, not yet published to npm, see
"Package status" below) and a PyPI package (`workspaceguard-cli`, Python,
`python/`, a genuine independent port).

## Package status

| Distribution | Status |
| --- | --- |
| npm (`workspaceguard-cli`) | Built, tested, CI green. Not yet published -- blocked on a manual 2FA-gated publish step on the maintainer's side. `npm install -g workspaceguard-cli` does not work yet. |
| PyPI (`workspaceguard-cli`) | Built, tested, packaged, and publish-gated. The first publish is currently pending a PyPI account-level throttle on new project names, unrelated to 2FA. Check [pypi.org/project/workspaceguard-cli](https://pypi.org/project/workspaceguard-cli/) for current live status; `pip install workspaceguard-cli` will work once it publishes. |

This page uses the Python CLI for every runnable example below. Until
either distribution is actually live, clone the repo and run the CLI from
source (see [CONTRIBUTING.md](../CONTRIBUTING.md#working-on-the-python-package-python)
for the editable-install steps) -- the commands, flags, and output shapes
shown below are exactly what you'll get once `pip install workspaceguard-cli`
is live.

## Install (once published)

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

By default the CLI reads/writes its config and usage data in the current
working directory. Set `WORKSPACEGUARD_DATA_DIR` to point it somewhere
else.

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
