import { homedir } from "node:os";
import { join } from "node:path";

/**
 * Default data directory when neither `--data-dir` nor
 * `WORKSPACEGUARD_DATA_DIR` is given. This used to default to
 * `process.cwd()`, which silently wrote a live AES-256-GCM master key into
 * whatever directory the command happened to be run from -- a real risk of
 * dropping (or, if that directory turned out to already hold one, colliding
 * with) key material in an unrelated project.
 *
 * `~/.workspaceguard` is stable regardless of cwd. This is implemented
 * directly with `node:os`'s `homedir()` rather than pulling in a
 * cross-platform app-data-directory package -- no such dependency exists
 * yet in package.json, and a single flat directory under the user's home
 * is enough here (this is not an OS-integrated desktop app with a reason
 * to follow each platform's full app-data convention).
 */
export function defaultDataDir(): string {
  return join(homedir(), ".workspaceguard");
}
