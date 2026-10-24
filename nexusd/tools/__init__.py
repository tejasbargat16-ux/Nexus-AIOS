"""
Nexus AIOS Tools Layer (Phase 2).

Central registry and dispatcher for all AI-executable tools across:
files, apps, network, and packages.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from nexusd.tools import apps, files, network, packages

logger = logging.getLogger("nexusd.tools")

# Master registry associating action names with implementation functions
TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "files.read": {
        "func": files.read_file,
        "description": "Read contents of a file safely with byte bounds.",
        "parameters": {"path": "str", "max_bytes": "int (optional)"},
    },
    "files.write": {
        "func": files.write_file,
        "description": "Write text content to a file, creating parent directories.",
        "parameters": {"path": "str", "content": "str", "append": "bool (optional)"},
    },
    "files.list": {
        "func": files.list_dir,
        "description": "List files and directories within a given path.",
        "parameters": {"path": "str (optional)", "max_items": "int (optional)"},
    },
    "files.search": {
        "func": files.search_files,
        "description": "Search recursively for files matching a pattern.",
        "parameters": {"pattern": "str", "root_path": "str (optional)", "max_results": "int (optional)"},
    },
    "files.move": {
        "func": files.move_file,
        "description": "Move or rename a file or directory.",
        "parameters": {"src": "str", "dst": "str"},
    },
    "files.delete": {
        "func": files.delete_file,
        "description": "Delete a file or directory.",
        "parameters": {"path": "str"},
    },
    "files.zip": {
        "func": files.zip_directory,
        "description": "Create a zip archive of a directory.",
        "parameters": {"src": "str", "out_zip": "str"},
    },
    "apps.launch": {
        "func": apps.launch_app,
        "description": "Launch an application or binary safely.",
        "parameters": {"app_name": "str", "args": "list[str] (optional)"},
    },
    "apps.close": {
        "func": apps.close_app,
        "description": "Close a running application by process name or PID.",
        "parameters": {"app_name": "str (optional)", "pid": "int (optional)"},
    },
    "apps.list": {
        "func": apps.list_running_apps,
        "description": "Query active system processes/apps.",
        "parameters": {"limit": "int (optional)"},
    },
    "network.connectivity": {
        "func": network.check_connectivity,
        "description": "Check internet connectivity and handshake latency.",
        "parameters": {"host": "str (optional)", "port": "int (optional)", "timeout": "float (optional)"},
    },
    "network.ip_info": {
        "func": network.get_ip_info,
        "description": "Retrieve local IP address and hostname.",
        "parameters": {},
    },
    "network.download": {
        "func": network.download_file,
        "description": "Stream and download a remote file with size caps.",
        "parameters": {"url": "str", "dest_path": "str", "max_bytes": "int (optional)"},
    },
    "network.notification": {
        "func": network.send_notification,
        "description": "Send a desktop or Termux notification.",
        "parameters": {"title": "str", "message": "str"},
    },
    "packages.check": {
        "func": packages.check_package,
        "description": "Check if a package or binary is installed on the system.",
        "parameters": {"name": "str"},
    },
    "packages.install": {
        "func": packages.install_package,
        "description": "Install a system package via apt/pkg/pacman/dnf.",
        "parameters": {"name": "str"},
    },
    "packages.update": {
        "func": packages.update_system,
        "description": "Update package manager repositories.",
        "parameters": {},
    },
}


def execute_tool(action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Execute a registered tool by its action key with provided arguments.

    Args:
        action: Tool action key (e.g. 'files.read').
        params: Arguments dictionary to pass to the tool function.

    Returns:
        dict: Structured execution result.
    """
    clean_action = action.strip()
    tool_entry = TOOL_REGISTRY.get(clean_action)

    if not tool_entry:
        return {
            "error": f"Unknown tool action: '{clean_action}'",
            "status": "error",
            "available_tools": list(TOOL_REGISTRY.keys()),
        }

    func: Callable[..., dict[str, Any]] = tool_entry["func"]
    call_params = params or {}

    try:
        logger.info("Executing tool '%s' with parameters %s", clean_action, call_params)
        result = func(**call_params)
        return result
    except TypeError as err:
        return {
            "error": f"Invalid arguments for tool '{clean_action}': {err}",
            "status": "error",
        }
    except Exception as err:
        logger.error("Tool execution failed '%s': %s", clean_action, err)
        return {
            "error": f"Tool execution failed: {err}",
            "status": "error",
        }


def list_tools() -> list[dict[str, Any]]:
    """Return catalog of all registered tools and their signatures."""
    catalog = []
    for action, meta in TOOL_REGISTRY.items():
        catalog.append({
            "action": action,
            "description": meta["description"],
            "parameters": meta["parameters"],
        })
    return catalog
