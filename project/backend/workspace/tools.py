"""Workspace tools for Agent use.

Provides safe, sandboxed file operations that the Agent can invoke via tool calls.
All paths are validated through PathSandbox before any filesystem access.

Tools:
    - list_workspace_files: List files in the current conversation's workspace
    - read_workspace_file: Read the contents of a workspace file
    - get_workspace_summary: Get a summary of the workspace contents
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from workspace.permissions import PathSandbox, SecurityError
from workspace.storage_provider import FileInfo
from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_READ_SIZE = 5 * 1024 * 1024  # 5MB max file read
MAX_FILES_IN_SUMMARY = 1000  # max files to include in summary


# ---------------------------------------------------------------------------
# Helper: Workspace path resolution
# ---------------------------------------------------------------------------


def _get_workspace_root(conversation_id: str) -> Path:
    """Resolve the workspace directory path for a conversation.

    Layout: {workspace_root}/{conversation_id}/

    Args:
        conversation_id: Conversation identifier.

    Returns:
        Resolved Path to the workspace directory.
    """
    workspace_root = Path(settings.workspace_root).resolve()
    return workspace_root / conversation_id


def _get_sandbox(conversation_id: str) -> PathSandbox:
    """Create a PathSandbox for the given conversation's workspace.

    Args:
        conversation_id: Conversation identifier.

    Returns:
        PathSandbox configured for this workspace.
    """
    root = _get_workspace_root(conversation_id)
    return PathSandbox(root)


def _file_type_from_name(name: str) -> str:
    """Infer a simple file type from the filename extension.

    Args:
        name: Filename (e.g. 'report.pdf').

    Returns:
        Lower-case extension without dot, or 'unknown'.
    """
    if "." in name:
        return name.rsplit(".", 1)[-1].lower()
    return "unknown"


# ---------------------------------------------------------------------------
# Tool: list_workspace_files
# ---------------------------------------------------------------------------


async def list_workspace_files(
    conversation_id: str,
    subdir: str = "",
) -> dict[str, Any]:
    """List files in the current conversation's workspace.

    Traverses the workspace directory (optionally scoped to *subdir*),
    validates every path through PathSandbox, and returns structured
    file metadata.

    Args:
        conversation_id: The active conversation ID.
        subdir: Subdirectory to list (default: workspace root).

    Returns:
        Structured dict:
        {
            "files": [
                {
                    "path": "uploads/report.pdf",
                    "name": "report.pdf",
                    "size": 12345,
                    "type": "pdf",
                    "mime_type": "application/pdf",
                    "is_directory": false,
                    "modified_at": "2024-01-15T08:30:00",
                },
                ...
            ],
            "total_count": 42,
            "conversation_id": "conv_abc123",
            "subdir": "uploads",
        }

    Raises:
        Returns error dict (never raises) so the Agent can react gracefully.
    """
    try:
        sandbox = _get_sandbox(conversation_id)
        workspace_root = _get_workspace_root(conversation_id)

        # Validate subdir if provided
        if subdir:
            try:
                sandbox.validate_path(subdir)
            except SecurityError as exc:
                return {
                    "success": False,
                    "error": f"Invalid subdir: {exc}",
                    "files": [],
                    "total_count": 0,
                    "conversation_id": conversation_id,
                    "subdir": subdir,
                }
            target_dir = workspace_root / subdir
        else:
            target_dir = workspace_root

        if not target_dir.exists():
            return {
                "success": True,
                "files": [],
                "total_count": 0,
                "conversation_id": conversation_id,
                "subdir": subdir,
                "note": "Directory does not exist yet",
            }

        # Walk the directory tree
        files: list[dict[str, Any]] = []
        total_count = 0

        for dirpath, _dirnames, filenames in os.walk(target_dir):
            # Skip hidden/system directories (except .workspace/)
            rel_dir = (
                Path(dirpath).relative_to(workspace_root)
                if dirpath != str(workspace_root)
                else Path("")
            )

            for filename in filenames:
                full_path = Path(dirpath) / filename
                rel_path = str(Path(rel_dir) / filename) if rel_dir != Path("") else filename

                # Validate through sandbox
                try:
                    sandbox.validate_path(rel_path)
                except SecurityError:
                    logger.warning(f"Skipping unsafe path: {rel_path}")
                    continue

                try:
                    stat = full_path.stat()
                    size = int(stat.st_size)
                    modified_at = stat.st_mtime
                except (OSError, IOError):
                    size = 0
                    modified_at = None

                file_entry = {
                    "path": rel_path,
                    "name": filename,
                    "size": size,
                    "type": _file_type_from_name(filename),
                    "mime_type": _guess_mime_type(filename),
                    "is_directory": False,
                    "modified_at": _fmt_timestamp(modified_at),
                }
                files.append(file_entry)
                total_count += 1

                if total_count >= MAX_FILES_IN_SUMMARY:
                    break

            if total_count >= MAX_FILES_IN_SUMMARY:
                break

        # Sort by path for consistent ordering
        files.sort(key=lambda f: f["path"])

        return {
            "success": True,
            "files": files,
            "total_count": total_count,
            "conversation_id": conversation_id,
            "subdir": subdir,
        }

    except SecurityError as exc:
        logger.error(f"Security error listing files: {exc}")
        return {
            "success": False,
            "error": f"Security violation: {exc}",
            "files": [],
            "total_count": 0,
            "conversation_id": conversation_id,
            "subdir": subdir,
        }
    except Exception as exc:
        logger.error(f"Unexpected error listing workspace files: {exc}")
        return {
            "success": False,
            "error": f"Internal error: {exc}",
            "files": [],
            "total_count": 0,
            "conversation_id": conversation_id,
            "subdir": subdir,
        }


# ---------------------------------------------------------------------------
# Tool: read_workspace_file
# ---------------------------------------------------------------------------


async def read_workspace_file(
    conversation_id: str,
    path: str,
) -> dict[str, Any]:
    """Read the contents of a file from the workspace.

    Validates the requested path through PathSandbox, reads up to
    MAX_READ_SIZE bytes, and returns the content as text (UTF-8) or
    base64-encoded binary data.

    Args:
        conversation_id: The active conversation ID.
        path: File path relative to the workspace root.

    Returns:
        Structured dict:
        {
            "success": true,
            "path": "uploads/report.pdf",
            "content": "... text or base64 ...",
            "encoding": "utf-8" | "base64",
            "size": 12345,
            "truncated": false,
            "conversation_id": "conv_abc123",
        }
    """
    import base64

    try:
        sandbox = _get_sandbox(conversation_id)
        workspace_root = _get_workspace_root(conversation_id)

        # Validate path
        try:
            sandbox.validate_path(path)
        except SecurityError as exc:
            return {
                "success": False,
                "error": f"Security violation: {exc}",
                "path": path,
                "conversation_id": conversation_id,
            }

        # Resolve full path
        if Path(path).is_absolute():
            full_path = workspace_root / Path(path).name
        else:
            full_path = workspace_root / path

        full_path = full_path.resolve()

        # Ensure still within workspace after resolution
        try:
            full_path.relative_to(workspace_root.resolve())
        except ValueError:
            return {
                "success": False,
                "error": "Resolved path escapes workspace root",
                "path": path,
                "conversation_id": conversation_id,
            }

        if not full_path.exists():
            return {
                "success": False,
                "error": f"File not found: {path}",
                "path": path,
                "conversation_id": conversation_id,
            }

        if not full_path.is_file():
            return {
                "success": False,
                "error": f"Path is not a file: {path}",
                "path": path,
                "conversation_id": conversation_id,
            }

        # Read up to MAX_READ_SIZE bytes
        try:
            with open(full_path, "rb") as fh:
                raw = fh.read(MAX_READ_SIZE)
        except PermissionError:
            return {
                "success": False,
                "error": f"Permission denied: {path}",
                "path": path,
                "conversation_id": conversation_id,
            }
        except OSError as exc:
            return {
                "success": False,
                "error": f"Read error: {exc}",
                "path": path,
                "conversation_id": conversation_id,
            }

        file_size = full_path.stat().st_size
        truncated = file_size > MAX_READ_SIZE

        # Try UTF-8 text decode, fall back to base64
        try:
            content = raw.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            content = base64.b64encode(raw).decode("ascii")
            encoding = "base64"

        return {
            "success": True,
            "path": path,
            "content": content,
            "encoding": encoding,
            "size": file_size,
            "truncated": truncated,
            "conversation_id": conversation_id,
        }

    except SecurityError as exc:
        logger.error(f"Security error reading file: {exc}")
        return {
            "success": False,
            "error": f"Security violation: {exc}",
            "path": path,
            "conversation_id": conversation_id,
        }
    except Exception as exc:
        logger.error(f"Unexpected error reading workspace file: {exc}")
        return {
            "success": False,
            "error": f"Internal error: {exc}",
            "path": path,
            "conversation_id": conversation_id,
        }


# ---------------------------------------------------------------------------
# Tool: get_workspace_summary
# ---------------------------------------------------------------------------


async def get_workspace_summary(
    conversation_id: str,
) -> dict[str, Any]:
    """Get a summary of the workspace contents.

    Computes aggregate statistics (total files, total size, file type
    breakdown, directory structure) for the conversation's workspace.

    Args:
        conversation_id: The active conversation ID.

    Returns:
        Structured dict:
        {
            "success": true,
            "conversation_id": "conv_abc123",
            "total_files": 42,
            "total_size": 1543200,
            "total_size_human": "1.47 MB",
            "directories": ["uploads", "outputs", "assets"],
            "type_breakdown": {"pdf": 5, "md": 12, "py": 8},
            "largest_files": [
                {"path": "uploads/report.pdf", "size": 500000},
                ...
            ],
        }
    """
    try:
        sandbox = _get_sandbox(conversation_id)
        workspace_root = _get_workspace_root(conversation_id)

        if not workspace_root.exists():
            return {
                "success": True,
                "conversation_id": conversation_id,
                "total_files": 0,
                "total_size": 0,
                "total_size_human": "0 B",
                "directories": [],
                "type_breakdown": {},
                "largest_files": [],
                "note": "Workspace has not been created yet",
            }

        total_files = 0
        total_size = 0
        type_breakdown: dict[str, int] = {}
        directories: set[str] = set()
        all_files: list[tuple[str, int]] = []

        for dirpath, dirnames, filenames in os.walk(workspace_root):
            rel_dir = (
                str(Path(dirpath).relative_to(workspace_root))
                if dirpath != str(workspace_root)
                else ""
            )

            for dirname in dirnames:
                dir_rel = (
                    f"{rel_dir}/{dirname}" if rel_dir else dirname
                )
                directories.add(dir_rel)

            for filename in filenames:
                full_path = Path(dirpath) / filename
                rel_path = (
                    f"{rel_dir}/{filename}" if rel_dir else filename
                )

                # Validate through sandbox
                try:
                    sandbox.validate_path(rel_path)
                except SecurityError:
                    continue

                try:
                    size = full_path.stat().st_size
                except (OSError, IOError):
                    size = 0

                total_files += 1
                total_size += size
                ftype = _file_type_from_name(filename)
                type_breakdown[ftype] = type_breakdown.get(ftype, 0) + 1
                all_files.append((rel_path, size))

        # Top 5 largest files
        all_files.sort(key=lambda x: x[1], reverse=True)
        largest_files = [
            {"path": p, "size": s, "size_human": _human_readable_size(s)}
            for p, s in all_files[:5]
        ]

        return {
            "success": True,
            "conversation_id": conversation_id,
            "total_files": total_files,
            "total_size": total_size,
            "total_size_human": _human_readable_size(total_size),
            "directories": sorted(directories),
            "type_breakdown": type_breakdown,
            "largest_files": largest_files,
        }

    except SecurityError as exc:
        logger.error(f"Security error in workspace summary: {exc}")
        return {
            "success": False,
            "error": f"Security violation: {exc}",
            "conversation_id": conversation_id,
        }
    except Exception as exc:
        logger.error(f"Unexpected error in workspace summary: {exc}")
        return {
            "success": False,
            "error": f"Internal error: {exc}",
            "conversation_id": conversation_id,
        }


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _guess_mime_type(filename: str) -> str:
    """Guess MIME type from filename extension.

    Args:
        filename: Name of the file.

    Returns:
        MIME type string or 'application/octet-stream'.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime_map = {
        "txt": "text/plain",
        "md": "text/markdown",
        "py": "text/x-python",
        "js": "text/javascript",
        "ts": "text/typescript",
        "json": "application/json",
        "yaml": "text/yaml",
        "yml": "text/yaml",
        "html": "text/html",
        "css": "text/css",
        "xml": "application/xml",
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "svg": "image/svg+xml",
        "csv": "text/csv",
        "zip": "application/zip",
        "tar": "application/x-tar",
        "gz": "application/gzip",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "ppt": "application/vnd.ms-powerpoint",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    return mime_map.get(ext, "application/octet-stream")


def _human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Human-readable string like '1.5 MB'.
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def _fmt_timestamp(ts: float | None) -> str | None:
    """Format a Unix timestamp to ISO-8601 string.

    Args:
        ts: Unix timestamp or None.

    Returns:
        ISO-8601 formatted string or None.
    """
    from datetime import datetime, timezone

    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
