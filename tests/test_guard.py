"""
Unit tests for Nexus AIOS Security Guard (Phase 3).
"""

from __future__ import annotations

import json
import time
import pytest
from nexusd.guard import SecurityAlert, SecurityGuard


@pytest.fixture
def guard_env(tmp_path):
    audit_file = tmp_path / "audit.log"
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    # Valid policy file
    policy_file = config_dir / "policy.yaml"
    policy_file.write_text("default: confirm\nrules: {}\n")

    guard = SecurityGuard(audit_log_path=audit_file, config_dir=config_dir)
    return guard, audit_file, config_dir


def test_guard_resource_metrics(guard_env):
    """Test resource metric collection."""
    guard, _, _ = guard_env
    metrics = guard.get_resource_metrics()
    assert "cpu_percent" in metrics
    assert "memory_percent" in metrics
    assert "disk_percent" in metrics
    assert "process_count" in metrics
    assert metrics["process_count"] >= 0


def test_guard_tripwire_policy_missing(tmp_path):
    """Test tripwire detection when policy.yaml is missing."""
    empty_config = tmp_path / "empty_config"
    empty_config.mkdir(parents=True)
    guard = SecurityGuard(config_dir=empty_config)

    alerts = guard.check_tripwires()
    assert len(alerts) >= 1
    assert any("policy.yaml" in a.message for a in alerts)


def test_guard_audit_anomaly_detection(guard_env):
    """Test detection of anomalous denial spikes in audit log."""
    guard, audit_file, _ = guard_env

    # Simulate 6 denied events in the audit log
    with open(audit_file, "w", encoding="utf-8") as f:
        for i in range(6):
            entry = {
                "timestamp": time.time(),
                "event": "tool.denied",
                "status": "denied",
                "data": {"tool": "danger.format"},
            }
            f.write(json.dumps(entry) + "\n")

    alerts = guard.check_audit_anomalies()
    assert len(alerts) >= 1
    assert any("denied tool executions" in a.message for a in alerts)


def test_guard_posture_scan_and_score(guard_env):
    """Test overall posture calculation and scoring."""
    guard, _, _ = guard_env
    report = guard.scan()
    assert "posture" in report
    assert "alerts" in report
    posture = report["posture"]
    assert 0 <= posture["score"] <= 100
    assert posture["level"] in ("optimal", "warning", "critical")


def test_guard_clear_alerts(guard_env):
    """Test clearing active alerts."""
    guard, _, _ = guard_env
    guard._alerts.append(
        SecurityAlert(
            id="test-alert",
            severity="warning",
            source="test",
            message="Test anomaly",
            timestamp=time.time(),
            details={},
        )
    )
    assert len(guard.get_alerts()) >= 1

    guard.clear_alerts()
    # Manual test alert was cleared
    assert not any(a["id"] == "test-alert" for a in guard.get_alerts())
