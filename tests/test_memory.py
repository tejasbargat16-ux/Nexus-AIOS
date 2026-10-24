"""Unit tests for Nexus AIOS Memory Store."""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexusd.memory.store import MemoryStore


@pytest.fixture
def memory_store(tmp_path):
    db_file = tmp_path / "test_nexus.db"
    return MemoryStore(db_path=db_file)


def test_facts_crud(memory_store):
    # Save facts
    memory_store.save_fact("user.editor", "nano", category="preference")
    memory_store.save_fact("system.theme", {"mode": "dark"}, category="ui")

    # Retrieve facts
    assert memory_store.get_fact("user.editor") == "nano"
    assert memory_store.get_fact("system.theme") == {"mode": "dark"}
    assert memory_store.get_fact("nonexistent") is None

    # Update fact
    memory_store.save_fact("user.editor", "vim", category="preference")
    assert memory_store.get_fact("user.editor") == "vim"

    # List facts
    all_facts = memory_store.list_facts()
    assert len(all_facts) == 2

    pref_facts = memory_store.list_facts(category="preference")
    assert len(pref_facts) == 1
    assert pref_facts[0]["key"] == "user.editor"

    # Delete fact
    assert memory_store.delete_fact("user.editor") is True
    assert memory_store.get_fact("user.editor") is None
    assert memory_store.delete_fact("user.editor") is False


def test_history_logging(memory_store):
    rec_id = memory_store.record_history(
        intent="check disk space",
        plan="Run df -h",
        tool_calls=[{"action": "system.df"}],
        result="Success: 20GB free",
        provider="local",
    )
    assert rec_id == 1

    history = memory_store.get_history(limit=10)
    assert len(history) == 1
    assert history[0]["intent"] == "check disk space"
    assert history[0]["provider"] == "local"
    assert history[0]["tool_calls"] == [{"action": "system.df"}]


def test_memory_save_and_semantic_search(memory_store):
    memory_store.save_fact("wifi.ssid", "NexusNet", category="network")
    memory_store.save_memory("Remember to backup files on Friday evening", category="reminder")
    memory_store.save_memory("Termux package installation uses pkg command", category="docs")

    # Search for wifi
    results = memory_store.search("wifi network")
    assert len(results) > 0
    assert results[0]["key"] == "wifi.ssid"

    # Search for backup reminder
    results2 = memory_store.search("backup files")
    assert len(results2) > 0
    assert "backup" in results2[0]["content"].lower()

    # Search non-matching term
    assert len(memory_store.search("completely_unrelated_nonsense_xyz")) == 0
