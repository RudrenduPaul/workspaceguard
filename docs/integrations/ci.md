# CI usage

WorkspaceGuard's usage report is structured (`--json` on the CLI, or
`usage_report()` in the library), so it's straightforward to use as a CI
gate -- for example, failing a build or sending an alert when a shared dev
or staging deployment's workspace is approaching its monthly cap, without
needing a hosted dashboard.

## Plain CI step (GitHub Actions, Python CLI)

```yaml
name: WorkspaceGuard usage check
on:
  schedule:
    - cron: '0 * * * *'  # hourly
  workflow_dispatch:

jobs:
  usage-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install workspaceguard-cli
      - name: Check usage
        env:
          WORKSPACEGUARD_DATA_DIR: ${{ vars.WORKSPACEGUARD_DATA_DIR }}
        run: |
          workspaceguard usage --json > usage.json
          cat usage.json
          # Fail the job if any workspace is at or above 90% of its cap.
          python3 -c "
          import json, sys
          report = json.load(open('usage.json'))['usage']
          over = [r for r in report if r['percentUsed'] is not None and r['percentUsed'] >= 90]
          if over:
              for r in over:
                  print(f\"{r['workspaceId']}: {r['percentUsed']}% of cap\", file=sys.stderr)
              sys.exit(1)
          "
```

(`WORKSPACEGUARD_DATA_DIR` needs to point at the same data directory your
running deployment's sidecar writes to -- a shared volume, a synced
directory, or wherever your deployment persists `.workspaceguard/`.)

## As a library call (the pattern examples/02-ci-gate-quota-check follows)

```python
import sys
from workspaceguard import create_workspace_guard, MockAdapter

async def main() -> int:
    guard = await create_workspace_guard(data_dir="./data", backend=MockAdapter())
    report = await guard.usage_report()
    over_threshold = [r for r in report if r.percent_used is not None and r.percent_used >= 90]
    if over_threshold:
        for r in over_threshold:
            print(f"{r.workspace_id}: {r.percent_used}% of cap", file=sys.stderr)
        return 1
    print("all workspaces under 90% of their cap")
    return 0
```

See [`python/examples/02-ci-gate-quota-check/`](../../python/examples/02-ci-gate-quota-check/)
for the full runnable version, including real process exit-code
propagation.

## Choosing a threshold

There's no single right threshold -- a shared household deployment with a
generous cap might only care about a hard 100% block (the built-in
`QuotaExceededError` behavior on `chat()`), while a cost-sensitive shared
dev/staging environment might want an earlier CI-level warning at 80-90%
before the cap actually blocks anyone. Both are just different consumers
of the same `usage_report()` / `workspaceguard usage --json` data --
WorkspaceGuard doesn't hardcode a "warning" tier, only the hard cap via
`set-cap`.
