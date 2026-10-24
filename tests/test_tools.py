"""Unit tests for Nexus AIOS Tools Layer."""

from __future__ import annotations

import sys
import unittest.mock as mock
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexusd.tools import TOOL_REGISTRY, execute_tool, list_tools
from nexusd.tools import apps, files, network, packages


# =============================================================================
# Files Tool Tests
# =============================================================================

def test_files_write_and_read(tmp_path):
    test_file = tmp_path / "hello.txt"
    write_res = files.write_file(str(test_file), "Hello Nexus AIOS!")
    assert write_res["status"] == "success"
    assert write_res["bytes_written"] == len("Hello Nexus AIOS!")

    read_res = files.read_file(str(test_file))
    assert read_res["status"] == "success"
    assert read_res["content"] == "Hello Nexus AIOS!"
    assert read_res["size_bytes"] == len("Hello Nexus AIOS!")
    assert read_res["truncated"] is False


def test_files_list_and_search(tmp_path):
    (tmp_path / "subdir").mkdir()
    (tmp_path / "file1.py").write_text("print(1)")
    (tmp_path / "subdir" / "file2.txt").write_text("data")

    # List dir
    list_res = files.list_dir(str(tmp_path))
    assert list_res["status"] == "success"
    names = [e["name"] for e in list_res["entries"]]
    assert "file1.py" in names
    assert "subdir" in names

    # Search pattern
    search_res = files.search_files("*.py", root_path=str(tmp_path))
    assert search_res["status"] == "success"
    assert "file1.py" in search_res["matches"]


def test_files_move_and_delete(tmp_path):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("move me")

    # Move
    mv_res = files.move_file(str(src), str(dst))
    assert mv_res["status"] == "success"
    assert not src.exists()
    assert dst.exists()

    # Delete
    del_res = files.delete_file(str(dst))
    assert del_res["status"] == "success"
    assert not dst.exists()


def test_files_zip_directory(tmp_path):
    dir_to_zip = tmp_path / "pack"
    dir_to_zip.mkdir()
    (dir_to_zip / "a.txt").write_text("apple")
    (dir_to_zip / "b.txt").write_text("banana")

    zip_out = tmp_path / "packed.zip"
    res = files.zip_directory(str(dir_to_zip), str(zip_out))
    assert res["status"] == "success"
    assert res["files_archived"] == 2
    assert zip_out.is_file()


def test_files_nonexistent(tmp_path):
    res = files.read_file(str(tmp_path / "nope.txt"))
    assert res["status"] == "error"
    assert "error" in res


# =============================================================================
# Apps Tool Tests
# =============================================================================

def test_apps_launch_blocked_binary():
    res = apps.launch_app("rm")
    assert res["status"] == "error"
    assert "prohibited" in res["error"]


def test_apps_launch_and_close(monkeypatch):
    class FakeProc:
        pid = 12345

    monkeypatch.setattr(apps.subprocess, "Popen", lambda *args, **kwargs: FakeProc())
    res = apps.launch_app("echo", args=["test"])
    assert res["status"] == "success"
    assert res["pid"] == 12345


def test_apps_list_running():
    res = apps.list_running_apps(limit=10)
    assert res["status"] == "success"
    assert "processes" in res


# =============================================================================
# Network Tool Tests
# =============================================================================

def test_network_connectivity():
    res = network.check_connectivity(host="127.0.0.1", port=65432, timeout=0.1)
    assert "connected" in res
    assert "status" in res


def test_network_ip_info():
    res = network.get_ip_info()
    assert res["status"] == "success"
    assert "hostname" in res
    assert "local_ip" in res


def test_network_download_invalid_scheme():
    res = network.download_file("ftp://example.com/file.txt", "file.txt")
    assert res["status"] == "error"
    assert "HTTP" in res["error"]


def test_network_notification():
    res = network.send_notification("Test Title", "Test Message")
    assert res["status"] in ("success", "logged")


# =============================================================================
# Packages Tool Tests
# =============================================================================

def test_packages_name_validation():
    # Dangerous injection attempt
    res = packages.check_package("nano; rm -rf /")
    assert res["status"] == "error"
    assert "Invalid package identifier" in res["error"]


def test_packages_check():
    # Check python or echo which is normally present
    res = packages.check_package("python")
    assert res["status"] == "success"
    assert "installed" in res


def test_packages_install_mocked(monkeypatch):
    class FakeCompleted:
        returncode = 0
        stdout = "Installed package successfully"
        stderr = ""

    monkeypatch.setattr(packages, "_detect_package_manager", lambda: ("apt-get", ["apt-get"]))
    monkeypatch.setattr(packages.subprocess, "run", lambda *args, **kwargs: FakeCompleted())

    res = packages.install_package("htop")
    assert res["status"] == "success"
    assert res["package"] == "htop"


# =============================================================================
# Tool Registry & Dispatcher Tests
# =============================================================================

def test_tool_registry():
    tools = list_tools()
    assert len(tools) >= 15
    actions = [t["action"] for t in tools]
    assert "files.read" in actions
    assert "network.connectivity" in actions
    assert "packages.install" in actions


def test_execute_tool_success(tmp_path):
    test_file = tmp_path / "exec_test.txt"
    test_file.write_text("Tool execution test content")

    res = execute_tool("files.read", {"path": str(test_file)})
    assert res["status"] == "success"
    assert res["content"] == "Tool execution test content"


def test_execute_tool_unknown():
    res = execute_tool("nonexistent.tool", {})
    assert res["status"] == "error"
    assert "Unknown tool action" in res["error"]
