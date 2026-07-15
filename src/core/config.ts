import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import YAML from "yaml";
import type { WorkspaceGuardConfig } from "./types.js";
import { WorkspaceNotFoundError } from "./types.js";

const DEFAULT_IDENTITY_HEADER = "cf-access-authenticated-user-email";

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
 * entry, never overwrites. Rejects loudly if the
 * identity is already claimed by a DIFFERENT workspace id: without this check, two workspace ids could silently share one
 * identity, and resolveWorkspaceId would deterministically route to
 * whichever was added first, merging two workspaces from the routing
 * layer's perspective without either operator being told.
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
  const existingByIdentity = config.workspaces.find((w) => w.identity === identity);
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
  return config.workspaces.find((w) => w.identity === identityHeaderValue)?.workspaceId;
}
