import { join } from "node:path";
import type { BackendAdapter, WorkspaceGuardConfig } from "./types.js";
import { IdentityNotFoundError } from "./types.js";
import { loadConfig, saveConfig, upsertWorkspace, resolveWorkspaceId, setWorkspaceCap } from "./config.js";
import { ensureWorkspaceDirs } from "./namespace.js";
import { Vault } from "./vault.js";
import { CircuitBreaker } from "./circuit-breaker.js";
import { ConsoleLogger, type Logger } from "./log.js";
import { UsageMeter, type WorkspaceUsage } from "./usage.js";

export interface WorkspaceUsageReport extends WorkspaceUsage {
  workspaceId: string;
  identity: string;
  monthlyMessageCap: number | undefined;
  percentUsed: number | null;
}

export interface IsolationGuardOptions {
  dataDir: string;
  backend: BackendAdapter;
  logger?: Logger;
  /** Test-only override for the circuit breaker's open-state cooldown. */
  circuitOpenCooldownMs?: number;
}

/**
 * Core isolation logic. Never imports a specific backend directly -- all
 * backend-specific behavior goes through the BackendAdapter interface, a
 * fixed architectural boundary. The CLI and the library export are both
 * thin wrappers around this class; there is exactly one
 * implementation of the isolation logic.
 */
export class IsolationGuard {
  private readonly dataDir: string;
  private readonly backend: BackendAdapter;
  private readonly logger: Logger;
  private readonly vault: Vault;
  private readonly circuit: CircuitBreaker;
  private readonly usage: UsageMeter;
  private config: WorkspaceGuardConfig = { backend: "odysseus", identityHeader: "", workspaces: [] };

  constructor(options: IsolationGuardOptions) {
    this.dataDir = options.dataDir;
    this.backend = options.backend;
    this.logger = options.logger ?? new ConsoleLogger();
    this.vault = new Vault(join(this.dataDir, ".workspaceguard", "master.key"));
    this.circuit = new CircuitBreaker(this.backend.name, this.logger, options.circuitOpenCooldownMs);
    this.usage = new UsageMeter(this.dataDir);
  }

  private get configPath(): string {
    return join(this.dataDir, "workspaceguard.config.yaml");
  }

  async init(): Promise<void> {
    await this.vault.init();
    this.config = await loadConfig(this.configPath);
  }

  async addWorkspace(workspaceId: string, identity: string): Promise<void> {
    this.config = upsertWorkspace(this.config, workspaceId, identity);
    await saveConfig(this.configPath, this.config);
    await ensureWorkspaceDirs(this.dataDir, workspaceId);
  }

  async setSecret(workspaceId: string, secret: string): Promise<void> {
    await this.vault.writeSecret(this.dataDir, workspaceId, secret);
  }

  async rotateKey(workspaceId: string): Promise<void> {
    await this.vault.rotate(this.dataDir, workspaceId);
  }

  /**
   * Resolves a workspace from an untrusted identity header value. Fails
   * closed on any miss -- never falls back to a default workspace. This is
   * the single choke point every request-handling path must go through.
   */
  resolveWorkspace(identityHeaderValue: string | undefined): string {
    const workspaceId = resolveWorkspaceId(this.config, identityHeaderValue);
    if (!workspaceId) {
      this.logger.log({
        type: "fail_closed",
        reason: "identity_not_found",
        detail: { identityHeaderValue: identityHeaderValue ?? null },
      });
      throw new IdentityNotFoundError(identityHeaderValue);
    }
    return workspaceId;
  }

  async chat(identityHeaderValue: string | undefined, message: string): Promise<string> {
    const workspaceId = this.resolveWorkspace(identityHeaderValue);
    const entry = this.config.workspaces.find((w) => w.workspaceId === workspaceId);
    await this.usage.checkQuota(workspaceId, entry?.monthlyMessageCap);
    const response = await this.circuit.call(() => this.backend.forwardChat(workspaceId, message));
    await this.usage.record(workspaceId, message);
    return response;
  }

  async status(): Promise<{ workspaceId: string; identity: string }[]> {
    return this.config.workspaces.map((w) => ({ workspaceId: w.workspaceId, identity: w.identity }));
  }

  /** Sets (`cap`) or clears (`undefined`) a workspace's monthly message cap. */
  async setCap(workspaceId: string, cap: number | undefined): Promise<void> {
    this.config = setWorkspaceCap(this.config, workspaceId, cap);
    await saveConfig(this.configPath, this.config);
  }

  /**
   * The admin-visibility surface this repo actually ships (the OSS free
   * tier) -- a hosted billing dashboard on top of this data is a separate,
   * closed-source product, never built in this repo.
   */
  async usageReport(): Promise<WorkspaceUsageReport[]> {
    const ids = this.config.workspaces.map((w) => w.workspaceId);
    const usageById = await this.usage.getAll(ids);
    return this.config.workspaces.map((w) => {
      const usage = usageById[w.workspaceId] ?? { period: "", messageCount: 0, estimatedBytes: 0 };
      const percentUsed =
        w.monthlyMessageCap !== undefined && w.monthlyMessageCap > 0
          ? Math.round((usage.messageCount / w.monthlyMessageCap) * 100)
          : null;
      return {
        workspaceId: w.workspaceId,
        identity: w.identity,
        monthlyMessageCap: w.monthlyMessageCap,
        percentUsed,
        ...usage,
      };
    });
  }
}
