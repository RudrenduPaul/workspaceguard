import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir, homedir } from "node:os";
import { join } from "node:path";
import { main, extractDataDirFlag, extractForceFlag, extractJsonFlag } from "./index.js";
import { defaultDataDir } from "../core/paths.js";

async function withTempDataDir<T>(fn: (dataDir: string) => Promise<T>): Promise<T> {
  const dir = await mkdtemp(join(tmpdir(), "workspaceguard-cli-test-"));
  try {
    return await fn(dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

async function runCli(argv: string[]): Promise<{ stdout: string; exitCode: number | undefined }> {
  const originalLog = console.log;
  const originalError = console.error;
  const originalExitCode = process.exitCode;
  process.exitCode = undefined;
  let stdout = "";
  console.log = (...parts: unknown[]) => {
    stdout += parts.map(String).join(" ") + "\n";
  };
  console.error = () => {}; // matches the real entrypoint's catch-all, silenced for test output
  try {
    // Mirrors the module-level `main().catch(...)` in cli/index.ts -- an
    // uncaught rejection sets exitCode 1, it doesn't propagate.
    await main(["node", "workspaceguard", ...argv]).catch(() => {
      process.exitCode = 1;
    });
    return { stdout, exitCode: process.exitCode };
  } finally {
    console.log = originalLog;
    console.error = originalError;
    process.exitCode = originalExitCode;
  }
}

// --- argv flag-parsing unit tests ---

test("extractDataDirFlag pulls out a space-separated --data-dir value", () => {
  const { dataDir, rest } = extractDataDirFlag(["status", "--data-dir", "/tmp/wg", "--json"]);
  assert.equal(dataDir, "/tmp/wg");
  assert.deepEqual(rest, ["status", "--json"]);
});

test("extractDataDirFlag pulls out an --data-dir=<path> value", () => {
  const { dataDir, rest } = extractDataDirFlag(["status", "--data-dir=/tmp/wg2"]);
  assert.equal(dataDir, "/tmp/wg2");
  assert.deepEqual(rest, ["status"]);
});

test("extractDataDirFlag returns undefined when the flag is absent", () => {
  const { dataDir, rest } = extractDataDirFlag(["status", "--json"]);
  assert.equal(dataDir, undefined);
  assert.deepEqual(rest, ["status", "--json"]);
});

test("extractForceFlag and extractJsonFlag strip their own flags without touching each other", () => {
  const { force, rest } = extractForceFlag(["init", "--force", "--json"]);
  assert.equal(force, true);
  assert.deepEqual(rest, ["init", "--json"]);
  const { json } = extractJsonFlag(rest);
  assert.equal(json, true);
});

// --- default data dir (regression: used to silently default to cwd) ---

test("defaultDataDir resolves under the user's home directory, never bare cwd", () => {
  const resolved = defaultDataDir();
  assert.equal(resolved, join(homedir(), ".workspaceguard"));
  assert.notEqual(resolved, process.cwd());
});

// --- CLI end-to-end: --data-dir override ---

test("init writes into the resolved --data-dir, not the current working directory", async () => {
  await withTempDataDir(async (dataDir) => {
    const cwdBefore = process.cwd();
    const { stdout, exitCode } = await runCli(["init", "--data-dir", dataDir, "--json"]);
    assert.notEqual(exitCode, 1);
    const payload = JSON.parse(stdout.trim().split("\n").pop() as string);
    assert.equal(payload.ok, true);
    assert.equal(payload.dataDir, dataDir);

    // The master key landed inside the explicit --data-dir, not cwd.
    const keyPath = join(dataDir, ".workspaceguard", "master.key");
    const raw = await readFile(keyPath, "utf8");
    assert.equal(Buffer.from(raw.trim(), "base64").length, 32);

    // cwd is untouched by the run.
    assert.equal(process.cwd(), cwdBefore);
    await assert.rejects(readFile(join(cwdBefore, ".workspaceguard", "master.key")));
  });
});

test("--data-dir flag takes precedence over WORKSPACEGUARD_DATA_DIR", async () => {
  await withTempDataDir(async (envDir) => {
    await withTempDataDir(async (flagDir) => {
      const original = process.env.WORKSPACEGUARD_DATA_DIR;
      process.env.WORKSPACEGUARD_DATA_DIR = envDir;
      try {
        const { stdout } = await runCli(["init", "--data-dir", flagDir, "--json"]);
        const payload = JSON.parse(stdout.trim().split("\n").pop() as string);
        assert.equal(payload.dataDir, flagDir);
        await assert.rejects(readFile(join(envDir, ".workspaceguard", "master.key")));
        await readFile(join(flagDir, ".workspaceguard", "master.key"), "utf8");
      } finally {
        if (original === undefined) delete process.env.WORKSPACEGUARD_DATA_DIR;
        else process.env.WORKSPACEGUARD_DATA_DIR = original;
      }
    });
  });
});

// --- CLI end-to-end: overwrite protection on a corrupted key ---

test("init refuses to silently regenerate a corrupted master key without --force", async () => {
  await withTempDataDir(async (dataDir) => {
    const keyDir = join(dataDir, ".workspaceguard");
    await mkdir(keyDir, { recursive: true });
    const keyPath = join(keyDir, "master.key");
    await writeFile(keyPath, "not-a-valid-key", "utf8");

    const { exitCode } = await runCli(["init", "--data-dir", dataDir, "--json"]);
    assert.equal(exitCode, 1);

    // The corrupted file was left untouched -- never silently overwritten.
    const stillRaw = await readFile(keyPath, "utf8");
    assert.equal(stillRaw, "not-a-valid-key");
  });
});

test("init --force regenerates over a corrupted master key", async () => {
  await withTempDataDir(async (dataDir) => {
    const keyDir = join(dataDir, ".workspaceguard");
    await mkdir(keyDir, { recursive: true });
    const keyPath = join(keyDir, "master.key");
    await writeFile(keyPath, "not-a-valid-key", "utf8");

    const { exitCode } = await runCli(["init", "--data-dir", dataDir, "--force", "--json"]);
    assert.notEqual(exitCode, 1);

    const raw = await readFile(keyPath, "utf8");
    assert.notEqual(raw, "not-a-valid-key");
    assert.equal(Buffer.from(raw.trim(), "base64").length, 32);
  });
});
