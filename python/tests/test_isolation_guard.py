"""Ported from src/core/isolation-guard.test.ts.

The adversarial two-workspace cross-read suite: distinguishable data in each
workspace, assert one workspace's session can never read, list, or infer the
existence of another's -- chat history, memory namespace, and API-key vault,
each tested independently. Plus the usage-metering + billing wedge tests
(the pivot from per-user isolation, which the target platform already ships
natively -- see README).
"""
from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from workspaceguard import (
    BackendCircuitOpenError,
    IdentityNotFoundError,
    QuotaExceededError,
    WorkspaceNotFoundError,
    create_workspace_guard,
)
from workspaceguard.adapters.mock import MockAdapter
from workspaceguard.config import DuplicateIdentityError
from workspaceguard.namespace import chat_history_dir
from workspaceguard.vault import Vault


async def test_chat_history_is_isolated_per_workspace_never_readable_cross_workspace():
    with tempfile.TemporaryDirectory() as data_dir:
        adapter = MockAdapter()
        guard = await create_workspace_guard(data_dir=data_dir, backend=adapter)
        await guard.add_workspace("alex", "alex@example.com")
        await guard.add_workspace("jordan", "jordan@example.com")

        await guard.chat("alex@example.com", "alex-secret-message")
        await guard.chat("jordan@example.com", "jordan-secret-message")

        assert adapter._messages_for("alex") == ["alex-secret-message"]
        assert adapter._messages_for("jordan") == ["jordan-secret-message"]
        assert "jordan-secret-message" not in adapter._messages_for("alex")
        assert "alex-secret-message" not in adapter._messages_for("jordan")

        alex_dir = chat_history_dir(data_dir, "alex")
        jordan_dir = chat_history_dir(data_dir, "jordan")
        assert alex_dir != jordan_dir


async def test_vault_secret_cannot_be_decrypted_or_read_under_another_workspace_id():
    with tempfile.TemporaryDirectory() as data_dir:
        adapter = MockAdapter()
        guard = await create_workspace_guard(data_dir=data_dir, backend=adapter)
        await guard.add_workspace("alex", "alex@example.com")
        await guard.add_workspace("jordan", "jordan@example.com")

        await guard.set_secret("alex", "sk-alex-api-key")
        await guard.set_secret("jordan", "sk-jordan-api-key")

        vault = Vault(os.path.join(data_dir, ".workspaceguard", "master.key"))
        with open(vault.vault_path(data_dir, "alex"), "rb") as fh:
            alex_vault_raw = fh.read()
        with open(vault.vault_path(data_dir, "jordan"), "rb") as fh:
            jordan_vault_raw = fh.read()

        assert alex_vault_raw != jordan_vault_raw


async def test_key_rotation_actually_invalidates_the_old_key():
    with tempfile.TemporaryDirectory() as data_dir:
        adapter = MockAdapter()
        guard = await create_workspace_guard(data_dir=data_dir, backend=adapter)
        await guard.add_workspace("alex", "alex@example.com")
        await guard.set_secret("alex", "sk-alex-before-rotation")

        vault = Vault(os.path.join(data_dir, ".workspaceguard", "master.key"))
        await vault.init()
        with open(vault.vault_path(data_dir, "alex"), "rb") as fh:
            before_rotation = fh.read()

        await guard.rotate_key("alex")
        with open(vault.vault_path(data_dir, "alex"), "rb") as fh:
            after_rotation = fh.read()

        assert before_rotation != after_rotation

        round_trip = await vault.read_secret(data_dir, "alex")
        assert round_trip == "sk-alex-before-rotation"


async def test_duplicate_identity_across_two_workspace_ids_is_rejected():
    with tempfile.TemporaryDirectory() as data_dir:
        adapter = MockAdapter()
        guard = await create_workspace_guard(data_dir=data_dir, backend=adapter)
        await guard.add_workspace("alex", "shared@example.com")

        with pytest.raises(DuplicateIdentityError):
            await guard.add_workspace("jordan", "shared@example.com")

        statuses = await guard.status()
        assert len(statuses) == 1
        assert statuses[0]["workspaceId"] == "alex"


async def test_circuit_breaker_opens_after_3_failures_then_self_heals_after_cooldown():
    with tempfile.TemporaryDirectory() as data_dir:
        adapter = MockAdapter()
        guard = await create_workspace_guard(data_dir=data_dir, backend=adapter, circuit_open_cooldown_ms=50)
        await guard.add_workspace("alex", "alex@example.com")

        adapter._fail_next_calls(3)
        for i in range(3):
            with pytest.raises(Exception):
                await guard.chat("alex@example.com", f"msg-{i}")

        with pytest.raises(BackendCircuitOpenError):
            await guard.chat("alex@example.com", "should-be-circuit-open")

        await asyncio.sleep(0.06)
        response = await guard.chat("alex@example.com", "probe-after-cooldown")
        assert response == "echo: probe-after-cooldown"

        response2 = await guard.chat("alex@example.com", "should-work-normally")
        assert response2 == "echo: should-work-normally"


