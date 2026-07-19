# WorkspaceGuard

Per-workspace usage metering and quota caps for one shared self-hosted AI assistant deployment.

Run [Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) (or a compatible self-hosted assistant) for your whole household or small team, and there is no way to see who sent how many messages this month, or to stop one person's usage from burning through everyone else's API budget. WorkspaceGuard is a thin sidecar that adds that layer: per-workspace message counts, optional monthly caps that fail closed, and a CLI report an admin (or another agent) can read.

```bash
npx workspaceguard usage
-> alex   [alex@example.com]: 812 messages this period, cap 1000 (81%)
-> jordan [jordan@example.com]: 203 messages this period, cap unlimited
```

![Installing workspaceguard-cli from npm and running init, add-workspace, set-cap, and usage for the first time in a terminal](./docs/demo.gif)

## Why this exists, and why it isn't what it used to be

This project originally set out to add per-user workspace isolation (separate chat history, memory, API keys) to a self-hosted AI chat platform. A feasibility spike found that premise was false for the target platform's current default configuration: per-user ownership on chat history, memory, and API tokens is already enforced by default, and its own setup docs walk through the shared-household deployment this project targeted.

Rather than ship a competing reimplementation of something the target platform already does correctly, this repo keeps its tested isolation engine (namespace separation, an AES-256-GCM vault with real key rotation, fail-closed identity resolution, a self-healing circuit breaker) as the identity-resolution substrate, and builds the layer that platform genuinely does not have: usage metering and quota enforcement per workspace. No billing, usage, or quota code exists in the target platform today.

**Free tier (this repo, MIT):** per-workspace message counting, monthly cap enforcement, a CLI/JSON usage report.
**Not in this repo:** a hosted, multi-tenant billing dashboard is a separate, closed-source product -- described here as a roadmap item, never merged into this MIT codebase.

## Install

```bash
npm install -g workspaceguard-cli
```

Or run it without installing:

```bash
npx workspaceguard-cli --help
```

The package is `workspaceguard-cli`; the command it installs is `workspaceguard`.

**Current status**: this npm package is built with CI green but is **not
yet published** to the npm registry -- blocked on a manual 2FA-gated
publish step on the maintainer's side. `npm install -g workspaceguard-cli`
does not work yet.

### Python port

