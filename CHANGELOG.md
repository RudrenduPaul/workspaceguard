# Changelog

All notable changes to WorkspaceGuard are documented in this file. This
covers both distributions -- the npm package (`workspaceguard-cli`, TS/JS,
repo root) and the PyPI package (`workspaceguard-cli`, Python, `python/`)
-- since they implement the same design; entries note which distribution
they apply to.

## [0.1.1 / Python 0.1.1] - Security fixes

Four fixes from a security review of the core isolation/metering engine, all applied to both distributions:

- **Quota enforcement used to fail open on a usage-store read error.** `loadUsage`/`load_usage` caught every error (permission errors, disk errors, a corrupted or truncated `usage.json`) and silently returned an empty store, resetting every workspace's usage to zero -- the opposite of the documented "fails closed" behavior. Now only a missing file (no usage recorded yet) is treated as empty; every other error propagates and blocks the request.
- **Quota check-then-record was an unlocked race (TOCTOU).** `checkQuota()`/`record()` were separate, unlocked read-modify-write operations, so N concurrent requests at `cap-1` could all read the same pre-cap count and all proceed, and concurrent `record()` calls could lose updates to each other. The quota check, backend call, and usage record are now wrapped in a single per-workspace in-process lock (`withLock` / `asyncio.Lock`), serializing requests to the same workspace without affecting concurrency across different workspaces.
- **Identity comparison had no normalization.** `Alex@Example.com ` and `alex@example.com` registered as two different identities, letting the duplicate-identity guard be evaded by a near-duplicate and producing two workspaces (two independent quotas) for one real-world identity. Identity comparisons are now case- and whitespace-insensitive; the originally-entered casing is still stored.
- **`workspaceId` was used unsanitized as a filesystem path segment and object key.** No allowlist was applied before a workspace id reached vault/namespace path construction, and a workspace literally named `__proto__` would set the in-memory usage store's own prototype instead of an own property. `addWorkspace`/`upsert_workspace` now reject any workspace id that isn't `[a-zA-Z0-9_-]+` or that matches a reserved name (`__proto__`, `constructor`, `prototype`, `.`, `..`).

Also: fixed a rounding-parity bug where Python's `round()` (round-half-to-even) diverged from the TS original's `Math.round()` (round-half-up) for exact-half `percentUsed` values (e.g. 12.5% -> 12 vs 13), despite both READMEs documenting the two distributions' `--json` output as identical. Pinned both CI/publish GitHub Actions workflows to commit SHAs instead of mutable tags (higher-impact in `publish.yml`, which handles `NPM_TOKEN` and OIDC provenance), added an explicit `permissions: contents: read` block to `ci.yml`, and added a Python test job to `ci.yml` -- previously only the TypeScript suite ran in CI, so the Python port's tests never executed on push/PR.

## [Python 0.1.0] - 2026-07-16

Initial Python port, built, tested, and packaged for PyPI as
`workspaceguard-cli`.

**Package status at this release**: the wheel and sdist are built and
verified (installs and runs correctly end to end in a fresh venv,
`twine check` passes), but the first PyPI publish is pending -- blocked by
a PyPI account-level throttle on registering brand-new project names
("429 Too many new projects created"), unrelated to 2FA (this account's
PyPI publishing needs no human 2FA). Separately, the npm package is built
with CI green but is also **not yet published** to the npm registry --
blocked on a manual 2FA-gated publish step on the maintainer's side.
Neither `pip install workspaceguard-cli` nor `npm install -g
workspaceguard-cli` is live as of this entry; check
[pypi.org/project/workspaceguard-cli](https://pypi.org/project/workspaceguard-cli/)
for current status. Once both unblock, the two distributions are intended
to be maintained together as equally first-class packages, same as this
account's other dual-distribution projects.

### Added

- `workspaceguard <init|add-workspace|status|rotate-key|usage|set-cap|scan>`
  CLI (console script `workspaceguard`, package `workspaceguard`) with the
  same command surface, flags, and human/`--json` output shapes as the
  TypeScript CLI (`src/cli/index.ts`).
- Programmatic async library API:
  `from workspaceguard import create_workspace_guard, MockAdapter, QuotaExceededError`,
  returning the same `WorkspaceUsageReport` shape the CLI's `usage --json`
  output serializes.
- Full isolation + metering engine reimplemented as genuine Python logic,
  module-for-module against the TypeScript source: `isolation_guard.py`
  (the `chat()` choke point), `usage.py` (per-workspace/per-month metering
  and `QuotaExceededError`), `vault.py` (AES-256-GCM per-workspace
  encryption via the `cryptography` package, real key rotation),
  `namespace.py` (per-workspace directory boundaries), `circuit_breaker.py`
  (fail-closed backend calls with half-open self-healing), `config.py`
  (`workspaceguard.config.yaml` load/save, camelCase keys for
  cross-distribution file compatibility).
- `BackendAdapter` abstract base class and `MockAdapter` (in-memory,
  test/experimentation only), ported from `src/adapters/mock.ts`. No real
  Odysseus HTTP adapter exists in either distribution yet -- see
  `docs/integrations/backends.md`.
- Full pytest suite (32 tests) ported from the TypeScript node:test suite
  (`src/core/usage.test.ts`, `src/core/isolation-guard.test.ts`), plus a
  CLI end-to-end suite not present in the TS suite.
- `docs/getting-started.md`, `docs/concepts.md`,
  `docs/integrations/ci.md`, `docs/integrations/backends.md`.
- `python/examples/` -- three runnable examples against the real library
  API: a basic usage report, a CI-gate-style quota check, and an
  agent-native JSON + quota-enforcement + fail-closed-identity demo.

### Notes

- Verified: all 32 pytest tests pass; all three `python/examples/` scripts
  run end to end against a real (temp-directory) `MockAdapter` deployment,
  including a real `QuotaExceededError` block and real fail-closed identity
  rejection with structured log lines.
- The vault's on-disk format (12-byte IV + 16-byte GCM auth tag +
  ciphertext) is kept identical between the TypeScript (`node:crypto`) and
  Python (`cryptography`'s `AESGCM`) implementations, though a real
  deployment would run one distribution or the other against a given data
  directory, not both simultaneously.
