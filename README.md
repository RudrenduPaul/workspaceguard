# WorkspaceGuard

Per-user workspace isolation for self-hosted AI assistants.

**Status: stopped, not published to npm.** This project was built as a scaffold
against the premise that self-hosted AI assistants like
[Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) lacked per-user
isolation of chat history, memory, and API keys. Reading Odysseus's actual
source during the feasibility spike showed that premise is false: Odysseus
already enforces per-user ownership on all three (`_verify_session_owner`,
`_verify_memory_owner`, owner-scoped API tokens), on by default
(`AUTH_ENABLED=true`), with setup docs that walk through the exact
shared-family-deployment scenario this project targeted.

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
