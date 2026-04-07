"""
Scheduler：使用 APScheduler 依設定週期定時執行 Pipeline。
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from src.pipeline import Pipeline
from src.rule_loader import RuleLoader

logger = logging.getLogger(__name__)


class Scheduler:
    """依設定的週期定時呼叫 Pipeline.run()。"""

    def __init__(
        self,
        interval_seconds: int,
        pipeline: Pipeline,
        rule_loader: RuleLoader,
    ) -> None:
        """
        :param interval_seconds: 排程執行間隔（秒）
        :param pipeline:         要執行的 Pipeline 實例
        :param rule_loader:      用於啟動時記錄規則數量的 RuleLoader
        """
        self._interval_seconds = interval_seconds
        self._pipeline = pipeline
        self._rule_loader = rule_loader
        self._scheduler = BlockingScheduler()

    def start(self) -> None:
        """啟動排程器，記錄啟動日誌後開始定時執行。"""
        self._log_startup_info()
        self._scheduler.add_job(
            self._pipeline.run,
            trigger="interval",
            seconds=self._interval_seconds,
            id="pipeline_run",
            max_instances=1,
        )
        logger.info(
            "Scheduler 啟動，執行間隔：%d 秒", self._interval_seconds
        )
        self._scheduler.start()

    def stop(self) -> None:
        """優雅停止排程器。"""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler 已停止")

    # ------------------------------------------------------------------
    # 內部輔助
    # ------------------------------------------------------------------

    def _log_startup_info(self) -> None:
        """記錄啟動時的規則數量與 Recipient 總數（需求 5.3）。"""
        try:
            rules = self._rule_loader.load()
            rule_count = len(rules)
            recipient_count = sum(len(r.recipients) for r in rules)
            logger.info(
                "Alert_System 啟動：載入 %d 條規則，共 %d 位 Recipient",
                rule_count, recipient_count,
            )
        except Exception as exc:
            logger.error("啟動時載入規則失敗：%s", exc)
