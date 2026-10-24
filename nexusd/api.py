"""
Nexus AIOS HTTP API (Phase 2).

Serves local REST endpoints for intent processing, tool execution, permission checking,
memory management, and audit inspection.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any
from flask import Flask, jsonify, request

from nexusd.audit import audit_logger
from nexusd.config import NexusConfig, load_config
from nexusd.memory.store import MemoryStore
from nexusd.permissions.engine import PermissionEngine
from nexusd.router import LLMRouter
from nexusd.tools import TOOL_REGISTRY, execute_tool, list_tools

logger = logging.getLogger("nexusd.api")
DAEMON_START_TIME = time.time()


def _extract_tool_call(llm_output: str) -> dict[str, Any] | None:
    """
    Attempt to extract structured tool call JSON from LLM text.
    Looks for JSON blocks or patterns like {"action": "...", "params": {...}} or {"tool": "..."}.
    """
    cleaned = llm_output.strip()

    # Direct JSON detection
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            action = data.get("action") or data.get("tool")
            if action and action in TOOL_REGISTRY:
                return {"action": action, "params": data.get("params", {})}
    except (json.JSONDecodeError, TypeError):
        pass

    # Markdown codeblock extraction
    json_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    for block in json_blocks:
        try:
            data = json.loads(block)
            if isinstance(data, dict):
                action = data.get("action") or data.get("tool")
                if action and action in TOOL_REGISTRY:
                    return {"action": action, "params": data.get("params", {})}
        except (json.JSONDecodeError, TypeError):
            continue

    return None


def create_app(
    config: NexusConfig | None = None,
    router: LLMRouter | None = None,
    permissions: PermissionEngine | None = None,
    memory: MemoryStore | None = None,
) -> Flask:
    """
    Application factory initializing Flask API with configuration, router,
    permission engine, and memory store.

    Args:
        config: System configuration object.
        router: LLMRouter instance.
        permissions: PermissionEngine instance.
        memory: MemoryStore instance.

    Returns:
        Flask: Configured application instance.
    """
    app = Flask("nexusd")
    cfg = config or load_config()
    llm_router = router or LLMRouter(cfg)
    perm_engine = permissions or PermissionEngine()
    mem_store = memory or MemoryStore()

    @app.route("/status", methods=["GET"])
    def get_status() -> Any:
        """Return daemon health, uptime, providers, and component status."""
        uptime = round(time.time() - DAEMON_START_TIME, 1)
        facts_count = len(mem_store.list_facts())
        return jsonify({
            "status": "ok",
            "service": "nexusd",
            "version": "0.2.0-phase2",
            "uptime_seconds": uptime,
            "components": {
                "tools_registered": len(TOOL_REGISTRY),
                "stored_facts": facts_count,
                "permission_rules": len(perm_engine.rules),
            },
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

    # =========================================================================
    # Tools & Permission Endpoints
    # =========================================================================

    @app.route("/tools", methods=["GET"])
    def get_tools() -> Any:
        """List all available tools and parameters."""
        tools = list_tools()
        return jsonify({"tools": tools, "count": len(tools)}), 200

    @app.route("/permissions", methods=["GET"])
    def get_permissions() -> Any:
        """Return current permission policy configuration."""
        return jsonify(perm_engine.get_policy()), 200

    @app.route("/permissions/check", methods=["POST"])
    def check_permission() -> Any:
        """Check authorization status for an action without executing."""
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action", "")).strip()
        params = payload.get("params", {})

        if not action:
            return jsonify({"error": "Missing 'action' field"}), 400

        level = perm_engine.check(action, params)
        return jsonify({
            "action": action,
            "level": level,
            "status": "ok",
        }), 200

    @app.route("/tool/execute", methods=["POST"])
    def run_tool() -> Any:
        """
        Directly execute a tool through permission policy verification.

        Payload:
            {
                "action": "files.read",
                "params": {"path": "..."},
                "confirmed": true|false
            }
        """
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action", "")).strip()
        params = payload.get("params", {}) or {}
        confirmed = bool(payload.get("confirmed", False))

        if not action:
            return jsonify({"error": "Missing 'action' field"}), 400

        # Permission evaluation
        perm_level = perm_engine.check(action, params)

        if perm_level == "deny":
            audit_logger.log(
                action="tool.denied",
                details={"tool": action, "params": params, "reason": "Policy violation"},
                status="denied",
            )
            return jsonify({
                "error": f"Action '{action}' is strictly prohibited by security policy",
                "action": action,
                "status": "denied",
            }), 403

        if perm_level == "confirm" and not confirmed:
            audit_logger.log(
                action="tool.confirmation_required",
                details={"tool": action, "params": params},
                status="pending_confirmation",
            )
            return jsonify({
                "status": "confirmation_required",
                "action": action,
                "params": params,
                "message": f"Action '{action}' requires user authorization to proceed",
            }), 200

        # Execute authorized tool
        start_t = time.perf_counter()
        result = execute_tool(action, params)
        duration_ms = round((time.perf_counter() - start_t) * 1000, 2)

        is_error = "error" in result
        status_tag = "error" if is_error else "ok"

        audit_logger.log(
            action=f"tool.executed.{action}",
            details={"params": params, "duration_ms": duration_ms, "status": status_tag},
            status=status_tag,
        )

        # Record in memory store
        mem_store.record_history(
            intent=f"Direct tool execution: {action}",
            tool_calls=[{"action": action, "params": params}],
            result=json.dumps(result),
        )

        return jsonify({
            "status": status_tag,
            "action": action,
            "result": result,
            "duration_ms": duration_ms,
        }), 200 if not is_error else 400

    # =========================================================================
    # Intent Processing (Integrated with Memory, Router, and Tools)
    # =========================================================================

    @app.route("/intent", methods=["POST"])
    def process_intent() -> Any:
        """
        Process natural language user intent via LLM router,
        with tool execution and persistent memory recording.
        """
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text", "")).strip()

        if not text:
            return jsonify({"error": "Missing or empty 'text' field in request body"}), 400

        prefer_override = payload.get("prefer")
        confirmed = bool(payload.get("confirmed", False))
        start_t = time.perf_counter()

        try:
            # Context enrichment: search relevant facts
            matched_facts = mem_store.search(text, limit=2)
            context_prefix = ""
            if matched_facts:
                context_prefix = f"[System Context: {json.dumps(matched_facts)}]\n"

            prompt_input = f"{context_prefix}{text}" if context_prefix else text

            # Generate plan / response via LLM Router
            response = llm_router.generate(prompt_input, prefer=prefer_override)
            provider = getattr(response, "provider", llm_router.last_provider)
            duration_ms = round((time.perf_counter() - start_t) * 1000, 2)
            reply_text = str(response)

            # Check if LLM emitted a structured tool call
            tool_call = _extract_tool_call(reply_text)
            tool_result = None

            if tool_call:
                action = tool_call["action"]
                params = tool_call.get("params", {})
                perm_level = perm_engine.check(action, params)

                if perm_level == "deny":
                    audit_logger.log(
                        action="tool.denied",
                        details={"tool": action, "params": params, "intent": text},
                        status="denied",
                    )
                    reply_text = f"Action '{action}' was blocked by security policy."
                elif perm_level == "confirm" and not confirmed:
                    audit_logger.log(
                        action="tool.confirmation_required",
                        details={"tool": action, "params": params, "intent": text},
                        status="pending_confirmation",
                    )
                    return jsonify({
                        "status": "confirmation_required",
                        "action": action,
                        "params": params,
                        "reply": f"Action '{action}' requires user confirmation before proceeding.",
                        "provider": provider,
                        "duration_ms": duration_ms,
                    }), 200
                else:
                    # Permitted or confirmed
                    tool_result = execute_tool(action, params)
                    audit_logger.log(
                        action=f"tool.executed.{action}",
                        details={"params": params, "intent": text},
                        status="ok",
                    )

            # Record event in audit log
            audit_logger.log(
                action="intent.processed",
                details={"intent": text, "reply_length": len(reply_text), "duration_ms": duration_ms},
                status="ok",
                provider=provider,
            )

            # Save in memory store history
            mem_store.record_history(
                intent=text,
                plan=reply_text,
                tool_calls=[tool_call] if tool_call else None,
                result=json.dumps(tool_result) if tool_result else None,
                provider=provider,
            )

            res_payload: dict[str, Any] = {
                "reply": reply_text,
                "provider": provider,
                "duration_ms": duration_ms,
            }
            if tool_result is not None:
                res_payload["tool_result"] = tool_result

            return jsonify(res_payload), 200

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

    # =========================================================================
    # Memory Management Endpoints
    # =========================================================================

    @app.route("/memory/facts", methods=["GET"])
    def get_facts() -> Any:
        """List stored system facts and preferences."""
        category = request.args.get("category")
        facts = mem_store.list_facts(category=category)
        return jsonify({"facts": facts, "count": len(facts)}), 200

    @app.route("/memory/facts", methods=["POST"])
    def save_fact() -> Any:
        """Store or update a fact/preference."""
        payload = request.get_json(silent=True) or {}
        key = str(payload.get("key", "")).strip()
        value = payload.get("value")
        category = str(payload.get("category", "general")).strip()

        if not key or value is None:
            return jsonify({"error": "Fields 'key' and 'value' are required"}), 400

        mem_store.save_fact(key, value, category=category)
        audit_logger.log("memory.fact_saved", {"key": key, "category": category}, status="ok")
        return jsonify({"status": "saved", "key": key}), 200

    @app.route("/memory/facts/<path:key>", methods=["DELETE"])
    def delete_fact(key: str) -> Any:
        """Delete a fact by key."""
        deleted = mem_store.delete_fact(key)
        if deleted:
            audit_logger.log("memory.fact_deleted", {"key": key}, status="ok")
            return jsonify({"status": "deleted", "key": key}), 200
        return jsonify({"error": f"Fact '{key}' not found"}), 404

    @app.route("/memory/search", methods=["GET"])
    def search_memory() -> Any:
        """Search memory facts and history by query term."""
        q = request.args.get("q", "").strip()
        limit_arg = request.args.get("limit", "5")
        try:
            limit = int(limit_arg)
        except ValueError:
            limit = 5

        if not q:
            return jsonify({"error": "Missing 'q' query parameter"}), 400

        results = mem_store.search(q, limit=limit)
        return jsonify({"query": q, "results": results, "count": len(results)}), 200

    @app.route("/memory/history", methods=["GET"])
    def get_memory_history() -> Any:
        """Retrieve recent intent execution history."""
        limit_arg = request.args.get("limit", "20")
        try:
            limit = int(limit_arg)
        except ValueError:
            limit = 20

        history = mem_store.get_history(limit=limit)
        return jsonify({"history": history, "count": len(history)}), 200

    # =========================================================================
    # Audit Inspection Endpoint
    # =========================================================================

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
