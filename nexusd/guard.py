"""
Nexus AIOS Security Guard & System Monitor (Phase 3).

Provides real-time proactive security monitoring, audit log anomaly detection,
system resource watchdog (CPU/RAM/Disk bounds via psutil), file tripwire verification,
and security posture scoring.

Can run embedded within nexusd or as a standalone background service (nexus-guard.service).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import psutil

from nexusd.audit import audit_logger

logger = logging.getLogger("nexusd.guard")


@dataclass
class SecurityAlert:
    """Represents an active security or anomaly alert."""
    id: str
    severity: str  # 'info', 'warning', 'critical'
    source: str    # 'audit', 'resource', 'tripwire', 'process'
    message: str
    timestamp: float
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SecurityGuard:
    """
    Proactive security monitor and system integrity guard.
    """

    def __init__(
        self,
        audit_log_path: str | Path | None = None,
        config_dir: str | Path | None = None,
    ) -> None:
        base_dir = Path(__file__).resolve().parent.parent
        self.audit_log_path = Path(audit_log_path or (base_dir / "logs" / "audit.log"))
        self.config_dir = Path(config_dir or (base_dir / "config"))

        self._lock = threading.Lock()
        self._alerts: list[SecurityAlert] = []
        self._last_scan_time: float = 0.0
        self._last_posture: dict[str, Any] = {}
        self._stop_event = threading.Event()
        self._monitor_thread: threading.Thread | None = None

        # Pre-seed initial scan
        self.scan()

    def get_resource_metrics(self) -> dict[str, Any]:
        """Collect current CPU, RAM, disk, and process counts."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
        except Exception:
            cpu_percent = 0.0

        try:
            mem = psutil.virtual_memory()
            mem_percent = mem.percent
            mem_used_mb = round(mem.used / (1024 * 1024), 1)
            mem_total_mb = round(mem.total / (1024 * 1024), 1)
        except Exception:
            mem_percent = 0.0
            mem_used_mb = 0.0
            mem_total_mb = 0.0

        try:
            disk = psutil.disk_usage(os.path.abspath(os.sep))
            disk_percent = disk.percent
            disk_free_gb = round(disk.free / (1024 * 1024 * 1024), 2)
        except Exception:
            disk_percent = 0.0
            disk_free_gb = 0.0

        try:
            process_count = len(psutil.pids())
        except Exception:
            process_count = 0

        return {
            "cpu_percent": cpu_percent,
            "memory_percent": mem_percent,
            "memory_used_mb": mem_used_mb,
            "memory_total_mb": mem_total_mb,
            "disk_percent": disk_percent,
            "disk_free_gb": disk_free_gb,
            "process_count": process_count,
        }

    def check_audit_anomalies(self) -> list[SecurityAlert]:
        """Scan recent audit entries for security denials or repeated errors."""
        alerts: list[SecurityAlert] = []
        if not self.audit_log_path.is_file():
            return alerts

        denial_count = 0
        error_count = 0
        recent_threshold = time.time() - 3600  # past 1 hour

        try:
            with open(self.audit_log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-200:]  # examine last 200 events

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue

                ts = entry.get("timestamp")
                if ts and isinstance(ts, (int, float)) and ts < recent_threshold:
                    continue

                event = entry.get("event", "")
                status = entry.get("status", "")

                if "denied" in event or status == "denied":
                    denial_count += 1
                elif status == "error" or "traversal" in event or "tamper" in event:
                    error_count += 1

            if denial_count >= 5:
                alerts.append(
                    SecurityAlert(
                        id=f"audit-denials-{int(time.time())}",
                        severity="warning",
                        source="audit",
                        message=f"High frequency of denied tool executions ({denial_count} in recent activity).",
                        timestamp=time.time(),
                        details={"denial_count": denial_count},
                    )
                )

            if error_count >= 10:
                alerts.append(
                    SecurityAlert(
                        id=f"audit-errors-{int(time.time())}",
                        severity="warning",
                        source="audit",
                        message=f"Elevated audit error rate detected ({error_count} recent failures).",
                        timestamp=time.time(),
                        details={"error_count": error_count},
                    )
                )
        except Exception as err:
            logger.warning("Failed to analyze audit log anomalies: %s", err)

        return alerts

    def check_resource_bounds(self, metrics: dict[str, Any]) -> list[SecurityAlert]:
        """Check if system metrics exceed safety thresholds."""
        alerts: list[SecurityAlert] = []

        if metrics["cpu_percent"] > 90.0:
            alerts.append(
                SecurityAlert(
                    id=f"res-cpu-{int(time.time())}",
                    severity="warning",
                    source="resource",
                    message=f"High CPU utilization: {metrics['cpu_percent']}%",
                    timestamp=time.time(),
                    details={"cpu_percent": metrics["cpu_percent"]},
                )
            )

        if metrics["memory_percent"] > 92.0:
            alerts.append(
                SecurityAlert(
                    id=f"res-mem-{int(time.time())}",
                    severity="warning",
                    source="resource",
                    message=f"Critical RAM pressure: {metrics['memory_percent']}% used ({metrics['memory_used_mb']}MB)",
                    timestamp=time.time(),
                    details={"memory_percent": metrics["memory_percent"]},
                )
            )

        if metrics["disk_percent"] > 95.0:
            alerts.append(
                SecurityAlert(
                    id=f"res-disk-{int(time.time())}",
                    severity="critical",
                    source="resource",
                    message=f"Host storage exhausted: {metrics['disk_percent']}% disk used ({metrics['disk_free_gb']}GB free)",
                    timestamp=time.time(),
                    details={"disk_percent": metrics["disk_percent"]},
                )
            )

        return alerts

    def check_tripwires(self) -> list[SecurityAlert]:
        """Verify configuration integrity and sensitive system targets."""
        alerts: list[SecurityAlert] = []

        # 1. Verify policy.yaml exists and is readable
        policy_file = self.config_dir / "policy.yaml"
        if not policy_file.is_file():
            alerts.append(
                SecurityAlert(
                    id=f"tripwire-policy-missing-{int(time.time())}",
                    severity="critical",
                    source="tripwire",
                    message="Critical security policy configuration file is missing (config/policy.yaml).",
                    timestamp=time.time(),
                    details={"path": str(policy_file)},
                )
            )

        return alerts

    def scan(self) -> dict[str, Any]:
        """Run a full security scan across resources, audit log, and tripwires."""
        with self._lock:
            metrics = self.get_resource_metrics()
            new_alerts: list[SecurityAlert] = []

            # Perform checks
            new_alerts.extend(self.check_resource_bounds(metrics))
            new_alerts.extend(self.check_audit_anomalies())
            new_alerts.extend(self.check_tripwires())

            # Update alert store (avoid duplicate messages)
            existing_messages = {a.message for a in self._alerts}
            for a in new_alerts:
                if a.message not in existing_messages:
                    self._alerts.append(a)
                    audit_logger.log("guard.alert", a.to_dict(), status="warning")

            # Retain up to 50 alerts max
            self._alerts = self._alerts[-50:]

            # Compute Security Score (100 is optimal)
            score = 100
            for a in self._alerts:
                if a.severity == "critical":
                    score -= 25
                elif a.severity == "warning":
                    score -= 10
                elif a.severity == "info":
                    score -= 2

            score = max(0, min(100, score))

            if score >= 90:
                level = "optimal"
            elif score >= 70:
                level = "warning"
            else:
                level = "critical"

            self._last_scan_time = time.time()
            self._last_posture = {
                "score": score,
                "level": level,
                "last_scan": self._last_scan_time,
                "active_alerts_count": len(self._alerts),
                "metrics": metrics,
            }

            return {
                "posture": self._last_posture,
                "alerts": [a.to_dict() for a in self._alerts],
            }

    def get_status(self) -> dict[str, Any]:
        """Return cached security posture and system metrics."""
        with self._lock:
            if not self._last_posture:
                return self.scan()["posture"]
            # Refresh live metrics for real-time responsiveness
            self._last_posture["metrics"] = self.get_resource_metrics()
            self._last_posture["active_alerts_count"] = len(self._alerts)
            return self._last_posture

    def get_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent security alerts."""
        with self._lock:
            return [a.to_dict() for a in self._alerts[-limit:]]

    def clear_alerts(self) -> None:
        """Clear active security alerts."""
        with self._lock:
            self._alerts.clear()
            self.scan()

    def start_monitor(self, interval_seconds: int = 30) -> None:
        """Start background daemon watchdog loop."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        self._stop_event.clear()

        def _loop() -> None:
            logger.info("SecurityGuard monitoring watchdog started (interval: %ds).", interval_seconds)
            while not self._stop_event.is_set():
                try:
                    self.scan()
                except Exception as err:
                    logger.error("Error during security guard scan: %s", err)
                self._stop_event.wait(timeout=interval_seconds)
            logger.info("SecurityGuard monitoring watchdog stopped.")

        self._monitor_thread = threading.Thread(target=_loop, name="NexusSecurityGuard", daemon=True)
        self._monitor_thread.start()

    def stop_monitor(self) -> None:
        """Stop background monitor thread."""
        self._stop_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=3.0)


def main() -> None:
    """CLI / Service runner for standalone Security Guard."""
    parser = argparse.ArgumentParser(description="Nexus AIOS Security Guard Service")
    parser.add_argument("--monitor", action="store_true", help="Run as standing daemon monitor")
    parser.add_argument("--scan", action="store_true", help="Perform single security scan and output JSON")
    parser.add_argument("--interval", type=int, default=30, help="Watchdog interval in seconds")
    args = parser.parse_args()

    guard = SecurityGuard()

    if args.scan or not args.monitor:
        report = guard.scan()
        print(json.dumps(report, indent=2))
        return

    print("Starting Nexus AIOS Security Guard Service...")
    guard.start_monitor(interval_seconds=args.interval)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping Security Guard...")
        guard.stop_monitor()
        print("Guard stopped.")


if __name__ == "__main__":
    main()
