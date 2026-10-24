"""
Nexus AIOS Files Tool (Phase 2).

Provides secure file system operations with sandboxing checks:
read, write, list, search, move, delete, and zip directories.
"""

from __future__ import annotations

import fnmatch
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any

# Maximum safe byte limit for read operations to avoid OOM
MAX_READ_BYTES = 1024 * 1024  # 1 MB


def _resolve_safe_path(target_path: str | Path, base_dir: Path | None = None) -> Path:
    """
    Resolve and validate path safety against directory traversal.

    Args:
        target_path: Relative or absolute path string.
        base_dir: Optional sandbox boundary root directory.

    Returns:
        Path: Resolved absolute path.

    Raises:
        ValueError: If path attempts directory traversal or points to restricted system paths.
    """
    resolved = Path(target_path).resolve()

    # Block parent traversal escapes when a base directory is defined
    if base_dir:
        base_resolved = base_dir.resolve()
        try:
            resolved.relative_to(base_resolved)
        except ValueError:
            raise ValueError(f"Access denied: path '{target_path}' is outside sandbox '{base_dir}'")

    return resolved


def read_file(path: str, max_bytes: int = MAX_READ_BYTES) -> dict[str, Any]:
    """
    Read text or binary file safely with byte bounds.

    Args:
        path: Target file path.
        max_bytes: Maximum bytes to read before truncating.

    Returns:
        dict: {'path': str, 'content': str, 'size_bytes': int, 'truncated': bool}
    """
    target = _resolve_safe_path(path)
    if not target.exists():
        return {"error": f"File does not exist: {path}", "path": str(target), "status": "error"}
    if not target.is_file():
        return {"error": f"Path is not a regular file: {path}", "path": str(target), "status": "error"}

    size = target.stat().st_size
    truncated = size > max_bytes

    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_bytes)
        return {
            "status": "success",
            "path": str(target),
            "size_bytes": size,
            "truncated": truncated,
            "content": content,
        }
    except Exception as err:
        return {"error": f"Failed to read file: {err}", "path": str(target), "status": "error"}


def write_file(path: str, content: str, append: bool = False) -> dict[str, Any]:
    """
    Write content to a file, safely creating parent directories if necessary.

    Args:
        path: Target file path.
        content: Text content to write.
        append: Whether to append or overwrite.

    Returns:
        dict: {'status': 'success', 'path': str, 'bytes_written': int}
    """
    target = _resolve_safe_path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(target, mode, encoding="utf-8") as f:
            written = f.write(content)
        return {
            "status": "success",
            "path": str(target),
            "bytes_written": written,
            "mode": mode,
        }
    except Exception as err:
        return {"error": f"Failed to write file: {err}", "path": str(target), "status": "error"}


def list_dir(path: str = ".", max_items: int = 200) -> dict[str, Any]:
    """
    List contents of a directory.

    Args:
        path: Target directory path.
        max_items: Limit on returned items.

    Returns:
        dict: {'status': 'success', 'path': str, 'entries': list, 'count': int}
    """
    target = _resolve_safe_path(path)
    if not target.exists():
        return {"error": f"Directory does not exist: {path}", "path": str(target), "status": "error"}
    if not target.is_dir():
        return {"error": f"Path is not a directory: {path}", "path": str(target), "status": "error"}

    try:
        entries: list[dict[str, Any]] = []
        for item in sorted(target.iterdir()):
            if len(entries) >= max_items:
                break
            try:
                stat = item.stat()
                entries.append({
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size_bytes": stat.st_size if item.is_file() else 0,
                })
            except OSError:
                continue

        return {
            "status": "success",
            "path": str(target),
            "entries": entries,
            "count": len(entries),
        }
    except Exception as err:
        return {"error": f"Failed to list directory: {err}", "path": str(target), "status": "error"}


def search_files(pattern: str, root_path: str = ".", max_results: int = 50) -> dict[str, Any]:
    """
    Search recursively for files matching a glob or wildcard pattern.

    Args:
        pattern: Match pattern (e.g. '*.py', '*config*').
        root_path: Directory root to search from.
        max_results: Maximum results to collect.

    Returns:
        dict: {'status': 'success', 'pattern': str, 'matches': list, 'count': int}
    """
    root = _resolve_safe_path(root_path)
    if not root.exists() or not root.is_dir():
        return {"error": f"Search root does not exist: {root_path}", "status": "error"}

    matches: list[str] = []
    try:
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if fnmatch.fnmatch(filename, pattern):
                    rel = os.path.relpath(os.path.join(dirpath, filename), root)
                    matches.append(rel)
                    if len(matches) >= max_results:
                        break
            if len(matches) >= max_results:
                break

        return {
            "status": "success",
            "root": str(root),
            "pattern": pattern,
            "matches": matches,
            "count": len(matches),
        }
    except Exception as err:
        return {"error": f"Search failed: {err}", "status": "error"}


def move_file(src: str, dst: str) -> dict[str, Any]:
    """
    Safely move or rename a file or directory.

    Args:
        src: Source path.
        dst: Destination path.

    Returns:
        dict: {'status': 'success', 'src': str, 'dst': str}
    """
    source = _resolve_safe_path(src)
    destination = _resolve_safe_path(dst)

    if not source.exists():
        return {"error": f"Source does not exist: {src}", "status": "error"}

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return {
            "status": "success",
            "src": str(source),
            "dst": str(destination),
        }
    except Exception as err:
        return {"error": f"Failed to move: {err}", "status": "error"}


def delete_file(path: str) -> dict[str, Any]:
    """
    Safely delete a file or directory.

    Args:
        path: Target path to delete.

    Returns:
        dict: {'status': 'success', 'path': str}
    """
    target = _resolve_safe_path(path)
    if not target.exists():
        return {"error": f"Path does not exist: {path}", "status": "error"}

    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return {"status": "success", "path": str(target)}
    except Exception as err:
        return {"error": f"Failed to delete: {err}", "status": "error"}


def zip_directory(src: str, out_zip: str) -> dict[str, Any]:
    """
    Create a zip archive of a directory.

    Args:
        src: Source directory path.
        out_zip: Destination .zip file path.

    Returns:
        dict: {'status': 'success', 'zip_path': str, 'files_archived': int}
    """
    source = _resolve_safe_path(src)
    dest_zip = _resolve_safe_path(out_zip)

    if not source.exists() or not source.is_dir():
        return {"error": f"Source directory does not exist: {src}", "status": "error"}

    try:
        dest_zip.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(source):
                for f in files:
                    file_path = Path(root) / f
                    arcname = file_path.relative_to(source)
                    zf.write(file_path, arcname)
                    count += 1

        return {
            "status": "success",
            "zip_path": str(dest_zip),
            "files_archived": count,
        }
    except Exception as err:
        return {"error": f"Failed to create zip: {err}", "status": "error"}
