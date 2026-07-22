# Security Policy

WorkspaceGuard sits in front of a shared self-hosted AI assistant
deployment and is trusted to keep workspaces isolated from each other and
to enforce usage quotas correctly. A vulnerability that lets one
workspace's requests, chat history, or vault secrets be read, quota-bypassed,
or attributed to another workspace is taken seriously and handled as a
priority.

## Supported versions

| Package | Version | Supported |
| --- | --- | --- |
| `workspaceguard-cli` (npm) | latest (0.1.x) | Published and installable via `npm install -g workspaceguard-cli`. See [npmjs.com/package/workspaceguard-cli](https://www.npmjs.com/package/workspaceguard-cli). |
| `workspaceguard-cli` (PyPI) | latest (0.1.x) | Published and installable via `pip install workspaceguard-cli`. See [pypi.org/project/workspaceguard-cli](https://pypi.org/project/workspaceguard-cli/). |

Both distributions are pre-1.0 and under active development. Security
fixes land on the latest `0.1.x` release of each; there is no older
supported line to backport to yet.

## Reporting a vulnerability

**Do not open a public GitHub issue for a security vulnerability.**

Report it privately via
[GitHub Security Advisories](https://github.com/RudrenduPaul/workspaceguard/security/advisories/new)
for this repository. Include:

- Which distribution is affected (npm package, PyPI package, or both).
- A minimal reproduction: the config/workspace setup and the command or
  library call that triggers the issue.
- What you expected WorkspaceGuard to do, and what it actually did.
- Your assessment of impact -- e.g. "workspace A's identity header resolves
  to workspace B" or "a rotated vault key can still decrypt the old
  ciphertext" are exactly the class of trust-boundary bypass this project
  exists to prevent.

## What counts as in scope

- Any path where `resolve_workspace()` / `resolveWorkspace()` can be made
  to return the wrong workspace id, or to fall back to a default workspace
  instead of failing closed, for an identity header value that was not
  explicitly registered.
- Any path where one workspace's chat history, memory, vault secret, or
  usage count becomes readable (directly or by inference) from another
  workspace's context.
- A key-rotation bypass: `rotate_key()` that does not actually invalidate
  decryption under the previous key generation.
- A quota-enforcement bypass: a request that reaches the backend and gets
  recorded despite the resolved workspace already being at its configured
  `monthlyMessageCap`.
- Any code path where content read from a config file, an identity header
  value, or a chat message is executed, evaluated, or used to construct a
  shell command, rather than only read, compared, or forwarded to the
  configured `BackendAdapter`.

## What is out of scope

- Vulnerabilities in the target self-hosted assistant platform itself
  (Odysseus or another backend you've adapted WorkspaceGuard to) -- report
  those to that project's own maintainers.
- The absence of a real Odysseus HTTP adapter, or of a hosted billing
  dashboard -- these are documented as not-yet-built (see
  `docs/integrations/backends.md` and the README), not silent gaps to
  discover.
- The npm package's current unpublished status -- not a security issue,
  see [CHANGELOG.md](./CHANGELOG.md).

## Current security posture, stated honestly

- The vault uses AES-256-GCM with a per-workspace, per-generation derived
  key (`HMAC-SHA256(master_key, "<workspace_id>:<generation>")`); rotation
  increments the generation before re-encrypting, so old ciphertext is
  genuinely unrecoverable under the new generation's key -- verified by a
  dedicated regression test in both distributions' test suites.
- The master key and each workspace's vault file are written with `chmod
  0600`. Filesystem permissions beyond that (who can read the host
  filesystem at all) are the deployment's responsibility, not something
  WorkspaceGuard can enforce from inside the process.
- The identity-header trust boundary (see `docs/concepts.md#trust-boundary`)
  is documented but not code-enforced: WorkspaceGuard cannot itself verify
  that a trusted reverse proxy sits in front of it. Deploying it directly
  reachable from the network without such a proxy defeats workspace
  isolation entirely.
- **Honest note**: this project does not currently publish SLSA
  provenance, Sigstore signatures, or an SBOM, and has no OpenSSF Scorecard
  badge set up -- none of that infrastructure exists yet for either
  distribution, so it isn't claimed here.

## Response

We aim to acknowledge a report within 5 business days and to have a fix or
a mitigation plan within 30 days for a confirmed, in-scope vulnerability.
Credit is given in the release notes unless you ask to remain anonymous.
