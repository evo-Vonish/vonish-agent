"""Read-only Git helpers bound to VonishAgent workspaces."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from core.config import settings


class WorkspaceGitError(ValueError):
    """Raised when a workspace id or path is invalid for Git operations."""


def workspace_root(workspace_id: str) -> Path:
    """Resolve a workspace id to an on-disk workspace path.

    The id is always treated as a child of settings.workspace_root. Absolute
    paths and traversal are rejected by checking the resolved path prefix.
    """
    raw = (workspace_id or "").strip()
    if not raw or raw == "current":
        raise WorkspaceGitError("workspace_id is required")
    base = Path(settings.workspace_root).resolve()
    target = (base / raw).resolve()
    if target != base and base not in target.parents:
        raise WorkspaceGitError("workspace path escape blocked")
    target.mkdir(parents=True, exist_ok=True)
    return target


def safe_file_arg(root: Path, file_path: str | None) -> str | None:
    if not file_path:
        return None
    raw = file_path.replace("\\", "/").strip().lstrip("/")
    target = (root / raw).resolve()
    if target != root and root not in target.parents:
        raise WorkspaceGitError("file path escape blocked")
    return raw


async def run_git(root: Path, *args: str, timeout: float = 20.0) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(root),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return 124, "", f"git command timed out after {timeout}s"
    return (
        process.returncode,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


async def is_git_repo(root: Path) -> bool:
    code, stdout, _ = await run_git(root, "rev-parse", "--is-inside-work-tree", timeout=5.0)
    return code == 0 and stdout.strip() == "true"


def _status_bucket(code: str) -> str:
    if "U" in code or code in {"AA", "DD"}:
        return "conflicts"
    if "D" in code:
        return "deleted"
    if code.strip() == "??":
        return "untracked"
    if code[0] != " ":
        return "staged"
    return "modified"


async def git_status(workspace_id: str) -> dict[str, Any]:
    root = workspace_root(workspace_id)
    if not await is_git_repo(root):
        return {
            "workspace_id": workspace_id,
            "root_path": str(root),
            "is_git_repo": False,
            "message": "当前 Workspace 不是 Git 仓库",
        }

    branch = ""
    code, stdout, stderr = await run_git(root, "status", "--porcelain=v1", "-b")
    if code != 0:
        return {"is_git_repo": True, "success": False, "error": stderr or stdout}

    staged: list[str] = []
    modified: list[str] = []
    untracked: list[str] = []
    deleted: list[str] = []
    conflicts: list[str] = []

    for line in stdout.splitlines():
        if line.startswith("## "):
            branch = line[3:].split("...", 1)[0].strip()
            continue
        if len(line) < 4:
            continue
        code_part = line[:2]
        path = line[3:].strip()
        bucket = _status_bucket(code_part)
        if bucket == "staged":
            staged.append(path)
        elif bucket == "modified":
            modified.append(path)
        elif bucket == "untracked":
            untracked.append(path)
        elif bucket == "deleted":
            deleted.append(path)
        else:
            conflicts.append(path)

    return {
        "workspace_id": workspace_id,
        "root_path": str(root),
        "is_git_repo": True,
        "branch": branch,
        "is_dirty": bool(staged or modified or untracked or deleted or conflicts),
        "staged": staged,
        "modified": modified,
        "untracked": untracked,
        "deleted": deleted,
        "conflicts": conflicts,
        "operation": None,
    }


async def git_diff(
    workspace_id: str,
    scope: str = "working",
    file_path: str | None = None,
    context_lines: int = 3,
    commit: str | None = None,
) -> dict[str, Any]:
    root = workspace_root(workspace_id)
    if not await is_git_repo(root):
        return {"workspace_id": workspace_id, "is_git_repo": False, "files": []}

    safe_path = safe_file_arg(root, file_path)
    args = ["diff", f"--unified={max(0, min(int(context_lines), 20))}", "--numstat"]
    if scope == "staged":
        args.insert(1, "--cached")
    elif scope == "commit" and commit:
        args = ["show", "--numstat", "--format=", commit]
    code, numstat, stderr = await run_git(root, *args)
    if code != 0:
        return {"success": False, "scope": scope, "error": stderr or numstat, "files": []}

    patch_args = ["diff", f"--unified={max(0, min(int(context_lines), 20))}"]
    if scope == "staged":
        patch_args.insert(1, "--cached")
    elif scope == "commit" and commit:
        patch_args = ["show", "--format=", f"--unified={max(0, min(int(context_lines), 20))}", commit]
    if safe_path:
        patch_args.extend(["--", safe_path])
    patch_code, patch, patch_err = await run_git(root, *patch_args, timeout=30.0)
    if patch_code != 0:
        return {"success": False, "scope": scope, "error": patch_err or patch, "files": []}

    stat_map: dict[str, dict[str, int]] = {}
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            add = 0 if parts[0] == "-" else int(parts[0] or 0)
            delete = 0 if parts[1] == "-" else int(parts[1] or 0)
            stat_map[parts[2]] = {"additions": add, "deletions": delete}

    files: list[dict[str, Any]] = []
    current_path = ""
    chunks: list[str] = []
    for line in patch.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current_path:
                stats = stat_map.get(current_path, {"additions": 0, "deletions": 0})
                files.append({"path": current_path, **stats, "patch": "".join(chunks)})
            parts = line.split(" b/", 1)
            current_path = parts[1].strip() if len(parts) == 2 else ""
            chunks = [line]
        else:
            chunks.append(line)
    if current_path:
        stats = stat_map.get(current_path, {"additions": 0, "deletions": 0})
        files.append({"path": current_path, **stats, "patch": "".join(chunks)})

    if safe_path:
        files = [file for file in files if file["path"] == safe_path]

    return {
        "workspace_id": workspace_id,
        "is_git_repo": True,
        "scope": scope,
        "files": files,
        "total_files": len(files),
        "additions": sum(file["additions"] for file in files),
        "deletions": sum(file["deletions"] for file in files),
    }


async def git_history(
    workspace_id: str,
    mode: str = "log",
    file_path: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    root = workspace_root(workspace_id)
    if not await is_git_repo(root):
        return {"workspace_id": workspace_id, "is_git_repo": False, "mode": mode}

    safe_path = safe_file_arg(root, file_path)
    limit = max(1, min(int(limit), 100))

    if mode == "blame" and safe_path:
        range_arg = []
        if line_start and line_end:
            range_arg = [f"-L{int(line_start)},{int(line_end)}"]
        code, stdout, stderr = await run_git(root, "blame", "--line-porcelain", *range_arg, "--", safe_path)
        if code != 0:
            return {"success": False, "mode": mode, "error": stderr or stdout, "lines": []}
        lines: list[dict[str, Any]] = []
        current: dict[str, Any] = {}
        for row in stdout.splitlines():
            if row.startswith("\t"):
                current["content"] = row[1:]
                lines.append(current)
                current = {}
            elif row.startswith("author "):
                current["author"] = row[7:]
            elif row.startswith("summary "):
                current["summary"] = row[8:]
            elif row and " " in row and not current.get("commit"):
                parts = row.split()
                current["commit"] = parts[0]
                if len(parts) >= 3:
                    current["line"] = int(parts[2])
        return {"workspace_id": workspace_id, "is_git_repo": True, "mode": mode, "file_path": safe_path, "lines": lines[:limit]}

    args = ["log", f"-n{limit}", "--date=short", "--pretty=format:%H%x1f%h%x1f%an%x1f%ad%x1f%s"]
    if safe_path:
        args.extend(["--", safe_path])
    code, stdout, stderr = await run_git(root, *args)
    if code != 0:
        return {"success": False, "mode": "log", "error": stderr or stdout, "commits": []}
    commits = []
    for line in stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 5:
            commits.append({
                "hash": parts[0],
                "short_hash": parts[1],
                "author": parts[2],
                "date": parts[3],
                "message": parts[4],
            })
    return {"workspace_id": workspace_id, "is_git_repo": True, "mode": "log", "commits": commits}
