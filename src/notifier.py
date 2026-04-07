"""
Notifier：去重檢查、組裝郵件並透過 EmailService 發送告警通知。
"""
from __future__ import annotations

import logging
import time

from src.dedupe_store import DedupeStore
from src.email_service import EmailService
from src.models import AlertEvent

logger = logging.getLogger(__name__)


class Notifier:
    """對每個 AlertEvent 的每位 Recipient 執行去重檢查後發送通知。"""

    def __init__(
        self,
        email_service: EmailService,
        dedupe_store: DedupeStore,
        retry_count: int = 3,
    ) -> None:
        """
        :param email_service: 負責實際發送郵件的服務
        :param dedupe_store:  去重狀態儲存，防止重複通知
        :param retry_count:   發送失敗時的重試次數（預設 3）
        """
        self.email_service = email_service
        self.dedupe_store = dedupe_store
        self.retry_count = retry_count

    # ------------------------------------------------------------------
    # 公開介面
    # ------------------------------------------------------------------

    def notify(self, events: list[AlertEvent]) -> None:
        """
        對 events 中每個 AlertEvent 的每位 Recipient 發送通知。

        流程：
        1. 查詢 DedupeStore，若已發送則跳過。
        2. 呼叫 EmailService.send()，失敗時依 retry_count 重試。
        3. 發送成功後呼叫 DedupeStore.mark_sent() 並記錄 INFO 日誌。
        4. 全部重試失敗後記錄 ERROR 日誌，不更新 DedupeStore。
        """
        for event in events:
            subject = f"【告警】{event.rule_name}"
            body = self.email_service.format_body(event)

            for recipient in event.recipients:
                if self.dedupe_store.is_sent(event.event_id, recipient):
                    logger.debug(
                        "已發送，跳過：event_id=%s, recipient=%s",
                        event.event_id, recipient,
                    )
                    continue

                success = self._send_with_retry(recipient, subject, body, event)

                if success:
                    self.dedupe_store.mark_sent(event.event_id, recipient)
                    logger.info(
                        "通知發送成功：event_id=%s, recipient=%s",
                        event.event_id, recipient,
                    )
                else:
                    logger.error(
                        "通知發送失敗（已重試 %d 次）：event_id=%s, recipient=%s",
                        self.retry_count, event.event_id, recipient,
                    )

    # ------------------------------------------------------------------
    # 內部輔助
    # ------------------------------------------------------------------

    def _send_with_retry(
        self,
        recipient: str,
        subject: str,
        body: str,
        event: AlertEvent,
    ) -> bool:
        """
        嘗試發送郵件，失敗時依 retry_count 重試。

        :return: 任一次成功則回傳 True，全部失敗回傳 False
        """
        attempts = self.retry_count + 1  # 1 次初始 + retry_count 次重試
        for attempt in range(attempts):
            if self.email_service.send([recipient], subject, body):
                return True
            if attempt < attempts - 1:
                logger.warning(
                    "郵件發送失敗，第 %d/%d 次重試：event_id=%s, recipient=%s",
                    attempt + 1, self.retry_count, event.event_id, recipient,
                )
        return False
