import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Vault } from "./vault.js";

async function withTempDataDir<T>(fn: (dataDir: string) => Promise<T>): Promise<T> {
  const dir = await mkdtemp(join(tmpdir(), "workspaceguard-vault-test-"));
  try {
    return await fn(dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

test("Vault.init() generates and persists a fresh 32-byte key when none exists yet", async () => {
  await withTempDataDir(async (dataDir) => {
    const keyPath = join(dataDir, ".workspaceguard", "master.key");
    const vault = new Vault(keyPath);
    await vault.init();

    const raw = await readFile(keyPath, "utf8");
    assert.equal(Buffer.from(raw.trim(), "base64").length, 32);
  });
});

test("Vault.init() reuses an existing valid key rather than overwriting it (idempotent, not an overwrite)", async () => {
  await withTempDataDir(async (dataDir) => {
    const keyPath = join(dataDir, ".workspaceguard", "master.key");
    const first = new Vault(keyPath);
    await first.init();
    const originalRaw = await readFile(keyPath, "utf8");

    const second = new Vault(keyPath);
    await second.init();
    const afterRaw = await readFile(keyPath, "utf8");

    assert.equal(originalRaw, afterRaw);
  });
});

test("Vault.init() refuses to silently overwrite a corrupted/invalid-length key file without force", async () => {
  await withTempDataDir(async (dataDir) => {
    const keyDir = join(dataDir, ".workspaceguard");
    await mkdir(keyDir, { recursive: true });
    const keyPath = join(keyDir, "master.key");
    await writeFile(keyPath, "dG9vLXNob3J0", "utf8"); // base64("too-short"), not 32 bytes

    const vault = new Vault(keyPath);
    await assert.rejects(() => vault.init(), /does not decode to a valid/);

    // File on disk is untouched.
    const stillRaw = await readFile(keyPath, "utf8");
    assert.equal(stillRaw, "dG9vLXNob3J0");
  });
});

test("Vault.init(force=true) regenerates over a corrupted key file", async () => {
  await withTempDataDir(async (dataDir) => {
    const keyDir = join(dataDir, ".workspaceguard");
    await mkdir(keyDir, { recursive: true });
    const keyPath = join(keyDir, "master.key");
    await writeFile(keyPath, "dG9vLXNob3J0", "utf8");

    const vault = new Vault(keyPath);
    await vault.init(true);

    const raw = await readFile(keyPath, "utf8");
    assert.notEqual(raw, "dG9vLXNob3J0");
    assert.equal(Buffer.from(raw.trim(), "base64").length, 32);
  });
});

test("Vault.init() propagates a non-ENOENT read error instead of silently generating a new key", async () => {
  await withTempDataDir(async (dataDir) => {
    // Point the "key file" path at a directory, not a file, so readFile
    // fails with EISDIR rather than ENOENT -- this must fail loudly, not
    // be swallowed into "no key yet, generate one."
    const keyPath = join(dataDir, ".workspaceguard", "master.key");
    await mkdir(keyPath, { recursive: true });

    const vault = new Vault(keyPath);
    await assert.rejects(() => vault.init());
  });
});
