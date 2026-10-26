"""
Integration tests for Phase 3 REST API endpoints.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexusd.api import create_app
from nexusd.config import NexusConfig
from nexusd.guard import SecurityGuard
from nexusd.memory.store import MemoryStore
from nexusd.permissions.engine import PermissionEngine
from nexusd.router import LLMRouter
from nexusd.scheduler import Scheduler


@pytest.fixture
def app_phase3(tmp_path):
    cfg = NexusConfig()
    cfg.model.cloud_api_key = "test-key"
    router = LLMRouter(cfg)

    policy_file = tmp_path / "test_policy.yaml"
    policy_file.write_text("default: allow\nrules: {}\n")
    perm_engine = PermissionEngine(policy_path=policy_file)

    db_path = tmp_path / "test_phase3_memory.db"
    mem_store = MemoryStore(db_path=db_path)
    scheduler = Scheduler(db_path=db_path)
    guard = SecurityGuard(audit_log_path=tmp_path / "test_audit.log", config_dir=tmp_path)

    app = create_app(
        config=cfg,
        router=router,
        permissions=perm_engine,
        memory=mem_store,
        scheduler=scheduler,
        guard=guard,
        start_scheduler=False,
    )
    app.config["TESTING"] = True
    yield app
    scheduler.stop()


def test_api_phase3_status_endpoint(app_phase3):
    client = app_phase3.test_client()
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["version"] == "0.3.0-phase3"
    comps = data["components"]
    assert "scheduled_tasks" in comps
    assert "security_score" in comps
    assert "security_level" in comps


def test_api_scheduler_crud(app_phase3):
    client = app_phase3.test_client()

    # 1. List default tasks
    resp = client.get("/scheduler/tasks")
    assert resp.status_code == 200
    tasks = resp.get_json()["tasks"]
    assert len(tasks) >= 2

    # 2. Create new task
    new_task = {
        "name": "Hourly Connectivity Sweep",
        "action_type": "tool",
        "payload": {"action": "network.check", "params": {"host": "8.8.8.8"}},
        "interval_seconds": 3600,
        "enabled": True,
    }
    create_resp = client.post("/scheduler/tasks", json=new_task)
    assert create_resp.status_code == 201
    created_id = create_resp.get_json()["task"]["id"]

    # 3. Toggle task
    toggle_resp = client.post(f"/scheduler/tasks/{created_id}/toggle", json={"enabled": False})
    assert toggle_resp.status_code == 200
    assert toggle_resp.get_json()["task"]["enabled"] is False

    # 4. Trigger task
    run_resp = client.post(f"/scheduler/tasks/{created_id}/run")
    assert run_resp.status_code == 200
    assert run_resp.get_json()["status"] == "ok"

    # 5. Delete task
    del_resp = client.delete(f"/scheduler/tasks/{created_id}")
    assert del_resp.status_code == 200

    # Verify deleted
    del_again = client.delete(f"/scheduler/tasks/{created_id}")
    assert del_again.status_code == 404


def test_api_scheduler_validation(app_phase3):
    client = app_phase3.test_client()

    # Missing name
    resp = client.post("/scheduler/tasks", json={"action_type": "tool", "interval_seconds": 60})
    assert resp.status_code == 400

    # Invalid interval
    resp2 = client.post("/scheduler/tasks", json={"name": "test", "action_type": "tool", "interval_seconds": -5})
    assert resp2.status_code == 400


def test_api_guard_endpoints(app_phase3):
    client = app_phase3.test_client()

    # Status
    status_resp = client.get("/guard/status")
    assert status_resp.status_code == 200
    data = status_resp.get_json()
    assert "score" in data
    assert "level" in data
    assert "metrics" in data

    # Alerts
    alerts_resp = client.get("/guard/alerts")
    assert alerts_resp.status_code == 200
    assert "alerts" in alerts_resp.get_json()

    # On-demand scan
    scan_resp = client.post("/guard/scan")
    assert scan_resp.status_code == 200
    assert "posture" in scan_resp.get_json()

    # Clear alerts
    clear_resp = client.post("/guard/alerts/clear")
    assert clear_resp.status_code == 200
    assert clear_resp.get_json()["status"] == "cleared"
