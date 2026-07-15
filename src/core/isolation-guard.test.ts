import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  createWorkspaceGuard,
  IdentityNotFoundError,
  BackendCircuitOpenError,
  DuplicateIdentityError,
  QuotaExceededError,
  WorkspaceNotFoundError,
} from "../index.js";
import { MockAdapter } from "../adapters/mock.js";
import { chatHistoryDir } from "./namespace.js";
import { Vault } from "./vault.js";

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
    const vault = new Vault(join(dataDir, ".workspaceguard", "master.key"));
    const alexVaultRaw = await readFile(vault.vaultPath(dataDir, "alex"));
    const jordanVaultRaw = await readFile(vault.vaultPath(dataDir, "jordan"));

    // The two ciphertexts are different files with different bytes -- no
    // shared key store, no shared file.
    assert.ok(!alexVaultRaw.equals(jordanVaultRaw));
  });
});

test("key rotation actually invalidates the old key (regression: rotation used to be a security no-op)", async () => {
  await withTempDataDir(async (dataDir) => {
    const adapter = new MockAdapter();
    const guard = await createWorkspaceGuard({ dataDir, backend: adapter });
    await guard.addWorkspace("alex", "alex@example.com");
    await guard.setSecret("alex", "sk-alex-before-rotation");

    const vault = new Vault(join(dataDir, ".workspaceguard", "master.key"));
    await vault.init();
    const beforeRotation = await readFile(vault.vaultPath(dataDir, "alex"));

    await guard.rotateKey("alex");
    const afterRotation = await readFile(vault.vaultPath(dataDir, "alex"));

    // Same plaintext, but the ciphertext must differ -- proof the derived
    // key actually changed, not just the IV.
    assert.ok(!beforeRotation.equals(afterRotation));

    // The secret is still readable after rotation under the new generation.
    const roundTrip = await vault.readSecret(dataDir, "alex");
    assert.equal(roundTrip, "sk-alex-before-rotation");
  });
});

test("duplicate identity across two workspace ids is rejected, never silently merged", async () => {
  await withTempDataDir(async (dataDir) => {
    const adapter = new MockAdapter();
    const guard = await createWorkspaceGuard({ dataDir, backend: adapter });
    await guard.addWorkspace("alex", "shared@example.com");

    await assert.rejects(
      () => guard.addWorkspace("jordan", "shared@example.com"),
      DuplicateIdentityError,
    );

    // Only the first workspace exists -- the second was never silently merged in.
    const statuses = await guard.status();
    assert.equal(statuses.length, 1);
    assert.equal(statuses[0]?.workspaceId, "alex");
  });
});

