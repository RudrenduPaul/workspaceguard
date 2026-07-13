import { createCipheriv, createDecipheriv, randomBytes, createHmac } from "node:crypto";
import { mkdir, readFile, writeFile, chmod } from "node:fs/promises";
import { dirname, join } from "node:path";
import { VaultDecryptionError } from "./types.js";

const ALGORITHM = "aes-256-gcm";
const KEY_BYTES = 32;
const IV_BYTES = 12;

/**
 * One derived AES-256-GCM key per workspace: chat history and memory get a
 * directory boundary, the API-key vault gets its own encrypted file per
 * workspace so a leaked file alone (without the master key) reveals
 * nothing. Uses node:crypto rather than libsodium-wrappers -- the latter's
 * ESM build does not resolve cleanly under strict Node ESM resolution, and
 * node:crypto is the right tool for this same-process symmetric use case
 * (no need for libsodium's asymmetric sealed-box, which solves a different
 * problem: encrypting to a recipient who doesn't hold the decryption key).
 */
export class Vault {
  private masterKey: Buffer | undefined;

  constructor(private readonly masterKeyPath: string) {}

  async init(): Promise<void> {
    try {
      const raw = await readFile(this.masterKeyPath, "utf8");
      this.masterKey = Buffer.from(raw.trim(), "base64");
    } catch {
      this.masterKey = randomBytes(KEY_BYTES);
      await mkdir(dirname(this.masterKeyPath), { recursive: true });
      await writeFile(this.masterKeyPath, this.masterKey.toString("base64"), "utf8");
      await chmod(this.masterKeyPath, 0o600);
    }
  }

  private requireMasterKey(): Buffer {
    if (!this.masterKey) {
      throw new Error("Vault.init() must run before any vault operation");
    }
    return this.masterKey;
  }

  private deriveWorkspaceKey(workspaceId: string, generation: number): Buffer {
    const master = this.requireMasterKey();
    return createHmac("sha256", master).update(`${workspaceId}:${generation}`).digest();
  }

  vaultPath(dataDir: string, workspaceId: string): string {
    return join(dataDir, "workspaces", workspaceId, "vault.bin");
  }

  private generationPath(dataDir: string, workspaceId: string): string {
    return join(dataDir, "workspaces", workspaceId, "key-generation");
  }

  private async readGeneration(dataDir: string, workspaceId: string): Promise<number> {
    try {
      const raw = await readFile(this.generationPath(dataDir, workspaceId), "utf8");
      return Number.parseInt(raw.trim(), 10) || 0;
    } catch {
      return 0;
    }
  }

  async writeSecret(dataDir: string, workspaceId: string, plaintext: string): Promise<void> {
    const generation = await this.readGeneration(dataDir, workspaceId);
    const key = this.deriveWorkspaceKey(workspaceId, generation);
    const iv = randomBytes(IV_BYTES);
    const cipher = createCipheriv(ALGORITHM, key, iv);
    const ciphertext = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
    const authTag = cipher.getAuthTag();
    const path = this.vaultPath(dataDir, workspaceId);
    await mkdir(dirname(path), { recursive: true });
    const payload = Buffer.concat([iv, authTag, ciphertext]);
    await writeFile(path, payload);
    await chmod(path, 0o600);
  }

  async readSecret(dataDir: string, workspaceId: string): Promise<string> {
    const generation = await this.readGeneration(dataDir, workspaceId);
    const key = this.deriveWorkspaceKey(workspaceId, generation);
    const path = this.vaultPath(dataDir, workspaceId);
    let payload: Buffer;
    try {
      payload = await readFile(path);
    } catch {
      throw new VaultDecryptionError(workspaceId);
    }
    const iv = payload.subarray(0, IV_BYTES);
    const authTag = payload.subarray(IV_BYTES, IV_BYTES + 16);
    const ciphertext = payload.subarray(IV_BYTES + 16);
    try {
      const decipher = createDecipheriv(ALGORITHM, key, iv);
      decipher.setAuthTag(authTag);
      const plaintext = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
      return plaintext.toString("utf8");
    } catch {
      throw new VaultDecryptionError(workspaceId);
    }
  }

  /**
   * Rotation increments the per-workspace key generation BEFORE
   * re-encrypting, so the new ciphertext is under a genuinely different
   * derived key -- anything encrypted under the old generation can no
   * longer be decrypted once the generation file is bumped. The original implementation re-derived the same
   * deterministic key on "rotation," which was a no-op security-wise;
   * this fixes that. Behavior for an in-flight stream during rotation is
   * a known open question, not resolved here.
   */
  async rotate(dataDir: string, workspaceId: string): Promise<void> {
    const existing = await this.readSecret(dataDir, workspaceId).catch(() => undefined);
    const currentGeneration = await this.readGeneration(dataDir, workspaceId);
    const nextGeneration = currentGeneration + 1;
    await mkdir(dirname(this.generationPath(dataDir, workspaceId)), { recursive: true });
    await writeFile(this.generationPath(dataDir, workspaceId), String(nextGeneration), "utf8");
    if (existing !== undefined) {
      await this.writeSecret(dataDir, workspaceId, existing);
    }
  }
}
