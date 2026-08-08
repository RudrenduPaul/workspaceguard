"""
Ported from src/core/vault.test.ts. Covers Vault.init()'s overwrite
protection: an existing valid key is reused (not overwritten), a
corrupted/invalid-length key file is never silently regenerated over
without --force, and a non-"missing file" read error propagates instead of
being swallowed into "no key yet."
"""
from __future__ import annotations

import base64
import os
import tempfile

import pytest

from workspaceguard.vault import Vault


async def test_vault_init_generates_and_persists_a_fresh_32_byte_key_when_none_exists():
    with tempfile.TemporaryDirectory() as data_dir:
        key_path = os.path.join(data_dir, ".workspaceguard", "master.key")
        vault = Vault(key_path)
        await vault.init()

        with open(key_path, "r", encoding="utf-8") as fh:
            raw = fh.read().strip()
        assert len(base64.b64decode(raw)) == 32


async def test_vault_init_reuses_an_existing_valid_key_rather_than_overwriting_it():
    with tempfile.TemporaryDirectory() as data_dir:
        key_path = os.path.join(data_dir, ".workspaceguard", "master.key")
        first = Vault(key_path)
        await first.init()
        with open(key_path, "r", encoding="utf-8") as fh:
            original_raw = fh.read()

        second = Vault(key_path)
        await second.init()
        with open(key_path, "r", encoding="utf-8") as fh:
            after_raw = fh.read()

        assert original_raw == after_raw


async def test_vault_init_refuses_to_silently_overwrite_a_corrupted_key_without_force():
    with tempfile.TemporaryDirectory() as data_dir:
        key_dir = os.path.join(data_dir, ".workspaceguard")
        os.makedirs(key_dir, exist_ok=True)
        key_path = os.path.join(key_dir, "master.key")
        with open(key_path, "w", encoding="utf-8") as fh:
            fh.write("dG9vLXNob3J0")  # base64("too-short"), not 32 bytes

        vault = Vault(key_path)
        with pytest.raises(ValueError, match="does not decode to a valid"):
            await vault.init()

        with open(key_path, "r", encoding="utf-8") as fh:
            still_raw = fh.read()
        assert still_raw == "dG9vLXNob3J0"


async def test_vault_init_force_true_regenerates_over_a_corrupted_key():
    with tempfile.TemporaryDirectory() as data_dir:
        key_dir = os.path.join(data_dir, ".workspaceguard")
        os.makedirs(key_dir, exist_ok=True)
        key_path = os.path.join(key_dir, "master.key")
        with open(key_path, "w", encoding="utf-8") as fh:
            fh.write("dG9vLXNob3J0")

        vault = Vault(key_path)
        await vault.init(force=True)

        with open(key_path, "r", encoding="utf-8") as fh:
            raw = fh.read().strip()
        assert raw != "dG9vLXNob3J0"
        assert len(base64.b64decode(raw)) == 32


async def test_vault_init_propagates_a_non_missing_file_read_error():
    with tempfile.TemporaryDirectory() as data_dir:
        # Point the "key file" path at a directory, not a file, so open()
        # fails with IsADirectoryError rather than FileNotFoundError -- this
        # must fail loudly, not be swallowed into "no key yet, generate one."
        key_path = os.path.join(data_dir, ".workspaceguard", "master.key")
        os.makedirs(key_path, exist_ok=True)

        vault = Vault(key_path)
        with pytest.raises(IsADirectoryError):
            await vault.init()
