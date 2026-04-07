"""Unit tests for DataFetcher.fetch_file_status()"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pymysql
import pytest

from src.data_fetcher import DataFetcher
from src.models import FileRecord


def _make_fetcher(conn=None):
    """Build a DataFetcher with _connect_all stubbed out."""
    with patch.object(DataFetcher, "_connect_all"):
        fetcher = DataFetcher(db_configs={})
    fetcher._connections["file_status"] = conn
    return fetcher


def _mock_conn_multi(table_rows: dict[str, list[dict]]):
    """Return a mock connection that returns different rows per table query."""
    call_count = [0]
    tables = ["radarFileCheck", "DSFileCheck", "HFradarFileCheck"]

    def fetchall_side_effect():
        idx = call_count[0]
        call_count[0] += 1
        table = tables[idx - 1] if idx > 0 else tables[0]
        return table_rows.get(table, [])

    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)

    # Track execute calls to know which table was queried
    executed_tables = []

    def execute_side_effect(sql, *args):
        for t in tables:
            if t in sql:
                executed_tables.append(t)
                break

    cursor.execute.side_effect = execute_side_effect
    cursor.fetchall.side_effect = lambda: table_rows.get(
        executed_tables[-1] if executed_tables else "", []
    )

    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def _mock_conn_simple(rows: list[dict]):
    """Return a mock connection that always returns the same rows."""
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

def test_fetch_file_status_no_connection_returns_empty_list():
    """When the connection is None (failed at init), return [] and log error."""
    fetcher = _make_fetcher(conn=None)
    result = fetcher.fetch_file_status()
    assert result == []


def test_fetch_file_status_empty_tables_returns_empty_list():
    """All three tables empty returns an empty list without error."""
    conn = _mock_conn_simple([])
    fetcher = _make_fetcher(conn=conn)
    assert fetcher.fetch_file_status() == []


def test_fetch_file_status_returns_file_records():
    """Rows from all three tables are mapped to FileRecord instances."""
    row = {"IP": "192.168.1.1", "FileName": "radar_20240115.dat", "FileType": "radar", "FileTime": 1705320000.0}
    conn = _mock_conn_simple([row])
    fetcher = _make_fetcher(conn=conn)
    result = fetcher.fetch_file_status()

    # 3 tables × 1 row each
    assert len(result) == 3
    assert all(isinstance(r, FileRecord) for r in result)


def test_fetch_file_status_source_table_set_correctly():
    """source_table field is set to the queried table name for each record."""
    row = {"IP": "10.0.0.1", "FileName": "file.dat", "FileType": "ds", "FileTime": 1705320000.0}
    conn = _mock_conn_multi({
        "radarFileCheck": [{"IP": "10.0.0.1", "FileName": "r.dat", "FileType": "radar", "FileTime": 1705320000.0}],
        "DSFileCheck":    [{"IP": "10.0.0.2", "FileName": "d.dat", "FileType": "ds",    "FileTime": 1705320001.0}],
        "HFradarFileCheck": [{"IP": "10.0.0.3", "FileName": "h.dat", "FileType": "hf", "FileTime": 1705320002.0}],
    })
    fetcher = _make_fetcher(conn=conn)
    result = fetcher.fetch_file_status()

    assert len(result) == 3
    source_tables = {r.source_table for r in result}
    assert source_tables == {"radarFileCheck", "DSFileCheck", "HFradarFileCheck"}


def test_fetch_file_status_queries_all_three_tables():
    """SQL must target all three CheckList tables."""
    conn = _mock_conn_simple([])
    fetcher = _make_fetcher(conn=conn)
    fetcher.fetch_file_status()

    executed_sqls = [c[0][0] for c in conn.cursor.return_value.execute.call_args_list]
    assert any("radarFileCheck" in sql for sql in executed_sqls)
    assert any("DSFileCheck" in sql for sql in executed_sqls)
    assert any("HFradarFileCheck" in sql for sql in executed_sqls)


def test_fetch_file_status_file_time_cast_to_float():
    """FileTime stored as string/Decimal is cast to float."""
    row = {"IP": "10.0.0.1", "FileName": "f.dat", "FileType": "radar", "FileTime": "1705320000"}
    conn = _mock_conn_simple([row])
    fetcher = _make_fetcher(conn=conn)
    result = fetcher.fetch_file_status()
    assert all(isinstance(r.file_time, float) for r in result)


def test_fetch_file_status_one_table_error_others_succeed():
    """A pymysql.Error on one table is caught; other tables still return records."""
    good_row = {"IP": "10.0.0.1", "FileName": "f.dat", "FileType": "radar", "FileTime": 1705320000.0}

    call_count = [0]

    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)

    def execute_side_effect(sql, *args):
        call_count[0] += 1
        if call_count[0] == 1:
            raise pymysql.Error("table error")

    cursor.execute.side_effect = execute_side_effect
    cursor.fetchall.return_value = [good_row]

    conn = MagicMock()
    conn.cursor.return_value = cursor

    fetcher = _make_fetcher(conn=conn)
    result = fetcher.fetch_file_status()

    # First table fails, two remaining tables succeed (1 row each)
    assert len(result) == 2
    assert all(isinstance(r, FileRecord) for r in result)


def test_fetch_file_status_record_fields_mapped_correctly():
    """All FileRecord fields are populated from the correct columns."""
    row = {"IP": "172.16.0.5", "FileName": "hf_data.bin", "FileType": "hf", "FileTime": 1705400000.5}
    conn = _mock_conn_simple([row])
    fetcher = _make_fetcher(conn=conn)
    result = fetcher.fetch_file_status()

    # Check one record (all three tables return the same row)
    r = result[0]
    assert r.ip == "172.16.0.5"
    assert r.file_name == "hf_data.bin"
    assert r.file_type == "hf"
    assert r.file_time == 1705400000.5
