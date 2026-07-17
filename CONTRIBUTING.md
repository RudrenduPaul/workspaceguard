# Contributing to WorkspaceGuard

WorkspaceGuard ships two distributions of the same design: an npm package
(`workspaceguard-cli`, TypeScript, repo root -- built and CI-green, **not
yet published to npm**, blocked on a manual 2FA-gated publish step) and a
PyPI package (`workspaceguard-cli`, Python, `python/`, published and
installable today). Please read this whole file before opening a PR --
which section applies depends on which codebase you're touching.

## Ground rules

- Every change lands with tests. Neither test suite is optional scaffolding
  -- both are the mechanism that keeps the two implementations in parity.
- A change to the isolation/metering logic (`chat()`'s pipeline, quota
  semantics, key rotation) should be made in **both** `src/core/` (TypeScript)
  and `python/src/workspaceguard/` (Python), with equivalent test coverage
  added to both suites where feasible. A behavior that only exists in one
  language is a silent gap between the two CLIs -- avoid it.
- Command names, flags, human-readable output text, and `--json` output
  shapes should read identically between the two CLIs wherever the
  underlying behavior is the same. If you intentionally diverge the two,
  say so explicitly in the PR description.
- WorkspaceGuard trusts an upstream identity header and fails closed on any
  resolution miss (see `docs/concepts.md#trust-boundary`). A change that
  weakens fail-closed behavior, or that makes `chat()` silently fall back
  to a default workspace on an unresolved identity, is not acceptable in
  either codebase.

## Working on the TypeScript package (repo root)

```bash
npm install
npm run build
npm test
```

- Source lives under `src/`; `src/core/` is the isolation/metering engine,
  `src/adapters/` holds `BackendAdapter` implementations, `src/cli/` is the
  CLI entry point.
- Tests use `node:test` (`src/**/*.test.ts`).
- `npm run build` compiles to `dist/`, which is what the `bin` entry
  (`workspaceguard`) and the library export both resolve to.

## Working on the Python package (`python/`)

```bash
cd python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

- Source lives under `python/src/workspaceguard/`, laid out to mirror the
  TypeScript module structure 1:1 (`isolation_guard.py`, `usage.py`,
  `vault.py`, `namespace.py`, `circuit_breaker.py`, `config.py`, `log.py`,
  `types.py`, `cli.py`, `adapters/`) so a change in one codebase has an
  obvious counterpart to check in the other.
- Tests use `pytest` with `pytest-asyncio` (`python/tests/test_*.py`).
- Build and verify a real install before opening a PR that touches
  packaging. Build the venv **outside** `python/` -- a venv built inside
  the source tree can get bundled into the sdist:
  ```bash
  python3 -m venv /tmp/wg-build-venv
  /tmp/wg-build-venv/bin/pip install -e "python[dev]"
  /tmp/wg-build-venv/bin/pytest python/tests
  python3 -m build python --outdir /tmp/wg-dist
  python3 -m venv /tmp/wg-verify && /tmp/wg-verify/bin/pip install /tmp/wg-dist/*.whl
  /tmp/wg-verify/bin/workspaceguard status --json
  ```

## Adding a backend adapter

`BackendAdapter` (`src/core/types.ts` / `python/src/workspaceguard/types.py`)
is the fixed boundary: `name`, `health_check()`/`healthCheck()`,
`forward_chat()`/`forwardChat()`. See
[docs/integrations/backends.md](./docs/integrations/backends.md) for what
"Odysseus and compatible backends" means concretely and a worked example of
implementing your own adapter. A real Odysseus HTTP adapter is the single
highest-value contribution this project currently needs -- see that doc for
the open feasibility question blocking it.

## Reporting a security issue

Do not open a public issue for a security vulnerability. See
[SECURITY.md](./SECURITY.md).

## License

By contributing, you agree your contribution is licensed under the same
MIT License that covers the rest of this repository (see
[LICENSE](./LICENSE)).
