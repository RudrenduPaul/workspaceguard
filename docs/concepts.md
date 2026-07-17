# Concepts

## The request pipeline

Both the npm and PyPI packages implement the same pipeline (TypeScript:
`src/core/isolation-guard.ts`; Python: `python/src/workspaceguard/isolation_guard.py`),
entered through `chat()`, the single choke point every request-handling
path must go through:

```
identity header value (untrusted, set by your reverse proxy)
     |
     v
resolve_workspace()  -> looks up the identity in workspaceguard.config.yaml.
     |                   Fails closed on any miss (IdentityNotFoundError) --
     |                   never falls back to a default workspace.
     v
check_quota()         -> QuotaExceededError if the resolved workspace has a
     |                   monthly cap and has already reached it. A workspace
     |                   with no cap set is never blocked.
     v
circuit breaker       -> calls BackendAdapter.forward_chat(). Opens after 3
     |                   consecutive failures; self-heals via a half-open
     |                   probe once the cooldown has passed.
     v
usage.record()        -> increments the resolved workspace's message count
                          and byte estimate for the current period.
```

A blocked request (fail-closed identity miss, quota exceeded, or an open
circuit) never reaches `usage.record()` -- only requests that actually
complete are counted.

## Why usage metering instead of per-user isolation

This project originally set out to add per-user workspace isolation
(separate chat history, memory, API keys) to a self-hosted AI chat
platform. A feasibility spike found that premise was false for the target
platform's current default configuration: per-user ownership on chat
history, memory, and API tokens is already enforced by default, and its
own setup docs walk through the shared-household deployment this project
targeted. Rather than ship a competing reimplementation of something the
target platform already does correctly, this project kept its tested
isolation engine as the identity-resolution substrate and built the layer
that platform genuinely does not have: usage metering and quota
enforcement per workspace.

## The isolation engine (kept, not the new work)

- **Namespace separation** (`namespace.py` / `namespace.ts`) -- chat history
  and memory get a real filesystem directory boundary per workspace
  (`<data_dir>/workspaces/<id>/chat`, `.../memory`), not a shared
  table/file with a workspace column. Easier to verify by inspection than a
  query filter.
- **Vault** (`vault.py` / `vault.ts`) -- one derived AES-256-GCM key per
  workspace, so a leaked vault file alone (without the deployment's master
  key) reveals nothing. The Python port uses the `cryptography` package's
  `AESGCM` primitive; the TypeScript original uses `node:crypto`. Both
  derive the per-workspace key as `HMAC-SHA256(master_key, "<workspace_id>:<generation>")`
  and write `iv (12 bytes) + auth tag (16 bytes) + ciphertext` to
  `<data_dir>/workspaces/<id>/vault.bin`, chmod'd `0600`.
- **Key rotation** -- `rotate_key()` increments the workspace's key
  generation *before* re-encrypting any existing secret, so the new
  ciphertext is genuinely under a different derived key. Anything
  encrypted under the old generation can no longer be decrypted once the
  generation file is bumped -- a real rotation, not a re-encryption under
  the same deterministic key.
- **Circuit breaker** (`circuit_breaker.py` / `circuit-breaker.ts`) -- fails
  closed on a backend that stops responding (3 consecutive failures opens
  the circuit) rather than silently bypassing whatever isolation/metering
  guarantees depend on a real backend call happening. A half-open probe
  after the cooldown (default 10 seconds) lets the circuit self-heal
  instead of staying open forever.

## Usage metering (the new work this project adds)

- **Per-workspace, per-month counters** (`usage.py` / `usage.ts`) -- stored
  at `<data_dir>/.workspaceguard/usage.json`, keyed by workspace id. Each
  entry tracks `period` (`"YYYY-MM"`, UTC), `messageCount`, and
  `estimatedBytes` (UTF-8 byte length of every recorded message, summed).
- **Automatic period rollover** -- reading a workspace's usage compares its
  stored `period` against the current one; a stale period (last month's
  leftover count) rolls over to a fresh zeroed bucket on read, with no
  cron job or scheduler needed, since every real read/write already knows
  what period it is.
- **Quota enforcement** -- `check_quota(workspace_id, cap)` raises
  `QuotaExceededError` once `messageCount >= cap`. `cap=None` (the default
  for a newly added workspace) means unlimited and is never blocked --
  quota enforcement is strictly opt-in per workspace via `set_cap()`.
- **The usage report** -- `usage_report()` (library) / `workspaceguard usage`
  (CLI) returns one entry per configured workspace: `workspace_id`,
  `identity`, `monthly_message_cap`, `percent_used` (`round(messageCount /
  cap * 100)`, or `None` when uncapped), plus the current period's
  `message_count` and `estimated_bytes`.

## Backend adapters

All backend-specific behavior goes through the `BackendAdapter` interface
(`name`, `health_check()`, `forward_chat(workspace_id, message)`) -- core
isolation/metering logic never imports a specific backend directly. Today
only `MockAdapter` exists (an in-memory stand-in used by the test suite and
for local experimentation); a real Odysseus HTTP adapter is blocked on a
feasibility spike into whether Odysseus's HTTP API exposes clean
interception points, or reads/writes some of its own state directly from
disk/DB in a way an HTTP-level proxy can't see. See
[integrations/backends.md](./integrations/backends.md) for what "Odysseus
and compatible backends" means concretely and how to write your own
adapter against the same interface today.

## Trust boundary

WorkspaceGuard trusts an upstream identity header (default:
`Cf-Access-Authenticated-User-Email`, configurable via
`identityHeader` in `workspaceguard.config.yaml`) to resolve the workspace.
It must never be directly reachable from the network -- only from behind
whatever trusted proxy sets that header (Cloudflare Access, Tailscale,
etc.). If this port is exposed without that proxy in front of it, anyone
can impersonate any workspace by sending an arbitrary header value. This is
documented and printed as a startup warning by `workspaceguard init`; it is
not code-enforced.

## Config and data files

- `<data_dir>/workspaceguard.config.yaml` -- `backend`, `identityHeader`,
  and the list of registered workspaces (`workspaceId`, `identity`,
  optional `monthlyMessageCap`). YAML keys are camelCase in both
  distributions, so a config file written by one is readable by the other.
- `<data_dir>/.workspaceguard/usage.json` -- the usage store described
  above.
- `<data_dir>/.workspaceguard/master.key` -- the deployment's master key
  (base64-encoded, chmod `0600`), generated on first `init()` if it doesn't
  already exist.
- `<data_dir>/workspaces/<id>/` -- per-workspace `chat/`, `memory/`
  directories, `vault.bin`, and `key-generation`.
