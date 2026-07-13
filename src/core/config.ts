import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import YAML from "yaml";
import type { WorkspaceGuardConfig } from "./types.js";

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

/** add-workspace on an existing id is idempotent -- returns the existing entry, never overwrites. */
export function upsertWorkspace(
  config: WorkspaceGuardConfig,
  workspaceId: string,
  identity: string,
): WorkspaceGuardConfig {
  const existing = config.workspaces.find((w) => w.workspaceId === workspaceId);
  if (existing) {
    return config;
  }
  return { ...config, workspaces: [...config.workspaces, { workspaceId, identity }] };
}

export function resolveWorkspaceId(
  config: WorkspaceGuardConfig,
  identityHeaderValue: string | undefined,
): string | undefined {
  if (!identityHeaderValue) return undefined;
  return config.workspaces.find((w) => w.identity === identityHeaderValue)?.workspaceId;
}
