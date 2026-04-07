"""
單元測試：DedupeStore（去重狀態儲存）
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from src.dedupe_store import InMemoryDedupeStore, MySQLDedupeStore


# ---------------------------------------------------------------------------
# InMemoryDedupeStore 測試
# ---------------------------------------------------------------------------

class TestInMemoryDedupeStore:
    def test_未標記時_is_sent_應回傳_False(self):
        store = InMemoryDedupeStore()
        assert store.is_sent("evt-001", "user@example.com") is False

    def test_mark_sent_後_is_sent_應回傳_True(self):
        store = InMemoryDedupeStore()
        store.mark_sent("evt-001", "user@example.com")
        assert store.is_sent("evt-001", "user@example.com") is True

    def test_不同收件人_互不影響(self):
        store = InMemoryDedupeStore()
        store.mark_sent("evt-001", "a@example.com")
        # 同一事件但不同收件人，應回傳 False
        assert store.is_sent("evt-001", "b@example.com") is False

    def test_不同事件_互不影響(self):
        store = InMemoryDedupeStore()
        store.mark_sent("evt-001", "user@example.com")
        # 不同事件但相同收件人，應回傳 False
        assert store.is_sent("evt-002", "user@example.com") is False

    def test_重複_mark_sent_不影響結果(self):
        store = InMemoryDedupeStore()
        store.mark_sent("evt-001", "user@example.com")
        store.mark_sent("evt-001", "user@example.com")  # 重複標記
        assert store.is_sent("evt-001", "user@example.com") is True

    def test_多筆紀錄_各自獨立(self):
        store = InMemoryDedupeStore()
        store.mark_sent("evt-001", "a@example.com")
        store.mark_sent("evt-002", "b@example.com")
        assert store.is_sent("evt-001", "a@example.com") is True
        assert store.is_sent("evt-002", "b@example.com") is True
        assert store.is_sent("evt-001", "b@example.com") is False
        assert store.is_sent("evt-002", "a@example.com") is False


# ---------------------------------------------------------------------------
# MySQLDedupeStore 測試（使用 mock PyMySQL 連線）
# ---------------------------------------------------------------------------

def _make_mock_conn(fetchone_result=None):
    """建立模擬的 PyMySQL 連線與 cursor。"""
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    # 支援 context manager（with conn.cursor() as cursor）
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


class TestMySQLDedupeStore:
    def test_is_sent_查無紀錄時回傳_False(self):
        conn, cursor = _make_mock_conn(fetchone_result=None)
        store = MySQLDedupeStore(conn)
        result = store.is_sent("evt-001", "user@example.com")
        assert result is False
        cursor.execute.assert_called_once()

    def test_is_sent_查有紀錄時回傳_True(self):
        conn, cursor = _make_mock_conn(fetchone_result=(1,))
        store = MySQLDedupeStore(conn)
        result = store.is_sent("evt-001", "user@example.com")
        assert result is True

    def test_mark_sent_執行_INSERT_並_commit(self):
        conn, cursor = _make_mock_conn()
        store = MySQLDedupeStore(conn)
        store.mark_sent("evt-001", "user@example.com")
        # 確認有執行 INSERT 語句
        cursor.execute.assert_called_once()
        sql_called = cursor.execute.call_args[0][0]
        assert "INSERT" in sql_called.upper()
        # 確認有 commit
        conn.commit.assert_called_once()

    def test_mark_sent_傳入正確參數(self):
        conn, cursor = _make_mock_conn()
        store = MySQLDedupeStore(conn)
        store.mark_sent("evt-abc", "recipient@test.com")
        args = cursor.execute.call_args[0][1]
        assert args[0] == "evt-abc"
        assert args[1] == "recipient@test.com"
        # sent_at 應為 datetime 物件
        from datetime import datetime
        assert isinstance(args[2], datetime)

    def test_init_table_執行_CREATE_TABLE_並_commit(self):
        conn, cursor = _make_mock_conn()
        store = MySQLDedupeStore(conn)
        store.init_table()
        cursor.execute.assert_called_once()
        sql_called = cursor.execute.call_args[0][0]
        assert "CREATE TABLE" in sql_called.upper()
        assert "alert_dedupe" in sql_called
        conn.commit.assert_called_once()

    def test_is_sent_查詢包含正確的_event_id_與_recipient(self):
        conn, cursor = _make_mock_conn(fetchone_result=None)
        store = MySQLDedupeStore(conn)
        store.is_sent("my-event", "target@mail.com")
        args = cursor.execute.call_args[0][1]
        assert args[0] == "my-event"
        assert args[1] == "target@mail.com"
