"""Tests for DataFetcher.fetch_all() — task 4.5."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.data_fetcher import DataFetcher
from src.models import DiskRecord, FetchResult, FileRecord, SystemRecord


def _make_fetcher() -> DataFetcher:
    """Build a DataFetcher with all DB connections mocked out."""
    with patch.object(DataFetcher, "_connect_all"):
        fetcher = DataFetcher.__new__(DataFetcher)
        fetcher._db_configs = {}
        fetcher._connections = {
            "disk_status": None,
            "system_status": None,
            "file_status": None,
        }
    return fetcher


# ---------------------------------------------------------------------------
# Basic integration
# ---------------------------------------------------------------------------

def test_fetch_all_returns_fetch_result():
    fetcher = _make_fetcher()
    fetcher.fetch_disk_status = MagicMock(return_value=[])
    fetcher.fetch_system_status = MagicMock(return_value=[])
    fetcher.fetch_file_status = MagicMock(return_value=[])

    result = fetcher.fetch_all()

    assert isinstance(result, FetchResult)


def test_fetch_all_sets_fetch_time_before_calls():
    fetcher = _make_fetcher()
    call_times: list[datetime] = []

    def record_time():
        call_times.append(datetime.now())
        return []

    fetcher.fetch_disk_status = record_time
    fetcher.fetch_system_status = MagicMock(return_value=[])
    fetcher.fetch_file_status = MagicMock(return_value=[])

    before = datetime.now()
    result = fetcher.fetch_all()
    after = datetime.now()

    assert before <= result.fetch_time <= after


def test_fetch_all_aggregates_records():
    disk = [DiskRecord(ip="1.1.1.1", server_time=datetime.now(), file_system="/", used=50.0)]
    system = [SystemRecord(ip="1.1.1.1", server_time=datetime.now(), load_1=1.0, load_5=1.0, load_15=1.0, memory_use=40.0)]
    file = [FileRecord(ip="1.1.1.1", file_name="f.bin", file_type="radar", file_time=1000.0, source_table="radarFileCheck")]

    fetcher = _make_fetcher()
    fetcher.fetch_disk_status = MagicMock(return_value=disk)
    fetcher.fetch_system_status = MagicMock(return_value=system)
    fetcher.fetch_file_status = MagicMock(return_value=file)

    result = fetcher.fetch_all()

    assert result.disk_records == disk
    assert result.system_records == system
    assert result.file_records == file


# ---------------------------------------------------------------------------
# Error isolation — each source failure must not affect the others
# ---------------------------------------------------------------------------

def test_fetch_all_disk_failure_returns_empty_disk():
    fetcher = _make_fetcher()
    fetcher.fetch_disk_status = MagicMock(side_effect=RuntimeError("disk boom"))
    fetcher.fetch_system_status = MagicMock(return_value=[])
    fetcher.fetch_file_status = MagicMock(return_value=[])

    result = fetcher.fetch_all()

    assert result.disk_records == []
    assert isinstance(result, FetchResult)


def test_fetch_all_system_failure_does_not_affect_disk_or_file():
    disk = [DiskRecord(ip="2.2.2.2", server_time=datetime.now(), file_system="/data", used=70.0)]
    file = [FileRecord(ip="2.2.2.2", file_name="x.bin", file_type="ds", file_time=2000.0, source_table="DSFileCheck")]

    fetcher = _make_fetcher()
    fetcher.fetch_disk_status = MagicMock(return_value=disk)
    fetcher.fetch_system_status = MagicMock(side_effect=Exception("system boom"))
    fetcher.fetch_file_status = MagicMock(return_value=file)

    result = fetcher.fetch_all()

    assert result.disk_records == disk
    assert result.system_records == []
    assert result.file_records == file


def test_fetch_all_file_failure_does_not_affect_disk_or_system():
    disk = [DiskRecord(ip="3.3.3.3", server_time=datetime.now(), file_system="/tmp", used=20.0)]
    system = [SystemRecord(ip="3.3.3.3", server_time=datetime.now(), load_1=0.5, load_5=0.5, load_15=0.5, memory_use=30.0)]

    fetcher = _make_fetcher()
    fetcher.fetch_disk_status = MagicMock(return_value=disk)
    fetcher.fetch_system_status = MagicMock(return_value=system)
    fetcher.fetch_file_status = MagicMock(side_effect=Exception("file boom"))

    result = fetcher.fetch_all()

    assert result.disk_records == disk
    assert result.system_records == system
    assert result.file_records == []


def test_fetch_all_all_sources_fail_returns_empty_lists():
    fetcher = _make_fetcher()
    fetcher.fetch_disk_status = MagicMock(side_effect=Exception("disk"))
    fetcher.fetch_system_status = MagicMock(side_effect=Exception("system"))
    fetcher.fetch_file_status = MagicMock(side_effect=Exception("file"))

    result = fetcher.fetch_all()

    assert result.disk_records == []
    assert result.system_records == []
    assert result.file_records == []
    assert isinstance(result.fetch_time, datetime)


# ---------------------------------------------------------------------------
# Property-based test — Property 1: 資料讀取錯誤隔離
# ---------------------------------------------------------------------------

# Feature: alert-notification-system, Property 1: 資料讀取錯誤隔離
# Validates: Requirements 1.2

from hypothesis import given, settings
from hypothesis import strategies as st

# Strategy: randomly pick a non-empty subset of sources to fail
_SOURCES = ["disk", "system", "file"]

_failing_sources_st = st.frozensets(
    st.sampled_from(_SOURCES), min_size=1, max_size=2
)

_disk_record_st = st.builds(
    DiskRecord,
    ip=st.ip_addresses(v=4).map(str),
    server_time=st.just(datetime(2024, 1, 15, 12, 0, 0)),
    file_system=st.just("/dev/sda1"),
    used=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
)

_system_record_st = st.builds(
    SystemRecord,
    ip=st.ip_addresses(v=4).map(str),
    server_time=st.just(datetime(2024, 1, 15, 12, 0, 0)),
    load_1=st.floats(min_value=0.0, max_value=32.0, allow_nan=False),
    load_5=st.floats(min_value=0.0, max_value=32.0, allow_nan=False),
    load_15=st.floats(min_value=0.0, max_value=32.0, allow_nan=False),
    memory_use=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
)

_file_record_st = st.builds(
    FileRecord,
    ip=st.ip_addresses(v=4).map(str),
    file_name=st.just("file.dat"),
    file_type=st.sampled_from(["radar", "ds", "hf"]),
    file_time=st.floats(min_value=1_000_000.0, max_value=2_000_000_000.0, allow_nan=False),
    source_table=st.sampled_from(["radarFileCheck", "DSFileCheck", "HFradarFileCheck"]),
)


@given(
    failing_sources=_failing_sources_st,
    disk_data=st.lists(_disk_record_st, min_size=1, max_size=5),
    system_data=st.lists(_system_record_st, min_size=1, max_size=5),
    file_data=st.lists(_file_record_st, min_size=1, max_size=5),
)
@settings(max_examples=100)
def test_fetch_error_isolation(failing_sources, disk_data, system_data, file_data):
    """Property 1: when any source raises an exception, the other sources'
    results in FetchResult are unaffected (non-empty lists equal to mocked data).
    Failing sources must return empty lists."""
    fetcher = _make_fetcher()

    # Wire up each source: failing → raise Exception, healthy → return data
    fetcher.fetch_disk_status = (
        MagicMock(side_effect=Exception("disk connection error"))
        if "disk" in failing_sources
        else MagicMock(return_value=disk_data)
    )
    fetcher.fetch_system_status = (
        MagicMock(side_effect=Exception("system connection error"))
        if "system" in failing_sources
        else MagicMock(return_value=system_data)
    )
    fetcher.fetch_file_status = (
        MagicMock(side_effect=Exception("file connection error"))
        if "file" in failing_sources
        else MagicMock(return_value=file_data)
    )

    result = fetcher.fetch_all()

    # Failing sources must produce empty lists
    if "disk" in failing_sources:
        assert result.disk_records == [], (
            f"disk failed but disk_records={result.disk_records!r}"
        )
    else:
        assert result.disk_records == disk_data, (
            f"disk healthy but disk_records={result.disk_records!r} != {disk_data!r}"
        )

    if "system" in failing_sources:
        assert result.system_records == [], (
            f"system failed but system_records={result.system_records!r}"
        )
    else:
        assert result.system_records == system_data, (
            f"system healthy but system_records={result.system_records!r} != {system_data!r}"
        )

    if "file" in failing_sources:
        assert result.file_records == [], (
            f"file failed but file_records={result.file_records!r}"
        )
    else:
        assert result.file_records == file_data, (
            f"file healthy but file_records={result.file_records!r} != {file_data!r}"
        )


# ---------------------------------------------------------------------------
# Property-based test — Property 2: 空資料不產生告警事件
# ---------------------------------------------------------------------------

# Feature: alert-notification-system, Property 2: 空資料不產生告警事件
# Validates: Requirements 1.2

# Strategy: randomly pick a non-empty subset of sources to return empty lists
_empty_sources_st = st.frozensets(
    st.sampled_from(_SOURCES), min_size=1, max_size=3
)


@given(
    empty_sources=_empty_sources_st,
    disk_data=st.lists(_disk_record_st, min_size=1, max_size=5),
    system_data=st.lists(_system_record_st, min_size=1, max_size=5),
    file_data=st.lists(_file_record_st, min_size=1, max_size=5),
)
@settings(max_examples=100)
def test_empty_source_produces_empty_fetch_result_field(
    empty_sources, disk_data, system_data, file_data
):
    """Property 2: when any data source returns an empty list, the corresponding
    FetchResult field should be an empty list."""
    fetcher = _make_fetcher()

    # Sources in empty_sources return [], others return non-empty data
    fetcher.fetch_disk_status = (
        MagicMock(return_value=[])
        if "disk" in empty_sources
        else MagicMock(return_value=disk_data)
    )
    fetcher.fetch_system_status = (
        MagicMock(return_value=[])
        if "system" in empty_sources
        else MagicMock(return_value=system_data)
    )
    fetcher.fetch_file_status = (
        MagicMock(return_value=[])
        if "file" in empty_sources
        else MagicMock(return_value=file_data)
    )

    result = fetcher.fetch_all()

    # Sources that returned [] must have empty lists in FetchResult
    if "disk" in empty_sources:
        assert result.disk_records == [], (
            f"disk returned [] but disk_records={result.disk_records!r}"
        )
    else:
        assert result.disk_records == disk_data, (
            f"disk returned data but disk_records={result.disk_records!r} != {disk_data!r}"
        )

    if "system" in empty_sources:
        assert result.system_records == [], (
            f"system returned [] but system_records={result.system_records!r}"
        )
    else:
        assert result.system_records == system_data, (
            f"system returned data but system_records={result.system_records!r} != {system_data!r}"
        )

    if "file" in empty_sources:
        assert result.file_records == [], (
            f"file returned [] but file_records={result.file_records!r}"
        )
    else:
        assert result.file_records == file_data, (
            f"file returned data but file_records={result.file_records!r} != {file_data!r}"
        )
