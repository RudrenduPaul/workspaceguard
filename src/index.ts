import { IsolationGuard } from "./core/isolation-guard.js";
import type { BackendAdapter } from "./core/types.js";

export { IsolationGuard } from "./core/isolation-guard.js";
export type { WorkspaceUsageReport } from "./core/isolation-guard.js";
export type { BackendAdapter } from "./core/types.js";
export { MockAdapter } from "./adapters/mock.js";
export {
  IdentityNotFoundError,
  VaultDecryptionError,
  BackendUnreachableError,
  BackendCircuitOpenError,
  WorkspaceNotFoundError,
} from "./core/types.js";
export { DuplicateIdentityError } from "./core/config.js";
export { QuotaExceededError } from "./core/usage.js";
export type { WorkspaceUsage } from "./core/usage.js";

export interface CreateWorkspaceGuardOptions {
  dataDir: string;
  backend: BackendAdapter;
  /** Test-only override for the circuit breaker's open-state cooldown. */
  circuitOpenCooldownMs?: number;
}

/**
 * The library entry point -- the "agent-native" surface. An orchestrator
 * process can call this directly instead of shelling out to the CLI.
 * No default backend -- a caller must be explicit about which adapter it
 * wants (the real Odysseus adapter ships once the feasibility spike
 * confirms clean HTTP interception; MockAdapter is exported for tests).
 */
export async function createWorkspaceGuard(options: CreateWorkspaceGuardOptions): Promise<IsolationGuard> {
  const guard = new IsolationGuard({
    dataDir: options.dataDir,
    backend: options.backend,
    circuitOpenCooldownMs: options.circuitOpenCooldownMs,
  });
  await guard.init();
  return guard;
}
