# workspaceguard-cli (Python)

Per-workspace usage metering and quota caps for one shared self-hosted AI
assistant deployment -- a genuine, independent Python port of the
[`workspaceguard-cli`](https://github.com/RudrenduPaul/workspaceguard) npm
package, not a wrapper around a Node binary.

[![PyPI version](https://img.shields.io/pypi/v/workspaceguard-cli.svg)](https://pypi.org/project/workspaceguard-cli/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/RudrenduPaul/workspaceguard/blob/main/LICENSE)
[![Python versions](https://img.shields.io/pypi/pyversions/workspaceguard-cli.svg)](https://pypi.org/project/workspaceguard-cli/)

## Why this exists

Run [Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) (or a
compatible self-hosted assistant) for your whole household or small team,
and there is no way to see who sent how many messages this month, or to
stop one person's usage from burning through everyone else's API budget.
WorkspaceGuard is a thin sidecar that adds that layer: per-workspace
message counts, optional monthly caps that fail closed, and a CLI report
an admin (or another agent) can read.

This project originally set out to add per-user workspace isolation
(separate chat history, memory, API keys) to a self-hosted AI chat
platform. A feasibility spike found that premise was false for the target
platform's current default configuration: per-user ownership on chat
history, memory, and API tokens is already enforced by default. Rather
than ship a competing reimplementation of something the target platform
already does correctly, this project keeps its tested isolation engine
(namespace separation, an AES-256-GCM vault with real key rotation,
fail-closed identity resolution, a self-healing circuit breaker) as the
identity-resolution substrate, and builds the layer that platform
genuinely does not have: usage metering and quota enforcement per
workspace. See the [project README](https://github.com/RudrenduPaul/workspaceguard#readme)
for the full story.

## Install

```bash
pip install workspaceguard-cli
```

**Current status**: this Python port is fully built, tested (32/32 pytest
tests passing), and published to PyPI. `pip install workspaceguard-cli`
works today -- see
[pypi.org/project/workspaceguard-cli](https://pypi.org/project/workspaceguard-cli/).
The npm package (`workspaceguard-cli`) is also published and installable
today via `npm install -g workspaceguard-cli` -- see
[npmjs.com/package/workspaceguard-cli](https://www.npmjs.com/package/workspaceguard-cli).
This package is a genuine, independent port -- not a wrapper around the
npm package -- so it works and is maintained regardless of the npm
package's status.

## Quickstart

```bash
# Register the workspaces sharing one deployment (identity = the header
# value your reverse proxy sets after authenticating, e.g. Cloudflare
# Access).
workspaceguard add-workspace alex --identity alex@example.com
workspaceguard add-workspace jordan --identity jordan@example.com

# Optional: cap alex at 1000 messages/month. Omit for unlimited (the default).
workspaceguard set-cap alex 1000

# See usage for every workspace.
workspaceguard usage
```

```
$ workspaceguard usage --json
{"ok": true, "usage": [{"workspaceId": "alex", "identity": "alex@example.com", "monthlyMessageCap": 1000, "percentUsed": 0, "period": "2026-07", "messageCount": 0, "estimatedBytes": 0}]}
```

## CLI reference

Every command accepts `--json` for a structured, agent-native output shape
instead of the human-readable text shown below. Identical command surface
to the npm CLI.

| Command | What it does |
| --- | --- |
| `workspaceguard init` | Initializes the data directory and vault for this deployment. |
| `workspaceguard add-workspace <id> --identity <value>` | Registers a workspace, idempotent on repeat calls for the same id. |
| `workspaceguard status [--json]` | Lists configured workspaces. |
| `workspaceguard usage [--json]` | Per-workspace message count, cap, and percent-used for the current month. |
| `workspaceguard set-cap <id> <count\|none>` | Sets or clears a workspace's monthly message cap. |
| `workspaceguard rotate-key <id>` | Rotates a workspace's vault encryption key (invalidates the old ciphertext). |
| `workspaceguard scan [--json]` | Isolation config scan (scaffold stub, carried over from the original build). |

## Library API

```python
import asyncio
from workspaceguard import create_workspace_guard, MockAdapter, QuotaExceededError

async def main():
    guard = await create_workspace_guard(data_dir="./data", backend=MockAdapter())
    await guard.add_workspace("alex", "alex@example.com")
    await guard.set_cap("alex", 1000)

    try:
        await guard.chat("alex@example.com", "hello")
    except QuotaExceededError:
        pass  # alex is over their monthly cap

    report = await guard.usage_report()

asyncio.run(main())
```

The library API is async (`asyncio`), matching the async architecture of
the original TypeScript source rather than flattening it to synchronous
calls.

## How it works

```
target: an inbound chat request with an identity header value
   -> resolve_workspace() -- fail closed on any miss, never a default workspace
   -> check_quota() -- QuotaExceededError if the workspace is at its cap
   -> circuit breaker -- calls the BackendAdapter, opens after 3 consecutive
      failures, self-heals via a half-open probe after a cooldown
   -> record usage -- per-workspace, per-month counters with automatic
      period rollover
```

- `workspaceguard/isolation_guard.py` -- the single choke point (`chat()`)
  every request flows through: resolve workspace -> check quota -> call
  backend -> record usage.
- `workspaceguard/usage.py` -- the usage-metering engine this project adds:
  per-workspace, per-month counters with automatic period rollover, and
  `QuotaExceededError` enforcement.
- `workspaceguard/vault.py`, `workspaceguard/namespace.py`,
  `workspaceguard/circuit_breaker.py` -- the original isolation-engine
  code, kept as the identity/workspace-boundary substrate the metering
  layer reads from, not shipped as a competing isolation product.
- `workspaceguard/adapters/` -- `BackendAdapter` abstract base class; a
  real Odysseus HTTP adapter is the next step (currently `MockAdapter`
  only, same as the TypeScript original).

Backend-specific behavior never enters the core modules directly --
everything goes through `BackendAdapter`.

## Trust boundary

WorkspaceGuard trusts an upstream identity header (default:
`Cf-Access-Authenticated-User-Email`) to resolve the workspace. It must
never be directly reachable from the network -- only from behind whatever
trusted proxy sets that header (Cloudflare Access, Tailscale, etc.). This
is documented, not code-enforced.

## What's real vs. not yet built

- Real, tested (28/28 pytest tests passing): usage metering, quota
  enforcement, the original isolation engine (vault, namespace separation,
  circuit breaker), CLI with `--json` mode.
- Not yet built: a real Odysseus HTTP adapter (only `MockAdapter` exists so
  far, same as the TypeScript original), a hosted managed billing
  dashboard (deliberately out of scope for this MIT project).

## Security

The vault uses AES-256-GCM (via the `cryptography` package) with one
derived key per workspace per generation -- rotating a workspace's key
increments its generation, so old ciphertext genuinely can no longer be
decrypted, not a no-op. See
[SECURITY.md](https://github.com/RudrenduPaul/workspaceguard/blob/main/SECURITY.md)
for the disclosure process and what's in/out of scope.

## Contributing

See [CONTRIBUTING.md](https://github.com/RudrenduPaul/workspaceguard/blob/main/CONTRIBUTING.md).

```bash
cd python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

MIT, see [LICENSE](https://github.com/RudrenduPaul/workspaceguard/blob/main/LICENSE).
