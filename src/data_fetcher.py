from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import pymysql
import pymysql.connections

from src.models import DiskRecord, FileRecord, FetchResult, SystemRecord

logger = logging.getLogger(__name__)


class DataFetcher:
    """從三個監控資料庫讀取最新快照。

    Args:
        db_configs: 各資料庫連線設定，格式如下：
            {
                "disk_status":   {"host": ..., "port": 3306, "user": ..., "password": ..., "database": ...},
                "system_status": {"host": ..., "port": 3306, "user": ..., "password": ..., "database": ...},
                "file_status":   {"host": ..., "port": 3306, "user": ..., "password": ..., "database": ...},
            }
    """

    def __init__(self, db_configs: dict[str, dict]) -> None:
        self._db_configs = db_configs
        self._connections: dict[str, Optional[pymysql.connections.Connection]] = {
            "disk_status": None,
            "system_status": None,
            "file_status": None,
        }
        self._connect_all()

    # ------------------------------------------------------------------
    # 內部連線管理
    # ------------------------------------------------------------------

    def _connect(self, name: str) -> Optional[pymysql.connections.Connection]:
        """嘗試建立單一資料庫連線，失敗時記錄錯誤並回傳 None。"""
        config = self._db_configs.get(name)
        if not config:
            logger.error("找不到資料庫 '%s' 的連線設定", name)
            return None
        try:
            conn = pymysql.connect(
                host=config["host"],
                port=int(config.get("port", 3306)),
                user=config["user"],
                password=config["password"],
                database=config["database"],
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10,
            )
            logger.info("已連線至資料庫 '%s'（%s/%s）", name, config["host"], config["database"])
            return conn
        except pymysql.Error as e:
            logger.error("連線資料庫 '%s' 失敗：%s", name, e)
            return None

    def _connect_all(self) -> None:
        """依序嘗試建立所有資料庫連線，各來源獨立，互不影響。"""
        for name in self._connections:
            self._connections[name] = self._connect(name)

    # ------------------------------------------------------------------
    # 公開介面（stub，後續任務實作）
    # ------------------------------------------------------------------

    def fetch_all(self) -> FetchResult:
        fetch_time = datetime.now()

        try:
            disk_records = self.fetch_disk_status()
        except Exception as e:
            logger.error("fetch_disk_status 發生未預期錯誤：%s", e)
            disk_records = []

        try:
            system_records = self.fetch_system_status()
        except Exception as e:
            logger.error("fetch_system_status 發生未預期錯誤：%s", e)
            system_records = []

        try:
            file_records = self.fetch_file_status()
        except Exception as e:
            logger.error("fetch_file_status 發生未預期錯誤：%s", e)
            file_records = []

        return FetchResult(
            disk_records=disk_records,
            system_records=system_records,
            file_records=file_records,
            fetch_time=fetch_time,
        )

    def fetch_disk_status(self) -> list[DiskRecord]:
        conn = self._connections.get("disk_status")
        if conn is None:
            logger.error("disk_status 資料庫連線不可用，無法讀取磁碟狀態")
            return []
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT IP, ServerTime, FileSystem, Used FROM CheckList"
                )
                rows = cursor.fetchall()
            return [
                DiskRecord(
                    ip=row["IP"],
                    server_time=row["ServerTime"],
                    file_system=row["FileSystem"],
                    used=float(row["Used"]),
                )
                for row in rows
            ]
        except pymysql.Error as e:
            logger.error("讀取 DiskStatus.CheckList 失敗：%s", e)
            return []

    def fetch_system_status(self) -> list[SystemRecord]:
        conn = self._connections.get("system_status")
        if conn is None:
            logger.error("system_status 資料庫連線不可用，無法讀取系統狀態")
            return []
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT IP, ServerTime, Load_1, Load_5, LOAD_15, MemoryUSE FROM CheckList"
                )
                rows = cursor.fetchall()
            return [
                SystemRecord(
                    ip=row["IP"],
                    server_time=row["ServerTime"],
                    load_1=float(row["Load_1"]),
                    load_5=float(row["Load_5"]),
                    load_15=float(row["LOAD_15"]),
                    memory_use=float(row["MemoryUSE"]),
                )
                for row in rows
            ]
        except pymysql.Error as e:
            logger.error("讀取 SystemStatus.CheckList 失敗：%s", e)
            return []

    def fetch_file_status(self) -> list[FileRecord]:
        conn = self._connections.get("file_status")
        if conn is None:
            logger.error("file_status 資料庫連線不可用，無法讀取檔案狀態")
            return []

        tables = ["radarFileCheck", "DSFileCheck", "HFradarFileCheck"]
        results: list[FileRecord] = []

        for table in tables:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"SELECT IP, FileName, FileType, FileTime FROM `{table}`"
                    )
                    rows = cursor.fetchall()
                for row in rows:
                    results.append(
                        FileRecord(
                            ip=row["IP"],
                            file_name=row["FileName"],
                            file_type=row["FileType"],
                            file_time=float(row["FileTime"]),
                            source_table=table,
                        )
                    )
            except pymysql.Error as e:
                logger.error("讀取 FileStatus.%s 失敗：%s", table, e)

        return results
