"""
Unit tests for Nexus AIOS LLMRouter (Phase 1).

Tests local Ollama/llama.cpp inference, cloud provider HTTP calls,
and automatic fallback failover mechanisms.
"""

from __future__ import annotations

import unittest.mock as mock
import pytest
import requests

from nexusd.config import NexusConfig
from nexusd.router import LLMResponse, LLMRouter


@pytest.fixture
def base_config() -> NexusConfig:
    """Fixture providing a standard configured NexusConfig object."""
    cfg = NexusConfig()
    cfg.router.prefer = "local"
    cfg.router.timeout_seconds = 2
    cfg.model.local_type = "ollama"
    cfg.model.local_url = "http://127.0.0.1:11434"
    cfg.model.local_model = "llama3.2:1b"
    cfg.model.cloud_provider = "openai"
    cfg.model.cloud_url = "https://api.openai.com/v1"
    cfg.model.cloud_model = "gpt-4o-mini"
    cfg.model.cloud_api_key = "test-sk-12345"
    return cfg


def test_router_local_success(base_config: NexusConfig):
    """Test standard local inference when local endpoint is responsive."""
    router = LLMRouter(base_config)

    mock_resp = mock.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": "Local model response: Hello from Ollama!"}
    }

    with mock.patch("requests.post", return_value=mock_resp) as mock_post:
        res = router.generate("Hello Nexus")
        assert "Hello from Ollama!" in str(res)
        assert getattr(res, "provider", None) == "local"
        assert router.last_provider == "local"
        mock_post.assert_called_once()


def test_router_fallback_to_cloud_on_local_error(base_config: NexusConfig):
    """Test automatic failover to cloud when local provider encounters error."""
    router = LLMRouter(base_config)

    mock_cloud_resp = mock.MagicMock()
    mock_cloud_resp.status_code = 200
    mock_cloud_resp.json.return_value = {
        "choices": [{"message": {"content": "Cloud fallback response"}}]
    }

    def side_effect(url, **kwargs):
        if "11434" in url:
            raise requests.exceptions.ConnectionError("Connection refused to local Ollama")
        return mock_cloud_resp

    with mock.patch("requests.post", side_effect=side_effect):
        res = router.generate("Run diagnostic")
        assert str(res) == "Cloud fallback response"
        assert getattr(res, "provider", None) == "cloud"
        assert router.last_provider == "cloud"


def test_router_fallback_to_local_on_cloud_error(base_config: NexusConfig):
    """Test fallback to local when cloud provider is preferred but fails."""
    base_config.router.prefer = "cloud"
    router = LLMRouter(base_config)

    mock_local_resp = mock.MagicMock()
    mock_local_resp.status_code = 200
    mock_local_resp.json.return_value = {
        "message": {"content": "Local backup online"}
    }

    def side_effect(url, **kwargs):
        if "api.openai.com" in url:
            raise requests.exceptions.Timeout("Cloud API timed out")
        return mock_local_resp

    with mock.patch("requests.post", side_effect=side_effect):
        res = router.generate("What is my IP?")
        assert str(res) == "Local backup online"
        assert getattr(res, "provider", None) == "local"
        assert router.last_provider == "local"


def test_router_both_fail_raises_runtime_error(base_config: NexusConfig):
    """Ensure RuntimeError is raised when all providers fail."""
    router = LLMRouter(base_config)

    with mock.patch("requests.post", side_effect=requests.exceptions.ConnectionError("All down")):
        with pytest.raises(RuntimeError) as exc_info:
            router.generate("Emergency request")
        assert "All LLM providers failed" in str(exc_info.value)


def test_router_cloud_missing_key_fallback(base_config: NexusConfig):
    """Test that missing NEXUS_API_KEY gracefully fails over without crashing."""
    base_config.router.prefer = "cloud"
    base_config.model.cloud_api_key = None
    router = LLMRouter(base_config)

    mock_local_resp = mock.MagicMock()
    mock_local_resp.status_code = 200
    mock_local_resp.json.return_value = {
        "message": {"content": "Local offline answer"}
    }

    with mock.patch("requests.post", return_value=mock_local_resp):
        res = router.generate("Offline mode intent")
        assert str(res) == "Local offline answer"
        assert getattr(res, "provider", None) == "local"


def test_router_prefer_override_parameter(base_config: NexusConfig):
    """Test that explicit prefer argument overrides the config preference."""
    base_config.router.prefer = "local"
    router = LLMRouter(base_config)

    mock_cloud_resp = mock.MagicMock()
    mock_cloud_resp.status_code = 200
    mock_cloud_resp.json.return_value = {
        "choices": [{"message": {"content": "Cloud response requested via flag"}}]
    }

    with mock.patch("requests.post", return_value=mock_cloud_resp) as mock_post:
        res = router.generate("Heavy analysis", prefer="cloud")
        assert "Cloud response" in str(res)
        assert getattr(res, "provider", None) == "cloud"
        call_url = mock_post.call_args[0][0]
        assert "api.openai.com" in call_url


def test_router_anthropic_provider(base_config: NexusConfig):
    """Test Anthropic Claude API formatting and parsing."""
    base_config.model.cloud_provider = "anthropic"
    base_config.model.cloud_model = "claude-3-5-haiku-20241022"
    router = LLMRouter(base_config)

    mock_resp = mock.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "content": [{"text": "Claude response: Safe action planned."}]
    }

    with mock.patch("requests.post", return_value=mock_resp) as mock_post:
        res = router.generate("Help me", prefer="cloud")
        assert "Claude response" in str(res)
        call_headers = mock_post.call_args[1]["headers"]
        assert call_headers["x-api-key"] == "test-sk-12345"
        assert call_headers["anthropic-version"] == "2023-06-01"
