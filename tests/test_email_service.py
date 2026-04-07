"""
單元測試：EmailService（郵件服務）
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.email_service import EmailService
from src.models import AlertEvent


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------

def _make_service(**kwargs) -> EmailService:
    defaults = dict(sender="sender@example.com", retry_count=3)
    defaults.update(kwargs)
    return EmailService(**defaults)


def _make_event(**kwargs) -> AlertEvent:
    defaults = dict(
        event_id="abc123",
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


def _mock_run(returncode: int = 0, stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# format_body 測試：郵件內文包含所有必要欄位（需求 3.2）
# ---------------------------------------------------------------------------

class TestFormatBody:
    def test_包含_triggered_at(self):
        body = _make_service().format_body(_make_event(triggered_at=datetime(2024, 6, 1, 12, 0, 0)))
        assert "2024-06-01 12:00:00" in body

    def test_包含_rule_name(self):
        body = _make_service().format_body(_make_event(rule_name="系統負載過高"))
        assert "系統負載過高" in body

    def test_包含_source_ip(self):
        body = _make_service().format_body(_make_event(source_ip="10.0.0.1"))
        assert "10.0.0.1" in body

    def test_包含_data_type(self):
        body = _make_service().format_body(_make_event(data_type="system"))
        assert "system" in body

    def test_包含_field_name(self):
        body = _make_service().format_body(_make_event(field_name="Load_1"))
        assert "Load_1" in body

    def test_包含_actual_value(self):
        body = _make_service().format_body(_make_event(actual_value=95.5))
        assert "95.5" in body

    def test_包含_threshold(self):
        body = _make_service().format_body(_make_event(threshold=90.0))
        assert "90.0" in body

    def test_包含_extra_資訊(self):
        body = _make_service().format_body(
            _make_event(extra={"file_system": "/dev/sda1", "file_name": "test.dat"})
        )
        assert "/dev/sda1" in body
        assert "test.dat" in body

    def test_extra_為空時不崩潰(self):
        body = _make_service().format_body(_make_event(extra={}))
        assert "Used" in body

    def test_包含_event_id(self):
        body = _make_service().format_body(_make_event(event_id="deadbeef"))
        assert "deadbeef" in body


# ---------------------------------------------------------------------------
# send() 測試：使用系統 mail 指令
# ---------------------------------------------------------------------------

class TestSend:
    def test_發送成功回傳_True(self):
        svc = _make_service()
        with patch("subprocess.run", return_value=_mock_run(0)):
            result = svc.send(["user@example.com"], "Test Subject", "Test Body")
        assert result is True

    def test_指令回傳非零時回傳_False(self):
        svc = _make_service()
        with patch("subprocess.run", return_value=_mock_run(1, "mail: command failed")):
            result = svc.send(["user@example.com"], "Test Subject", "Test Body")
        assert result is False

    def test_找不到_mail_指令時回傳_False(self):
        svc = _make_service()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = svc.send(["user@example.com"], "Subject", "Body")
        assert result is False

    def test_例外時回傳_False(self):
        svc = _make_service()
        with patch("subprocess.run", side_effect=OSError("permission denied")):
            result = svc.send(["user@example.com"], "Subject", "Body")
        assert result is False

    def test_收件人列表為空時回傳_False(self):
        svc = _make_service()
        result = svc.send([], "Subject", "Body")
        assert result is False

    def test_呼叫_mail_指令帶正確參數(self):
        svc = _make_service()
        with patch("subprocess.run", return_value=_mock_run(0)) as mock_run:
            svc.send(["a@example.com", "b@example.com"], "Alert", "Body text")
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "mail"
        assert cmd[1] == "-s"
        assert cmd[2] == "Alert"
        assert "a@example.com" in cmd
        assert "b@example.com" in cmd

    def test_郵件內文透過_stdin_傳入(self):
        svc = _make_service()
        with patch("subprocess.run", return_value=_mock_run(0)) as mock_run:
            svc.send(["user@example.com"], "Subject", "Hello body")
        kwargs = mock_run.call_args[1]
        assert kwargs["input"] == "Hello body"
        assert kwargs["text"] is True

    def test_發送失敗時記錄錯誤日誌(self):
        svc = _make_service()
        with patch("subprocess.run", return_value=_mock_run(1, "error")):
            with patch("src.email_service.logger") as mock_logger:
                svc.send(["user@example.com"], "Subject", "Body")
                mock_logger.error.assert_called_once()


# ---------------------------------------------------------------------------
# 整合：format_body + send 組合驗證
# ---------------------------------------------------------------------------

class TestFormatBodyAndSend:
    def test_format_body_產生的內文可正常發送(self):
        svc = _make_service()
        event = _make_event()
        body = svc.format_body(event)
        with patch("subprocess.run", return_value=_mock_run(0)):
            result = svc.send(event.recipients, f"【告警】{event.rule_name}", body)
        assert result is True

    def test_郵件主旨包含規則名稱(self):
        event = _make_event(rule_name="記憶體使用率過高")
        subject = f"【告警】{event.rule_name}"
        assert "記憶體使用率過高" in subject
