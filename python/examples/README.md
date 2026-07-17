# Python examples

Each numbered subdirectory is a real, runnable script against the actual
`workspaceguard` Python library (`from workspaceguard import
create_workspace_guard, ...`), not pseudocode. Each one uses `MockAdapter`
and a temp data directory so it runs standalone with no setup beyond `pip
install -e .` (or `pip install workspaceguard-cli`) from the `python/`
directory -- nothing external is required.

```bash
cd python
pip install -e .
```

Then run any example directly:

```bash
python3 examples/01-basic-usage-report/report.py
python3 examples/02-ci-gate-quota-check/gate.py
python3 examples/03-agent-native-json/agent_report.py
```

| Example | What it demonstrates |
| --- | --- |
| [01-basic-usage-report](./01-basic-usage-report/) | The core library call: register workspaces, set a cap, send chat messages through `chat()`, read back `usage_report()`. |
| [02-ci-gate-quota-check](./02-ci-gate-quota-check/) | Using `usage_report()` as a CI-gate script: a configurable percent-of-cap warning threshold, real process exit-code propagation, suitable to drop into a scheduled CI job. |
| [03-agent-native-json](./03-agent-native-json/) | The agent-native use case: calling WorkspaceGuard in-process, serializing a usage report to JSON, catching `QuotaExceededError` as normal control flow, and the fail-closed identity resolution rejecting a missing/spoofed identity header. |
