"""
Nexus AIOS Packages Tool (Phase 2).

Safely queries, checks, and installs system software packages via host package managers:
apt / dpkg on Debian/Ubuntu/proot, pkg on Termux, pacman, or dnf.
Enforces strict package name sanitization to eliminate shell injection risks.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

# Only valid alphanumeric package names with standard separators
PACKAGE_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.\+]+$")


def _validate_package_name(name: str) -> str:
    """Validate package name against injection attempts."""
    clean = name.strip()
    if not clean or not PACKAGE_NAME_REGEX.match(clean):
        raise ValueError(f"Invalid package identifier: '{name}'. Only alphanumeric characters and -_.+ are allowed.")
    return clean


def _detect_package_manager() -> tuple[str, list[str]]:
    """Detect available package management tool."""
    if shutil.which("pkg"):
        return "pkg", ["pkg"]
    if shutil.which("apt-get"):
        return "apt-get", ["apt-get"]
    if shutil.which("apt"):
        return "apt", ["apt"]
    if shutil.which("pacman"):
        return "pacman", ["pacman"]
    if shutil.which("dnf"):
        return "dnf", ["dnf"]
    return "none", []


def check_package(name: str) -> dict[str, Any]:
    """
    Check if a package or binary is installed on the system.

    Args:
        name: Name of the package or binary.

    Returns:
        dict: {'status': 'success'|'error', 'installed': bool, 'package': str}
    """
    try:
        pkg_name = _validate_package_name(name)
    except ValueError as err:
        return {"error": str(err), "status": "error"}

    # 1. Quick check if binary is in PATH
    binary_path = shutil.which(pkg_name)
    if binary_path:
        return {
            "status": "success",
            "package": pkg_name,
            "installed": True,
            "binary_path": binary_path,
        }

    # 2. Query dpkg if available (Debian / Termux / Ubuntu)
    if shutil.which("dpkg-query"):
        res = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", pkg_name],
            capture_output=True,
            text=True,
        )
        installed = "install ok installed" in res.stdout
        return {
            "status": "success",
            "package": pkg_name,
            "installed": installed,
            "manager": "dpkg",
        }

    return {
        "status": "success",
        "package": pkg_name,
        "installed": False,
        "details": "No binary in PATH and package manager query returned uninstalled",
    }


def install_package(name: str) -> dict[str, Any]:
    """
    Install a package using the system package manager.

    Args:
        name: Valid package name.

    Returns:
        dict: {'status': 'success'|'error', 'package': str, 'output': str}
    """
    try:
        pkg_name = _validate_package_name(name)
    except ValueError as err:
        return {"error": str(err), "status": "error"}

    mgr, cmd_base = _detect_package_manager()
    if mgr == "none":
        return {"error": "No supported package manager detected (apt/pkg/pacman/dnf)", "status": "error"}

    cmd: list[str] = []
    if mgr in ("apt-get", "apt"):
        cmd = cmd_base + ["install", "-y", pkg_name]
    elif mgr == "pkg":
        cmd = ["pkg", "install", "-y", pkg_name]
    elif mgr == "pacman":
        cmd = ["pacman", "-S", "--noconfirm", pkg_name]
    elif mgr == "dnf":
        cmd = ["dnf", "install", "-y", pkg_name]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode == 0:
            return {
                "status": "success",
                "package": pkg_name,
                "manager": mgr,
                "output": proc.stdout[-500:] if proc.stdout else "",
            }
        return {
            "error": f"Package manager returned non-zero exit code: {proc.returncode}",
            "stderr": proc.stderr[-500:] if proc.stderr else proc.stdout[-500:],
            "status": "error",
        }
    except Exception as err:
        return {"error": f"Failed to execute package installation: {err}", "status": "error"}


def update_system() -> dict[str, Any]:
    """
    Update package repository lists.

    Returns:
        dict: {'status': 'success'|'error', 'manager': str}
    """
    mgr, cmd_base = _detect_package_manager()
    if mgr == "none":
        return {"error": "No supported package manager detected", "status": "error"}

    cmd: list[str] = []
    if mgr in ("apt-get", "apt"):
        cmd = cmd_base + ["update"]
    elif mgr == "pkg":
        cmd = ["pkg", "update"]
    elif mgr == "pacman":
        cmd = ["pacman", "-Sy"]
    elif mgr == "dnf":
        cmd = ["dnf", "check-update"]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {
            "status": "success" if proc.returncode in (0, 100) else "error",
            "manager": mgr,
            "exit_code": proc.returncode,
        }
    except Exception as err:
        return {"error": f"Update failed: {err}", "status": "error"}
