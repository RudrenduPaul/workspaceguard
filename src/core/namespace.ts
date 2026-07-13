import { mkdir } from "node:fs/promises";
import { join } from "node:path";

/**
 * Chat history and memory get a directory boundary per workspace, not a
 * shared table/file with a workspace column -- easier to verify by
 * inspection than a query filter.
 */
export function chatHistoryDir(dataDir: string, workspaceId: string): string {
  return join(dataDir, "workspaces", workspaceId, "chat");
}

export function memoryDir(dataDir: string, workspaceId: string): string {
  return join(dataDir, "workspaces", workspaceId, "memory");
}

export async function ensureWorkspaceDirs(dataDir: string, workspaceId: string): Promise<void> {
  await mkdir(chatHistoryDir(dataDir, workspaceId), { recursive: true });
  await mkdir(memoryDir(dataDir, workspaceId), { recursive: true });
}
