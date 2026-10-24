"""
Nexus AIOS LLM Router (Phase 1).

Routes intent messages between local offline models (Ollama/llama.cpp)
and cloud LLM providers (OpenAI/Anthropic/compatible), with automatic failover.
"""

from __future__ import annotations

import logging
from typing import Any
import requests

from nexusd.config import NexusConfig

logger = logging.getLogger("nexusd.router")


class LLMResponse(str):
    """
    String subclass containing provider metadata.
    Enables string compatibility while retaining provider tracking for auditing.
    """
    provider: str

    def __new__(cls, text: str, provider: str = "local") -> LLMResponse:
        obj = super().__new__(cls, text)
        obj.provider = provider
        return obj

    @property
    def reply(self) -> str:
        """Alias for response text."""
        return str(self)

    @property
    def text(self) -> str:
        """Alias for response text."""
        return str(self)


class LLMRouter:
    """Intelligent router managing local and cloud LLM execution."""

    def __init__(self, config: NexusConfig) -> None:
        self.config = config
        self.last_provider: str = config.router.prefer

    def _call_local(self, messages: list[dict[str, str]]) -> str:
        """Execute request against local Ollama or llama.cpp endpoint."""
        timeout = self.config.router.timeout_seconds
        local_type = self.config.model.local_type.lower()
        base_url = self.config.model.local_url.rstrip("/")

        if local_type == "llamacpp":
            url = f"{base_url}/v1/chat/completions"
            payload = {
                "model": self.config.model.local_model,
                "messages": messages,
                "stream": False,
            }
            resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            return str(data["choices"][0]["message"]["content"]).strip()
        else:
            url = f"{base_url}/api/chat"
            payload = {
                "model": self.config.model.local_model,
                "messages": messages,
                "stream": False,
            }
            resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            return str(data["message"]["content"]).strip()

    def _call_cloud(self, messages: list[dict[str, str]]) -> str:
        """Execute request against cloud provider endpoint."""
        api_key = self.config.model.cloud_api_key
        if not api_key:
            raise ValueError("No NEXUS_API_KEY provided for cloud provider")

        timeout = self.config.router.timeout_seconds
        provider = self.config.model.cloud_provider.lower()
        cloud_url = self.config.model.cloud_url.rstrip("/")

        if provider in ("anthropic", "claude"):
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            system_prompt = ""
            user_messages = []
            for m in messages:
                if m.get("role") == "system":
                    system_prompt = m.get("content", "")
                else:
                    user_messages.append(m)

            payload: dict[str, Any] = {
                "model": self.config.model.cloud_model,
                "messages": user_messages,
                "max_tokens": 1024,
            }
            if system_prompt:
                payload["system"] = system_prompt

            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            return str(data["content"][0]["text"]).strip()
        else:
            url = f"{cloud_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.config.model.cloud_model,
                "messages": messages,
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            return str(data["choices"][0]["message"]["content"]).strip()

    def generate(
        self,
        messages: list[dict[str, str]] | str,
        prefer: str | None = None,
    ) -> str:
        """
        Generate completion for prompt/messages, failing over between local and cloud.

        Args:
            messages: Prompt string or list of message dictionaries.
            prefer: Optional provider override ('local' | 'cloud').

        Returns:
            str: Completion reply (instance of LLMResponse with .provider).
        """
        if isinstance(messages, str):
            msg_list = [{"role": "user", "content": messages}]
        else:
            msg_list = messages

        preferred = (prefer or self.config.router.prefer).lower()
        if preferred not in ("local", "cloud"):
            preferred = "local"

        fallback = "cloud" if preferred == "local" else "local"
        providers_sequence = [preferred, fallback]
        last_error: Exception | None = None

        for provider in providers_sequence:
            try:
                if provider == "local":
                    logger.debug("Dispatching request to local provider (%s)...", self.config.model.local_type)
                    reply = self._call_local(msg_list)
                else:
                    logger.debug("Dispatching request to cloud provider (%s)...", self.config.model.cloud_provider)
                    reply = self._call_cloud(msg_list)

                self.last_provider = provider
                logger.info("Successfully generated response using %s provider.", provider)
                return LLMResponse(reply, provider=provider)

            except Exception as err:
                logger.warning(
                    "Provider '%s' failed (%s). Attempting fallback if available.",
                    provider,
                    err,
                )
                last_error = err

        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")
