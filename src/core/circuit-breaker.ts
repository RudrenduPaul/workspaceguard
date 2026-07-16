import type { Logger } from "./log.js";
import { BackendCircuitOpenError, BackendUnreachableError } from "./types.js";

const FAILURE_THRESHOLD = 3;
const CONNECT_TIMEOUT_MS = 3000;
const DEFAULT_OPEN_COOLDOWN_MS = 10_000;

/**
 * Fail closed, never pass-through-unisolated -- the worst failure mode
 * here is a silent cross-workspace leak, so an unreachable backend must
 * block, not bypass, isolation. Opens after 3 consecutive failures. The
 * original implementation never called onHealthCheckSuccess from
 * anywhere, so an open circuit had no path back to closed -- a one-way
 * trip switch, not a real circuit breaker. This fixes that: once
 * OPEN_COOLDOWN_MS has passed since opening, the next call is let
 * through as a half-open probe; success closes the circuit, failure keeps
 * it open and restarts the cooldown.
 */
export class CircuitBreaker {
  private consecutiveFailures = 0;
  private open = false;
  private openedAt = 0;

  constructor(
    private readonly backendName: string,
    private readonly logger: Logger,
    private readonly openCooldownMs: number = DEFAULT_OPEN_COOLDOWN_MS,
  ) {}

  private probeAllowed(): boolean {
    return this.open && Date.now() - this.openedAt >= this.openCooldownMs;
  }

  async call<T>(fn: () => Promise<T>): Promise<T> {
    if (this.open && !this.probeAllowed()) {
      throw new BackendCircuitOpenError(this.backendName);
    }
    try {
      const result = await this.withTimeout(fn());
      this.consecutiveFailures = 0;
      this.onHealthCheckSuccess();
      return result;
    } catch {
      this.consecutiveFailures += 1;
      if (this.consecutiveFailures >= FAILURE_THRESHOLD) {
        this.openCircuit();
      }
      throw new BackendUnreachableError(this.backendName);
    }
  }

  private openCircuit(): void {
    const wasOpen = this.open;
    this.open = true;
    this.openedAt = Date.now();
    if (!wasOpen) {
      this.logger.log({ type: "circuit_state_change", backend: this.backendName, state: "open" });
    }
  }

  /** A health check success (or a successful half-open probe) closes the circuit again. */
  onHealthCheckSuccess(): void {
    if (this.open) {
      this.open = false;
      this.consecutiveFailures = 0;
      this.logger.log({ type: "circuit_state_change", backend: this.backendName, state: "closed" });
    }
  }

  private withTimeout<T>(promise: Promise<T>): Promise<T> {
    return Promise.race([
      promise,
      new Promise<T>((_, reject) =>
        setTimeout(() => reject(new Error("connect timeout")), CONNECT_TIMEOUT_MS),
      ),
    ]);
  }
}
