import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { UsageMeter, QuotaExceededError, currentUsageFor, loadUsage, usagePath } from "./usage.js";

async function withTempDataDir<T>(fn: (dataDir: string) => Promise<T>): Promise<T> {
  const dir = await mkdtemp(join(tmpdir(), "workspaceguard-usage-test-"));
  try {
    return await fn(dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

test("usage metering: recording increments per-workspace count and byte estimate", async () => {
  await withTempDataDir(async (dataDir) => {
    const meter = new UsageMeter(dataDir);
    await meter.record("alex", "hello");
    await meter.record("alex", "world!!");

    const usage = await meter.get("alex");
    assert.equal(usage.messageCount, 2);
    assert.equal(usage.estimatedBytes, Buffer.byteLength("hello") + Buffer.byteLength("world!!"));
  });
});

test("usage metering: workspaces are isolated -- one workspace's usage never leaks into another's", async () => {
  await withTempDataDir(async (dataDir) => {
    const meter = new UsageMeter(dataDir);
    await meter.record("alex", "a1");
    await meter.record("alex", "a2");
    await meter.record("jordan", "j1");

    const all = await meter.getAll(["alex", "jordan"]);
    assert.equal(all.alex?.messageCount, 2);
    assert.equal(all.jordan?.messageCount, 1);
  });
});

test("usage metering: an unconfigured workspace reads as zero, not an error", async () => {
  await withTempDataDir(async (dataDir) => {
    const meter = new UsageMeter(dataDir);
    const usage = await meter.get("never-recorded");
    assert.equal(usage.messageCount, 0);
    assert.equal(usage.estimatedBytes, 0);
  });
});

test("quota: undefined cap never throws, regardless of usage", async () => {
  await withTempDataDir(async (dataDir) => {
    const meter = new UsageMeter(dataDir);
    for (let i = 0; i < 50; i++) await meter.record("alex", "msg");
    await assert.doesNotReject(() => meter.checkQuota("alex", undefined));
  });
});

test("quota: throws QuotaExceededError once messageCount reaches the configured cap", async () => {
  await withTempDataDir(async (dataDir) => {
    const meter = new UsageMeter(dataDir);
    await assert.doesNotReject(() => meter.checkQuota("alex", 2));
    await meter.record("alex", "msg-1");
    await assert.doesNotReject(() => meter.checkQuota("alex", 2));
    await meter.record("alex", "msg-2");
    await assert.rejects(() => meter.checkQuota("alex", 2), QuotaExceededError);
  });
});

test("quota: one workspace hitting its cap never blocks a sibling workspace", async () => {
  await withTempDataDir(async (dataDir) => {
    const meter = new UsageMeter(dataDir);
    await meter.record("alex", "msg-1");
    await assert.rejects(() => meter.checkQuota("alex", 1), QuotaExceededError);
    await assert.doesNotReject(() => meter.checkQuota("jordan", 1));
  });
});

test("loadUsage: a missing usage.json is a legitimate empty store", async () => {
  await withTempDataDir(async (dataDir) => {
    const store = await loadUsage(dataDir);
    assert.deepEqual(store, {});
  });
});

test("loadUsage: a corrupted usage.json throws instead of silently reading as empty (regression: this used to fail open, lifting every quota)", async () => {
  await withTempDataDir(async (dataDir) => {
    const meter = new UsageMeter(dataDir);
    await meter.record("alex", "msg-1"); // creates .workspaceguard/ and usage.json
    await writeFile(usagePath(dataDir), "{ not valid json", "utf8");

    await assert.rejects(() => loadUsage(dataDir), /corrupted/);
    await assert.rejects(() => meter.checkQuota("alex", 1), /corrupted/);
  });
});

test("loadUsage: a usage.json holding a JSON array (unexpected shape) throws instead of silently reading as empty", async () => {
  await withTempDataDir(async (dataDir) => {
    const meter = new UsageMeter(dataDir);
    await meter.record("alex", "msg-1");
    await writeFile(usagePath(dataDir), "[]", "utf8");

    await assert.rejects(() => loadUsage(dataDir), /unexpected shape/);
  });
});

test("currentUsageFor rolls a stale period over to a fresh zeroed bucket instead of inflating it", () => {
  const stale = currentUsageFor({ alex: { period: "2020-01", messageCount: 999, estimatedBytes: 999 } }, "alex");
  assert.equal(stale.messageCount, 0);
  assert.equal(stale.estimatedBytes, 0);
  assert.notEqual(stale.period, "2020-01");
});
