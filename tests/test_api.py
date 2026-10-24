"""Integration tests for nexusd Flask API."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is available
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import unittest.mock as mock
import pytest

from nexusd.api import create_app
from nexusd.config import NexusConfig
from nexusd.router import LLMResponse, LLMRouter


@pytest.fixture
def test_app():
    cfg = NexusConfig()
    cfg.model.cloud_api_key = "test-key"
    router = LLMRouter(cfg)
    app = create_app(config=cfg, router=router)
    app.config["TESTING"] = True
    return app


def test_api_status_endpoint(test_app):
    client = test_app.test_client()
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "nexusd"
    assert "uptime_seconds" in data
    assert "providers" in data


def test_api_intent_validation_empty(test_app):
    client = test_app.test_client()
    resp = client.post("/intent", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_api_intent_success(test_app):
    client = test_app.test_client()
    fake_response = LLMResponse("Ready to assist you.", "local")

    with mock.patch.object(LLMRouter, "generate", return_value=fake_response):
        resp = client.post("/intent", json={"text": "check system status"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["reply"] == "Ready to assist you."
        assert data["provider"] == "local"
        assert "duration_ms" in data


def test_api_audit_endpoint(test_app):
    client = test_app.test_client()
    resp = client.get("/audit")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "entries" in data
    assert "count" in data
