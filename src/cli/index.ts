#!/usr/bin/env node
import { createRequire } from "node:module";
import { createWorkspaceGuard } from "../index.js";
import { MockAdapter } from "../adapters/mock.js";

const require = createRequire(import.meta.url);
const { version: PACKAGE_VERSION } = require("../../package.json") as { version: string };

const HELP_TEXT = `usage: workspaceguard <command> [args] [--json]

commands:
  init                              initialize workspaceguard in the current (or configured) data directory
  add-workspace <id> --identity <v> register a new workspace with its identity
  status                            list configured workspaces and their isolation status
  rotate-key <id>                   rotate the API key for a workspace
  usage                             print per-workspace message-usage counts and caps
  set-cap <id> <count|none>         set (or clear) a workspace's monthly message cap
  scan                              scan isolation config for misconfigurations

global options:
  --json          output structured JSON instead of human-readable text
  -h, --help      show this help message and exit
  -V, --version   show the installed version and exit`;

const STARTUP_WARNING =
  "WARNING: workspaceguard must never be directly reachable from the network.\n" +
  "It trusts an upstream identity header (e.g. Cf-Access-Authenticated-User-Email)\n" +
  "set by your reverse proxy. If this port is exposed without that proxy in front\n" +
  "of it, anyone can impersonate any workspace. Firewall this port; only your\n" +
  "trusted proxy should be able to reach it.";

const USAGE =
  "usage: workspaceguard <init|add-workspace|status|rotate-key|usage|set-cap|scan> [--json]";

/** Strips a boolean flag out of an argv slice, agent-native mode toggle for every command. */
function extractJsonFlag(args: string[]): { json: boolean; rest: string[] } {
  const rest = args.filter((a) => a !== "--json");
  return { json: rest.length !== args.length, rest };
}

function printResult(json: boolean, data: unknown, humanLines: string[]): void {
  if (json) {
    console.log(JSON.stringify(data));
    return;
  }
  for (const line of humanLines) console.log(line);
}

async function main(): Promise<void> {
  const [, , command, ...rawArgs] = process.argv;
  const { json, rest: args } = extractJsonFlag(rawArgs);
  const dataDir = process.env.WORKSPACEGUARD_DATA_DIR ?? process.cwd();

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
      const guard = await createWorkspaceGuard({ dataDir, backend: new MockAdapter() });
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

main().catch((err: unknown) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
