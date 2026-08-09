# Changelog

All notable changes to WorkspaceGuard are documented in this file. This
covers both distributions -- the npm package (`workspaceguard-cli`, TS/JS,
repo root) and the PyPI package (`workspaceguard-cli`, Python, `python/`)
-- since they implement the same design; entries note which distribution
they apply to.

## [0.1.6] - npm only -- fix silent no-op on global/npx install

**Known issue on the currently published `0.1.5` npm release**: a clean
`npm install -g workspaceguard-cli` (or an `npx workspaceguard-cli`
invocation), followed by running `workspaceguard --help`, `--version`, or
any command, produces zero output and exits `0` -- the CLI's entrypoint
guard in `src/cli/index.ts` never runs. Root cause: the guard compared
`import.meta.url` against `pathToFileURL(process.argv[1]).href` without
first resolving symlinks, and both a global npm `bin` install and an
`npx` run wire `workspaceguard` up as a symlink -- `process.argv[1]`
stays the symlink path while `import.meta.url` resolves through it to the
real target file, so the two never matched. The Python distribution
(`python/`) is unaffected -- this is fixed in this version:

- **Resolved `process.argv[1]` via `fs.realpathSync` before comparing**
  against `import.meta.url`, so the guard correctly recognizes itself
  when invoked through a symlink (global npm bin, npx) as well as a
  direct `node dist/cli/index.js` run.
- Verified via `npm pack` + a global install into a disposable prefix
  (reproducing the real symlinked-bin install path): `workspaceguard
  --help` and `workspaceguard --version` now print the documented output
  and exit `0`.
- No behavior change for direct/non-symlinked invocations; all 41
  existing tests pass unchanged.

## [0.1.5 / Python 0.1.5] - Data directory default and overwrite protection

Security/UX fix from a same-day audit reproducing the documented
quickstart: `workspaceguard init` silently wrote a live AES-256-GCM
`master.key` into whatever directory the command was run from, with no
flag to redirect it (an undocumented `WORKSPACEGUARD_DATA_DIR` env var
already existed in the code but was easy to miss and not surfaced as a
`--help` option), and no distinction between "no key yet" and "the
existing key file looks wrong" before deciding whether to generate one.
Applied identically to both distributions (`src/core/`, `python/src/workspaceguard/`):

- **Changed default data directory from the current working directory to
  `~/.workspaceguard`.** New `src/core/paths.ts` / `python/src/workspaceguard/paths.py`
  (`defaultDataDir()` / `default_data_dir()`) resolve a stable,
  cwd-independent default with no new dependency (no cross-platform
  app-data-directory package was already a dependency of either
  distribution).
- **Added a real `--data-dir <path>` CLI flag** to every command, not just
  `init` (`workspaceguard status --data-dir ~/.workspaceguard`, etc.).
  Resolution order is now `--data-dir` flag, then `WORKSPACEGUARD_DATA_DIR`
  env var (unchanged, now documented in `--help` and both READMEs), then
  `~/.workspaceguard`.
- **Added overwrite protection to `Vault.init()`/`vault.init()`.** Only a
  genuinely missing key file (`ENOENT` / `FileNotFoundError`) is treated as
  "no key yet, generate one" -- any other read failure (permission denied,
  the path is a directory, a disk error) now propagates instead of being
  silently swallowed into "no key yet," which previously risked generating
  and writing a fresh key over an existing one on an ambiguous read error.
  If a key file exists but doesn't decode to a valid 32-byte key
  (corrupted or truncated), `init` now refuses to regenerate it and exits
  non-zero with an explanation, unless the new `--force` flag is passed --
  regenerating over a corrupted key permanently invalidates anything
  already encrypted under the old one, so this is opt-in, not automatic.
- Documented all of the above in `docs/getting-started.md`, the root
  README, and `python/README.md`'s CLI reference (new "Global options"
  section in each).
- New tests: `src/core/vault.test.ts`, `src/cli/index.test.ts`,
  `python/tests/test_vault.py`, plus additions to
  `python/tests/test_cli.py`, covering the new default location,
  `--data-dir` precedence over the env var, and the corrupted-key
  overwrite-protection/`--force` behavior in both distributions.

## [0.1.3 / Python 0.1.3] - Pending publish -- CLI fix, metadata, doc corrections

**Known issue on the currently published `0.1.2` release of both
distributions**: `workspaceguard -h` / `--help` and `workspaceguard -V` /
`--version` do not match the CLI reference table in either README --
running either flag falls through to the default unknown-command branch,
which prints a bare one-line usage string and exits with status `1`
instead of printing the documented help/version text and exiting `0`.
This is fixed in this version, but **as of this entry the fix has not yet
been published** to either registry -- `npm install -g workspaceguard-cli`
and `pip install workspaceguard-cli` will keep installing the affected
`0.1.2` build until a new release goes out. Track publish status via
[npmjs.com/package/workspaceguard-cli](https://www.npmjs.com/package/workspaceguard-cli)
and [pypi.org/project/workspaceguard-cli](https://pypi.org/project/workspaceguard-cli/).

- **Fixed**: `-h`/`--help` and `-V`/`--version` now print the documented
  help text / installed version and exit `0`, in both `src/cli/index.ts`
  and `python/src/workspaceguard/cli.py`.
- **Fixed**: the npm `package.json` was missing its `author`/`contributors`
  fields on the published `0.1.2` release even though both maintainers were
  already listed as npm package maintainers; both fields are now present so
  the manifest itself (not just npm's separate maintainers list) credits
  both authors.
- **Fixed**: corrected stale/self-contradictory test-count claims across
  the docs. The TypeScript suite (`src/core/usage.test.ts` +
  `src/core/isolation-guard.test.ts`) has 27 tests, not the previously
  claimed 20. The Python suite (`python/tests/test_cli.py` +
  `test_isolation_guard.py` + `test_usage.py`) has 40 tests, not the
  previously claimed 32 (root README and `python/README.md`'s Install
  section) or 28 (`python/README.md`'s own "What's real vs. not yet built"
  section, which disagreed with its own Install section above it).
- **Fixed**: removed a stale `SECURITY.md` line stating the npm package's
  "current unpublished status" was out of scope -- the npm package has been
  published and installable since before the `0.1.1` release; that line
  was leftover from an earlier pre-publish draft and contradicted the
  Supported Versions table two sections above it in the same file.
- `python/pyproject.toml`'s `version` field is bumped to `0.1.3` to match
  the npm side's already-bumped (but likewise unpublished) `0.1.3` and to
  stop it silently understating that the published `0.1.2` PyPI release
  predates this fix.

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

**Package status at this release**: the wheel and sdist were built and
verified (installs and runs correctly end to end in a fresh venv,
`twine check` passes), but the first PyPI publish was pending -- initially
blocked by a PyPI account-level throttle on registering brand-new project
names ("429 Too many new projects created"), unrelated to 2FA (this
account's PyPI publishing needs no human 2FA). Separately, the npm package
was built with CI green but not yet published to the npm registry either.
**Update**: both throttles have since cleared. `pip install
workspaceguard-cli` and `npm install -g workspaceguard-cli` both work
today; see
[pypi.org/project/workspaceguard-cli](https://pypi.org/project/workspaceguard-cli/)
and [npmjs.com/package/workspaceguard-cli](https://www.npmjs.com/package/workspaceguard-cli).
The two distributions are maintained together as equally first-class
packages, same as this account's other dual-distribution projects.

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
