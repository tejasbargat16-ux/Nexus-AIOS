"""
Nexus AIOS Configuration Module (Phase 1).

Loads, validates, and manages system configurations from YAML and environment variables.
Designed for minimal resource overhead on ARM64 Termux and Linux desktop environments.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml


@dataclass
class ApiConfig:
    """HTTP API server configuration."""
    host: str = "127.0.0.1"
    port: int = 8765
    debug: bool = False


@dataclass
class RouterConfig:
    """LLM Router and failover settings."""
    prefer: str = "local"  # 'local' | 'cloud'
    timeout_seconds: int = 15


@dataclass
class ModelConfig:
    """LLM provider endpoints and model identifiers."""
    local_type: str = "ollama"  # 'ollama' | 'llamacpp'
    local_url: str = "http://127.0.0.1:11434"
    local_model: str = "llama3.2:1b"
    local_path: str = ""
    cloud_provider: str = "openai"  # 'openai' | 'anthropic' | 'groq' | 'openrouter'
    cloud_url: str = "https://api.openai.com/v1"
    cloud_model: str = "gpt-4o-mini"
    cloud_api_key: str | None = None


@dataclass
class NexusConfig:
    """Root configuration tree for Nexus AIOS."""
    api: ApiConfig = field(default_factory=ApiConfig)
    router: RouterConfig = field(default_factory=RouterConfig)
    model: ModelConfig = field(default_factory=ModelConfig)


def _find_default_config_path() -> Path:
    """Locate config file in repository, user home, or /etc."""
    repo_config = Path(__file__).resolve().parent.parent / "config" / "nexus.yaml"
    if repo_config.is_file():
        return repo_config

    home_config = Path.home() / ".config" / "nexus" / "nexus.yaml"
    if home_config.is_file():
        return home_config

    return repo_config


def load_config(config_path: str | Path | None = None) -> NexusConfig:
    """
    Load configuration from YAML file with environment variable overrides.

    Args:
        config_path: Explicit path to YAML configuration file.

    Returns:
        NexusConfig: Validated system configuration object.
    """
    target_path = Path(
        config_path
        or os.getenv("NEXUS_CONFIG_PATH")
        or _find_default_config_path()
    )

    data: dict[str, Any] = {}
    if target_path.is_file():
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    data = loaded
        except Exception:
            pass

    api_data = data.get("api", {}) or {}
    router_data = data.get("router", {}) or {}
    model_data = data.get("model", {}) or {}

    # Build ApiConfig with env overrides
    api_host = os.getenv("NEXUS_API_HOST", api_data.get("host", "127.0.0.1"))
    api_port_raw = os.getenv("NEXUS_API_PORT", str(api_data.get("port", 8765)))
    try:
        api_port = int(api_port_raw)
    except ValueError:
        api_port = 8765

    api_debug = bool(api_data.get("debug", False))
    api_cfg = ApiConfig(host=api_host, port=api_port, debug=api_debug)

    # Build RouterConfig with env overrides
    router_prefer = os.getenv("NEXUS_ROUTER_PREFER", router_data.get("prefer", "local")).lower()
    if router_prefer not in ("local", "cloud"):
        router_prefer = "local"

    timeout_raw = os.getenv("NEXUS_ROUTER_TIMEOUT", str(router_data.get("timeout_seconds", 15)))
    try:
        timeout_seconds = int(timeout_raw)
    except ValueError:
        timeout_seconds = 15

    router_cfg = RouterConfig(prefer=router_prefer, timeout_seconds=timeout_seconds)

    # Build ModelConfig with env overrides
    cloud_key = os.getenv("NEXUS_API_KEY")
    model_cfg = ModelConfig(
        local_type=os.getenv("NEXUS_LOCAL_TYPE", model_data.get("local_type", "ollama")),
        local_url=os.getenv("NEXUS_LOCAL_URL", model_data.get("local_url", "http://127.0.0.1:11434")),
        local_model=os.getenv("NEXUS_LOCAL_MODEL", model_data.get("local_model", "llama3.2:1b")),
        local_path=os.getenv("NEXUS_LOCAL_PATH", model_data.get("local_path", "")),
        cloud_provider=os.getenv("NEXUS_CLOUD_PROVIDER", model_data.get("cloud_provider", "openai")),
        cloud_url=os.getenv("NEXUS_CLOUD_URL", model_data.get("cloud_url", "https://api.openai.com/v1")),
        cloud_model=os.getenv("NEXUS_CLOUD_MODEL", model_data.get("cloud_model", "gpt-4o-mini")),
        cloud_api_key=cloud_key,
    )

    return NexusConfig(api=api_cfg, router=router_cfg, model=model_cfg)
