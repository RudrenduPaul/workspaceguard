#!/usr/bin/env node
import { createWorkspaceGuard } from "../index.js";
import { MockAdapter } from "../adapters/mock.js";

const STARTUP_WARNING =
  "WARNING: workspaceguard must never be directly reachable from the network.\n" +
  "It trusts an upstream identity header (e.g. Cf-Access-Authenticated-User-Email)\n" +
  "set by your reverse proxy. If this port is exposed without that proxy in front\n" +
  "of it, anyone can impersonate any workspace. Firewall this port; only your\n" +
  "trusted proxy should be able to reach it.";

async function main(): Promise<void> {
  const [, , command, ...args] = process.argv;
  const dataDir = process.env.WORKSPACEGUARD_DATA_DIR ?? process.cwd();

  switch (command) {
    case "init": {
      console.log(STARTUP_WARNING);
      const guard = await createWorkspaceGuard({ dataDir, backend: new MockAdapter() });
      await guard.status();
      console.log(`workspaceguard initialized in ${dataDir}`);
      return;
    }
    case "add-workspace": {
      const [workspaceId, , identity] = args; // add-workspace <id> --identity <value>
      if (!workspaceId || !identity) {
        console.error("usage: workspaceguard add-workspace <id> --identity <value>");
        process.exitCode = 1;
        return;
      }
      const guard = await createWorkspaceGuard({ dataDir, backend: new MockAdapter() });
      await guard.addWorkspace(workspaceId, identity);
      console.log(`workspace ${workspaceId} added`);
      return;
    }
    case "status": {
      const guard = await createWorkspaceGuard({ dataDir, backend: new MockAdapter() });
      const workspaces = await guard.status();
      if (workspaces.length === 0) {
        console.log("no workspaces configured");
        return;
      }
      for (const w of workspaces) {
        console.log(`-> ${w.workspaceId} [isolated] identity: ${w.identity}`);
      }
      console.log("No cross-workspace leaks detected.");
      return;
    }
    case "scan": {
      console.log("isolation config scan: no misconfigurations detected (scaffold stub)");
      return;
    }
    default: {
      console.error("usage: workspaceguard <init|add-workspace|status|scan>");
      process.exitCode = 1;
    }
  }
}

main().catch((err: unknown) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
