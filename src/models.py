from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AlertRule:
    name: str                # 規則名稱（唯一識別）
    source: str              # 資料來源：disk | system | file
    field: str               # 目標欄位：Used | Load_1 | Load_5 | LOAD_15 | MemoryUSE | FileLag
    threshold: float         # 閾值
    recipients: list[str]    # 收件人 E-mail 列表（至少一位）
    enabled: bool = True     # 是否啟用


@dataclass
class DiskRecord:
    ip: str
    server_time: datetime
    file_system: str
    used: float              # 磁碟使用率 (%)


@dataclass
class SystemRecord:
    ip: str
    server_time: datetime
    load_1: float
    load_5: float
    load_15: float
    memory_use: float        # 記憶體使用率 (%)


@dataclass
class FileRecord:
    ip: str
    file_name: str
    file_type: str
    file_time: float         # Unix timestamp
    source_table: str        # radarFileCheck | DSFileCheck | HFradarFileCheck


@dataclass
class AlertEvent:
    event_id: str            # 唯一識別碼（hash）
    triggered_at: datetime   # 觸發時間
    rule_name: str           # 觸發的規則名稱
    source_ip: str           # 來源 IP
    data_type: str           # disk | system | file
    field_name: str          # 觸發欄位名稱
    actual_value: float      # 實際數值
    threshold: float         # 閾值
    extra: dict              # 附加資訊（如 FileSystem、FileName、FileType 等）
    recipients: list[str]    # 收件人列表


@dataclass
class FetchResult:
    disk_records: list[DiskRecord]
    system_records: list[SystemRecord]
    file_records: list[FileRecord]
    fetch_time: datetime     # 本次讀取的時間戳（用於計算 FileLag）
