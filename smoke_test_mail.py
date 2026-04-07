"""
smoke_test_mail.py

模擬一筆雷達檔案延遲超過閾值的資料，走完整個
Evaluator → Notifier → EmailService 流程，
實際發送告警 mail 給 rules.yaml 中設定的收件人。

執行方式：
    python smoke_test_mail.py
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from unittest.mock import MagicMock

from src.dedupe_store import DedupeStore
from src.email_service import EmailService
from src.evaluator import Evaluator
from src.models import FetchResult, FileRecord
from src.notifier import Notifier
from src.rule_loader import RuleLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    # ── 1. 載入規則 ──────────────────────────────────────────────────
    rule_loader = RuleLoader("config/rules.yaml")

    # ── 2. 建立一筆假的雷達檔案記錄（延遲 60 分鐘，遠超 30 分鐘閾值）──
    now = datetime.now()
    fetch_ts = now.timestamp()
    lag_minutes = 60.0
    fake_file_time = fetch_ts - lag_minutes * 60  # 60 分鐘前的 Unix timestamp

    fake_file_record = FileRecord(
        ip="192.168.1.99",
        file_name="RADAR_TEST_20260407.nc",
        file_type="radar",
        file_time=fake_file_time,
        source_table="radarFileCheck",
    )

    snapshot = FetchResult(
        disk_records=[],
        system_records=[],
        file_records=[fake_file_record],
        fetch_time=now,
    )

    # ── 3. 評估告警 ───────────────────────────────────────────────────
    evaluator = Evaluator(rule_loader)
    events = evaluator.evaluate(snapshot)

    if not events:
        logger.warning("沒有產生任何 AlertEvent，請確認 rules.yaml 中雷達延遲規則已啟用")
        return

    # 把收件人換成 rules.yaml 的 default_recipients
    default_recipients = ["dev01@rsd.cwa.gov.tw", "mhochin@gmail.com"]
    for event in events:
        event.recipients = default_recipients
        logger.info(
            "AlertEvent 產生：rule=%s, ip=%s, lag=%.1f 分鐘, recipients=%s",
            event.rule_name, event.source_ip, event.actual_value, event.recipients,
        )

    # ── 4. 發送通知（使用真實 EmailService，不 mock）─────────────────
    email_service = EmailService()

    # DedupeStore 用 mock，讓每次測試都能重新發送（不受去重限制）
    dedupe_store = MagicMock(spec=DedupeStore)
    dedupe_store.is_sent.return_value = False

    notifier = Notifier(email_service=email_service, dedupe_store=dedupe_store)
    notifier.notify(events)

    logger.info("smoke test 完成，請檢查收件匣")


if __name__ == "__main__":
    main()
