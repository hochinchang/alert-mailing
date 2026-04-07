"""
Pipeline：依序執行 DataFetcher → Evaluator → Notifier → EventLogger。
"""
from __future__ import annotations

import logging
from datetime import datetime

from src.data_fetcher import DataFetcher
from src.evaluator import Evaluator
from src.event_logger import EventLogger
from src.notifier import Notifier
from src.rule_loader import RuleLoader

logger = logging.getLogger(__name__)


class Pipeline:
    """整合所有元件，執行一個完整的告警處理週期。"""

    def __init__(
        self,
        data_fetcher: DataFetcher,
        evaluator: Evaluator,
        notifier: Notifier,
        event_logger: EventLogger,
        rule_loader: RuleLoader,
    ) -> None:
        self.data_fetcher = data_fetcher
        self.evaluator = evaluator
        self.notifier = notifier
        self.event_logger = event_logger
        self.rule_loader = rule_loader

    def run(self) -> None:
        """執行一個排程週期：讀取 → 評估 → 通知 → 記錄。"""
        start_time = datetime.now()
        logger.info("Pipeline 開始執行：%s", start_time.isoformat())

        # 1. 讀取資料
        snapshot = self.data_fetcher.fetch_all()
        disk_count = len(snapshot.disk_records)
        system_count = len(snapshot.system_records)
        file_count = len(snapshot.file_records)
        logger.info(
            "資料讀取完成：disk=%d, system=%d, file=%d",
            disk_count, system_count, file_count,
        )

        # 2. 評估告警
        events = self.evaluator.evaluate(snapshot)
        logger.info("評估完成：產生 %d 個 AlertEvent", len(events))

        # 3. 發送通知
        self.notifier.notify(events)

        # 4. 記錄事件歷史
        for event in events:
            try:
                self.event_logger.save(event)
            except Exception as exc:
                logger.error("儲存 AlertEvent 失敗：event_id=%s, error=%s", event.event_id, exc)

        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()
        logger.info(
            "Pipeline 執行完畢：%s（耗時 %.2f 秒）"
            "，disk=%d, system=%d, file=%d, events=%d",
            end_time.isoformat(), elapsed,
            disk_count, system_count, file_count, len(events),
        )
