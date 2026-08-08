#!/usr/bin/env node
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { createWorkspaceGuard } from "../index.js";
import { MockAdapter } from "../adapters/mock.js";
import { defaultDataDir } from "../core/paths.js";

const require = createRequire(import.meta.url);
const { version: PACKAGE_VERSION } = require("../../package.json") as { version: string };

const HELP_TEXT = `usage: workspaceguard <command> [args] [--data-dir <path>] [--json]

commands:
  init                              initialize workspaceguard in the current (or configured) data directory
  add-workspace <id> --identity <v> register a new workspace with its identity
  status                            list configured workspaces and their isolation status
  rotate-key <id>                   rotate the API key for a workspace
  usage                             print per-workspace message-usage counts and caps
  set-cap <id> <count|none>         set (or clear) a workspace's monthly message cap
  scan                              scan isolation config for misconfigurations

global options:
  --data-dir <path>  data directory to use for config, vault, and usage data.
                      Overrides WORKSPACEGUARD_DATA_DIR. Default:
                      $WORKSPACEGUARD_DATA_DIR, then ~/.workspaceguard.
  --force            (init only) regenerate the master key even if an
                      existing key file at the resolved data dir looks
                      corrupted. WARNING: permanently invalidates anything
                      already encrypted under the old key.
  --json             output structured JSON instead of human-readable text
  -h, --help         show this help message and exit
  -V, --version      show the installed version and exit`;

const STARTUP_WARNING =
  "WARNING: workspaceguard must never be directly reachable from the network.\n" +
  "It trusts an upstream identity header (e.g. Cf-Access-Authenticated-User-Email)\n" +
  "set by your reverse proxy. If this port is exposed without that proxy in front\n" +
  "of it, anyone can impersonate any workspace. Firewall this port; only your\n" +
  "trusted proxy should be able to reach it.";

const USAGE =
  "usage: workspaceguard <init|add-workspace|status|rotate-key|usage|set-cap|scan> [--json]";

/** Strips a boolean flag out of an argv slice, agent-native mode toggle for every command. */
export function extractJsonFlag(args: string[]): { json: boolean; rest: string[] } {
  const rest = args.filter((a) => a !== "--json");
  return { json: rest.length !== args.length, rest };
}

/** Strips `--data-dir <path>` / `--data-dir=<path>` out of an argv slice. */
export function extractDataDirFlag(args: string[]): { dataDir: string | undefined; rest: string[] } {
  const rest: string[] = [];
  let dataDir: string | undefined;
  for (let i = 0; i < args.length; i++) {
    const arg = args[i] as string;
    if (arg === "--data-dir") {
      dataDir = args[i + 1];
      i++;
      continue;
    }
    if (arg.startsWith("--data-dir=")) {
      dataDir = arg.slice("--data-dir=".length);
      continue;
    }
    rest.push(arg);
  }
  return { dataDir, rest };
}

/** Strips the `--force`/`-f` flag out of an argv slice (currently only meaningful for `init`). */
export function extractForceFlag(args: string[]): { force: boolean; rest: string[] } {
  const rest = args.filter((a) => a !== "--force" && a !== "-f");
  return { force: rest.length !== args.length, rest };
}

function printResult(json: boolean, data: unknown, humanLines: string[]): void {
  if (json) {
    console.log(JSON.stringify(data));
    return;
  }
  for (const line of humanLines) console.log(line);
}

