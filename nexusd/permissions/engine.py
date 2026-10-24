"""
Nexus AIOS Permission Engine (Phase 2).

Evaluates every AI-planned tool action against security policies before execution.
Enforces strict three-tier authorization:
  - 'allow'  : Silently permitted (safe, read-only actions).
  - 'confirm': Requires explicit user approval before execution.
  - 'deny'   : Strictly prohibited (dangerous actions, root escapes, disk formats).
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any
import yaml

logger = logging.getLogger("nexusd.permissions")

# Patterns strictly blocked regardless of rule definitions
DANGEROUS_PATH_PATTERNS = [
    re.compile(r"(^|[/\\])\.\.([/\\]|$)"),            # Directory traversal (..)
    re.compile(r"^/etc/(shadow|gshadow|sudoers)", re.I), # Sensitive auth files
    re.compile(r"^/dev/(sd[a-z]|nvme[0-9]|null|zero)", re.I), # Block devices
    re.compile(r"^/boot", re.I),                     # Bootloader/kernel files
    re.compile(r"^[a-zA-Z]:\\(windows|boot)", re.I),  # Windows system root
]

DANGEROUS_COMMAND_KEYWORDS = {
    "mkfs", "fdisk", "format", "dd", "rm -rf /", ":(){ :|:& };:", "shred"
}

DEFAULT_POLICY_RULES: dict[str, str] = {
    "files.read": "allow",
    "files.list": "allow",
    "files.search": "allow",
    "files.zip": "allow",
    "files.write": "confirm",
    "files.move": "confirm",
    "files.delete": "confirm",
    "apps.list": "allow",
    "apps.launch": "confirm",
    "apps.close": "confirm",
    "network.connectivity": "allow",
    "network.ip_info": "allow",
    "network.notification": "allow",
    "network.download": "confirm",
    "packages.check": "allow",
    "packages.install": "confirm",
    "packages.update": "confirm",
    "system.format": "deny",
    "system.raw_shell": "deny",
    "system.poweroff": "confirm",
    "system.reboot": "confirm",
}


class PermissionEngine:
    """Evaluates planned tool actions against system security policies."""

    def __init__(self, policy_path: str | Path | None = None) -> None:
        self.policy_path = self._resolve_policy_path(policy_path)
        self.default_level: str = "confirm"
        self.rules: dict[str, str] = dict(DEFAULT_POLICY_RULES)
        self.reload_policy()

    def _resolve_policy_path(self, path: str | Path | None) -> Path:
        """Resolve policy file path from param, env, or default repo config."""
        if path:
            return Path(path)
        env_path = os.getenv("NEXUS_POLICY_PATH")
        if env_path:
            return Path(env_path)
        repo_config = Path(__file__).resolve().parent.parent.parent / "config" / "policy.yaml"
        return repo_config

    def reload_policy(self) -> None:
        """Load or reload rules from policy.yaml."""
        if self.policy_path.is_file():
            try:
                with open(self.policy_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        self.default_level = data.get("default", "confirm").lower()
                        custom_rules = data.get("rules", {})
                        if isinstance(custom_rules, dict):
                            # First apply wildcard rules so they update default rules in the same domain
                            for action, level in custom_rules.items():
                                if isinstance(level, str) and level.lower() in ("allow", "confirm", "deny"):
                                    clean_lvl = level.lower()
                                    if action.strip().endswith(".*"):
                                        prefix = action.strip()[:-2]
                                        for rk in list(self.rules.keys()):
                                            if rk.startswith(f"{prefix}."):
                                                self.rules[rk] = clean_lvl
                                    self.rules[action.strip()] = clean_lvl
                            # Second pass to ensure exact rules override wildcards
                            for action, level in custom_rules.items():
                                if isinstance(level, str) and level.lower() in ("allow", "confirm", "deny"):
                                    self.rules[action.strip()] = level.lower()
                logger.debug("Loaded %d policy rules from %s", len(self.rules), self.policy_path)
            except Exception as err:
                logger.warning("Failed to parse policy file %s (%s). Using fallback defaults.", self.policy_path, err)

    def _check_parameter_safety(self, params: dict[str, Any]) -> str | None:
        """
        Scan tool parameters for malicious paths, traversal, or dangerous commands.

        Returns:
            str reason if unsafe, or None if parameters pass safety checks.
        """
        for key, val in params.items():
            str_val = str(val).strip()

            # Path checks
            if "path" in key.lower() or "file" in key.lower() or "dir" in key.lower() or "src" in key.lower() or "dst" in key.lower():
                for pattern in DANGEROUS_PATH_PATTERNS:
                    if pattern.search(str_val):
                        return f"Parameter '{key}' violates path security boundary: {str_val}"

            # Command checks
            for keyword in DANGEROUS_COMMAND_KEYWORDS:
                if keyword in str_val.lower():
                    return f"Parameter '{key}' contains prohibited destructive keyword: {keyword}"

        return None

    def check(self, action: str, params: dict[str, Any] | None = None) -> str:
        """
        Check authorization level for an action.

        Args:
            action: Action identifier (e.g. 'files.read', 'packages.install').
            params: Dictionary of parameters passed to the tool.

        Returns:
            'allow' | 'confirm' | 'deny'
        """
        action = action.strip()
        params = params or {}

        # 1. Parameter safety scan - always deny dangerous patterns immediately
        safety_violation = self._check_parameter_safety(params)
        if safety_violation:
            logger.warning("Action '%s' DENIED by security guard: %s", action, safety_violation)
            return "deny"

        # 2. Match exact rule
        if action in self.rules:
            level = self.rules[action]
            logger.debug("Permission rule matched for '%s': %s", action, level)
            return level

        # 3. Wildcard prefix match (e.g. 'files.*')
        prefix = action.split(".", 1)[0] + ".*"
        if prefix in self.rules:
            level = self.rules[prefix]
            logger.debug("Permission wildcard matched for '%s' (%s): %s", action, prefix, level)
            return level

        # 4. Fallback default level
        logger.debug("No specific rule for '%s'. Applying default: %s", action, self.default_level)
        return self.default_level

    def is_allowed(self, action: str, params: dict[str, Any] | None = None) -> bool:
        """Convenience method returning True if action is 'allow'."""
        return self.check(action, params) == "allow"

    def set_rule(self, action: str, level: str) -> None:
        """Dynamically update an authorization rule."""
        level = level.lower()
        if level not in ("allow", "confirm", "deny"):
            raise ValueError(f"Invalid permission level: {level}. Expected 'allow', 'confirm', or 'deny'.")
        self.rules[action] = level

    def get_policy(self) -> dict[str, Any]:
        """Return full active policy configuration."""
        return {
            "default": self.default_level,
            "rules": dict(self.rules),
            "policy_path": str(self.policy_path),
        }
