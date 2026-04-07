"""Tests for src/evaluator.py – unit tests (5.8) and property tests (5.9, 5.10, 5.11)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.evaluator import Evaluator
from src.models import (
    AlertRule,
    DiskRecord,
    FetchResult,
    FileRecord,
    SystemRecord,
)
from src.rule_loader import RuleLoader

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_rule(
    name: str = "test-rule",
    source: str = "disk",
    field: str = "Used",
    threshold: float = 90.0,
    enabled: bool = True,
    recipients: list[str] | None = None,
) -> AlertRule:
    return AlertRule(
        name=name,
        source=source,
        field=field,
        threshold=threshold,
        recipients=recipients or ["admin@example.com"],
        enabled=enabled,
    )


def _make_evaluator(rules: list[AlertRule]) -> Evaluator:
    loader = MagicMock(spec=RuleLoader)
    loader.load.return_value = rules
    return Evaluator(loader)


def _disk_snapshot(ip: str, used: float, file_system: str = "/dev/sda1") -> FetchResult:
    return FetchResult(
        disk_records=[DiskRecord(ip=ip, server_time=_NOW, file_system=file_system, used=used)],
        system_records=[],
        file_records=[],
        fetch_time=_NOW,
    )


def _system_snapshot(ip: str, load_1=0.0, load_5=0.0, load_15=0.0, memory_use=0.0) -> FetchResult:
    return FetchResult(
        disk_records=[],
        system_records=[SystemRecord(
            ip=ip, server_time=_NOW,
            load_1=load_1, load_5=load_5, load_15=load_15, memory_use=memory_use,
        )],
        file_records=[],
        fetch_time=_NOW,
    )


def _file_snapshot(ip: str, file_time, fetch_time: datetime = _NOW) -> FetchResult:
    return FetchResult(
        disk_records=[],
        system_records=[],
        file_records=[FileRecord(
            ip=ip,
            file_name="radar.nc",
            file_type="nc",
            file_time=file_time,
            source_table="radarFileCheck",
        )],
        fetch_time=fetch_time,
    )


# ---------------------------------------------------------------------------
# 5.8 Unit tests
# ---------------------------------------------------------------------------

class TestDiskAlert:
    def test_disk_alert_triggered(self):
        ev = _make_evaluator([_make_rule(source="disk", field="Used", threshold=90.0)])
        events = ev.evaluate(_disk_snapshot("10.0.0.1", used=95.0))
        assert len(events) == 1
        e = events[0]
        assert e.actual_value == 95.0
        assert e.threshold == 90.0
        assert e.field_name == "Used"
        assert e.data_type == "disk"
        assert e.source_ip == "10.0.0.1"

    def test_disk_alert_not_triggered(self):
        ev = _make_evaluator([_make_rule(source="disk", field="Used", threshold=90.0)])
        events = ev.evaluate(_disk_snapshot("10.0.0.1", used=85.0))
        assert events == []

    def test_disk_alert_equal_threshold_not_triggered(self):
        ev = _make_evaluator([_make_rule(source="disk", field="Used", threshold=90.0)])
        events = ev.evaluate(_disk_snapshot("10.0.0.1", used=90.0))
        assert events == []


class TestSystemAlert:
    def test_system_load1_alert(self):
        ev = _make_evaluator([_make_rule(source="system", field="Load_1", threshold=4.0)])
        events = ev.evaluate(_system_snapshot("10.0.0.2", load_1=5.0))
        assert len(events) == 1
        assert events[0].field_name == "Load_1"
        assert events[0].actual_value == 5.0

    def test_system_load5_alert(self):
        ev = _make_evaluator([_make_rule(source="system", field="Load_5", threshold=4.0)])
        events = ev.evaluate(_system_snapshot("10.0.0.2", load_5=5.0))
        assert len(events) == 1
        assert events[0].field_name == "Load_5"

    def test_system_load15_alert(self):
        ev = _make_evaluator([_make_rule(source="system", field="LOAD_15", threshold=4.0)])
        events = ev.evaluate(_system_snapshot("10.0.0.2", load_15=5.0))
        assert len(events) == 1
        assert events[0].field_name == "LOAD_15"

    def test_system_memory_alert(self):
        ev = _make_evaluator([_make_rule(source="system", field="MemoryUSE", threshold=85.0)])
        events = ev.evaluate(_system_snapshot("10.0.0.2", memory_use=90.0))
        assert len(events) == 1
        assert events[0].field_name == "MemoryUSE"
        assert events[0].actual_value == 90.0


class TestFileAlert:
    def test_file_lag_alert(self):
        # file_time = now - 3600s → FileLag = 60 min > threshold 30
        fetch_time = _NOW
        file_time = fetch_time.timestamp() - 3600
        ev = _make_evaluator([_make_rule(source="file", field="FileLag", threshold=30.0)])
        events = ev.evaluate(_file_snapshot("10.0.0.3", file_time=file_time, fetch_time=fetch_time))
        assert len(events) == 1
        assert events[0].actual_value == pytest.approx(60.0)
        assert events[0].field_name == "FileLag"
        assert events[0].data_type == "file"

    def test_file_lag_none(self):
        ev = _make_evaluator([_make_rule(source="file", field="FileLag", threshold=30.0)])
        events = ev.evaluate(_file_snapshot("10.0.0.3", file_time=None))
        assert events == []

    def test_file_lag_negative(self):
        # file_time in the future → negative lag → treated as 0 → no alert
        fetch_time = _NOW
        file_time = fetch_time.timestamp() + 3600  # future
        ev = _make_evaluator([_make_rule(source="file", field="FileLag", threshold=30.0)])
        events = ev.evaluate(_file_snapshot("10.0.0.3", file_time=file_time, fetch_time=fetch_time))
        assert events == []

    def test_file_lag_extra_fields(self):
        fetch_time = _NOW
        file_time = fetch_time.timestamp() - 3600
        ev = _make_evaluator([_make_rule(source="file", field="FileLag", threshold=30.0)])
        events = ev.evaluate(_file_snapshot("10.0.0.3", file_time=file_time, fetch_time=fetch_time))
        assert events[0].extra == {
            "file_name": "radar.nc",
            "file_type": "nc",
            "source_table": "radarFileCheck",
        }


class TestDisabledRule:
    def test_disabled_rule_skipped(self):
        rule = _make_rule(source="disk", field="Used", threshold=90.0, enabled=False)
        ev = _make_evaluator([rule])
        events = ev.evaluate(_disk_snapshot("10.0.0.1", used=99.0))
        assert events == []


class TestEventId:
    def test_event_id_deterministic(self):
        rule = _make_rule(source="disk", field="Used", threshold=90.0)
        ev = _make_evaluator([rule])
        snap = _disk_snapshot("10.0.0.1", used=95.0)
        events1 = ev.evaluate(snap)
        events2 = ev.evaluate(snap)
        assert events1[0].event_id == events2[0].event_id

    def test_event_id_is_sha256_hex(self):
        rule = _make_rule(source="disk", field="Used", threshold=90.0)
        ev = _make_evaluator([rule])
        events = ev.evaluate(_disk_snapshot("10.0.0.1", used=95.0))
        assert len(events[0].event_id) == 64
        assert all(c in "0123456789abcdef" for c in events[0].event_id)


# ---------------------------------------------------------------------------
# 5.9 Property 3: evaluation result matches actual_value > threshold
# ---------------------------------------------------------------------------

# Feature: alert-notification-system, Property 3: 評估結果與閾值比較一致性
@given(
    actual=st.floats(min_value=0, max_value=200, allow_nan=False, allow_infinity=False),
    threshold=st.floats(min_value=0, max_value=200, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_evaluation_threshold_consistency(actual: float, threshold: float):
    rule = _make_rule(source="disk", field="Used", threshold=threshold)
    ev = _make_evaluator([rule])
    events = ev.evaluate(_disk_snapshot("10.0.0.1", used=actual))
    should_alert = actual > threshold
    assert (len(events) > 0) == should_alert
    if should_alert:
        assert events[0].actual_value == actual
        assert events[0].threshold == threshold


# ---------------------------------------------------------------------------
# 5.10 Property 4: invalid rules don't affect valid rules' evaluation results
# ---------------------------------------------------------------------------

# Feature: alert-notification-system, Property 4: 無效規則不中斷評估流程
@given(
    extra_rules=st.lists(
        st.one_of(
            # disabled rules
            st.just(_make_rule(name="disabled", source="disk", field="Used", threshold=50.0, enabled=False)),
            # unknown source rules
            st.just(_make_rule(name="bad-source", source="unknown_source", field="Used", threshold=50.0)),
            # unknown field rules
            st.just(_make_rule(name="bad-field", source="system", field="UNKNOWN_FIELD", threshold=1.0)),
        ),
        min_size=0,
        max_size=5,
    )
)
@settings(max_examples=100)
def test_invalid_rules_skipped(extra_rules: list[AlertRule]):
    valid_rule = _make_rule(name="valid-disk", source="disk", field="Used", threshold=90.0)

    # Evaluator with only valid rule
    ev_valid = _make_evaluator([valid_rule])
    snap = _disk_snapshot("10.0.0.1", used=95.0)
    expected = ev_valid.evaluate(snap)

    # Evaluator with valid + extra (invalid/disabled) rules
    ev_mixed = _make_evaluator([valid_rule] + extra_rules)
    actual = ev_mixed.evaluate(snap)

    # Filter to only events from the valid rule
    actual_valid = [e for e in actual if e.rule_name == valid_rule.name]
    assert len(actual_valid) == len(expected)
    if expected:
        assert actual_valid[0].actual_value == expected[0].actual_value
        assert actual_valid[0].threshold == expected[0].threshold


# ---------------------------------------------------------------------------
# 5.11 Property 9: disabled rules never produce AlertEvent
# ---------------------------------------------------------------------------

# Feature: alert-notification-system, Property 9: 停用規則不參與評估
@given(
    actual=st.floats(min_value=0, max_value=200, allow_nan=False, allow_infinity=False),
    threshold=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_disabled_rule_not_evaluated(actual: float, threshold: float):
    rule = _make_rule(source="disk", field="Used", threshold=threshold, enabled=False)
    ev = _make_evaluator([rule])
    events = ev.evaluate(_disk_snapshot("10.0.0.1", used=actual))
    assert events == [], (
        f"Disabled rule produced AlertEvent: actual={actual}, threshold={threshold}"
    )
