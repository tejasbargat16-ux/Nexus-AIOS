"""Integration tests for Phase 2 REST API endpoints."""

from __future__ import annotations

import sys
import unittest.mock as mock
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexusd.api import create_app
from nexusd.config import NexusConfig
from nexusd.memory.store import MemoryStore
from nexusd.permissions.engine import PermissionEngine
from nexusd.router import LLMResponse, LLMRouter


@pytest.fixture
def app_phase2(tmp_path):
    cfg = NexusConfig()
    cfg.model.cloud_api_key = "test-key"
    router = LLMRouter(cfg)

    # Isolated test policy
    policy_path = tmp_path / "test_policy.yaml"
    policy_path.write_text("""
default: confirm
rules:
  files.read: allow
  files.delete: confirm
  system.format: deny
  network.ip_info: allow
""")
    perm_engine = PermissionEngine(policy_path=policy_path)
    mem_store = MemoryStore(db_path=tmp_path / "test_api_memory.db")

    app = create_app(config=cfg, router=router, permissions=perm_engine, memory=mem_store)
    app.config["TESTING"] = True
    return app


def test_api_phase2_status_endpoint(app_phase2):
    client = app_phase2.test_client()
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["version"] in ("0.2.0-phase2", "0.3.0-phase3")
    assert "components" in data
    assert data["components"]["tools_registered"] >= 15


def test_api_tools_endpoint(app_phase2):
    client = app_phase2.test_client()
    resp = client.get("/tools")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "tools" in data
    assert data["count"] >= 15


def test_api_permissions_endpoint(app_phase2):
    client = app_phase2.test_client()
    resp = client.get("/permissions")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["default"] == "confirm"
    assert "rules" in data


def test_api_permissions_check_endpoint(app_phase2):
    client = app_phase2.test_client()
    resp = client.post("/permissions/check", json={"action": "files.read"})
    assert resp.status_code == 200
    assert resp.get_json()["level"] == "allow"

    resp2 = client.post("/permissions/check", json={"action": "files.delete"})
    assert resp2.status_code == 200
    assert resp2.get_json()["level"] == "confirm"


def test_api_tool_execute_allowed(app_phase2):
    client = app_phase2.test_client()
    resp = client.post("/tool/execute", json={"action": "network.ip_info", "params": {}})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "result" in data


def test_api_tool_execute_denied(app_phase2):
    client = app_phase2.test_client()
    resp = client.post("/tool/execute", json={"action": "system.format", "params": {}})
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["status"] == "denied"


def test_api_tool_execute_confirmation_required_and_confirmed(app_phase2, tmp_path):
    target = tmp_path / "to_delete.txt"
    target.write_text("temporary data")

    client = app_phase2.test_client()

    # 1. Without confirmation
    resp1 = client.post("/tool/execute", json={"action": "files.delete", "params": {"path": str(target)}})
    assert resp1.status_code == 200
    data1 = resp1.get_json()
    assert data1["status"] == "confirmation_required"
    assert target.exists()

    # 2. With explicit user confirmation
    resp2 = client.post("/tool/execute", json={
        "action": "files.delete",
        "params": {"path": str(target)},
        "confirmed": True,
    })
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2["status"] == "ok"
    assert not target.exists()


def test_api_memory_facts_endpoints(app_phase2):
    client = app_phase2.test_client()

    # Create fact
    post_resp = client.post("/memory/facts", json={
        "key": "user.name",
        "value": "Tejas",
        "category": "profile",
    })
    assert post_resp.status_code == 200

    # Get facts
    get_resp = client.get("/memory/facts")
    assert get_resp.status_code == 200
    facts = get_resp.get_json()["facts"]
    assert any(f["key"] == "user.name" and f["value"] == "Tejas" for f in facts)

    # Search memory
    search_resp = client.get("/memory/search?q=Tejas")
    assert search_resp.status_code == 200
    results = search_resp.get_json()["results"]
    assert len(results) > 0

    # Delete fact
    del_resp = client.delete("/memory/facts/user.name")
    assert del_resp.status_code == 200


def test_api_intent_with_tool_call(app_phase2, tmp_path):
    client = app_phase2.test_client()

    test_file = tmp_path / "greeting.txt"
    test_file.write_text("Greetings from Nexus AIOS!")

    fake_llm_json = f'{{"action": "files.read", "params": {{"path": "{test_file.as_posix()}"}}}}'
    fake_response = LLMResponse(fake_llm_json, "local")

    with mock.patch.object(LLMRouter, "generate", return_value=fake_response):
        resp = client.post("/intent", json={"text": "read greeting.txt"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "tool_result" in data
        assert data["tool_result"]["content"] == "Greetings from Nexus AIOS!"

    # Verify intent was recorded in memory history
    hist_resp = client.get("/memory/history")
    assert hist_resp.status_code == 200
    hist = hist_resp.get_json()["history"]
    assert len(hist) > 0
    assert hist[0]["intent"] == "read greeting.txt"