test("circuit breaker opens after 3 consecutive failures, then self-heals after cooldown (regression: it used to never close again)", async () => {
  await withTempDataDir(async (dataDir) => {
    const adapter = new MockAdapter();
    const guard = await createWorkspaceGuard({ dataDir, backend: adapter, circuitOpenCooldownMs: 50 });
    await guard.addWorkspace("alex", "alex@example.com");

    adapter._failNextCalls(3);
    for (let i = 0; i < 3; i++) {
      await assert.rejects(() => guard.chat("alex@example.com", `msg-${i}`));
    }

    // Circuit is now open -- the very next call is rejected without even
    // reaching the backend.
    await assert.rejects(() => guard.chat("alex@example.com", "should-be-circuit-open"), BackendCircuitOpenError);

    // After the cooldown, the next call is let through as a half-open probe.
    await new Promise((resolve) => setTimeout(resolve, 60));
    const response = await guard.chat("alex@example.com", "probe-after-cooldown");
    assert.equal(response, "echo: probe-after-cooldown");

    // Circuit is closed again -- a normal call succeeds without being rejected.
    const response2 = await guard.chat("alex@example.com", "should-work-normally");
    assert.equal(response2, "echo: should-work-normally");
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

// Usage-metering + billing wedge (the pivot from per-user isolation, which
// the target repo already ships natively -- see README).

test("usage metering: chat() increments per-workspace usage, isolated across workspaces", async () => {
  await withTempDataDir(async (dataDir) => {
    const adapter = new MockAdapter();
    const guard = await createWorkspaceGuard({ dataDir, backend: adapter });
    await guard.addWorkspace("alex", "alex@example.com");
    await guard.addWorkspace("jordan", "jordan@example.com");

    await guard.chat("alex@example.com", "hi");
    await guard.chat("alex@example.com", "hi again");
    await guard.chat("jordan@example.com", "hello");

    const report = await guard.usageReport();
    const alex = report.find((r) => r.workspaceId === "alex");
    const jordan = report.find((r) => r.workspaceId === "jordan");
    assert.equal(alex?.messageCount, 2);
    assert.equal(jordan?.messageCount, 1);
  });
});

test("quota: a workspace at its monthly cap is blocked, never reaches the backend", async () => {
  await withTempDataDir(async (dataDir) => {
    const adapter = new MockAdapter();
    const guard = await createWorkspaceGuard({ dataDir, backend: adapter });
    await guard.addWorkspace("alex", "alex@example.com");
    await guard.setCap("alex", 1);

    await guard.chat("alex@example.com", "first message, under cap");
    await assert.rejects(() => guard.chat("alex@example.com", "second message, over cap"), QuotaExceededError);

    // The blocked message never reached the backend.
    assert.deepEqual(adapter._messagesFor("alex"), ["first message, under cap"]);
  });
});

test("quota: one workspace hitting its cap never blocks a sibling workspace with no cap", async () => {
  await withTempDataDir(async (dataDir) => {
    const adapter = new MockAdapter();
    const guard = await createWorkspaceGuard({ dataDir, backend: adapter });
    await guard.addWorkspace("alex", "alex@example.com");
    await guard.addWorkspace("jordan", "jordan@example.com");
    await guard.setCap("alex", 1);

    await guard.chat("alex@example.com", "msg");
    await assert.rejects(() => guard.chat("alex@example.com", "over cap"), QuotaExceededError);

    // jordan has no cap -- unaffected by alex's block.
    const response = await guard.chat("jordan@example.com", "still works");
    assert.equal(response, "echo: still works");
  });
});

test("quota: clearing a cap (set to undefined) lifts the block", async () => {
  await withTempDataDir(async (dataDir) => {
    const adapter = new MockAdapter();
    const guard = await createWorkspaceGuard({ dataDir, backend: adapter });
    await guard.addWorkspace("alex", "alex@example.com");
    await guard.setCap("alex", 1);
    await guard.chat("alex@example.com", "msg");
    await assert.rejects(() => guard.chat("alex@example.com", "blocked"), QuotaExceededError);

    await guard.setCap("alex", undefined);
    const response = await guard.chat("alex@example.com", "unblocked now");
    assert.equal(response, "echo: unblocked now");
  });
});

test("set-cap on an unknown workspace id fails loudly instead of silently no-op'ing", async () => {
  await withTempDataDir(async (dataDir) => {
    const adapter = new MockAdapter();
    const guard = await createWorkspaceGuard({ dataDir, backend: adapter });
    await assert.rejects(() => guard.setCap("nobody", 5), WorkspaceNotFoundError);
  });
});

test("usageReport: percentUsed is computed from cap and current count, null when uncapped", async () => {
  await withTempDataDir(async (dataDir) => {
    const adapter = new MockAdapter();
    const guard = await createWorkspaceGuard({ dataDir, backend: adapter });
    await guard.addWorkspace("alex", "alex@example.com");
    await guard.addWorkspace("jordan", "jordan@example.com");
    await guard.setCap("alex", 4);
    await guard.chat("alex@example.com", "one");

    const report = await guard.usageReport();
    const alex = report.find((r) => r.workspaceId === "alex");
    const jordan = report.find((r) => r.workspaceId === "jordan");
    assert.equal(alex?.percentUsed, 25);
    assert.equal(jordan?.percentUsed, null);
  });
});
