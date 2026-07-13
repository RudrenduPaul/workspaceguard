export interface WorkspaceEntry {
  workspaceId: string;
  identity: string;
}

export interface WorkspaceGuardConfig {
  backend: string;
  identityHeader: string;
  workspaces: WorkspaceEntry[];
}

export interface BackendAdapter {
  readonly name: string;
  healthCheck(): Promise<boolean>;
  forwardChat(workspaceId: string, message: string): Promise<string>;
}

export class IdentityNotFoundError extends Error {
  constructor(public readonly headerValue: string | undefined) {
    super("no workspace configured for this identity");
    this.name = "IdentityNotFoundError";
  }
}

export class VaultDecryptionError extends Error {
  constructor(public readonly workspaceId: string) {
    super(`could not decrypt vault for workspace ${workspaceId}`);
    this.name = "VaultDecryptionError";
  }
}

export class BackendUnreachableError extends Error {
  constructor(public readonly backend: string) {
    super(`backend ${backend} did not respond`);
    this.name = "BackendUnreachableError";
  }
}

export class BackendCircuitOpenError extends Error {
  constructor(public readonly backend: string) {
    super(`backend ${backend} circuit is open, refusing calls`);
    this.name = "BackendCircuitOpenError";
  }
}
