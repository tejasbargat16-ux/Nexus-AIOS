"""
Nexus AIOS Apps Tool (Phase 2).

Provides application lifecycle management: launching, closing, and listing apps.
Platform-aware: handles Android Termux (am / termux-open-url), Linux desktop (xdg-open / systemd),
and Windows/cross-platform fallback with strict subprocess validation (shell=False).
"""

from __future__ import annotations

import os
import platform
import shutil
import signal
import subprocess
from typing import Any

# Prohibited application names that must never be launched directly
BLOCKED_EXECUTABLES = {
    "rm", "mkfs", "dd", "fdisk", "shutdown", "poweroff", "reboot", "bash", "sh"
}


def _is_termux() -> bool:
    """Check if running in Android Termux environment."""
    return "com.termux" in os.environ.get("PREFIX", "") or os.path.exists("/data/data/com.termux")


def launch_app(app_name: str, args: list[str] | None = None) -> dict[str, Any]:
    """
    Safely launch an application or executable.

    Args:
        app_name: Binary or app name (e.g. 'htop', 'nano', 'firefox', 'calc').
        args: Optional list of command line arguments.

    Returns:
        dict: {'status': 'success'|'error', 'app': str, 'pid': int|None}
    """
    clean_app = app_name.strip()
    if not clean_app:
        return {"error": "Empty app_name specified", "status": "error"}

    base_name = os.path.basename(clean_app).lower()
    if base_name in BLOCKED_EXECUTABLES:
        return {"error": f"Launching '{base_name}' is prohibited by safety policy", "status": "error"}

    cmd_args = [clean_app] + ([str(a) for a in args] if args else [])

    try:
        # 1. Android Termux dispatch
        if _is_termux():
            # If it's a URL or file, try termux-open
            if clean_app.startswith(("http://", "https://", "file://")) and shutil.which("termux-open"):
                proc = subprocess.Popen(["termux-open", clean_app])
                return {"status": "success", "app": clean_app, "pid": proc.pid, "platform": "termux"}
            elif shutil.which("am"):
                # Android activity manager
                proc = subprocess.Popen(["am", "start", "-a", "android.intent.action.VIEW", "-d", clean_app])
                return {"status": "success", "app": clean_app, "pid": proc.pid, "platform": "android-am"}

        # 2. Check if binary is in PATH
        resolved = shutil.which(clean_app)
        exec_path = resolved or clean_app

        # 3. Spawn process without shell to prevent injection
        proc = subprocess.Popen(
            [exec_path] + (cmd_args[1:] if resolved else []),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
        return {
            "status": "success",
            "app": clean_app,
            "pid": proc.pid,
            "platform": platform.system().lower(),
        }
    except FileNotFoundError:
        return {"error": f"Application '{clean_app}' not found on system", "status": "error"}
    except Exception as err:
        return {"error": f"Failed to launch app '{clean_app}': {err}", "status": "error"}


def close_app(app_name: str | None = None, pid: int | None = None) -> dict[str, Any]:
    """
    Close or terminate a running application by PID or process name.

    Args:
        app_name: Process name to terminate (e.g. 'nano', 'python3').
        pid: Explicit process ID to terminate.

    Returns:
        dict: {'status': 'success'|'error', 'target': str|int}
    """
    if pid is not None:
        try:
            os.kill(pid, signal.SIGTERM)
            return {"status": "success", "pid": pid, "action": "terminated"}
        except ProcessLookupError:
            return {"error": f"No process found with PID {pid}", "status": "error"}
        except Exception as err:
            return {"error": f"Failed to terminate PID {pid}: {err}", "status": "error"}

    if app_name:
        clean_name = app_name.strip()
        system = platform.system().lower()
        try:
            if system == "windows":
                # Use taskkill safely on Windows
                res = subprocess.run(["taskkill", "/F", "/IM", clean_name], capture_output=True, text=True)
                if res.returncode == 0:
                    return {"status": "success", "app": clean_name, "action": "taskkill"}
                return {"error": f"Failed to close '{clean_name}': {res.stderr.strip()}", "status": "error"}
            else:
                # Use pkill on Linux / Termux
                if shutil.which("pkill"):
                    res = subprocess.run(["pkill", "-f", clean_name], capture_output=True)
                    if res.returncode == 0:
                        return {"status": "success", "app": clean_name, "action": "pkill"}
                    return {"error": f"No active process matching '{clean_name}'", "status": "error"}
                return {"error": "pkill utility not available", "status": "error"}
        except Exception as err:
            return {"error": f"Failed to close app '{clean_name}': {err}", "status": "error"}

    return {"error": "Must provide either 'pid' or 'app_name'", "status": "error"}


def list_running_apps(limit: int = 50) -> dict[str, Any]:
    """
    Query active system processes/apps.

    Returns:
        dict: {'status': 'success', 'processes': list, 'count': int}
    """
    system = platform.system().lower()
    processes: list[dict[str, Any]] = []

    try:
        if system == "windows":
            # Query tasklist safely
            res = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                for line in res.stdout.strip().splitlines()[:limit]:
                    parts = [p.strip('"\r') for p in line.split('","')]
                    if len(parts) >= 2:
                        try:
                            processes.append({"name": parts[0], "pid": int(parts[1])})
                        except ValueError:
                            continue
        else:
            # Linux / Termux ps
            res = subprocess.run(["ps", "-eo", "pid,comm", "--sort=-%mem"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                lines = res.stdout.strip().splitlines()[1:limit + 1]
                for line in lines:
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2:
                        try:
                            processes.append({"pid": int(parts[0]), "name": parts[1]})
                        except ValueError:
                            continue

        return {
            "status": "success",
            "processes": processes,
            "count": len(processes),
        }
    except Exception as err:
        return {"error": f"Failed to query running processes: {err}", "status": "error"}
