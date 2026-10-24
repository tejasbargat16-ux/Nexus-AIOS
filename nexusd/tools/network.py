"""
Nexus AIOS Network Tool (Phase 2).

Provides safe network inspection, connectivity checking, controlled file downloads,
and desktop / Termux notification dispatch.
"""

from __future__ import annotations

import logging
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any
import requests

from nexusd.tools.files import _resolve_safe_path

logger = logging.getLogger("nexusd.tools.network")
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024  # 50 MB safety cap


def check_connectivity(host: str = "8.8.8.8", port: int = 53, timeout: float = 3.0) -> dict[str, Any]:
    """
    Check external internet connectivity via fast socket handshake.

    Args:
        host: Target DNS or server host.
        port: Target port (default DNS 53).
        timeout: Socket timeout in seconds.

    Returns:
        dict: {'status': 'success'|'offline', 'connected': bool, 'latency_ms': float}
    """
    start_t = time.perf_counter()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
        return {
            "status": "success",
            "connected": True,
            "host": host,
            "port": port,
            "latency_ms": latency_ms,
        }
    except Exception as err:
        return {
            "status": "offline",
            "connected": False,
            "host": host,
            "port": port,
            "error": str(err),
        }


def get_ip_info() -> dict[str, Any]:
    """
    Query local hostname and primary outbound network IP address.

    Returns:
        dict: {'status': 'success', 'hostname': str, 'local_ip': str}
    """
    hostname = socket.gethostname()
    local_ip = "127.0.0.1"
    try:
        # Determine outbound socket IP without sending data
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    return {
        "status": "success",
        "hostname": hostname,
        "local_ip": local_ip,
    }


def download_file(
    url: str,
    dest_path: str,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    timeout: int = 30,
) -> dict[str, Any]:
    """
    Stream and download a remote file with byte limits and sandbox path validation.

    Args:
        url: HTTP or HTTPS URL to download.
        dest_path: Target destination path on local disk.
        max_bytes: Maximum allowed file size in bytes.
        timeout: Request timeout in seconds.

    Returns:
        dict: {'status': 'success'|'error', 'path': str, 'bytes_downloaded': int}
    """
    if not url.startswith(("http://", "https://")):
        return {"error": "Only HTTP and HTTPS URLs are permitted", "status": "error"}

    target = _resolve_safe_path(dest_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        with requests.get(url, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()

            # Check Content-Length header if provided
            content_length = resp.headers.get("content-length")
            if content_length and int(content_length) > max_bytes:
                return {
                    "error": f"Remote file ({content_length} bytes) exceeds maximum limit ({max_bytes} bytes)",
                    "status": "error",
                }

            downloaded = 0
            with open(target, "wb") as f:
                for chunk in resp.iter_content(chunk_size=16384):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        # Abort and remove partial file
                        target.unlink(missing_ok=True)
                        return {
                            "error": f"Download exceeded size threshold of {max_bytes} bytes",
                            "status": "error",
                        }
                    f.write(chunk)

        return {
            "status": "success",
            "url": url,
            "path": str(target),
            "bytes_downloaded": downloaded,
        }
    except Exception as err:
        target.unlink(missing_ok=True)
        return {"error": f"Download failed: {err}", "status": "error"}


def send_notification(title: str, message: str) -> dict[str, Any]:
    """
    Dispatch a system desktop or Termux notification.

    Args:
        title: Notification header.
        message: Notification body text.

    Returns:
        dict: {'status': 'success'|'fallback', 'platform': str}
    """
    clean_title = str(title).strip()
    clean_msg = str(message).strip()

    # 1. Android Termux notification
    if shutil.which("termux-notification"):
        try:
            subprocess.run(
                ["termux-notification", "--title", clean_title, "--content", clean_msg],
                check=True,
                timeout=5,
            )
            return {"status": "success", "platform": "termux"}
        except Exception:
            pass

    # 2. Linux desktop (notify-send)
    if shutil.which("notify-send"):
        try:
            subprocess.run(
                ["notify-send", clean_title, clean_msg],
                check=True,
                timeout=5,
            )
            return {"status": "success", "platform": "linux-desktop"}
        except Exception:
            pass

    # 3. Fallback to daemon logger
    logger.info("NOTIFICATION [%s]: %s", clean_title, clean_msg)
    return {"status": "logged", "platform": "logger", "title": clean_title, "message": clean_msg}
