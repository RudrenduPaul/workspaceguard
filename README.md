# WorkspaceGuard

Per-user workspace isolation for self-hosted AI assistants.

**Status: early scaffold, not yet installable.** The isolation engine (chat
history, memory namespace, API-key vault) and the adversarial isolation
test suite are implemented against a mock backend. The real adapter for
self-hosted AI assistants (starting with Odysseus) is still in progress.
This README will be replaced with the full version once the first real
adapter ships.

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
