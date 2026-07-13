export type LogEvent =
  | { type: "fail_closed"; reason: string; detail: Record<string, unknown> }
  | { type: "circuit_state_change"; backend: string; state: "open" | "closed" };

export interface Logger {
  log(event: LogEvent): void;
}

/**
 * Minimum production logging: every
 * fail-closed decision and every circuit-breaker state change gets one
 * structured line. This is the only way the "zero cross-workspace leaks"
 * claim is verifiable outside of CI.
 */
export class ConsoleLogger implements Logger {
  log(event: LogEvent): void {
    const line = { ts: new Date().toISOString(), ...event };
    console.log(JSON.stringify(line));
  }
}
