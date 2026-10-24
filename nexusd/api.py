"""
Nexus AIOS HTTP API (Phase 1).

Serves local REST endpoints for intent processing, daemon status, and audit inspection.
Strictly decoupled from tool execution for Phase 1 safety.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from flask import Flask, jsonify, request

from nexusd.audit import audit_logger
from nexusd.config import NexusConfig, load_config
from nexusd.router import LLMRouter

logger = logging.getLogger("nexusd.api")
DAEMON_START_TIME = time.time()


def create_app(
    config: NexusConfig | None = None,
    router: LLMRouter | None = None,
) -> Flask:
    """
    Application factory initializing Flask API with configuration and router.

    Args:
        config: System configuration object (loads default if None).
        router: LLMRouter instance (initializes default if None).

    Returns:
        Flask: Configured application instance.
    """
    app = Flask("nexusd")
    cfg = config or load_config()
    llm_router = router or LLMRouter(cfg)

    @app.route("/status", methods=["GET"])
    def get_status() -> Any:
        """Return daemon health, uptime, and configured LLM providers."""
        uptime = round(time.time() - DAEMON_START_TIME, 1)
        return jsonify({
            "status": "ok",
            "service": "nexusd",
            "version": "0.1.0-phase1",
            "uptime_seconds": uptime,
            "providers": {
                "preferred": cfg.router.prefer,
                "local": {
                    "type": cfg.model.local_type,
                    "url": cfg.model.local_url,
                    "model": cfg.model.local_model,
                },
                "cloud": {
                    "provider": cfg.model.cloud_provider,
                    "model": cfg.model.cloud_model,
                    "configured": bool(cfg.model.cloud_api_key),
                },
            },
        }), 200

    @app.route("/intent", methods=["POST"])
    def process_intent() -> Any:
        """
        Process natural language user intent via LLM router.

        Phase 1 Safety:
            - Does NOT execute shell or system commands.
            - Strictly generates textual plan / natural-language response.

        Request JSON:
            {"text": "user intent string", "prefer": "local|cloud" (optional)}

        Returns:
            {"reply": str, "provider": str, "duration_ms": float}
        """
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text", "")).strip()

        if not text:
            return jsonify({"error": "Missing or empty 'text' field in request body"}), 400

        prefer_override = payload.get("prefer")
        start_t = time.perf_counter()

        try:
            # =================================================================
            # SAFETY (Phase 1): LLM only outputs text, no shell execution.
            #
            # TODO (Phase 2 Permission & Tool Execution Hook):
            # 1. Parse structured tool invocation requests from LLM output.
            # 2. Call permission_engine.check(tool_name, params):
            #       - 'allow': proceed with execution silently.
            #       - 'confirm': request interactive user authorization.
            #       - 'deny': abort immediately, log security alert.
            # 3. Execute approved tool from nexusd/tools/ (files, apps, packages, network).
            # 4. Save interactions and outcomes into nexusd/memory/store.py.
            # =================================================================

            response = llm_router.generate(text, prefer=prefer_override)
            provider = getattr(response, "provider", llm_router.last_provider)
            duration_ms = round((time.perf_counter() - start_t) * 1000, 2)

            audit_logger.log(
                action="intent.processed",
                details={"intent": text, "reply_length": len(str(response)), "duration_ms": duration_ms},
                status="ok",
                provider=provider,
            )

            return jsonify({
                "reply": str(response),
                "provider": provider,
                "duration_ms": duration_ms,
            }), 200

        except Exception as err:
            duration_ms = round((time.perf_counter() - start_t) * 1000, 2)
            logger.error("Intent processing failed: %s", err)
            audit_logger.log(
                action="intent.failed",
                details={"intent": text, "error": str(err), "duration_ms": duration_ms},
                status="error",
                provider=prefer_override or cfg.router.prefer,
            )
            return jsonify({"error": f"Failed to process intent: {err}"}), 502

    @app.route("/audit", methods=["GET"])
    def get_audit() -> Any:
        """Retrieve recent audit events."""
        limit_arg = request.args.get("limit", "50")
        try:
            limit = max(1, min(int(limit_arg), 200))
        except ValueError:
            limit = 50

        entries = audit_logger.get_recent(limit=limit)
        return jsonify({"entries": entries, "count": len(entries)}), 200

    return app
