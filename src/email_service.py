"""
EmailService：透過系統 mail 指令發送告警通知郵件。
"""
from __future__ import annotations

import logging
import subprocess

from src.models import AlertEvent

logger = logging.getLogger(__name__)


class EmailService:
    """使用系統 `mail` 指令發送郵件。"""

    def __init__(self, sender: str = "", retry_count: int = 3, **kwargs) -> None:
        # sender 與其他 SMTP 參數保留以維持介面相容性，mail 指令不需要
        self.sender = sender
        self.retry_count = retry_count

    # ------------------------------------------------------------------
    # 公開介面
    # ------------------------------------------------------------------

    def send(self, to: list[str], subject: str, body: str) -> bool:
        """
        透過系統 mail 指令發送郵件。

        等同於：echo "<body>" | mail -s "<subject>" recipient1 recipient2 ...

        :param to: 收件人 E-mail 列表
        :param subject: 郵件主旨
        :param body: 郵件內文（純文字）
        :return: 發送成功回傳 True，失敗回傳 False
        """
        if not to:
            logger.warning("收件人列表為空，略過發送")
            return False

        cmd = ["mail", "-s", subject] + to
        try:
            result = subprocess.run(
                cmd,
                input=body,
                text=True,
                capture_output=True,
            )
            if result.returncode != 0:
                logger.error(
                    "郵件發送失敗：to=%s, subject=%s, stderr=%s",
                    to, subject, result.stderr.strip(),
                )
                return False
            return True
        except FileNotFoundError:
            logger.error("找不到 mail 指令，請確認系統已安裝 mailutils 或 mailx")
            return False
        except Exception as exc:
            logger.error("郵件發送失敗：to=%s, subject=%s, error=%s", to, subject, exc)
            return False

    def format_body(self, event: AlertEvent) -> str:
        """
        將 AlertEvent 格式化為郵件內文。

        包含需求 3.2 所要求的所有欄位：
        - triggered_at（Alert_Event 發生時間）
        - rule_name（觸發的 Alert_Rule 名稱）
        - source_ip（來源 IP）
        - data_type（監控資料類型）
        - field_name（觸發欄位名稱）
        - actual_value（實際數值）
        - threshold（閾值）
        - extra（附加資訊）
        """
        lines = [
            "【告警通知】",
            "",
            f"發生時間：{event.triggered_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"規則名稱：{event.rule_name}",
            f"來源 IP：{event.source_ip}",
            f"資料類型：{event.data_type}",
            f"觸發欄位：{event.field_name}",
            f"實際數值：{event.actual_value}",
            f"閾值：{event.threshold}",
        ]

        if event.extra:
            lines.append("附加資訊：")
            for key, value in event.extra.items():
                lines.append(f"  {key}: {value}")

        lines += ["", f"事件 ID：{event.event_id}"]
        return "\n".join(lines)
