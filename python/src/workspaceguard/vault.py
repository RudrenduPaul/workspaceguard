"""
One derived AES-256-GCM key per workspace: chat history and memory get a
directory boundary (namespace.py), the API-key vault gets its own encrypted
file per workspace so a leaked file alone (without the master key) reveals
nothing. Ported from src/core/vault.ts, using the `cryptography` package's
AESGCM primitive (the Python ecosystem's standard, actively maintained
choice for authenticated symmetric encryption) in place of Node's
node:crypto.

On-disk layout is kept identical to the TypeScript original (12-byte IV +
16-byte GCM auth tag + ciphertext, concatenated) so a vault file's format is
conceptually portable between the two distributions even though a real
deployment would run one or the other against a given data directory, not
both against the same one simultaneously.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .types import VaultDecryptionError

KEY_BYTES = 32
IV_BYTES = 12
TAG_BYTES = 16


class Vault:
    def __init__(self, master_key_path: str) -> None:
        self._master_key_path = master_key_path
        self._master_key: Optional[bytes] = None

    async def init(self) -> None:
        try:
            with open(self._master_key_path, "r", encoding="utf-8") as fh:
                raw = fh.read().strip()
            import base64

            self._master_key = base64.b64decode(raw)
        except FileNotFoundError:
            import base64

            self._master_key = secrets.token_bytes(KEY_BYTES)
            os.makedirs(os.path.dirname(self._master_key_path), exist_ok=True)
            with open(self._master_key_path, "w", encoding="utf-8") as fh:
                fh.write(base64.b64encode(self._master_key).decode("ascii"))
            os.chmod(self._master_key_path, 0o600)

    def _require_master_key(self) -> bytes:
        if self._master_key is None:
            raise RuntimeError("Vault.init() must run before any vault operation")
        return self._master_key

    def _derive_workspace_key(self, workspace_id: str, generation: int) -> bytes:
        master = self._require_master_key()
        message = f"{workspace_id}:{generation}".encode("utf-8")
        return hmac.new(master, message, hashlib.sha256).digest()

    def vault_path(self, data_dir: str, workspace_id: str) -> str:
        return os.path.join(data_dir, "workspaces", workspace_id, "vault.bin")

    def _generation_path(self, data_dir: str, workspace_id: str) -> str:
        return os.path.join(data_dir, "workspaces", workspace_id, "key-generation")

    def _read_generation(self, data_dir: str, workspace_id: str) -> int:
        try:
            with open(self._generation_path(data_dir, workspace_id), "r", encoding="utf-8") as fh:
                return int(fh.read().strip() or "0")
        except (FileNotFoundError, ValueError):
            return 0

    async def write_secret(self, data_dir: str, workspace_id: str, plaintext: str) -> None:
        generation = self._read_generation(data_dir, workspace_id)
        key = self._derive_workspace_key(workspace_id, generation)
        iv = secrets.token_bytes(IV_BYTES)
        aesgcm = AESGCM(key)
        sealed = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
        ciphertext, auth_tag = sealed[:-TAG_BYTES], sealed[-TAG_BYTES:]
        path = self.vault_path(data_dir, workspace_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(iv + auth_tag + ciphertext)
        os.chmod(path, 0o600)

    async def read_secret(self, data_dir: str, workspace_id: str) -> str:
        generation = self._read_generation(data_dir, workspace_id)
        key = self._derive_workspace_key(workspace_id, generation)
        path = self.vault_path(data_dir, workspace_id)
        try:
            with open(path, "rb") as fh:
                payload = fh.read()
        except FileNotFoundError:
            raise VaultDecryptionError(workspace_id)
        iv = payload[:IV_BYTES]
        auth_tag = payload[IV_BYTES : IV_BYTES + TAG_BYTES]
        ciphertext = payload[IV_BYTES + TAG_BYTES :]
        try:
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(iv, ciphertext + auth_tag, None)
            return plaintext.decode("utf-8")
        except (InvalidTag, ValueError):
            raise VaultDecryptionError(workspace_id)

    async def rotate(self, data_dir: str, workspace_id: str) -> None:
        """
        Rotation increments the per-workspace key generation BEFORE
        re-encrypting, so the new ciphertext is under a genuinely different
        derived key -- anything encrypted under the old generation can no
        longer be decrypted once the generation file is bumped. Behavior for
        an in-flight stream during rotation is a known open question, not
        resolved here (matches the TypeScript original).
        """
        try:
            existing: Optional[str] = await self.read_secret(data_dir, workspace_id)
        except VaultDecryptionError:
            existing = None
        current_generation = self._read_generation(data_dir, workspace_id)
        next_generation = current_generation + 1
        generation_path = self._generation_path(data_dir, workspace_id)
        os.makedirs(os.path.dirname(generation_path), exist_ok=True)
        with open(generation_path, "w", encoding="utf-8") as fh:
            fh.write(str(next_generation))
        if existing is not None:
            await self.write_secret(data_dir, workspace_id, existing)
