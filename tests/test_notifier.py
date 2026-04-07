"""
單元測試與屬性測試：Notifier（通知器）
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.dedupe_store import InMemoryDedupeStore
from src.models import AlertEvent
from src.notifier import Notifier


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------

def _make_event(**kwargs) -> AlertEvent:
    defaults = dict(
        event_id="evt-001",
        triggered_at=datetime(2024, 6, 1, 12, 0, 0),
        rule_name="磁碟使用率過高",
        source_ip="192.168.1.1",
        data_type="disk",
        field_name="Used",
        actual_value=95.5,
        threshold=90.0,
        extra={"file_system": "/dev/sda1"},
        recipients=["admin@example.com"],
    )
    defaults.update(kwargs)
    return AlertEvent(**defaults)


def _make_mock_email_service(send_return: bool = True) -> MagicMock:
    svc = MagicMock()
    svc.send.return_value = send_return
    svc.format_body.return_value = "郵件內文"
    return svc


def _make_notifier(send_return: bool = True, retry_count: int = 3):
    email_svc = _make_mock_email_service(send_return)
    dedupe = InMemoryDedupeStore()
    notifier = Notifier(email_svc, dedupe, retry_count=retry_count)
    return notifier, email_svc, dedupe


# ---------------------------------------------------------------------------
# 單元測試：基本行為
# ---------------------------------------------------------------------------

class TestNotifierBasic:
    def test_發送成功後_mark_sent_被呼叫(self):
        notifier, email_svc, dedupe = _make_notifier(send_return=True)
        event = _make_event(event_id="e1", recipients=["a@example.com"])
        notifier.notify([event])
        assert dedupe.is_sent("e1", "a@example.com") is True

    def test_發送失敗時_mark_sent_不被呼叫(self):
        notifier, email_svc, dedupe = _make_notifier(send_return=False, retry_count=0)
        event = _make_event(event_id="e1", recipients=["a@example.com"])
        notifier.notify([event])
        assert dedupe.is_sent("e1", "a@example.com") is False

    def test_已發送的收件人不再呼叫_send(self):
        notifier, email_svc, dedupe = _make_notifier(send_return=True)
        event = _make_event(event_id="e1", recipients=["a@example.com"])
        notifier.notify([event])
        first_call_count = email_svc.send.call_count
        # 再次 notify 同一事件
        notifier.notify([event])
        assert email_svc.send.call_count == first_call_count  # 不應再呼叫

    def test_多位收件人各自發送(self):
        notifier, email_svc, dedupe = _make_notifier(send_return=True)
        event = _make_event(recipients=["a@example.com", "b@example.com", "c@example.com"])
        notifier.notify([event])
        assert email_svc.send.call_count == 3

    def test_空事件列表不呼叫_send(self):
        notifier, email_svc, dedupe = _make_notifier()
        notifier.notify([])
        email_svc.send.assert_not_called()

    def test_發送成功記錄_INFO_日誌(self):
        notifier, email_svc, dedupe = _make_notifier(send_return=True)
        event = _make_event(recipients=["a@example.com"])
        with patch("src.notifier.logger") as mock_logger:
            notifier.notify([event])
            mock_logger.info.assert_called_once()

    def test_全部失敗記錄_ERROR_日誌(self):
        notifier, email_svc, dedupe = _make_notifier(send_return=False, retry_count=0)
        event = _make_event(recipients=["a@example.com"])
        with patch("src.notifier.logger") as mock_logger:
            notifier.notify([event])
            mock_logger.error.assert_called_once()

    def test_send_傳入單一收件人列表(self):
        notifier, email_svc, dedupe = _make_notifier(send_return=True)
        event = _make_event(recipients=["target@example.com"])
        notifier.notify([event])
        call_args = email_svc.send.call_args[0]
        assert call_args[0] == ["target@example.com"]


# ---------------------------------------------------------------------------
# 單元測試：重試邏輯
# ---------------------------------------------------------------------------

class TestNotifierRetry:
    def test_retry_count_0_只嘗試一次(self):
        notifier, email_svc, dedupe = _make_notifier(send_return=False, retry_count=0)
        event = _make_event(recipients=["a@example.com"])
        notifier.notify([event])
        assert email_svc.send.call_count == 1

    def test_retry_count_3_失敗時共嘗試4次(self):
        notifier, email_svc, dedupe = _make_notifier(send_return=False, retry_count=3)
        event = _make_event(recipients=["a@example.com"])
        notifier.notify([event])
        assert email_svc.send.call_count == 4

    def test_第一次成功不再重試(self):
        notifier, email_svc, dedupe = _make_notifier(send_return=True, retry_count=3)
        event = _make_event(recipients=["a@example.com"])
        notifier.notify([event])
        assert email_svc.send.call_count == 1

    def test_第二次成功停止重試(self):
        email_svc = MagicMock()
        # 第一次失敗，第二次成功
        email_svc.send.side_effect = [False, True]
        email_svc.format_body.return_value = "body"
        dedupe = InMemoryDedupeStore()
        notifier = Notifier(email_svc, dedupe, retry_count=3)
        event = _make_event(recipients=["a@example.com"])
        notifier.notify([event])
        assert email_svc.send.call_count == 2
        assert dedupe.is_sent(event.event_id, "a@example.com") is True


# ---------------------------------------------------------------------------
# 屬性測試（屬性 5）：通知覆蓋所有收件人
# Feature: alert-notification-system, Property 5: 通知覆蓋所有收件人
# ---------------------------------------------------------------------------

_email_strategy = st.emails()
_recipients_strategy = st.lists(_email_strategy, min_size=1, max_size=10, unique=True)


@given(recipients=_recipients_strategy)
@settings(max_examples=100)
def test_notify_all_recipients(recipients):
    """
    屬性 5：對任意 AlertEvent 與收件人列表，
    EmailService.send 的呼叫次數應等於收件人數量。
    """
    # Feature: alert-notification-system, Property 5: 通知覆蓋所有收件人
    email_svc = _make_mock_email_service(send_return=True)
    dedupe = InMemoryDedupeStore()
    notifier = Notifier(email_svc, dedupe, retry_count=0)
    event = _make_event(event_id="prop5-evt", recipients=recipients)

    notifier.notify([event])

    assert email_svc.send.call_count == len(recipients)


# ---------------------------------------------------------------------------
# 屬性測試（屬性 6）：郵件內文包含所有必要欄位
# Feature: alert-notification-system, Property 6: 通知郵件內容完整性
# ---------------------------------------------------------------------------

_printable = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")),
    min_size=1, max_size=30,
)
_ip_strategy = st.from_regex(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", fullmatch=True)
_float_strategy = st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
_datetime_strategy = st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2099, 12, 31))
_data_type_strategy = st.sampled_from(["disk", "system", "file"])


@given(
    rule_name=_printable,
    source_ip=_ip_strategy,
    data_type=_data_type_strategy,
    field_name=_printable,
    actual_value=_float_strategy,
    threshold=_float_strategy,
    triggered_at=_datetime_strategy,
)
@settings(max_examples=100)
def test_email_content_completeness(
    rule_name, source_ip, data_type, field_name, actual_value, threshold, triggered_at
):
    """
    屬性 6：對任意 AlertEvent，組裝的郵件內文應包含所有必要欄位。
    """
    # Feature: alert-notification-system, Property 6: 通知郵件內容完整性
    from src.email_service import EmailService

    svc = EmailService(
        smtp_host="smtp.example.com",
        smtp_port=587,
        sender="sender@example.com",
        username="sender@example.com",
        password="secret",
    )
    event = AlertEvent(
        event_id="prop6-evt",
        triggered_at=triggered_at,
        rule_name=rule_name,
        source_ip=source_ip,
        data_type=data_type,
        field_name=field_name,
        actual_value=actual_value,
        threshold=threshold,
        extra={},
        recipients=["r@example.com"],
    )

    body = svc.format_body(event)

    assert triggered_at.strftime("%Y-%m-%d %H:%M:%S") in body
    assert rule_name in body
    assert source_ip in body
    assert data_type in body
    assert field_name in body
    assert str(actual_value) in body
    assert str(threshold) in body


# ---------------------------------------------------------------------------
# 屬性測試（屬性 7）：發送失敗重試次數符合設定
# Feature: alert-notification-system, Property 7: 發送失敗重試次數符合設定
# ---------------------------------------------------------------------------

@given(retry_count=st.integers(min_value=0, max_value=10))
@settings(max_examples=50)
def test_retry_count_matches_config(retry_count):
    """
    屬性 7：EmailService 持續失敗時，呼叫總次數應為 retry_count + 1。
    """
    # Feature: alert-notification-system, Property 7: 發送失敗重試次數符合設定
    email_svc = _make_mock_email_service(send_return=False)
    dedupe = InMemoryDedupeStore()
    notifier = Notifier(email_svc, dedupe, retry_count=retry_count)
    event = _make_event(recipients=["a@example.com"])

    notifier.notify([event])

    assert email_svc.send.call_count == retry_count + 1


# ---------------------------------------------------------------------------
# 屬性測試（屬性 8）：防重複通知冪等性
# Feature: alert-notification-system, Property 8: 防重複通知冪等性
# ---------------------------------------------------------------------------

@given(call_count=st.integers(min_value=1, max_value=10))
@settings(max_examples=50)
def test_dedupe_idempotency(call_count):
    """
    屬性 8：多次呼叫 notify() 時，同一（event_id, recipient）組合的
    實際發送次數應恰好為 1。
    """
    # Feature: alert-notification-system, Property 8: 防重複通知冪等性
    email_svc = _make_mock_email_service(send_return=True)
    dedupe = InMemoryDedupeStore()
    notifier = Notifier(email_svc, dedupe, retry_count=0)
    event = _make_event(event_id="prop8-evt", recipients=["a@example.com"])

    for _ in range(call_count):
        notifier.notify([event])

    # 無論呼叫幾次，send 只應被呼叫一次
    assert email_svc.send.call_count == 1
