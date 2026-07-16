# WorkspaceGuard

Per-workspace usage metering and quota caps for one shared self-hosted AI assistant deployment.

Run [Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) (or a compatible self-hosted assistant) for your whole household or small team, and there is no way to see who sent how many messages this month, or to stop one person's usage from burning through everyone else's API budget. WorkspaceGuard is a thin sidecar that adds that layer: per-workspace message counts, optional monthly caps that fail closed, and a CLI report an admin (or another agent) can read.

```bash
npx workspaceguard usage
-> alex   [alex@example.com]: 812 messages this period, cap 1000 (81%)
-> jordan [jordan@example.com]: 203 messages this period, cap unlimited
```

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

## License

MIT.
