from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime

from src.models import AlertEvent

logger = logging.getLogger(__name__)


class EventLogger(ABC):
    """告警事件歷史紀錄的抽象基底類別。"""

    @abstractmethod
    def save(self, event: AlertEvent) -> None:
        """將 AlertEvent 寫入歷史紀錄。"""
        ...

    @abstractmethod
    def get(self, event_id: str) -> AlertEvent | None:
        """以 event_id 查詢歷史紀錄，回傳 AlertEvent 或 None。"""
        ...


class MySQLEventLogger(EventLogger):
    """使用 MySQL 儲存告警事件歷史，寫入 AlertSystem.alert_events 表。"""

    def __init__(self, connection) -> None:
        """
        :param connection: PyMySQL 連線物件（指向 AlertSystem 資料庫）
        """
        self._conn = connection

    def init_table(self) -> None:
        """若 alert_events 表不存在則自動建立。"""
        sql = """
            CREATE TABLE IF NOT EXISTS alert_events (
                event_id      VARCHAR(64)   NOT NULL,
                triggered_at  DATETIME      NOT NULL,
                rule_name     VARCHAR(255)  NOT NULL,
                source_ip     VARCHAR(64)   NOT NULL,
                data_type     VARCHAR(32)   NOT NULL,
                field_name    VARCHAR(64)   NOT NULL,
                actual_value  FLOAT         NOT NULL,
                threshold     FLOAT         NOT NULL,
                extra_json    TEXT,
                notify_status VARCHAR(32),
                PRIMARY KEY (event_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        with self._conn.cursor() as cursor:
            cursor.execute(sql)
        self._conn.commit()
        logger.info("alert_events 表已確認存在（或已建立）")

    def save(self, event: AlertEvent) -> None:
        """將 AlertEvent 寫入 alert_events 表，重複 event_id 時忽略。"""
        sql = """
            INSERT IGNORE INTO alert_events
                (event_id, triggered_at, rule_name, source_ip, data_type,
                 field_name, actual_value, threshold, extra_json, notify_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        extra_json = json.dumps(event.extra, ensure_ascii=False)
        with self._conn.cursor() as cursor:
            cursor.execute(sql, (
                event.event_id,
                event.triggered_at,
                event.rule_name,
                event.source_ip,
                event.data_type,
                event.field_name,
                event.actual_value,
                event.threshold,
                extra_json,
                None,
            ))
        self._conn.commit()
        logger.info("已記錄告警事件：event_id=%s", event.event_id)

    def get(self, event_id: str) -> AlertEvent | None:
        """以 event_id 查詢 alert_events 表，回傳重建的 AlertEvent 或 None。"""
        sql = """
            SELECT event_id, triggered_at, rule_name, source_ip, data_type,
                   field_name, actual_value, threshold, extra_json
            FROM alert_events
            WHERE event_id = %s
            LIMIT 1
        """
        with self._conn.cursor() as cursor:
            cursor.execute(sql, (event_id,))
            row = cursor.fetchone()
        if row is None:
            return None
        (eid, triggered_at, rule_name, source_ip, data_type,
         field_name, actual_value, threshold, extra_json) = row
        extra = json.loads(extra_json) if extra_json else {}
        if isinstance(triggered_at, str):
            triggered_at = datetime.fromisoformat(triggered_at)
        return AlertEvent(
            event_id=eid,
            triggered_at=triggered_at,
            rule_name=rule_name,
            source_ip=source_ip,
            data_type=data_type,
            field_name=field_name,
            actual_value=actual_value,
            threshold=threshold,
            extra=extra,
            recipients=[],
        )


class InMemoryEventLogger(EventLogger):
    """記憶體內告警事件歷史紀錄，供測試使用。"""

    def __init__(self) -> None:
        self._store: dict[str, AlertEvent] = {}

    def save(self, event: AlertEvent) -> None:
        """將 AlertEvent 存入記憶體（重複 event_id 時忽略）。"""
        if event.event_id not in self._store:
            # 序列化再反序列化 extra，模擬 JSON round-trip
            extra_copy = json.loads(json.dumps(event.extra))
            self._store[event.event_id] = AlertEvent(
                event_id=event.event_id,
                triggered_at=event.triggered_at,
                rule_name=event.rule_name,
                source_ip=event.source_ip,
                data_type=event.data_type,
                field_name=event.field_name,
                actual_value=event.actual_value,
                threshold=event.threshold,
                extra=extra_copy,
                recipients=[],
            )

    def get(self, event_id: str) -> AlertEvent | None:
        """以 event_id 查詢記憶體，回傳 AlertEvent 或 None。"""
        return self._store.get(event_id)
