from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from src.models import AlertEvent, AlertRule, FetchResult
from src.rule_loader import RuleLoader

logger = logging.getLogger(__name__)

# Field name → SystemRecord attribute mapping
_SYSTEM_FIELD_MAP = {
    "Load_1": "load_1",
    "Load_5": "load_5",
    "LOAD_15": "load_15",
    "MemoryUSE": "memory_use",
}


def _make_event_id(rule_name: str, ip: str, field_name: str, fetch_time: datetime) -> str:
    cycle_ts = str(int(fetch_time.timestamp()))
    raw = f"{rule_name}:{ip}:{field_name}:{cycle_ts}"
    return hashlib.sha256(raw.encode()).hexdigest()


class Evaluator:
    def __init__(self, rule_loader: RuleLoader) -> None:
        self.rule_loader = rule_loader

    def evaluate(self, snapshot: FetchResult) -> list[AlertEvent]:
        rules = self.rule_loader.load()
        events: list[AlertEvent] = []

        for rule in rules:
            if not rule.enabled:
                continue

            if rule.source == "disk":
                events.extend(self._eval_disk(rule, snapshot))
            elif rule.source == "system":
                events.extend(self._eval_system(rule, snapshot))
            elif rule.source == "file":
                events.extend(self._eval_file(rule, snapshot))
            else:
                logger.warning("Rule '%s' has unknown source: %s", rule.name, rule.source)

        return events

    # ------------------------------------------------------------------
    # Disk evaluation
    # ------------------------------------------------------------------
    def _eval_disk(self, rule: AlertRule, snapshot: FetchResult) -> list[AlertEvent]:
        events: list[AlertEvent] = []
        for record in snapshot.disk_records:
            actual = record.used
            if actual > rule.threshold:
                event_id = _make_event_id(rule.name, record.ip, rule.field, snapshot.fetch_time)
                events.append(AlertEvent(
                    event_id=event_id,
                    triggered_at=snapshot.fetch_time,
                    rule_name=rule.name,
                    source_ip=record.ip,
                    data_type="disk",
                    field_name=rule.field,
                    actual_value=actual,
                    threshold=rule.threshold,
                    extra={"file_system": record.file_system},
                    recipients=list(rule.recipients),
                ))
        return events

    # ------------------------------------------------------------------
    # System evaluation (Load_1 / Load_5 / LOAD_15 / MemoryUSE)
    # ------------------------------------------------------------------
    def _eval_system(self, rule: AlertRule, snapshot: FetchResult) -> list[AlertEvent]:
        attr = _SYSTEM_FIELD_MAP.get(rule.field)
        if attr is None:
            logger.warning("Rule '%s' has unknown system field: %s", rule.name, rule.field)
            return []

        events: list[AlertEvent] = []
        for record in snapshot.system_records:
            actual = getattr(record, attr)
            if actual > rule.threshold:
                event_id = _make_event_id(rule.name, record.ip, rule.field, snapshot.fetch_time)
                events.append(AlertEvent(
                    event_id=event_id,
                    triggered_at=snapshot.fetch_time,
                    rule_name=rule.name,
                    source_ip=record.ip,
                    data_type="system",
                    field_name=rule.field,
                    actual_value=actual,
                    threshold=rule.threshold,
                    extra={},
                    recipients=list(rule.recipients),
                ))
        return events

    # ------------------------------------------------------------------
    # File evaluation (FileLag)
    # ------------------------------------------------------------------
    def _eval_file(self, rule: AlertRule, snapshot: FetchResult) -> list[AlertEvent]:
        events: list[AlertEvent] = []
        fetch_ts = snapshot.fetch_time.timestamp()

        for record in snapshot.file_records:
            # Validate file_time
            try:
                if record.file_time is None:
                    raise ValueError("file_time is None")
                file_ts = float(record.file_time)
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "Rule '%s': invalid file_time for %s (%s) – skipping",
                    rule.name, record.file_name, exc,
                )
                continue

            lag = (fetch_ts - file_ts) / 60.0
            if lag < 0:
                lag = 0.0

            if lag > rule.threshold:
                event_id = _make_event_id(rule.name, record.ip, rule.field, snapshot.fetch_time)
                events.append(AlertEvent(
                    event_id=event_id,
                    triggered_at=snapshot.fetch_time,
                    rule_name=rule.name,
                    source_ip=record.ip,
                    data_type="file",
                    field_name=rule.field,
                    actual_value=lag,
                    threshold=rule.threshold,
                    extra={
                        "file_name": record.file_name,
                        "file_type": record.file_type,
                        "source_table": record.source_table,
                    },
                    recipients=list(rule.recipients),
                ))
        return events
