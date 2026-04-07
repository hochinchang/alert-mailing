"""Unit tests for DataFetcher.fetch_disk_status()"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pymysql
import pytest

from src.data_fetcher import DataFetcher
from src.models import DiskRecord


def _make_fetcher(conn=None):
    """Build a DataFetcher with _connect_all stubbed out."""
    with patch.object(DataFetcher, "_connect_all"):
        fetcher = DataFetcher(db_configs={})
    fetcher._connections["disk_status"] = conn
    return fetcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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

def test_fetch_disk_status_returns_disk_records():
    """Normal rows are mapped to DiskRecord instances correctly."""
    now = datetime(2024, 1, 15, 12, 0, 0)
    rows = [
        {"IP": "192.168.1.1", "ServerTime": now, "FileSystem": "/dev/sda1", "Used": 75.5},
        {"IP": "192.168.1.2", "ServerTime": now, "FileSystem": "/dev/sdb1", "Used": 50.0},
    ]
    fetcher = _make_fetcher(conn=_mock_conn(rows))
    result = fetcher.fetch_disk_status()

    assert len(result) == 2
    assert all(isinstance(r, DiskRecord) for r in result)
    assert result[0].ip == "192.168.1.1"
    assert result[0].server_time == now
    assert result[0].file_system == "/dev/sda1"
    assert result[0].used == 75.5
    assert result[1].ip == "192.168.1.2"


def test_fetch_disk_status_queries_checklist_table():
    """The SQL must target the CheckList table."""
    conn = _mock_conn([])
    fetcher = _make_fetcher(conn=conn)
    fetcher.fetch_disk_status()

    executed_sql: str = conn.cursor.return_value.execute.call_args[0][0]
    assert "CheckList" in executed_sql


def test_fetch_disk_status_empty_table_returns_empty_list():
    """An empty CheckList returns an empty list without error."""
    fetcher = _make_fetcher(conn=_mock_conn([]))
    assert fetcher.fetch_disk_status() == []


def test_fetch_disk_status_no_connection_returns_empty_list():
    """When the connection is None (failed at init), return [] and log error."""
    fetcher = _make_fetcher(conn=None)
    result = fetcher.fetch_disk_status()
    assert result == []


def test_fetch_disk_status_db_error_returns_empty_list():
    """A pymysql.Error during query is caught and returns []."""
    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.execute.side_effect = pymysql.Error("connection lost")

    conn = MagicMock()
    conn.cursor.return_value = cursor

    fetcher = _make_fetcher(conn=conn)
    result = fetcher.fetch_disk_status()
    assert result == []


def test_fetch_disk_status_used_cast_to_float():
    """Used values stored as strings/Decimal are cast to float."""
    now = datetime(2024, 1, 15, 12, 0, 0)
    rows = [{"IP": "10.0.0.1", "ServerTime": now, "FileSystem": "/", "Used": "88"}]
    fetcher = _make_fetcher(conn=_mock_conn(rows))
    result = fetcher.fetch_disk_status()
    assert isinstance(result[0].used, float)
    assert result[0].used == 88.0
