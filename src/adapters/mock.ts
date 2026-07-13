import type { BackendAdapter } from "../core/types.js";

/**
 * In-memory mock backend, used for the scaffold-stage isolation tests only.
 * The real Odysseus adapter is blocked on the feasibility spike (open
 * question from an internal note: does Odysseus's HTTP API expose clean
 * interception points, or does it read/write some of this directly from
 * disk/DB in a way an HTTP-level proxy can't see?).
 */
export class MockAdapter implements BackendAdapter {
  readonly name = "mock";
  private readonly messagesByWorkspace = new Map<string, string[]>();

  async healthCheck(): Promise<boolean> {
    return true;
  }

  async forwardChat(workspaceId: string, message: string): Promise<string> {
    const existing = this.messagesByWorkspace.get(workspaceId) ?? [];
    existing.push(message);
    this.messagesByWorkspace.set(workspaceId, existing);
    return `echo: ${message}`;
  }

  /** Test-only inspection point -- never exposed through the public adapter interface. */
  _messagesFor(workspaceId: string): string[] {
    return this.messagesByWorkspace.get(workspaceId) ?? [];
  }
}
