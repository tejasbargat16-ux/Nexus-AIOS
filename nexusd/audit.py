"""
Nexus AIOS Audit Logger.

Records every system and AI action as structured JSON lines in logs/audit.log.
Ensures thread safety and minimal memory footprint on ARM64 and low-spec systems.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    """Thread-safe append-only JSON-lines audit logger."""

    def __init__(self, log_file: str | Path | None = None) -> None:
        if log_file:
            self.log_path = Path(log_file)
        else:
            base_dir = Path(__file__).resolve().parent.parent
            self.log_path = base_dir / "logs" / "audit.log"

        self._lock = threading.Lock()
        self._ensure_log_dir()

    def _ensure_log_dir(self) -> None:
        """Create logs directory if it does not exist."""
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def log(
        self,
        action: str,
        details: dict[str, Any] | None = None,
        status: str = "ok",
        provider: str | None = None,
    ) -> dict[str, Any]:
        """
        Append a structured event to the audit log.
        
        Args:
            action: Name of the action (e.g. 'intent.received', 'tool.exec').
            details: Contextual payload for the event.
            status: Status code or result ('ok', 'error', 'denied').
            provider: LLM provider that processed the event ('local' | 'cloud').
            
        Returns:
            dict: The recorded audit entry.
        """
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "status": status,
            "provider": provider,
            "details": details or {},
        }

        self._ensure_log_dir()
        line = json.dumps(entry) + "\n"

        with self._lock:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line)

        return entry

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Retrieve the most recent audit log entries.
        
        Args:
            limit: Maximum number of recent entries to return (default 50).
            
        Returns:
            list[dict]: List of parsed audit entries ordered from newest to oldest.
        """
        if not self.log_path.is_file():
            return []

        entries: list[dict[str, Any]] = []
        with self._lock:
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError:
                return []

        # Parse from newest lines backwards
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
                if len(entries) >= limit:
                    break
            except json.JSONDecodeError:
                continue

        return entries


# Default module-level audit instance
audit_logger = AuditLogger()
