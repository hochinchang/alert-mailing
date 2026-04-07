from __future__ import annotations

import logging
from typing import Optional

import yaml

from src.models import AlertRule

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {"name", "source", "field", "threshold", "recipients"}


class RuleLoader:
    def __init__(self, config_path: str) -> None:
        self.config_path = config_path

    def load(self) -> list[AlertRule]:
        """從 YAML 設定檔讀取並回傳 list[AlertRule]。"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logger.error("無效的 YAML 格式：%s", e)
            return []
        except OSError as e:
            logger.error("無法開啟設定檔 %s：%s", self.config_path, e)
            return []

        rules_data = config.get("rules", []) if config else []
        result: list[AlertRule] = []
        for rule_dict in rules_data:
            rule = self.validate(rule_dict)
            if rule is not None:
                result.append(rule)
        return result

    def validate(self, rule_dict: dict) -> Optional[AlertRule]:
        """驗證必要欄位，缺少時記錄 WARNING 並回傳 None。"""
        missing = REQUIRED_FIELDS - set(rule_dict.keys())
        if missing:
            name = rule_dict.get("name", "<未命名>")
            logger.warning("規則 '%s' 缺少必要欄位：%s", name, missing)
            return None

        recipients = rule_dict["recipients"]
        if not isinstance(recipients, list) or len(recipients) == 0:
            name = rule_dict.get("name", "<未命名>")
            logger.warning("規則 '%s' 的 recipients 必須為非空列表", name)
            return None

        return AlertRule(
            name=rule_dict["name"],
            source=rule_dict["source"],
            field=rule_dict["field"],
            threshold=float(rule_dict["threshold"]),
            recipients=list(rule_dict["recipients"]),
            enabled=bool(rule_dict.get("enabled", True)),
        )
