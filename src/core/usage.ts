import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";

export interface WorkspaceUsage {
  period: string;
  messageCount: number;
  estimatedBytes: number;
}

export type UsageStore = Record<string, WorkspaceUsage>;

export class QuotaExceededError extends Error {
  constructor(
    public readonly workspaceId: string,
    public readonly cap: number,
  ) {
    super(`workspace ${workspaceId} has reached its monthly cap of ${cap} messages`);
    this.name = "QuotaExceededError";
  }
}

function currentPeriod(): string {
  const now = new Date();
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function usagePath(dataDir: string): string {
  return join(dataDir, ".workspaceguard", "usage.json");
}

export async function loadUsage(dataDir: string): Promise<UsageStore> {
  try {
    const raw = await readFile(usagePath(dataDir), "utf8");
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return {};
    }
    return parsed as UsageStore;
  } catch {
    return {};
  }
}

export async function saveUsage(dataDir: string, store: UsageStore): Promise<void> {
  const path = usagePath(dataDir);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, JSON.stringify(store, null, 2), "utf8");
}

/**
 * Rolls a workspace's counter over to a fresh period on read -- a stale
 * count from last month must never inflate this month's total or trip a
 * cap that shouldn't apply yet (no cron/scheduler needed, since every real
 * read/write already knows what period it is).
 */
export function currentUsageFor(store: UsageStore, workspaceId: string): WorkspaceUsage {
  const existing = store[workspaceId];
  const period = currentPeriod();
  if (!existing || existing.period !== period) {
    return { period, messageCount: 0, estimatedBytes: 0 };
  }
  return existing;
}

/**
 * Per-workspace usage metering -- the wedge this repo now ships instead of
 * per-user isolation (already native in the target repo, see README).
 * Reads/writes are not lock-guarded against concurrent processes, the same
 * accepted tradeoff config.ts already makes for `workspaceguard.config.yaml`
 * (single-sidecar-process deployment model, documented in an internal note).
 */
export class UsageMeter {
  constructor(private readonly dataDir: string) {}

  async record(workspaceId: string, message: string): Promise<WorkspaceUsage> {
    const store = await loadUsage(this.dataDir);
    const usage = currentUsageFor(store, workspaceId);
    usage.messageCount += 1;
    usage.estimatedBytes += Buffer.byteLength(message, "utf8");
    store[workspaceId] = usage;
    await saveUsage(this.dataDir, store);
    return usage;
  }

  async get(workspaceId: string): Promise<WorkspaceUsage> {
    const store = await loadUsage(this.dataDir);
    return currentUsageFor(store, workspaceId);
  }

  async getAll(workspaceIds: string[]): Promise<Record<string, WorkspaceUsage>> {
    const store = await loadUsage(this.dataDir);
    const result: Record<string, WorkspaceUsage> = {};
    for (const id of workspaceIds) {
      result[id] = currentUsageFor(store, id);
    }
    return result;
  }

  /**
   * Throws QuotaExceededError once a workspace has reached its configured
   * cap. `cap === undefined` means unlimited -- never blocks a workspace
   * that has no cap set, so this stays free/OSS-safe by default.
   */
  async checkQuota(workspaceId: string, cap: number | undefined): Promise<void> {
    if (cap === undefined) return;
    const usage = await this.get(workspaceId);
    if (usage.messageCount >= cap) {
      throw new QuotaExceededError(workspaceId, cap);
    }
  }
}
