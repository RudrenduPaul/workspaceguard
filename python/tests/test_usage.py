"""Ported from src/core/usage.test.ts."""
from __future__ import annotations

import tempfile

import pytest

from workspaceguard.usage import (
    QuotaExceededError,
    UsageMeter,
    current_usage_for,
    load_usage,
    usage_path,
    WorkspaceUsage,
)


async def test_recording_increments_per_workspace_count_and_byte_estimate():
    with tempfile.TemporaryDirectory() as data_dir:
        meter = UsageMeter(data_dir)
        await meter.record("alex", "hello")
        await meter.record("alex", "world!!")

        usage = await meter.get("alex")
        assert usage.message_count == 2
        assert usage.estimated_bytes == len("hello".encode("utf-8")) + len("world!!".encode("utf-8"))


async def test_workspaces_are_isolated_usage_never_leaks_between_workspaces():
    with tempfile.TemporaryDirectory() as data_dir:
        meter = UsageMeter(data_dir)
        await meter.record("alex", "a1")
        await meter.record("alex", "a2")
        await meter.record("jordan", "j1")

        all_usage = await meter.get_all(["alex", "jordan"])
        assert all_usage["alex"].message_count == 2
        assert all_usage["jordan"].message_count == 1


async def test_unconfigured_workspace_reads_as_zero_not_an_error():
    with tempfile.TemporaryDirectory() as data_dir:
        meter = UsageMeter(data_dir)
        usage = await meter.get("never-recorded")
        assert usage.message_count == 0
        assert usage.estimated_bytes == 0


async def test_quota_undefined_cap_never_throws_regardless_of_usage():
    with tempfile.TemporaryDirectory() as data_dir:
        meter = UsageMeter(data_dir)
        for _ in range(50):
            await meter.record("alex", "msg")
        await meter.check_quota("alex", None)  # must not raise


async def test_quota_throws_once_message_count_reaches_configured_cap():
    with tempfile.TemporaryDirectory() as data_dir:
        meter = UsageMeter(data_dir)
        await meter.check_quota("alex", 2)  # must not raise
        await meter.record("alex", "msg-1")
        await meter.check_quota("alex", 2)  # must not raise
        await meter.record("alex", "msg-2")
        with pytest.raises(QuotaExceededError):
            await meter.check_quota("alex", 2)


async def test_one_workspace_hitting_cap_never_blocks_a_sibling_workspace():
    with tempfile.TemporaryDirectory() as data_dir:
        meter = UsageMeter(data_dir)
        await meter.record("alex", "msg-1")
        with pytest.raises(QuotaExceededError):
            await meter.check_quota("alex", 1)
        await meter.check_quota("jordan", 1)  # must not raise


async def test_load_usage_missing_file_is_a_legitimate_empty_store():
    with tempfile.TemporaryDirectory() as data_dir:
        store = load_usage(data_dir)
        assert store == {}


async def test_load_usage_corrupted_file_raises_instead_of_silently_reading_as_empty():
    """Regression: this used to fail open, lifting every quota."""
    with tempfile.TemporaryDirectory() as data_dir:
        meter = UsageMeter(data_dir)
        await meter.record("alex", "msg-1")  # creates .workspaceguard/usage.json
        with open(usage_path(data_dir), "w", encoding="utf-8") as fh:
            fh.write("{ not valid json")

        with pytest.raises(ValueError, match="corrupted"):
            load_usage(data_dir)
        with pytest.raises(ValueError, match="corrupted"):
            await meter.check_quota("alex", 1)


async def test_load_usage_unexpected_shape_raises_instead_of_silently_reading_as_empty():
    with tempfile.TemporaryDirectory() as data_dir:
        meter = UsageMeter(data_dir)
        await meter.record("alex", "msg-1")
        with open(usage_path(data_dir), "w", encoding="utf-8") as fh:
            fh.write("[]")

        with pytest.raises(ValueError, match="unexpected shape"):
            load_usage(data_dir)


def test_current_usage_for_rolls_stale_period_over_to_fresh_zeroed_bucket():
    stale = current_usage_for(
        {"alex": WorkspaceUsage(period="2020-01", message_count=999, estimated_bytes=999)}, "alex"
    )
    assert stale.message_count == 0
    assert stale.estimated_bytes == 0
    assert stale.period != "2020-01"
