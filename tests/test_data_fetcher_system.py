"""Unit tests for DataFetcher.fetch_system_status()"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pymysql
import pytest

from src.data_fetcher import DataFetcher
from src.models import SystemRecord


def _make_fetcher(conn=None):
    """Build a DataFetcher with _connect_all stubbed out."""
    with patch.object(DataFetcher, "_connect_all"):
        fetcher = DataFetcher(db_configs={})
    fetcher._connections["system_status"] = conn
    return fetcher


def _mock_conn(rows: list[dict]):
    """Return a mock PyMySQL connection whose cursor yields *rows*."""
    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchall.return_value = rows

    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fetch_system_status_returns_system_records():
    """Normal rows are mapped to SystemRecord instances correctly."""
    now = datetime(2024, 1, 15, 12, 0, 0)
    rows = [
        {"IP": "192.168.1.1", "ServerTime": now, "Load_1": 1.5, "Load_5": 1.2, "LOAD_15": 0.9, "MemoryUSE": 72.3},
        {"IP": "192.168.1.2", "ServerTime": now, "Load_1": 3.0, "Load_5": 2.8, "LOAD_15": 2.5, "MemoryUSE": 85.0},
    ]
    fetcher = _make_fetcher(conn=_mock_conn(rows))
    result = fetcher.fetch_system_status()

    assert len(result) == 2
    assert all(isinstance(r, SystemRecord) for r in result)
    assert result[0].ip == "192.168.1.1"
    assert result[0].server_time == now
    assert result[0].load_1 == 1.5
    assert result[0].load_5 == 1.2
    assert result[0].load_15 == 0.9
    assert result[0].memory_use == 72.3
    assert result[1].ip == "192.168.1.2"


def test_fetch_system_status_queries_checklist_table():
    """The SQL must target the CheckList table."""
    conn = _mock_conn([])
    fetcher = _make_fetcher(conn=conn)
    fetcher.fetch_system_status()

    executed_sql: str = conn.cursor.return_value.execute.call_args[0][0]
    assert "CheckList" in executed_sql


def test_fetch_system_status_empty_table_returns_empty_list():
    """An empty CheckList returns an empty list without error."""
    fetcher = _make_fetcher(conn=_mock_conn([]))
    assert fetcher.fetch_system_status() == []


def test_fetch_system_status_no_connection_returns_empty_list():
    """When the connection is None (failed at init), return [] and log error."""
    fetcher = _make_fetcher(conn=None)
    result = fetcher.fetch_system_status()
    assert result == []


def test_fetch_system_status_db_error_returns_empty_list():
    """A pymysql.Error during query is caught and returns []."""
    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.execute.side_effect = pymysql.Error("connection lost")

    conn = MagicMock()
    conn.cursor.return_value = cursor

    fetcher = _make_fetcher(conn=conn)
    result = fetcher.fetch_system_status()
    assert result == []


def test_fetch_system_status_values_cast_to_float():
    """Load and MemoryUSE values stored as strings/Decimal are cast to float."""
    now = datetime(2024, 1, 15, 12, 0, 0)
    rows = [{"IP": "10.0.0.1", "ServerTime": now, "Load_1": "2", "Load_5": "1", "LOAD_15": "0", "MemoryUSE": "90"}]
    fetcher = _make_fetcher(conn=_mock_conn(rows))
    result = fetcher.fetch_system_status()
    assert isinstance(result[0].load_1, float)
    assert isinstance(result[0].load_5, float)
    assert isinstance(result[0].load_15, float)
    assert isinstance(result[0].memory_use, float)
    assert result[0].memory_use == 90.0