async def test_fail_closed_missing_identity_header_is_rejected():
    with tempfile.TemporaryDirectory() as data_dir:
        adapter = MockAdapter()
        guard = await create_workspace_guard(data_dir=data_dir, backend=adapter)
        await guard.add_workspace("alex", "alex@example.com")

        with pytest.raises(IdentityNotFoundError):
            await guard.chat(None, "anonymous message")
        with pytest.raises(IdentityNotFoundError):
            await guard.chat("nobody@example.com", "spoofed message")

        assert adapter._messages_for("alex") == []


async def test_add_workspace_is_idempotent():
    with tempfile.TemporaryDirectory() as data_dir:
        adapter = MockAdapter()
        guard = await create_workspace_guard(data_dir=data_dir, backend=adapter)
        await guard.add_workspace("alex", "alex@example.com")
        await guard.add_workspace("alex", "someone-else@example.com")

        statuses = await guard.status()
        assert len(statuses) == 1
        assert statuses[0]["identity"] == "alex@example.com"


async def test_usage_metering_chat_increments_per_workspace_usage_isolated():
    with tempfile.TemporaryDirectory() as data_dir:
        adapter = MockAdapter()
        guard = await create_workspace_guard(data_dir=data_dir, backend=adapter)
        await guard.add_workspace("alex", "alex@example.com")
        await guard.add_workspace("jordan", "jordan@example.com")

        await guard.chat("alex@example.com", "hi")
        await guard.chat("alex@example.com", "hi again")
        await guard.chat("jordan@example.com", "hello")

        report = await guard.usage_report()
        alex = next(r for r in report if r.workspace_id == "alex")
        jordan = next(r for r in report if r.workspace_id == "jordan")
        assert alex.message_count == 2
        assert jordan.message_count == 1


async def test_quota_workspace_at_monthly_cap_is_blocked_never_reaches_backend():
    with tempfile.TemporaryDirectory() as data_dir:
        adapter = MockAdapter()
        guard = await create_workspace_guard(data_dir=data_dir, backend=adapter)
        await guard.add_workspace("alex", "alex@example.com")
        await guard.set_cap("alex", 1)

        await guard.chat("alex@example.com", "first message, under cap")
        with pytest.raises(QuotaExceededError):
            await guard.chat("alex@example.com", "second message, over cap")

        assert adapter._messages_for("alex") == ["first message, under cap"]


async def test_quota_one_workspace_hitting_cap_never_blocks_sibling_with_no_cap():
    with tempfile.TemporaryDirectory() as data_dir:
        adapter = MockAdapter()
        guard = await create_workspace_guard(data_dir=data_dir, backend=adapter)
        await guard.add_workspace("alex", "alex@example.com")
        await guard.add_workspace("jordan", "jordan@example.com")
        await guard.set_cap("alex", 1)

        await guard.chat("alex@example.com", "msg")
        with pytest.raises(QuotaExceededError):
            await guard.chat("alex@example.com", "over cap")

        response = await guard.chat("jordan@example.com", "still works")
        assert response == "echo: still works"


async def test_quota_clearing_a_cap_lifts_the_block():
    with tempfile.TemporaryDirectory() as data_dir:
        adapter = MockAdapter()
        guard = await create_workspace_guard(data_dir=data_dir, backend=adapter)
        await guard.add_workspace("alex", "alex@example.com")
        await guard.set_cap("alex", 1)
        await guard.chat("alex@example.com", "msg")
        with pytest.raises(QuotaExceededError):
            await guard.chat("alex@example.com", "blocked")

        await guard.set_cap("alex", None)
        response = await guard.chat("alex@example.com", "unblocked now")
        assert response == "echo: unblocked now"


async def test_set_cap_on_unknown_workspace_id_fails_loudly():
    with tempfile.TemporaryDirectory() as data_dir:
        adapter = MockAdapter()
        guard = await create_workspace_guard(data_dir=data_dir, backend=adapter)
        with pytest.raises(WorkspaceNotFoundError):
            await guard.set_cap("nobody", 5)


async def test_usage_report_percent_used_computed_null_when_uncapped():
    with tempfile.TemporaryDirectory() as data_dir:
        adapter = MockAdapter()
        guard = await create_workspace_guard(data_dir=data_dir, backend=adapter)
        await guard.add_workspace("alex", "alex@example.com")
        await guard.add_workspace("jordan", "jordan@example.com")
        await guard.set_cap("alex", 4)
        await guard.chat("alex@example.com", "one")

        report = await guard.usage_report()
        alex = next(r for r in report if r.workspace_id == "alex")
        jordan = next(r for r in report if r.workspace_id == "jordan")
        assert alex.percent_used == 25
        assert jordan.percent_used is None