export async function main(argv: string[] = process.argv): Promise<void> {
  const [, , command, ...rawArgs] = argv;
  const { json, rest: afterJson } = extractJsonFlag(rawArgs);
  const { dataDir: dataDirFlag, rest: afterDataDir } = extractDataDirFlag(afterJson);
  const { force, rest: args } = extractForceFlag(afterDataDir);
  const dataDir = dataDirFlag ?? process.env.WORKSPACEGUARD_DATA_DIR ?? defaultDataDir();

  switch (command) {
    case "--help":
    case "-h": {
      console.log(HELP_TEXT);
      return;
    }
    case "--version":
    case "-V": {
      console.log(PACKAGE_VERSION);
      return;
    }
    case "init": {
      if (!json) console.log(STARTUP_WARNING);
      const guard = await createWorkspaceGuard({ dataDir, backend: new MockAdapter(), force });
      const workspaces = await guard.status();
      printResult(json, { ok: true, dataDir, workspaces }, [`workspaceguard initialized in ${dataDir}`]);
      return;
    }
    case "add-workspace": {
      const [workspaceId, , identity] = args; // add-workspace <id> --identity <value>
      if (!workspaceId || !identity) {
        printResult(
          json,
          { ok: false, error: "usage: workspaceguard add-workspace <id> --identity <value>" },
          ["usage: workspaceguard add-workspace <id> --identity <value>"],
        );
        process.exitCode = 1;
        return;
      }
      const guard = await createWorkspaceGuard({ dataDir, backend: new MockAdapter() });
      await guard.addWorkspace(workspaceId, identity);
      printResult(json, { ok: true, workspaceId, identity }, [`workspace ${workspaceId} added`]);
      return;
    }
    case "status": {
      const guard = await createWorkspaceGuard({ dataDir, backend: new MockAdapter() });
      const workspaces = await guard.status();
      printResult(json, { ok: true, workspaces }, [
        ...(workspaces.length === 0
          ? ["no workspaces configured"]
          : [
              ...workspaces.map((w) => `-> ${w.workspaceId} [isolated] identity: ${w.identity}`),
              "No cross-workspace leaks detected.",
            ]),
      ]);
      return;
    }
    case "rotate-key": {
      const [workspaceId] = args;
      if (!workspaceId) {
        printResult(json, { ok: false, error: "usage: workspaceguard rotate-key <id>" }, [
          "usage: workspaceguard rotate-key <id>",
        ]);
        process.exitCode = 1;
        return;
      }
      const guard = await createWorkspaceGuard({ dataDir, backend: new MockAdapter() });
      await guard.rotateKey(workspaceId);
      printResult(json, { ok: true, workspaceId }, [`workspace ${workspaceId} key rotated`]);
      return;
    }
    case "usage": {
      const guard = await createWorkspaceGuard({ dataDir, backend: new MockAdapter() });
      const report = await guard.usageReport();
      printResult(json, { ok: true, usage: report }, [
        ...(report.length === 0
          ? ["no workspaces configured"]
          : report.map((r) => {
              const cap = r.monthlyMessageCap !== undefined ? `${r.monthlyMessageCap}` : "unlimited";
              const pct = r.percentUsed !== null ? ` (${r.percentUsed}%)` : "";
              return `-> ${r.workspaceId} [${r.identity}]: ${r.messageCount} messages this period, cap ${cap}${pct}`;
            })),
      ]);
      return;
    }
    case "set-cap": {
      const [workspaceId, capArg] = args;
      if (!workspaceId || !capArg) {
        printResult(
          json,
          { ok: false, error: "usage: workspaceguard set-cap <workspaceId> <count|none>" },
          ["usage: workspaceguard set-cap <workspaceId> <count|none>"],
        );
        process.exitCode = 1;
        return;
      }
      const cap = capArg === "none" ? undefined : Number.parseInt(capArg, 10);
      if (cap !== undefined && (!Number.isFinite(cap) || cap < 0)) {
        printResult(json, { ok: false, error: `invalid cap value: ${capArg}` }, [
          `invalid cap value: ${capArg} (must be a non-negative integer or "none")`,
        ]);
        process.exitCode = 1;
        return;
      }
      const guard = await createWorkspaceGuard({ dataDir, backend: new MockAdapter() });
      await guard.setCap(workspaceId, cap);
      printResult(json, { ok: true, workspaceId, cap: cap ?? null }, [
        cap === undefined
          ? `workspace ${workspaceId} cap cleared (unlimited)`
          : `workspace ${workspaceId} cap set to ${cap} messages/month`,
      ]);
      return;
    }
    case "scan": {
      printResult(json, { ok: true, findings: [] }, [
        "isolation config scan: no misconfigurations detected (scaffold stub)",
      ]);
      return;
    }
    default: {
      printResult(json, { ok: false, error: USAGE }, [USAGE]);
      process.exitCode = 1;
    }
  }
}

// Only run when invoked directly as the CLI entrypoint (`node cli/index.js`
// or the `workspaceguard` bin), never as a side effect of a test importing
// this module for its exported parsing helpers / `main()`. Compared via
// pathToFileURL (not a raw string template) because import.meta.url
// percent-encodes characters like spaces in the path while process.argv[1]
// does not -- a naive `file://${process.argv[1]}` comparison silently
// never matches on a path containing a space.
const isDirectRun = (() => {
  try {
    return process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href;
  } catch {
    return false;
  }
})();

if (isDirectRun) {
  main().catch((err: unknown) => {
    console.error(err instanceof Error ? err.message : String(err));
    process.exitCode = 1;
  });
}
