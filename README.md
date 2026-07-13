# WorkspaceGuard

Per-user workspace isolation for self-hosted AI assistants.

**Status: stopped, not published to npm.** This project was built as a scaffold to explore per-user isolation for self-hosted AI assistants. A feasibility spike found that a comparable open-source project already provides equivalent per-user isolation by default, so this scaffold was stopped short of a full backend integration.

The code here is real and tested (isolation engine with namespace
separation, an AES-256-GCM vault with working key rotation, fail-closed
identity resolution, a self-healing circuit breaker, an adversarial
two-workspace cross-read test suite, 7/7 passing), kept public as a working
example rather than deleted. It was never adapted to a real backend and
was never published as an npm package.

## Install

Not yet published to npm. Coming soon.

## Develop

```bash
npm install
npm test
npm run build
```

## License

MIT.
