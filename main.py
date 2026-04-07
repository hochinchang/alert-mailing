"""
Alert Notification System — 主程式進入點

讀取設定檔、初始化所有元件、啟動 Scheduler。
處理 SIGTERM/SIGINT 信號以優雅關閉。
"""
from __future__ import annotations

import logging
import os
import re
import signal
import sys

import pymysql
import yaml
from dotenv import load_dotenv

from src.data_fetcher import DataFetcher
from src.dedupe_store import MySQLDedupeStore
from src.email_service import EmailService
from src.evaluator import Evaluator
from src.event_logger import MySQLEventLogger
from src.notifier import Notifier
from src.pipeline import Pipeline
from src.rule_loader import RuleLoader
from src.scheduler import Scheduler

# ---------------------------------------------------------------------------
# 日誌設定
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 環境變數插值
# ---------------------------------------------------------------------------

_ENV_PATTERN = re.compile(r"\{\{\s*env:(\w+)\s*\}\}")


def _resolve_env(value: str) -> str:
    """將 '{{ env:VAR }}' 語法替換為對應的環境變數值。"""
    def _replace(match: re.Match) -> str:
        var = match.group(1)
        result = os.environ.get(var, "")
        if not result:
            logger.warning("環境變數 '%s' 未設定或為空", var)
        return result
    return _ENV_PATTERN.sub(_replace, value)


def _resolve_config(obj):
    """遞迴處理設定物件，將所有字串值中的環境變數語法展開。"""
    if isinstance(obj, dict):
        return {k: _resolve_config(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_config(item) for item in obj]
    if isinstance(obj, str):
        return _resolve_env(obj)
    return obj

# ---------------------------------------------------------------------------
# 設定檔載入
# ---------------------------------------------------------------------------

def load_config(config_path: str) -> dict:
    """載入並解析 YAML 設定檔，展開環境變數。"""
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _resolve_config(raw)

# ---------------------------------------------------------------------------
# 元件初始化
# ---------------------------------------------------------------------------

def build_db_connection(db_cfg: dict):
    """建立 PyMySQL 連線，失敗時拋出例外。"""
    return pymysql.connect(
        host=db_cfg["host"],
        port=int(db_cfg.get("port", 3306)),
        user=db_cfg["user"],
        password=db_cfg["password"],
        database=db_cfg["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )


def build_scheduler(config: dict) -> Scheduler:
    """依設定初始化所有元件並組裝 Scheduler。"""
    db_cfgs = config["databases"]
    email_cfg = config["email"]
    scheduler_cfg = config["scheduler"]

    # DataFetcher（各資料庫連線設定直接傳入，DataFetcher 內部管理連線）
    data_fetcher = DataFetcher(db_configs={
        "disk_status":   db_cfgs["disk_status"],
        "system_status": db_cfgs["system_status"],
        "file_status":   db_cfgs["file_status"],
    })

    # RuleLoader
    rule_loader = RuleLoader(config_path="config/rules.yaml")

    # Evaluator
    evaluator = Evaluator(rule_loader=rule_loader)

    # EmailService（使用系統 mail 指令）
    email_service = EmailService(
        sender=email_cfg.get("sender", ""),
        retry_count=int(email_cfg.get("retry_count", 3)),
    )

    # AlertSystem DB 連線（DedupeStore + EventLogger 共用）
    alert_conn = build_db_connection(db_cfgs["alert_store"])

    # DedupeStore
    dedupe_store = MySQLDedupeStore(connection=alert_conn)
    dedupe_store.init_table()

    # EventLogger
    event_logger = MySQLEventLogger(connection=alert_conn)
    event_logger.init_table()

    # Notifier
    notifier = Notifier(
        email_service=email_service,
        dedupe_store=dedupe_store,
        retry_count=int(email_cfg.get("retry_count", 3)),
    )

    # Pipeline
    pipeline = Pipeline(
        data_fetcher=data_fetcher,
        evaluator=evaluator,
        notifier=notifier,
        event_logger=event_logger,
        rule_loader=rule_loader,
    )

    return Scheduler(
        interval_seconds=int(scheduler_cfg.get("interval_seconds", 300)),
        pipeline=pipeline,
        rule_loader=rule_loader,
    )

# ---------------------------------------------------------------------------
# 主程式
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv()

    config_path = os.environ.get("CONFIG_PATH", "config/rules.yaml")
    logger.info("載入設定檔：%s", config_path)

    try:
        config = load_config(config_path)
    except (OSError, yaml.YAMLError) as exc:
        logger.error("無法載入設定檔：%s", exc)
        sys.exit(1)

    try:
        scheduler = build_scheduler(config)
    except Exception as exc:
        logger.error("元件初始化失敗：%s", exc)
        sys.exit(1)

    # 優雅關閉：處理 SIGTERM / SIGINT
    def _shutdown(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("收到信號 %s，正在關閉 Scheduler…", sig_name)
        scheduler.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("Alert Notification System 啟動中…")
    scheduler.start()  # 阻塞直到 stop() 被呼叫


if __name__ == "__main__":
    main()
