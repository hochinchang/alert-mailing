"""
整合測試：Pipeline 端對端流程（mock DB 與 mock EmailService）
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.dedupe_store import InMemoryDedupeStore
from src.evaluator import Evaluator
from src.event_logger import InMemoryEventLogger
from src.models import AlertRule, DiskRecord, FetchResult, SystemRecord, FileRecord
from src.notifier import Notifier
from src.pipeline import Pipeline
from src.rule_loader import RuleLoader


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------

def _make_rule_loader(rules: list[AlertRule]) -> RuleLoader:
    """回傳一個 load() 固定回傳指定規則的 mock RuleLoader。"""
    loader = MagicMock(spec=RuleLoader)
    loader.load.return_value = rules
    return loader


def _make_mock_fetcher(snapshot: FetchResult) -> MagicMock:
    fetcher = MagicMock()
    fetcher.fetch_all.return_value = snapshot
    return fetcher


def _make_mock_email_service(send_return: bool = True) -> MagicMock:
    svc = MagicMock()
    svc.send.return_value = send_return
    svc.format_body.return_value = "mock body"
    return svc


def _make_fetch_result(
    disk_records=None,
    system_records=None,
    file_records=None,
    fetch_time=None,
) -> FetchResult:
    return FetchResult(
        disk_records=disk_records or [],
        system_records=system_records or [],
        file_records=file_records or [],
        fetch_time=fetch_time or datetime(2024, 6, 1, 12, 0, 0),
    )


# ---------------------------------------------------------------------------
# 整合測試
# ---------------------------------------------------------------------------

class TestPipelineIntegration:
    """模擬完整管線執行一個週期的端對端整合測試。"""

    def _build_pipeline(self, snapshot: FetchResult, rules: list[AlertRule], email_svc=None):
        """建立完整 Pipeline，使用 mock DataFetcher 與 InMemory 儲存。"""
        if email_svc is None:
            email_svc = _make_mock_email_service()

        rule_loader = _make_rule_loader(rules)
        fetcher = _make_mock_fetcher(snapshot)
        evaluator = Evaluator(rule_loader)
        dedupe_store = InMemoryDedupeStore()
        notifier = Notifier(email_svc, dedupe_store, retry_count=0)
        event_logger = InMemoryEventLogger()

        pipeline = Pipeline(
            data_fetcher=fetcher,
            evaluator=evaluator,
            notifier=notifier,
            event_logger=event_logger,
            rule_loader=rule_loader,
        )
        return pipeline, event_logger, email_svc, dedupe_store

    def test_disk_alert_end_to_end(self):
        """磁碟使用率超過閾值時，應產生 AlertEvent 並發送通知且記錄歷史。"""
        rule = AlertRule(
            name="磁碟使用率過高",
            source="disk",
            field="Used",
            threshold=80.0,
            recipients=["admin@example.com"],
            enabled=True,
        )
        snapshot = _make_fetch_result(
            disk_records=[
                DiskRecord(ip="10.0.0.1", server_time=datetime.now(), file_system="/dev/sda1", used=95.0)
            ]
        )
        pipeline, event_logger, email_svc, dedupe_store = self._build_pipeline(snapshot, [rule])

        pipeline.run()

        # 應發送一封郵件
        assert email_svc.send.call_count == 1
        # 應記錄一筆事件歷史
        assert len(event_logger._store) == 1
        event = list(event_logger._store.values())[0]
        assert event.rule_name == "磁碟使用率過高"
        assert event.actual_value == 95.0
        assert event.data_type == "disk"

    def test_no_alert_when_below_threshold(self):
        """資料未超過閾值時，不應產生 AlertEvent 也不應發送通知。"""
        rule = AlertRule(
            name="磁碟使用率過高",
            source="disk",
            field="Used",
            threshold=90.0,
            recipients=["admin@example.com"],
            enabled=True,
        )
        snapshot = _make_fetch_result(
            disk_records=[
                DiskRecord(ip="10.0.0.1", server_time=datetime.now(), file_system="/dev/sda1", used=50.0)
            ]
        )
        pipeline, event_logger, email_svc, _ = self._build_pipeline(snapshot, [rule])

        pipeline.run()

        assert email_svc.send.call_count == 0
        assert len(event_logger._store) == 0

    def test_system_alert_end_to_end(self):
        """系統負載超過閾值時，應產生 AlertEvent 並發送通知。"""
        rule = AlertRule(
            name="系統負載過高",
            source="system",
            field="Load_1",
            threshold=4.0,
            recipients=["ops@example.com"],
            enabled=True,
        )
        snapshot = _make_fetch_result(
            system_records=[
                SystemRecord(
                    ip="10.0.0.2",
                    server_time=datetime.now(),
                    load_1=6.5,
                    load_5=5.0,
                    load_15=4.5,
                    memory_use=70.0,
                )
            ]
        )
        pipeline, event_logger, email_svc, _ = self._build_pipeline(snapshot, [rule])

        pipeline.run()

        assert email_svc.send.call_count == 1
        event = list(event_logger._store.values())[0]
        assert event.data_type == "system"
        assert event.field_name == "Load_1"
        assert event.actual_value == 6.5

    def test_file_alert_end_to_end(self):
        """檔案延遲超過閾值時，應產生 AlertEvent 並發送通知。"""
        rule = AlertRule(
            name="雷達檔案延遲",
            source="file",
            field="FileLag",
            threshold=30.0,
            recipients=["radar@example.com"],
            enabled=True,
        )
        fetch_time = datetime(2024, 6, 1, 12, 0, 0)
        # file_time 比 fetch_time 早 60 分鐘 → FileLag = 60 > 30
        file_ts = fetch_time.timestamp() - 3600
        snapshot = _make_fetch_result(
            file_records=[
                FileRecord(
                    ip="10.0.0.3",
                    file_name="radar_data.bin",
                    file_type="radar",
                    file_time=file_ts,
                    source_table="radarFileCheck",
                )
            ],
            fetch_time=fetch_time,
        )
        pipeline, event_logger, email_svc, _ = self._build_pipeline(snapshot, [rule])

        pipeline.run()

        assert email_svc.send.call_count == 1
        event = list(event_logger._store.values())[0]
        assert event.data_type == "file"
        assert event.actual_value == pytest.approx(60.0)

    def test_disabled_rule_produces_no_event(self):
        """停用的規則不應產生 AlertEvent，即使資料超過閾值。"""
        rule = AlertRule(
            name="停用規則",
            source="disk",
            field="Used",
            threshold=50.0,
            recipients=["admin@example.com"],
            enabled=False,
        )
        snapshot = _make_fetch_result(
            disk_records=[
                DiskRecord(ip="10.0.0.1", server_time=datetime.now(), file_system="/dev/sda1", used=99.0)
            ]
        )
        pipeline, event_logger, email_svc, _ = self._build_pipeline(snapshot, [rule])

        pipeline.run()

        assert email_svc.send.call_count == 0
        assert len(event_logger._store) == 0

    def test_dedupe_prevents_duplicate_notification(self):
        """同一 AlertEvent 對同一 Recipient 多次執行 Pipeline 只發送一次通知。"""
        rule = AlertRule(
            name="磁碟使用率過高",
            source="disk",
            field="Used",
            threshold=80.0,
            recipients=["admin@example.com"],
            enabled=True,
        )
        fetch_time = datetime(2024, 6, 1, 12, 0, 0)
        snapshot = _make_fetch_result(
            disk_records=[
                DiskRecord(ip="10.0.0.1", server_time=fetch_time, file_system="/dev/sda1", used=95.0)
            ],
            fetch_time=fetch_time,
        )
        email_svc = _make_mock_email_service()
        rule_loader = _make_rule_loader([rule])
        fetcher = _make_mock_fetcher(snapshot)
        evaluator = Evaluator(rule_loader)
        dedupe_store = InMemoryDedupeStore()
        notifier = Notifier(email_svc, dedupe_store, retry_count=0)
        event_logger = InMemoryEventLogger()
        pipeline = Pipeline(fetcher, evaluator, notifier, event_logger, rule_loader)

        # 執行兩次，相同 fetch_time → 相同 event_id
        pipeline.run()
        pipeline.run()

        # 去重機制確保只發送一次
        assert email_svc.send.call_count == 1

    def test_empty_data_produces_no_events(self):
        """所有資料來源回傳空列表時，不應產生任何 AlertEvent。"""
        rule = AlertRule(
            name="磁碟使用率過高",
            source="disk",
            field="Used",
            threshold=80.0,
            recipients=["admin@example.com"],
            enabled=True,
        )
        snapshot = _make_fetch_result()  # 全部空列表
        pipeline, event_logger, email_svc, _ = self._build_pipeline(snapshot, [rule])

        pipeline.run()

        assert email_svc.send.call_count == 0
        assert len(event_logger._store) == 0

    def test_multiple_rules_multiple_events(self):
        """多條規則同時觸發時，應各自產生 AlertEvent 並發送通知。"""
        rules = [
            AlertRule("磁碟告警", "disk", "Used", 80.0, ["admin@example.com"], True),
            AlertRule("記憶體告警", "system", "MemoryUSE", 85.0, ["ops@example.com"], True),
        ]
        snapshot = _make_fetch_result(
            disk_records=[
                DiskRecord(ip="10.0.0.1", server_time=datetime.now(), file_system="/dev/sda1", used=95.0)
            ],
            system_records=[
                SystemRecord(
                    ip="10.0.0.2",
                    server_time=datetime.now(),
                    load_1=1.0, load_5=1.0, load_15=1.0,
                    memory_use=90.0,
                )
            ],
        )
        pipeline, event_logger, email_svc, _ = self._build_pipeline(snapshot, rules)

        pipeline.run()

        assert email_svc.send.call_count == 2
        assert len(event_logger._store) == 2

    def test_fetch_all_called_once_per_run(self):
        """每次 Pipeline.run() 應恰好呼叫一次 DataFetcher.fetch_all()。"""
        rule = AlertRule("磁碟告警", "disk", "Used", 80.0, ["admin@example.com"], True)
        snapshot = _make_fetch_result()
        pipeline, _, _, _ = self._build_pipeline(snapshot, [rule])

        pipeline.run()
        pipeline.run()

        assert pipeline.data_fetcher.fetch_all.call_count == 2
