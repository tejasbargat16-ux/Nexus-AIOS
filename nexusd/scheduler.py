"""
Nexus AIOS Task Scheduler (Phase 3).

Provides interval and recurring background task scheduling for autonomous operations,
system health checks, automated security scans, and scheduled user intents.
Persists tasks to SQLite and executes jobs safely without blocking the main daemon loop.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("nexusd.scheduler")


@dataclass
class ScheduledTask:
    """Represents a scheduled job."""
    id: str
    name: str
    action_type: str  # 'intent', 'tool', or 'system'
    payload: dict[str, Any]
    interval_seconds: int
    enabled: bool = True
    last_run: float | None = None
    next_run: float = 0.0
    run_count: int = 0
    last_status: str = "pending"  # 'pending', 'ok', 'error'
    last_result: str = ""
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert task to dictionary representation."""
        data = asdict(self)
        # Compute time until next run in seconds
        now = time.time()
        data["due_in_seconds"] = max(0, round(self.next_run - now, 1))
        return data


class Scheduler:
    """
    Thread-safe persistent task scheduler.
    Executes scheduled intents, tools, or system maintenance jobs at specified intervals.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        executor_fn: Callable[[ScheduledTask], Any] | None = None,
    ) -> None:
        if db_path:
            self.db_path = Path(db_path)
        else:
            base_dir = Path(__file__).resolve().parent / "memory"
            self.db_path = base_dir / "nexus.db"

        self.executor_fn = executor_fn
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._ensure_db()
        self._seed_default_tasks()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and return an SQLite connection."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db(self) -> None:
        """Initialize the scheduled_tasks table schema."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS scheduled_tasks (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        action_type TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        interval_seconds INTEGER NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        last_run REAL,
                        next_run REAL NOT NULL,
                        run_count INTEGER NOT NULL DEFAULT 0,
                        last_status TEXT NOT NULL DEFAULT 'pending',
                        last_result TEXT DEFAULT '',
                        created_at REAL NOT NULL
                    )
                """)
                conn.commit()

    def _seed_default_tasks(self) -> None:
        """Seed built-in maintenance and monitoring tasks if not present."""
        existing = {t.id for t in self.list_tasks()}

        defaults = [
            ScheduledTask(
                id="sys-health-check",
                name="System Health & Network Sweep",
                action_type="tool",
                payload={"action": "network.check", "params": {"host": "1.1.1.1", "port": 53}},
                interval_seconds=300,  # 5 minutes
                enabled=True,
                next_run=time.time() + 300,
                created_at=time.time(),
            ),
            ScheduledTask(
                id="sec-guard-sweep",
                name="Security Guard Automated Scan",
                action_type="system",
                payload={"action": "guard.scan"},
                interval_seconds=600,  # 10 minutes
                enabled=True,
                next_run=time.time() + 600,
                created_at=time.time(),
            ),
        ]

        for task in defaults:
            if task.id not in existing:
                self.add_task(
                    name=task.name,
                    action_type=task.action_type,
                    payload=task.payload,
                    interval_seconds=task.interval_seconds,
                    task_id=task.id,
                    enabled=task.enabled,
                )

    def list_tasks(self) -> list[ScheduledTask]:
        """Return all registered scheduled tasks."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM scheduled_tasks ORDER BY created_at ASC"
                )
                rows = cursor.fetchall()

        tasks: list[ScheduledTask] = []
        for r in rows:
            try:
                payload = json.loads(r["payload_json"])
            except (json.JSONDecodeError, TypeError):
                payload = {}

            tasks.append(
                ScheduledTask(
                    id=r["id"],
                    name=r["name"],
                    action_type=r["action_type"],
                    payload=payload,
                    interval_seconds=int(r["interval_seconds"]),
                    enabled=bool(r["enabled"]),
                    last_run=float(r["last_run"]) if r["last_run"] is not None else None,
                    next_run=float(r["next_run"]),
                    run_count=int(r["run_count"]),
                    last_status=r["last_status"] or "pending",
                    last_result=r["last_result"] or "",
                    created_at=float(r["created_at"]),
                )
            )
        return tasks

    def get_task(self, task_id: str) -> ScheduledTask | None:
        """Retrieve a specific scheduled task by ID."""
        tasks = [t for t in self.list_tasks() if t.id == task_id]
        return tasks[0] if tasks else None

    def add_task(
        self,
        name: str,
        action_type: str,
        payload: dict[str, Any],
        interval_seconds: int,
        task_id: str | None = None,
        enabled: bool = True,
    ) -> ScheduledTask:
        """
        Register a new task or update an existing one.
        """
        tid = task_id or f"task-{uuid.uuid4().hex[:8]}"
        now = time.time()
        next_run = now + interval_seconds
        payload_str = json.dumps(payload)

        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO scheduled_tasks (
                        id, name, action_type, payload_json, interval_seconds,
                        enabled, last_run, next_run, run_count, last_status, last_result, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 0, 'pending', '', ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name,
                        action_type=excluded.action_type,
                        payload_json=excluded.payload_json,
                        interval_seconds=excluded.interval_seconds,
                        enabled=excluded.enabled
                    """,
                    (tid, name, action_type, payload_str, interval_seconds, 1 if enabled else 0, next_run, now),
                )
                conn.commit()

        logger.info("Registered scheduled task: %s (%s, every %ds)", name, tid, interval_seconds)
        task = self.get_task(tid)
        if not task:
            raise RuntimeError(f"Failed to create task {tid}")
        return task

    def remove_task(self, task_id: str) -> bool:
        """Delete a scheduled task."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
                conn.commit()
                deleted = cursor.rowcount > 0

        if deleted:
            logger.info("Deleted scheduled task: %s", task_id)
        return deleted

    def toggle_task(self, task_id: str, enabled: bool | None = None) -> ScheduledTask | None:
        """Toggle task enabled state (or explicitly set it)."""
        task = self.get_task(task_id)
        if not task:
            return None

        new_state = (not task.enabled) if enabled is None else enabled
        now = time.time()
        next_run = (now + task.interval_seconds) if new_state else task.next_run

        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE scheduled_tasks SET enabled = ?, next_run = ? WHERE id = ?",
                    (1 if new_state else 0, next_run, task_id),
                )
                conn.commit()

        logger.info("Toggled task %s enabled=%s", task_id, new_state)
        return self.get_task(task_id)

    def trigger_task(self, task_id: str) -> dict[str, Any]:
        """Manually trigger immediate execution of a task."""
        task = self.get_task(task_id)
        if not task:
            return {"status": "error", "message": f"Task '{task_id}' not found"}

        return self._execute_task(task)

    def _execute_task(self, task: ScheduledTask) -> dict[str, Any]:
        """Execute a single task and update its stats."""
        start_time = time.time()
        logger.info("Executing scheduled task '%s' (action: %s)", task.name, task.action_type)

        status = "ok"
        result_str = ""

        try:
            if self.executor_fn:
                exec_result = self.executor_fn(task)
                result_str = str(exec_result)[:500]
            else:
                result_str = f"Simulated execution for {task.action_type}: {task.payload}"
        except Exception as err:
            logger.error("Error executing task %s: %s", task.id, err)
            status = "error"
            result_str = f"Error: {err}"

        elapsed = round(time.time() - start_time, 2)
        now = time.time()
        next_run = now + task.interval_seconds

        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE scheduled_tasks
                    SET last_run = ?, next_run = ?, run_count = run_count + 1,
                        last_status = ?, last_result = ?
                    WHERE id = ?
                    """,
                    (now, next_run, status, f"{result_str} (in {elapsed}s)", task.id),
                )
                conn.commit()

        return {
            "task_id": task.id,
            "status": status,
            "result": result_str,
            "elapsed_seconds": elapsed,
            "next_run": next_run,
        }

    def _run_loop(self) -> None:
        """Main loop checking for due tasks every second."""
        logger.info("Scheduler worker thread active.")
        while not self._stop_event.is_set():
            now = time.time()
            tasks = self.list_tasks()

            for task in tasks:
                if self._stop_event.is_set():
                    break
                if task.enabled and task.next_run <= now:
                    try:
                        self._execute_task(task)
                    except Exception as err:
                        logger.error("Unexpected error in scheduled task %s: %s", task.id, err)

            self._stop_event.wait(timeout=1.0)

        logger.info("Scheduler worker loop exited.")

    def start(self) -> None:
        """Start background scheduler loop."""
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._run_loop, name="NexusSchedulerWorker", daemon=True
        )
        self._worker_thread.start()
        logger.info("Scheduler started successfully.")

    def stop(self) -> None:
        """Stop background scheduler cleanly."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3.0)
        logger.info("Scheduler stopped.")
