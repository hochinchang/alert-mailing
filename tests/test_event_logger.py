"""
屬性測試與單元測試：EventLogger（告警事件歷史紀錄）
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.event_logger import InMemoryEventLogger, MySQLEventLogger
from src.models import AlertEvent


# ---------------------------------------------------------------------------
# 輔助函式
# ---------------------------------------------------------------------------

def _make_mock_conn(fetchone_result=None):
    """建立模擬的 PyMySQL 連線與 cursor。"""
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


def _make_event(**kwargs) -> AlertEvent:
    defaults = dict(
        event_id="evt-001",
        triggered_at=datetime(2024, 1, 1, 12, 0, 0),
        rule_name="磁碟使用率過高",
        source_ip="192.168.1.1",
        data_type="disk",
        field_name="Used",
        actual_value=95.0,
        threshold=90.0,
        extra={"file_system": "/dev/sda1"},
        recipients=["admin@example.com"],
    )
    defaults.update(kwargs)
    return AlertEvent(**defaults)


# ---------------------------------------------------------------------------
# InMemoryEventLogger 單元測試
# ---------------------------------------------------------------------------

class TestInMemoryEventLogger:
    def test_save_then_get_回傳相同事件(self):
        logger = InMemoryEventLogger()
        event = _make_event()
        logger.save(event)
        result = logger.get(event.event_id)
        assert result is not None
        assert result.event_id == event.event_id
        assert result.rule_name == event.rule_name

    def test_get_不存在的_event_id_回傳_None(self):
        logger = InMemoryEventLogger()
        assert logger.get("nonexistent") is None

    def test_重複_save_不覆蓋(self):
        logger = InMemoryEventLogger()
        event1 = _make_event(rule_name="first")
        event2 = _make_event(rule_name="second")  # 相同 event_id
        logger.save(event1)
        logger.save(event2)
        result = logger.get(event1.event_id)
        assert result.rule_name == "first"

    def test_recipients_不儲存(self):
        logger = InMemoryEventLogger()
        event = _make_event(recipients=["a@b.com", "c@d.com"])
        logger.save(event)
        result = logger.get(event.event_id)
        assert result.recipients == []

    def test_extra_dict_正確儲存(self):
        logger = InMemoryEventLogger()
        event = _make_event(extra={"key": "value", "num": "42"})
        logger.save(event)
        result = logger.get(event.event_id)
        assert result.extra == {"key": "value", "num": "42"}


# ---------------------------------------------------------------------------
# MySQLEventLogger 單元測試（使用 mock）
# ---------------------------------------------------------------------------

class TestMySQLEventLogger:
    def test_init_table_執行_CREATE_TABLE_並_commit(self):
        conn, cursor = _make_mock_conn()
        el = MySQLEventLogger(conn)
        el.init_table()
        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args[0][0]
        assert "CREATE TABLE" in sql.upper()
        assert "alert_events" in sql
        conn.commit.assert_called_once()

    def test_save_執行_INSERT_並_commit(self):
        conn, cursor = _make_mock_conn()
        el = MySQLEventLogger(conn)
        event = _make_event()
        el.save(event)
        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args[0][0]
        assert "INSERT" in sql.upper()
        conn.commit.assert_called_once()

    def test_get_查無紀錄時回傳_None(self):
        conn, cursor = _make_mock_conn(fetchone_result=None)
        el = MySQLEventLogger(conn)
        result = el.get("nonexistent")
        assert result is None

    def test_get_查有紀錄時回傳_AlertEvent(self):
        import json
        row = (
            "evt-001",
            datetime(2024, 1, 1, 12, 0, 0),
            "磁碟使用率過高",
            "192.168.1.1",
            "disk",
            "Used",
            95.0,
            90.0,
            json.dumps({"file_system": "/dev/sda1"}),
        )
        conn, cursor = _make_mock_conn(fetchone_result=row)
        el = MySQLEventLogger(conn)
        result = el.get("evt-001")
        assert result is not None
        assert result.event_id == "evt-001"
        assert result.rule_name == "磁碟使用率過高"
        assert result.extra == {"file_system": "/dev/sda1"}
        assert result.recipients == []

    def test_save_傳入正確的_event_id(self):
        conn, cursor = _make_mock_conn()
        el = MySQLEventLogger(conn)
        event = _make_event(event_id="test-id-123")
        el.save(event)
        args = cursor.execute.call_args[0][1]
        assert args[0] == "test-id-123"


# ---------------------------------------------------------------------------
# 屬性測試：Property 11 — Alert_Event 歷史紀錄 Round-Trip
# ---------------------------------------------------------------------------

# Feature: alert-notification-system, Property 11: Alert_Event 歷史紀錄 Round-Trip

alert_event_strategy = st.builds(
    AlertEvent,
    event_id=st.text(min_size=1, max_size=64),
    triggered_at=st.datetimes(),
    rule_name=st.text(min_size=1),
    source_ip=st.text(min_size=1),
    data_type=st.text(min_size=1),
    field_name=st.text(min_size=1),
    actual_value=st.floats(allow_nan=False, allow_infinity=False),
    threshold=st.floats(allow_nan=False, allow_infinity=False),
    extra=st.dictionaries(st.text(), st.text()),
    recipients=st.lists(st.text()),
)


@given(event=alert_event_strategy)
@settings(max_examples=100)
def test_event_history_round_trip(event: AlertEvent):
    """
    # Feature: alert-notification-system, Property 11: Alert_Event 歷史紀錄 Round-Trip

    Validates: Requirements 5.2

    對於任意 AlertEvent，save() 後 get() 應回傳欄位一致的紀錄。
    """
    logger = InMemoryEventLogger()
    logger.save(event)
    result = logger.get(event.event_id)

    assert result is not None
    assert result.event_id == event.event_id
    assert result.triggered_at == event.triggered_at
    assert result.rule_name == event.rule_name
    assert result.source_ip == event.source_ip
    assert result.data_type == event.data_type
    assert result.field_name == event.field_name
    assert result.actual_value == event.actual_value
    assert result.threshold == event.threshold
    assert result.extra == event.extra
