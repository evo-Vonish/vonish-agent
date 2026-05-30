"""search_workspace tool handler — grep across conversation workspace files."""

from __future__ import annotations

import asyncio
import fnmatch
import re
from pathlib import Path
from typing import Any


MAX_FILE_SIZE = 1_000_000       # 1 MB
MAX_FILES_SCANNED = 5000
DEFAULT_MAX_RESULTS = 50
DEFAULT_CONTEXT_LINES = 2
TIMEOUT_SECONDS = 10

DEFAULT_EXCLUDES = [
    ".workspace/**", ".agent/**", "node_modules/**", ".git/**",
    "__pycache__/**", "dist/**", "build/**", "*.pyc", ".venv/**",
]


def _is_text_file(path: Path) -> bool:
    """Quick check: skip obvious binary files."""
    binary_exts = {".pyc", ".so", ".dll", ".exe", ".bin", ".png", ".jpg",
                   ".gif", ".ico", ".woff", ".woff2", ".ttf", ".eot",
                   ".zip", ".tar", ".gz", ".7z", ".mp3", ".mp4", ".o"}
    return path.suffix.lower() not in binary_exts


def _should_skip(path: str, include_globs: list[str], exclude_globs: list[str]) -> bool:
    """Check if a relative path should be excluded."""
    # Include filter
    if include_globs:
        if not any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(Path(path).name, g)
                   for g in include_globs):
            return True
    # Exclude filter
    for g in exclude_globs:
        if fnmatch.fnmatch(path, g) or fnmatch.fnmatch(Path(path).name, g):
            return True
    return False


async def handle_search_workspace(
    conversation_id: str = "",
    pattern: str = "",
    path: str = ".",
    regex: bool = False,
    case_sensitive: bool = False,
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    context_lines: int = DEFAULT_CONTEXT_LINES,
    workspace_root: str = "",
    **_: Any,
) -> dict[str, Any]:
    """Search text patterns across workspace files."""

    if not pattern:
        return {"success": False, "error": "pattern is required"}

    # Resolve workspace directory
    if workspace_root:
        ws = Path(workspace_root) / conversation_id
    else:
        from core.config import settings
        ws = Path(settings.workspace_root) / conversation_id

    # Resolve target dir within workspace
    target = (ws / path).resolve()
    if not str(target).startswith(str(ws.resolve())):
        return {"success": False, "error": f"Path escape blocked: {path}"}
    if not target.exists() or not target.is_dir():
        return {"success": False, "error": f"Directory not found: {path}"}

    # Compile pattern
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        compiled = re.compile(pattern, flags) if regex else None
    except re.error as e:
        return {"success": False, "error": f"Invalid regex: {e}"}

    includes = include_globs or []
    excludes = exclude_globs or DEFAULT_EXCLUDES

    results: list[dict] = []
    total_matches = 0
    truncated = False
    files_scanned = 0

    def _search_file(fp: Path) -> None:
        nonlocal total_matches, truncated, files_scanned

        rel = str(fp.relative_to(ws)).replace("\\", "/")
        if _should_skip(rel, includes, excludes):
            return
        if not _is_text_file(fp):
            return
        if fp.stat().st_size > MAX_FILE_SIZE:
            return

        files_scanned += 1
        if files_scanned > MAX_FILES_SCANNED:
            return

        try:
            lines = fp.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return

        for i, line in enumerate(lines):
            if truncated:
                break

            lineno = i + 1
            if compiled:
                found = compiled.search(line)
                if not found:
                    continue
                column = found.start() + 1
            else:
                search_line = line if case_sensitive else line.lower()
                search_pat = pattern if case_sensitive else pattern.lower()
                pos = search_line.find(search_pat)
                if pos == -1:
                    continue
                column = pos + 1

            total_matches += 1

            # Build preview with context
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            preview = [
                {"line": j + 1, "text": lines[j]}
                for j in range(start, end)
            ]

            results.append({
                "path": rel,
                "line": lineno,
                "column": column,
                "match": line.strip()[:200],
                "preview": preview,
            })

            if len(results) >= max_results:
                truncated = True
                return

    # Walk and search
    try:
        _walk_and_search(target, ws, _search_file)
    except TimeoutError:
        truncated = True

    return {
        "success": True,
        "query": {
            "pattern": pattern,
            "regex": regex,
            "path": path,
        },
        "total_matches": total_matches,
        "truncated": truncated,
        "results": results[:max_results],
        "files_scanned": files_scanned,
    }


def _walk_and_search(root: Path, ws: Path, cb: callable) -> None:
    """Walk directory tree and call cb for each file."""
    for entry in root.iterdir():
        if entry.is_dir():
            # Skip hidden dirs
            if entry.name.startswith(".") or entry.name == "__pycache__":
                continue
            if entry.name in ("node_modules", "dist", "build", ".git", ".venv"):
                continue
            _walk_and_search(entry, ws, cb)
        elif entry.is_file():
            cb(entry)
