from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger(__name__)


class DedupeStore(ABC):
    """去重狀態儲存的抽象基底類別。"""

    @abstractmethod
    def is_sent(self, event_id: str, recipient: str) -> bool:
        """檢查指定事件是否已對該收件人發送過通知。"""
        ...

    @abstractmethod
    def mark_sent(self, event_id: str, recipient: str) -> None:
        """將指定事件對該收件人的發送狀態標記為已發送。"""
        ...


class MySQLDedupeStore(DedupeStore):
    """使用 MySQL 儲存去重狀態，將已發送紀錄寫入 AlertSystem.alert_dedupe 表。"""

    def __init__(self, connection) -> None:
        """
        :param connection: PyMySQL 連線物件（指向 AlertSystem 資料庫）
        """
        self._conn = connection

    def init_table(self) -> None:
        """若 alert_dedupe 表不存在則自動建立。"""
        sql = """
            CREATE TABLE IF NOT EXISTS alert_dedupe (
                event_id   VARCHAR(64)  NOT NULL,
                recipient  VARCHAR(255) NOT NULL,
                sent_at    DATETIME     NOT NULL,
                PRIMARY KEY (event_id, recipient)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        with self._conn.cursor() as cursor:
            cursor.execute(sql)
        self._conn.commit()
        logger.info("alert_dedupe 表已確認存在（或已建立）")

    def is_sent(self, event_id: str, recipient: str) -> bool:
        """查詢 alert_dedupe 表，確認是否已有對應紀錄。"""
        sql = (
            "SELECT 1 FROM alert_dedupe "
            "WHERE event_id = %s AND recipient = %s LIMIT 1"
        )
        with self._conn.cursor() as cursor:
            cursor.execute(sql, (event_id, recipient))
            row = cursor.fetchone()
        return row is not None

    def mark_sent(self, event_id: str, recipient: str) -> None:
        """將已發送紀錄寫入 alert_dedupe 表。"""
        sql = (
            "INSERT IGNORE INTO alert_dedupe (event_id, recipient, sent_at) "
            "VALUES (%s, %s, %s)"
        )
        sent_at = datetime.utcnow()
        with self._conn.cursor() as cursor:
            cursor.execute(sql, (event_id, recipient, sent_at))
        self._conn.commit()
        logger.info("已記錄發送狀態：event_id=%s, recipient=%s", event_id, recipient)


class InMemoryDedupeStore(DedupeStore):
    """記憶體內去重狀態儲存，供測試使用。"""

    def __init__(self) -> None:
        # 使用 set 儲存 (event_id, recipient) 組合
        self._sent: set[tuple[str, str]] = set()

    def is_sent(self, event_id: str, recipient: str) -> bool:
        """檢查是否已標記為已發送。"""
        return (event_id, recipient) in self._sent

    def mark_sent(self, event_id: str, recipient: str) -> None:
        """將 (event_id, recipient) 加入已發送集合。"""
        self._sent.add((event_id, recipient))
