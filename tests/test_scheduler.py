"""
Unit tests for Nexus AIOS Task Scheduler (Phase 3).
"""

from __future__ import annotations

import time
import pytest
from nexusd.scheduler import ScheduledTask, Scheduler


@pytest.fixture
def test_scheduler(tmp_path):
    db_file = tmp_path / "test_scheduler.db"
    sched = Scheduler(db_path=db_file)
    yield sched
    sched.stop()


def test_scheduler_initialization(test_scheduler):
    """Test scheduler initialization and default seed tasks."""
    tasks = test_scheduler.list_tasks()
    assert len(tasks) >= 2
    task_ids = [t.id for t in tasks]
    assert "sys-health-check" in task_ids
    assert "sec-guard-sweep" in task_ids


def test_add_and_get_task(test_scheduler):
    """Test creating and retrieving a custom scheduled task."""
    task = test_scheduler.add_task(
        name="Backup Memory Store",
        action_type="tool",
        payload={"action": "files.list", "params": {"path": "."}},
        interval_seconds=120,
        task_id="custom-backup",
    )
    assert task.id == "custom-backup"
    assert task.name == "Backup Memory Store"
    assert task.interval_seconds == 120
    assert task.enabled is True

    retrieved = test_scheduler.get_task("custom-backup")
    assert retrieved is not None
    assert retrieved.name == "Backup Memory Store"
    assert retrieved.payload["action"] == "files.list"


def test_toggle_task(test_scheduler):
    """Test toggling task enabled state."""
    task = test_scheduler.add_task(
        name="Toggle Test",
        action_type="intent",
        payload={"text": "ping"},
        interval_seconds=60,
        task_id="toggle-task",
        enabled=True,
    )
    assert task.enabled is True

    # Disable
    updated = test_scheduler.toggle_task("toggle-task", enabled=False)
    assert updated is not None
    assert updated.enabled is False

    # Toggle back
    updated2 = test_scheduler.toggle_task("toggle-task")
    assert updated2 is not None
    assert updated2.enabled is True


def test_remove_task(test_scheduler):
    """Test deleting a scheduled task."""
    test_scheduler.add_task(
        name="Temp Job",
        action_type="system",
        payload={},
        interval_seconds=30,
        task_id="temp-job",
    )
    assert test_scheduler.get_task("temp-job") is not None

    deleted = test_scheduler.remove_task("temp-job")
    assert deleted is True
    assert test_scheduler.get_task("temp-job") is None

    # Deleting nonexistent returns False
    assert test_scheduler.remove_task("nonexistent") is False


def test_trigger_task_execution(tmp_path):
    """Test manual task triggering and callback execution."""
    db_file = tmp_path / "exec_scheduler.db"
    executed = []

    def mock_executor(task: ScheduledTask):
        executed.append(task.id)
        return "Mock Success"

    sched = Scheduler(db_path=db_file, executor_fn=mock_executor)
    sched.add_task(
        name="Trigger Test",
        action_type="tool",
        payload={"action": "test"},
        interval_seconds=50,
        task_id="exec-task",
    )

    result = sched.trigger_task("exec-task")
    assert result["status"] == "ok"
    assert "Mock Success" in result["result"]
    assert "exec-task" in executed

    task = sched.get_task("exec-task")
    assert task.run_count == 1
    assert task.last_status == "ok"
    assert task.last_run is not None


def test_scheduler_lifecycle(test_scheduler):
    """Test starting and stopping scheduler thread."""
    test_scheduler.start()
    assert test_scheduler._worker_thread is not None
    assert test_scheduler._worker_thread.is_alive()

    # Second start is idempotent
    test_scheduler.start()

    test_scheduler.stop()
    assert test_scheduler._stop_event.is_set()
