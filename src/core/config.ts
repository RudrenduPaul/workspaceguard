import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import YAML from "yaml";
import type { WorkspaceGuardConfig } from "./types.js";
import { WorkspaceNotFoundError } from "./types.js";

const DEFAULT_IDENTITY_HEADER = "cf-access-authenticated-user-email";

// workspaceId is used to build filesystem paths (vault, namespace, chat
// history dirs) and as an object key -- an allowlist plus a reserved-name
// denylist closes both a path-traversal vector (e.g. "../../etc") and a
// prototype-pollution-shaped vector (e.g. "__proto__" as an object key)
// before either ever reaches those call sites.
const WORKSPACE_ID_PATTERN = /^[a-zA-Z0-9_-]+$/;
const RESERVED_WORKSPACE_IDS = new Set(["__proto__", "constructor", "prototype", ".", ".."]);

export class InvalidWorkspaceIdError extends Error {
  constructor(public readonly workspaceId: string) {
    super(
      `workspace id "${workspaceId}" is invalid: must match ${WORKSPACE_ID_PATTERN} and must not be a reserved name`,
    );
    this.name = "InvalidWorkspaceIdError";
  }
}

function assertValidWorkspaceId(workspaceId: string): void {
  if (!WORKSPACE_ID_PATTERN.test(workspaceId) || RESERVED_WORKSPACE_IDS.has(workspaceId)) {
    throw new InvalidWorkspaceIdError(workspaceId);
  }
}

// Identities are compared case/whitespace-insensitively so that
// "Alex@Example.com " and "alex@example.com" resolve to the same
// workspace -- without this, the duplicate-identity guard below could be
// evaded by registering a near-duplicate, producing two workspaces (and
// two independent quotas) for what is really one real-world identity.
// The original casing is still stored, only comparisons are normalized.
function normalizeIdentity(identity: string): string {
  return identity.trim().toLowerCase();
}

export async function loadConfig(configPath: string): Promise<WorkspaceGuardConfig> {
  try {
    const raw = await readFile(configPath, "utf8");
    const parsed = YAML.parse(raw) as WorkspaceGuardConfig;
    return {
      backend: parsed.backend ?? "odysseus",
      identityHeader: parsed.identityHeader ?? DEFAULT_IDENTITY_HEADER,
      workspaces: parsed.workspaces ?? [],
    };
  } catch {
    return { backend: "odysseus", identityHeader: DEFAULT_IDENTITY_HEADER, workspaces: [] };
  }
}

export async function saveConfig(configPath: string, config: WorkspaceGuardConfig): Promise<void> {
  await mkdir(dirname(configPath), { recursive: true });
  await writeFile(configPath, YAML.stringify(config), "utf8");
}

export class DuplicateIdentityError extends Error {
  constructor(
    public readonly identity: string,
    public readonly existingWorkspaceId: string,
  ) {
    super(`identity "${identity}" is already assigned to workspace "${existingWorkspaceId}"`);
    this.name = "DuplicateIdentityError";
  }
}

/**
 * add-workspace on an existing id is idempotent -- returns the existing
 * entry, never overwrites. Rejects loudly if the identity is already
 * claimed by a DIFFERENT workspace id: without this check, two workspace
 * ids could silently share one identity, and resolveWorkspaceId would
 * deterministically route to whichever was added first, merging two
 * workspaces from the routing layer's perspective without either
 * operator being told.
 */
export function upsertWorkspace(
  config: WorkspaceGuardConfig,
  workspaceId: string,
  identity: string,
): WorkspaceGuardConfig {
  const existingById = config.workspaces.find((w) => w.workspaceId === workspaceId);
  if (existingById) {
    return config;
  }
  assertValidWorkspaceId(workspaceId);
  const existingByIdentity = config.workspaces.find((w) => normalizeIdentity(w.identity) === normalizeIdentity(identity));
  if (existingByIdentity) {
    throw new DuplicateIdentityError(identity, existingByIdentity.workspaceId);
  }
  return { ...config, workspaces: [...config.workspaces, { workspaceId, identity }] };
}

/**
 * Sets (or clears, with `cap === undefined`) a workspace's monthly message
 * cap. Rejects loudly on an unknown workspace id rather than silently
 * no-op'ing, matching upsertWorkspace's fail-loud-on-ambiguity precedent.
 */
export function setWorkspaceCap(
  config: WorkspaceGuardConfig,
  workspaceId: string,
  cap: number | undefined,
): WorkspaceGuardConfig {
  const index = config.workspaces.findIndex((w) => w.workspaceId === workspaceId);
  if (index === -1) {
    throw new WorkspaceNotFoundError(workspaceId);
  }
  const workspaces = [...config.workspaces];
  const entry = { ...workspaces[index] };
  if (cap === undefined) {
    delete entry.monthlyMessageCap;
  } else {
    entry.monthlyMessageCap = cap;
  }
  workspaces[index] = entry;
  return { ...config, workspaces };
}

export function resolveWorkspaceId(
  config: WorkspaceGuardConfig,
  identityHeaderValue: string | undefined,
): string | undefined {
  if (!identityHeaderValue) return undefined;
  const normalized = normalizeIdentity(identityHeaderValue);
  return config.workspaces.find((w) => normalizeIdentity(w.identity) === normalized)?.workspaceId;
}