A genuine, independent Python port of this same design lives in
[`python/`](./python) -- same CLI command surface, same `--json` output
shapes, its own async implementation (not a wrapper around this Node
package). It's built, tested (32/32 pytest tests passing), and packaged
for PyPI as `workspaceguard-cli`; the first publish is pending a PyPI
account-level throttle on new project names (unrelated to 2FA -- this
account's PyPI publishing needs no human 2FA). Check
[pypi.org/project/workspaceguard-cli](https://pypi.org/project/workspaceguard-cli/)
for current live status, or see [`python/README.md`](./python/README.md).

## Quickstart

```bash
# Register the workspaces sharing one deployment (identity = the header value
# your reverse proxy sets after authenticating, e.g. Cloudflare Access).
workspaceguard add-workspace alex --identity alex@example.com
workspaceguard add-workspace jordan --identity jordan@example.com

# Optional: cap alex at 1000 messages/month. Omit for unlimited (the default).
workspaceguard set-cap alex 1000

# See usage for every workspace.
workspaceguard usage
```

Every chat request that flows through the sidecar's `chat()` entry point resolves a workspace from the trusted identity header, checks that workspace's cap (if any), forwards to the backend, then records the usage -- one choke point, not scattered checks.

![Running workspaceguard status --json, rotate-key, and usage --json to show structured output and vault key rotation](./docs/usage.gif)

## CLI reference

Every command accepts `--json` for a structured, agent-native output shape instead of the human-readable text shown below.

| Command | What it does |
|---|---|
| `workspaceguard init` | Initializes the data directory and vault for this deployment. |
| `workspaceguard add-workspace <id> --identity <value>` | Registers a workspace, idempotent on repeat calls for the same id. |
| `workspaceguard status [--json]` | Lists configured workspaces. |
| `workspaceguard usage [--json]` | Per-workspace message count, cap, and percent-used for the current month. |
| `workspaceguard set-cap <id> <count\|none>` | Sets or clears a workspace's monthly message cap. |
| `workspaceguard rotate-key <id>` | Rotates a workspace's vault encryption key (invalidates the old ciphertext). |
| `workspaceguard scan [--json]` | Isolation config scan (scaffold stub, carried over from the original build). |

```bash
$ workspaceguard usage --json
{"ok":true,"usage":[{"workspaceId":"alex","identity":"alex@example.com","monthlyMessageCap":1000,"percentUsed":81,"period":"2026-07","messageCount":812,"estimatedBytes":48213}]}
```

The `--json` mode is what makes this genuinely agent-native rather than just human-convenient: an orchestrator or monitoring agent can call `workspaceguard usage --json` and parse the result directly instead of scraping terminal output.

## Library API

```ts
import { createWorkspaceGuard, MockAdapter, QuotaExceededError } from "workspaceguard-cli";

const guard = await createWorkspaceGuard({ dataDir: "./data", backend: new MockAdapter() });
await guard.addWorkspace("alex", "alex@example.com");
await guard.setCap("alex", 1000);

try {
  await guard.chat("alex@example.com", "hello");
} catch (err) {
  if (err instanceof QuotaExceededError) {
    // alex is over their monthly cap
  }
}

const report = await guard.usageReport();
```

## Architecture

- `src/core/isolation-guard.ts` -- the single choke point (`chat()`) every request flows through: resolve workspace -> check quota -> call backend -> record usage.
- `src/core/usage.ts` -- the usage-metering engine this pivot adds: per-workspace, per-month counters with automatic period rollover, and `QuotaExceededError` enforcement.
- `src/core/vault.ts`, `src/core/namespace.ts`, `src/core/circuit-breaker.ts` -- the original isolation-engine code, kept as the identity/workspace-boundary substrate the metering layer reads from, not shipped as a competing isolation product.
- `src/adapters/` -- `BackendAdapter` interface; a real Odysseus HTTP adapter is the next step (currently `MockAdapter` only, same as the original build).

Backend-specific behavior never enters `src/core/` directly -- everything goes through `BackendAdapter`.

## Trust boundary

WorkspaceGuard trusts an upstream identity header (default: `Cf-Access-Authenticated-User-Email`) to resolve the workspace. It must never be directly reachable from the network -- only from behind whatever trusted proxy sets that header (Cloudflare Access, Tailscale, etc.). This is documented, not code-enforced.

## What's real vs. not yet built

- Real, tested (20/20 passing): usage metering, quota enforcement, the original isolation engine (vault, namespace separation, circuit breaker), CLI with `--json` mode.
- Not yet built: a real Odysseus HTTP adapter (only `MockAdapter` exists so far), a hosted managed billing dashboard (deliberately out of scope for this MIT repo).

## Docs

- [docs/getting-started.md](./docs/getting-started.md)
- [docs/concepts.md](./docs/concepts.md)
- [docs/integrations/ci.md](./docs/integrations/ci.md)
- [docs/integrations/backends.md](./docs/integrations/backends.md)

## FAQ

**Q: What does WorkspaceGuard actually do?**
A: It adds per-workspace usage metering and quota enforcement in front of one shared self-hosted AI assistant deployment. Concretely: it counts messages per workspace per month, lets you set an optional cap that fails closed once hit, and gives you (or an agent) a `workspaceguard usage` report. It does not add chat history, memory, or API key isolation itself -- that already exists by default in the target platform (see "Why this exists" above), and WorkspaceGuard's own isolation code (`src/core/vault.ts`, `src/core/namespace.ts`) is kept only as the identity-resolution substrate the metering layer reads from.

**Q: What's WorkspaceGuard's actual differentiator?**
A: Narrow scope done well, not a full billing platform and not a reimplementation of isolation the backend already has. Every request flows through one choke point (`chat()` in `src/core/isolation-guard.ts`: resolve workspace, check quota, call backend, record usage), quota enforcement fails closed (a corrupted or unreadable usage store blocks requests instead of silently resetting everyone's usage to zero, fixed in 0.1.1 per [CHANGELOG.md](./CHANGELOG.md)), and every command supports `--json` for agent-native output.

**Q: How does WorkspaceGuard compare to Odysseus?**
A: It's not a competing product. WorkspaceGuard is a sidecar that sits in front of an Odysseus deployment (or a compatible backend); it doesn't replace anything Odysseus already does.

| Capability | WorkspaceGuard | Odysseus (native) |
|---|---|---|
| Per-user isolation (chat history, memory, API keys) | Not reimplemented; treated as already solved | Yes, built in by default |
| Per-workspace message counting | Yes | No |
| Monthly quota caps, fail-closed | Yes | No |
| CLI / `--json` usage report | Yes | No |

**Q: What platforms does WorkspaceGuard run on?**
A: The npm package (`workspaceguard-cli`) requires Node.js 20 or newer (`engines.node` in `package.json`). The Python port in [`python/`](./python) requires Python 3.9 through 3.13 (see the classifiers in `python/pyproject.toml`). Neither distribution ships a platform-specific binary, so both run wherever their respective runtime does (Linux, macOS, Windows).

**Q: Is WorkspaceGuard a CLI, a library, or both?**
A: Both, in both distributions. The CLI (`workspaceguard <command>`) covers `init`, `add-workspace`, `status`, `usage`, `set-cap`, `rotate-key`, and `scan`. The same functionality is also importable directly (`createWorkspaceGuard` from the TypeScript package, `create_workspace_guard` from the Python package) for anything that wants to call it from code instead of shelling out.

**Q: What's a real current limitation I should know about before relying on this?**
A: The only backend adapter implemented today is `MockAdapter`, an in-memory adapter used for tests and local experimentation. A real Odysseus HTTP adapter has not been built yet (see [docs/integrations/backends.md](./docs/integrations/backends.md)), so WorkspaceGuard does not yet forward live chat traffic to an actual Odysseus deployment. The metering and quota logic itself is real and tested; the network bridge to a live backend is the piece still outstanding.

**Q: Does WorkspaceGuard need its own API keys, or hold any of my AI provider credentials?**
A: No. The only backend adapter that exists right now (`MockAdapter`) is in-memory and calls no external API. All backend-specific behavior is isolated behind the `BackendAdapter` interface (`src/adapters/`), so WorkspaceGuard's own code never needs to see provider credentials directly.

**Q: Is WorkspaceGuard free to use commercially?**
A: Yes. This repository is MIT licensed in full, no dual-licensing and no feature gate. The mention above of a hosted, multi-tenant billing dashboard is a separate, closed-source product described only as a roadmap item; no billing-dashboard code lives in, or is withheld from, this MIT codebase.

## Contributing and security

See [CONTRIBUTING.md](./CONTRIBUTING.md) and [SECURITY.md](./SECURITY.md).
Notable changes are tracked in [CHANGELOG.md](./CHANGELOG.md).

## License

MIT.
