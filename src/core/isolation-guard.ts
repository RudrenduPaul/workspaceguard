import { join } from "node:path";
import type { BackendAdapter, WorkspaceGuardConfig } from "./types.js";
import { IdentityNotFoundError } from "./types.js";
import { loadConfig, saveConfig, upsertWorkspace, resolveWorkspaceId } from "./config.js";
import { ensureWorkspaceDirs } from "./namespace.js";
import { Vault } from "./vault.js";
import { CircuitBreaker } from "./circuit-breaker.js";
import { ConsoleLogger, type Logger } from "./log.js";

export interface IsolationGuardOptions {
  dataDir: string;
  backend: BackendAdapter;
  logger?: Logger;
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
  private config: WorkspaceGuardConfig = { backend: "odysseus", identityHeader: "", workspaces: [] };

  constructor(options: IsolationGuardOptions) {
    this.dataDir = options.dataDir;
    this.backend = options.backend;
    this.logger = options.logger ?? new ConsoleLogger();
    this.vault = new Vault(join(this.dataDir, ".workspaceguard", "master.key"));
    this.circuit = new CircuitBreaker(this.backend.name, this.logger);
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
    return this.circuit.call(() => this.backend.forwardChat(workspaceId, message));
  }

  async status(): Promise<{ workspaceId: string; identity: string }[]> {
    return this.config.workspaces.map((w) => ({ workspaceId: w.workspaceId, identity: w.identity }));
  }
}
