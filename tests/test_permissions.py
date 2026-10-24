"""Unit tests for Nexus AIOS Permission Engine."""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexusd.permissions.engine import PermissionEngine


@pytest.fixture
def engine(tmp_path):
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text("""
default: confirm
rules:
  files.read: allow
  files.delete: confirm
  system.format: deny
  network.*: allow
""")
    return PermissionEngine(policy_path=policy_file)


def test_permission_exact_match(engine):
    assert engine.check("files.read") == "allow"
    assert engine.check("files.delete") == "confirm"
    assert engine.check("system.format") == "deny"


def test_permission_wildcard_match(engine):
    assert engine.check("network.connectivity") == "allow"
    assert engine.check("network.download") == "allow"


def test_permission_default_fallback(engine):
    assert engine.check("unregistered.custom_action") == "confirm"


def test_permission_directory_traversal_blocked(engine):
    # Attempting to read a path with '..' should be automatically denied
    result = engine.check("files.read", params={"path": "../secret.txt"})
    assert result == "deny"


def test_permission_sensitive_system_path_blocked(engine):
    # Attempting to target /etc/shadow or /boot should be denied
    assert engine.check("files.read", params={"path": "/etc/shadow"}) == "deny"
    assert engine.check("files.read", params={"path": "/boot/vmlinuz"}) == "deny"


def test_permission_destructive_keyword_blocked(engine):
    assert engine.check("files.delete", params={"cmd": "mkfs.ext4 /dev/sda1"}) == "deny"
    assert engine.check("files.delete", params={"target": "rm -rf /"}) == "deny"


def test_permission_dynamic_update(engine):
    assert engine.check("files.delete") == "confirm"
    engine.set_rule("files.delete", "allow")
    assert engine.check("files.delete") == "allow"
    assert engine.is_allowed("files.delete") is True

    with pytest.raises(ValueError):
        engine.set_rule("files.delete", "invalid_level")


def test_permission_get_policy(engine):
    policy = engine.get_policy()
    assert policy["default"] == "confirm"
    assert "files.read" in policy["rules"]
