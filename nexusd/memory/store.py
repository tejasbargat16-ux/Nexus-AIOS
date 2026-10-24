"""
Nexus AIOS Memory Store (Phase 2).

Provides SQLite persistent memory storage for user preferences, facts,
conversation/intent history, and local semantic search without heavy dependencies.
Designed for high efficiency on low-resource ARM64 and Linux environments.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("nexusd.memory")


class MemoryStore:
    """Manages SQLite persistent memory, history logging, and lightweight semantic search."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path:
            self.db_path = Path(db_path)
        else:
            base_dir = Path(__file__).resolve().parent
            self.db_path = base_dir / "nexus.db"

        self._lock = threading.Lock()
        self._ensure_db_dir()
        self._init_db()

    def _ensure_db_dir(self) -> None:
        """Ensure parent directory for database exists."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def _get_connection(self) -> sqlite3.Connection:
        """Create and return a new SQLite connection with dict row factory."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize required database schemas."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Facts table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS facts (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        category TEXT DEFAULT 'general',
                        updated_at TEXT NOT NULL
                    )
                """)
                # Conversation / Intent history
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        intent TEXT NOT NULL,
                        plan TEXT,
                        tool_calls TEXT,
                        result TEXT,
                        provider TEXT,
                        created_at TEXT NOT NULL
                    )
                """)
                # General long-term memories / documents
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        content TEXT NOT NULL,
                        category TEXT DEFAULT 'general',
                        metadata TEXT,
                        created_at TEXT NOT NULL
                    )
                """)
                conn.commit()

    # =========================================================================
    # Facts API (Key-Value Preferences and Context)
    # =========================================================================

    def save_fact(self, key: str, value: Any, category: str = "general") -> None:
        """
        Save or update a fact or user preference.

        Args:
            key: Unique fact identifier (e.g. 'user.preferred_editor').
            value: Fact value (will be JSON serialized).
            category: Semantic grouping (e.g. 'preference', 'hardware', 'profile').
        """
        now = datetime.now(timezone.utc).isoformat()
        serialized = json.dumps(value) if not isinstance(value, str) else value

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO facts (key, value, category, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value=excluded.value,
                        category=excluded.category,
                        updated_at=excluded.updated_at
                    """,
                    (key.strip(), serialized, category.strip(), now),
                )
                conn.commit()

    def get_fact(self, key: str) -> Any | None:
        """Retrieve a specific fact by key."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM facts WHERE key = ?", (key.strip(),))
                row = cursor.fetchone()
                if not row:
                    return None
                val = row["value"]
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return val

    def list_facts(self, category: str | None = None) -> list[dict[str, Any]]:
        """List all stored facts, optionally filtered by category."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if category:
                    cursor.execute("SELECT * FROM facts WHERE category = ? ORDER BY key", (category.strip(),))
                else:
                    cursor.execute("SELECT * FROM facts ORDER BY category, key")
                rows = cursor.fetchall()
                results = []
                for r in rows:
                    raw_val = r["value"]
                    try:
                        parsed_val = json.loads(raw_val)
                    except (json.JSONDecodeError, TypeError):
                        parsed_val = raw_val
                    results.append({
                        "key": r["key"],
                        "value": parsed_val,
                        "category": r["category"],
                        "updated_at": r["updated_at"],
                    })
                return results

    def delete_fact(self, key: str) -> bool:
        """Delete a fact by key."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM facts WHERE key = ?", (key.strip(),))
                deleted = cursor.rowcount > 0
                conn.commit()
                return deleted

    # =========================================================================
    # Intent & Execution History
    # =========================================================================

    def record_history(
        self,
        intent: str,
        plan: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        result: str | None = None,
        provider: str | None = None,
    ) -> int:
        """Record an intent request and its execution details."""
        now = datetime.now(timezone.utc).isoformat()
        tools_str = json.dumps(tool_calls) if tool_calls else None

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO history (intent, plan, tool_calls, result, provider, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (intent.strip(), plan, tools_str, result, provider, now),
                )
                conn.commit()
                return cursor.lastrowid

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Retrieve recent intent history ordered newest first."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM history ORDER BY id DESC LIMIT ?",
                    (max(1, limit),),
                )
                rows = cursor.fetchall()
                results = []
                for r in rows:
                    tool_calls = None
                    if r["tool_calls"]:
                        try:
                            tool_calls = json.loads(r["tool_calls"])
                        except json.JSONDecodeError:
                            tool_calls = r["tool_calls"]

                    results.append({
                        "id": r["id"],
                        "intent": r["intent"],
                        "plan": r["plan"],
                        "tool_calls": tool_calls,
                        "result": r["result"],
                        "provider": r["provider"],
                        "created_at": r["created_at"],
                    })
                return results

    # =========================================================================
    # Memories & Semantic Recall
    # =========================================================================

    def save_memory(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        category: str = "general",
    ) -> int:
        """Save an arbitrary textual note or semantic memory item."""
        now = datetime.now(timezone.utc).isoformat()
        meta_str = json.dumps(metadata) if metadata else None

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO memories (content, category, metadata, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (content.strip(), category.strip(), meta_str, now),
                )
                conn.commit()
                return cursor.lastrowid

    def _tokenize(self, text: str) -> set[str]:
        """Simple tokenizer extracting lowercase alphanumeric terms."""
        return set(re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", text.lower()))

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        Lightweight semantic and keyword relevance search over facts and memories.
        Calculates Jaccard/overlap relevance scores without heavyweight dependencies.

        Args:
            query: Natural language query string.
            limit: Maximum items to return.

        Returns:
            list[dict]: Ranked list of matching memory and fact items with score.
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        candidates: list[dict[str, Any]] = []

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Search facts
                cursor.execute("SELECT key, value, category, updated_at FROM facts")
                for r in cursor.fetchall():
                    full_text = f"{r['key']} {r['value']} {r['category']}"
                    doc_tokens = self._tokenize(full_text)
                    intersection = query_tokens.intersection(doc_tokens)
                    if intersection:
                        score = len(intersection) / math.sqrt(len(query_tokens) * len(doc_tokens))
                        candidates.append({
                            "type": "fact",
                            "key": r["key"],
                            "content": r["value"],
                            "category": r["category"],
                            "score": round(score, 3),
                        })

                # Search memories
                cursor.execute("SELECT id, content, category, metadata, created_at FROM memories")
                for r in cursor.fetchall():
                    full_text = f"{r['content']} {r['category']} {r['metadata'] or ''}"
                    doc_tokens = self._tokenize(full_text)
                    intersection = query_tokens.intersection(doc_tokens)
                    if intersection:
                        score = len(intersection) / math.sqrt(len(query_tokens) * len(doc_tokens))
                        candidates.append({
                            "type": "memory",
                            "id": r["id"],
                            "content": r["content"],
                            "category": r["category"],
                            "score": round(score, 3),
                        })

        # Sort descending by score
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:limit]
