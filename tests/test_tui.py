"""
Unit tests for Nexus AIOS Terminal User Interface (TUI) (Phase 3).
"""

from __future__ import annotations

import pytest
from rich.panel import Panel
from ui.tui.app import NexusTUI


def test_tui_initialization():
    """Test TUI client initialization with host and port."""
    tui = NexusTUI(host="127.0.0.1", port=8765)
    assert tui.host == "127.0.0.1"
    assert tui.port == 8765
    assert tui.base_url == "http://127.0.0.1:8765"
    assert tui.active_tab == "intent"


def test_tui_offline_check():
    """Test offline check on non-bound port."""
    # Port 59999 is unlikely to be listening
    tui = NexusTUI(host="127.0.0.1", port=59999)
    assert tui.is_daemon_online() is False
    assert tui.get_status() == {}


def test_tui_render_header():
    """Test header rendering with rich panel."""
    tui = NexusTUI()
    status_mock = {
        "uptime_seconds": 120,
        "version": "0.3.0-phase3",
        "providers": {"preferred": "local"},
        "components": {"security_score": 95, "security_level": "optimal"},
    }
    panel = tui.render_header(status_mock)
    assert isinstance(panel, Panel)


def test_tui_render_navigation():
    """Test navigation bar rendering."""
    tui = NexusTUI()
    nav_panel = tui.render_navigation()
    assert isinstance(nav_panel, Panel)
