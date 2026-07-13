import type { Logger } from "./log.js";
import { BackendCircuitOpenError, BackendUnreachableError } from "./types.js";

const FAILURE_THRESHOLD = 3;
const CONNECT_TIMEOUT_MS = 3000;

/**
 * Fail closed, never pass-through-unisolated, per the worst-failure-mode
 * concern (an internal note + an internal note). Opens after 3 consecutive failures,
 * closes again the moment a health check succeeds.
 */
export class CircuitBreaker {
  private consecutiveFailures = 0;
  private open = false;

  constructor(
    private readonly backendName: string,
    private readonly logger: Logger,
  ) {}

  async call<T>(fn: () => Promise<T>): Promise<T> {
    if (this.open) {
      throw new BackendCircuitOpenError(this.backendName);
    }
    try {
      const result = await this.withTimeout(fn());
      this.consecutiveFailures = 0;
      return result;
    } catch {
      this.consecutiveFailures += 1;
      if (this.consecutiveFailures >= FAILURE_THRESHOLD && !this.open) {
        this.open = true;
        this.logger.log({ type: "circuit_state_change", backend: this.backendName, state: "open" });
      }
      throw new BackendUnreachableError(this.backendName);
    }
  }

  /** A health check success closes the circuit again. */
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
