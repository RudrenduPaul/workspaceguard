/**
 * A per-key in-process async mutex. Serializes concurrent calls that share
 * a key so a check-then-act sequence (e.g. quota check, then record) can't
 * interleave across two concurrent callers -- without this, N concurrent
 * requests at cap-1 could all pass the same pre-cap read and all proceed.
 * In-process is sufficient given this repo's documented single-sidecar-
 * process deployment model (see usage.ts); a multi-process deployment
 * would need a cross-process lock instead, which this repo does not
 * support today.
 */
const locks = new Map<string, Promise<void>>();

export async function withLock<T>(key: string, fn: () => Promise<T>): Promise<T> {
  const previous = locks.get(key) ?? Promise.resolve();
  let release!: () => void;
  const current = new Promise<void>((resolve) => {
    release = resolve;
  });
  locks.set(key, previous.then(() => current));
  await previous;
  try {
    return await fn();
  } finally {
    release();
  }
}
