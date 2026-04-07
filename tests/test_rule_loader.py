"""Tests for RuleLoader — unit tests and property-based tests."""
from __future__ import annotations

import textwrap
import tempfile
import os

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.rule_loader import RuleLoader, REQUIRED_FIELDS
from src.models import AlertRule

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_RULE_DICT = {
    "name": "磁碟使用率過高",
    "source": "disk",
    "field": "Used",
    "threshold": 90.0,
    "recipients": ["admin@example.com"],
    "enabled": True,
}


def _make_yaml_file(content: str) -> str:
    """Write content to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ---------------------------------------------------------------------------
# Unit tests — validate()
# ---------------------------------------------------------------------------

class TestValidate:
    def setup_method(self):
        self.loader = RuleLoader("dummy.yaml")

    def test_valid_rule_returns_alert_rule(self):
        rule = self.loader.validate(VALID_RULE_DICT)
        assert isinstance(rule, AlertRule)
        assert rule.name == "磁碟使用率過高"
        assert rule.source == "disk"
        assert rule.field == "Used"
        assert rule.threshold == 90.0
        assert rule.recipients == ["admin@example.com"]
        assert rule.enabled is True

    def test_enabled_defaults_to_true_when_absent(self):
        d = {k: v for k, v in VALID_RULE_DICT.items() if k != "enabled"}
        rule = self.loader.validate(d)
        assert rule is not None
        assert rule.enabled is True

    def test_missing_name_returns_none(self):
        d = {k: v for k, v in VALID_RULE_DICT.items() if k != "name"}
        assert self.loader.validate(d) is None

    def test_missing_source_returns_none(self):
        d = {k: v for k, v in VALID_RULE_DICT.items() if k != "source"}
        assert self.loader.validate(d) is None

    def test_missing_field_returns_none(self):
        d = {k: v for k, v in VALID_RULE_DICT.items() if k != "field"}
        assert self.loader.validate(d) is None

    def test_missing_threshold_returns_none(self):
        d = {k: v for k, v in VALID_RULE_DICT.items() if k != "threshold"}
        assert self.loader.validate(d) is None

    def test_missing_recipients_returns_none(self):
        d = {k: v for k, v in VALID_RULE_DICT.items() if k != "recipients"}
        assert self.loader.validate(d) is None

    def test_empty_recipients_returns_none(self):
        d = {**VALID_RULE_DICT, "recipients": []}
        assert self.loader.validate(d) is None

    def test_missing_field_logs_warning(self, caplog):
        import logging
        d = {k: v for k, v in VALID_RULE_DICT.items() if k != "threshold"}
        with caplog.at_level(logging.WARNING, logger="src.rule_loader"):
            self.loader.validate(d)
        assert any("threshold" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Unit tests — load()
# ---------------------------------------------------------------------------

class TestLoad:
    def test_load_valid_yaml_returns_rules(self):
        yaml_content = textwrap.dedent("""\
            rules:
              - name: "磁碟使用率過高"
                source: disk
                field: Used
                threshold: 90.0
                recipients:
                  - admin@example.com
                enabled: true
              - name: "系統負載過高"
                source: system
                field: Load_1
                threshold: 4.0
                recipients:
                  - ops@example.com
                enabled: false
        """)
        path = _make_yaml_file(yaml_content)
        try:
            loader = RuleLoader(path)
            rules = loader.load()
            assert len(rules) == 2
            assert rules[0].name == "磁碟使用率過高"
            assert rules[1].enabled is False
        finally:
            os.unlink(path)

    def test_load_skips_invalid_rules(self):
        yaml_content = textwrap.dedent("""\
            rules:
              - name: "有效規則"
                source: disk
                field: Used
                threshold: 90.0
                recipients:
                  - admin@example.com
              - source: system
                field: Load_1
                threshold: 4.0
                recipients:
                  - ops@example.com
        """)
        path = _make_yaml_file(yaml_content)
        try:
            loader = RuleLoader(path)
            rules = loader.load()
            assert len(rules) == 1
            assert rules[0].name == "有效規則"
        finally:
            os.unlink(path)

    def test_load_invalid_yaml_returns_empty_list(self):
        path = _make_yaml_file("rules: [\ninvalid yaml: {{{")
        try:
            loader = RuleLoader(path)
            rules = loader.load()
            assert rules == []
        finally:
            os.unlink(path)

    def test_load_missing_file_returns_empty_list(self):
        loader = RuleLoader("/nonexistent/path/rules.yaml")
        rules = loader.load()
        assert rules == []

    def test_load_empty_rules_section_returns_empty_list(self):
        path = _make_yaml_file("rules: []\n")
        try:
            loader = RuleLoader(path)
            assert loader.load() == []
        finally:
            os.unlink(path)

    def test_load_real_config(self):
        """Smoke test against the actual config/rules.yaml."""
        loader = RuleLoader("config/rules.yaml")
        rules = loader.load()
        assert len(rules) > 0
        for rule in rules:
            assert isinstance(rule, AlertRule)


# ---------------------------------------------------------------------------
# Property-based test — Property 10
# ---------------------------------------------------------------------------

# Feature: alert-notification-system, Property 10: 規則驗證拒絕不完整規則
@given(
    fields_to_remove=st.frozensets(
        st.sampled_from(sorted(REQUIRED_FIELDS)),
        min_size=1,
    )
)
@settings(max_examples=100)
def test_rule_validation_rejects_incomplete(fields_to_remove):
    """
    Validates: Requirements 4.3, 4.4

    For any rule dict missing one or more required fields,
    validate() must return None.
    """
    loader = RuleLoader("dummy.yaml")
    complete = {
        "name": "test-rule",
        "source": "disk",
        "field": "Used",
        "threshold": 80.0,
        "recipients": ["user@example.com"],
        "enabled": True,
    }
    incomplete = {k: v for k, v in complete.items() if k not in fields_to_remove}
    result = loader.validate(incomplete)
    assert result is None, (
        f"validate() should return None when fields {fields_to_remove} are missing, "
        f"but got {result}"
    )
