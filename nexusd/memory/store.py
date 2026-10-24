"""
Memory Store (Phase 2 Placeholder).

TODO (Phase 2):
- SQLite database persistence in nexusd/memory/nexus.db.
- Schemas for user preferences, facts, conversation history, and tool outputs.
- Local embeddings and cosine similarity search for semantic recall.
- Optional multi-device sync in Phase 5.
"""

from typing import Any


class MemoryStore:
    """Manages SQLite persistent memory and vector embeddings."""

    def __init__(self, db_path: str = "nexusd/memory/nexus.db") -> None:
        self.db_path = db_path

    def save_fact(self, key: str, value: Any) -> None:
        """Save user preference or system fact."""
        raise NotImplementedError("Memory store will be implemented in Phase 2.")

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Semantic search over stored memory."""
        raise NotImplementedError("Memory store will be implemented in Phase 2.")
