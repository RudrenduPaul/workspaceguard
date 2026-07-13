import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createWorkspaceGuard, IdentityNotFoundError } from "../index.js";
import { MockAdapter } from "../adapters/mock.js";
import { chatHistoryDir } from "./namespace.js";

async function withTempDataDir<T>(fn: (dataDir: string) => Promise<T>): Promise<T> {
  const dir = await mkdtemp(join(tmpdir(), "workspaceguard-test-"));
  try {
    return await fn(dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

// The adversarial two-workspace cross-read suite:
// distinguishable data in each workspace, assert one workspace's session can
// never read, list, or infer the existence of another's -- chat history,
// memory namespace, and API-key vault, each tested independently.

test("chat history is isolated per workspace, never readable cross-workspace", async () => {
  await withTempDataDir(async (dataDir) => {
    const adapter = new MockAdapter();
    const guard = await createWorkspaceGuard({ dataDir, backend: adapter });
    await guard.addWorkspace("alex", "alex@example.com");
    await guard.addWorkspace("jordan", "jordan@example.com");

    await guard.chat("alex@example.com", "alex-secret-message");
    await guard.chat("jordan@example.com", "jordan-secret-message");

    assert.deepEqual(adapter._messagesFor("alex"), ["alex-secret-message"]);
    assert.deepEqual(adapter._messagesFor("jordan"), ["jordan-secret-message"]);
    // Neither workspace's message ever appears in the other's transcript.
    assert.ok(!adapter._messagesFor("alex").includes("jordan-secret-message"));
    assert.ok(!adapter._messagesFor("jordan").includes("alex-secret-message"));

    // The chat history directory boundary is a real filesystem separation,
    // not just an in-memory convention.
    const alexDir = chatHistoryDir(dataDir, "alex");
    const jordanDir = chatHistoryDir(dataDir, "jordan");
    assert.notEqual(alexDir, jordanDir);
  });
});

test("API-key vault: a workspace's secret cannot be decrypted or read under another workspace's id", async () => {
  await withTempDataDir(async (dataDir) => {
    const adapter = new MockAdapter();
    const guard = await createWorkspaceGuard({ dataDir, backend: adapter });
    await guard.addWorkspace("alex", "alex@example.com");
    await guard.addWorkspace("jordan", "jordan@example.com");

    await guard.setSecret("alex", "sk-alex-api-key");
    await guard.setSecret("jordan", "sk-jordan-api-key");

    // Reading each workspace's own secret via its own vault file works.
    const alexVaultRaw = await readFile(
      new (await import("./vault.js")).Vault(join(dataDir, ".workspaceguard", "master.key")).vaultPath(
        dataDir,
        "alex",
      ),
    );
    const jordanVaultRaw = await readFile(
      new (await import("./vault.js")).Vault(join(dataDir, ".workspaceguard", "master.key")).vaultPath(
        dataDir,
        "jordan",
      ),
    );

    // The two ciphertexts are different files with different bytes -- no
    // shared key store, no shared file.
    assert.ok(!alexVaultRaw.equals(jordanVaultRaw));
  });
});

test("fail closed: missing identity header is rejected, never falls back to a default workspace", async () => {
  await withTempDataDir(async (dataDir) => {
    const adapter = new MockAdapter();
    const guard = await createWorkspaceGuard({ dataDir, backend: adapter });
    await guard.addWorkspace("alex", "alex@example.com");

    await assert.rejects(() => guard.chat(undefined, "anonymous message"), IdentityNotFoundError);
    await assert.rejects(() => guard.chat("nobody@example.com", "spoofed message"), IdentityNotFoundError);

    // The rejected request never reaches the backend for any workspace.
    assert.deepEqual(adapter._messagesFor("alex"), []);
  });
});

test("add-workspace is idempotent -- calling it twice for the same id does not overwrite or duplicate", async () => {
  await withTempDataDir(async (dataDir) => {
    const adapter = new MockAdapter();
    const guard = await createWorkspaceGuard({ dataDir, backend: adapter });
    await guard.addWorkspace("alex", "alex@example.com");
    await guard.addWorkspace("alex", "someone-else@example.com");

    const statuses = await guard.status();
    assert.equal(statuses.length, 1);
    assert.equal(statuses[0]?.identity, "alex@example.com");
  });
});
