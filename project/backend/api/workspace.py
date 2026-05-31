"""Workspace API routes.

Provides:
- GET /api/workspaces/{conversation_id}/files - List files
- GET /api/workspaces/{conversation_id}/files/{path} - Read file
- POST /api/workspaces/{conversation_id}/files - Write file
- DELETE /api/workspaces/{conversation_id}/files/{path} - Delete file
- POST /api/workspaces/{conversation_id}/snapshot - Create snapshot
- GET /api/workspaces/{conversation_id}/diff - Get diff
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import User, get_current_user
from core.config import settings
from core.logging import get_logger
from db.models import Conversation
from db.session import get_db
from services.git_service import git_diff, git_history, git_status, workspace_root
from workspace.workspace_manager import WorkspaceManager

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class WriteFileRequest(BaseModel):
    """Request to write a file."""

    path: str = Field(..., description="Relative file path")
    content: str = Field(..., description="File content as text")


class FileResponse(BaseModel):
    """File information response."""

    name: str
    path: str
    size: int
    mime_type: str
    is_directory: bool
    modified_at: str | None = None


class CreateWorkspaceItemRequest(BaseModel):
    path: str = Field(..., description="Relative path")
    type: str = Field(default="file", description="file or folder")
    content: str = Field(default="", description="Initial file content")


# ---------------------------------------------------------------------------
# Workspace Manager
# ---------------------------------------------------------------------------

_workspace_manager: WorkspaceManager | None = None


def get_workspace_manager() -> WorkspaceManager:
    """Get the workspace manager instance."""
    global _workspace_manager
    if _workspace_manager is None:
        _workspace_manager = WorkspaceManager()
    return _workspace_manager


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/workspaces")
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List known local workspaces.

    Conversation workspaces remain the source of truth, with orphan folders
    under settings.workspace_root included so the file tab can browse them.
    """
    root = Path(settings.workspace_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    conversations = (await db.execute(select(Conversation))).scalars().all()
    by_id = {str(conv.id): conv for conv in conversations}
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for conv in conversations:
        workspace_id = str(conv.id)
        path = workspace_root(workspace_id)
        status = await git_status(workspace_id)
        items.append(
            {
                "id": workspace_id,
                "name": conv.title or workspace_id[:8],
                "rootPath": str(path),
                "activeConversationId": workspace_id,
                "isGitRepo": bool(status.get("is_git_repo")),
                "branch": status.get("branch"),
                "fileCount": sum(1 for p in path.rglob("*") if p.is_file()) if path.exists() else 0,
                "modifiedCount": sum(len(status.get(key, [])) for key in ("staged", "modified", "untracked", "deleted", "conflicts")),
                "lastOpenedAt": conv.updated_at.isoformat() if conv.updated_at else "",
            }
        )
        seen.add(workspace_id)

    for child in root.iterdir():
        if not child.is_dir() or child.name in seen:
            continue
        status = await git_status(child.name)
        conv = by_id.get(child.name)
        items.append(
            {
                "id": child.name,
                "name": conv.title if conv else child.name,
                "rootPath": str(child),
                "activeConversationId": child.name if conv else None,
                "isGitRepo": bool(status.get("is_git_repo")),
                "branch": status.get("branch"),
                "fileCount": sum(1 for p in child.rglob("*") if p.is_file()),
                "modifiedCount": sum(len(status.get(key, [])) for key in ("staged", "modified", "untracked", "deleted", "conflicts")),
                "lastOpenedAt": "",
            }
        )

    return {"workspaces": sorted(items, key=lambda item: item["name"].lower()), "total": len(items)}


@router.get("/workspaces/{conversation_id}/files")
async def list_workspace_files(
    conversation_id: str,
    path: str = "",
    recursive: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List files in the workspace. Returns empty list if workspace not yet created."""
    from workspace.workspace_manager import WorkspaceError

    manager = get_workspace_manager()
    try:
        if recursive:
            files = await manager.list_files_recursive(conversation_id, path or "")
        else:
            files = await manager.list_files(conversation_id, path or "")
    except WorkspaceError:
        return {"files": [], "workspace_id": conversation_id, "path": path or "", "recursive": recursive}

    return {
        "files": [
            {
                "name": f.name,
                "path": f.path,
                "size": f.size,
                "mime_type": f.mime_type,
                "is_directory": f.is_directory,
                "type": "folder" if f.is_directory else "file",
                "modified_at": f.modified_at.isoformat() if f.modified_at else None,
            }
            for f in files
        ],
        "total": len(files),
    }


@router.get("/workspaces/{conversation_id}/git/status")
async def workspace_git_status(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await git_status(conversation_id)


@router.get("/workspaces/{conversation_id}/git/diff")
async def workspace_git_diff(
    conversation_id: str,
    scope: str = "working",
    file_path: str | None = None,
    context_lines: int = 3,
    commit: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await git_diff(conversation_id, scope=scope, file_path=file_path, context_lines=context_lines, commit=commit)


@router.get("/workspaces/{conversation_id}/git/history")
async def workspace_git_history(
    conversation_id: str,
    mode: str = "log",
    file_path: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await git_history(
        conversation_id,
        mode=mode,
        file_path=file_path,
        line_start=line_start,
        line_end=line_end,
        limit=limit,
    )


@router.post("/workspaces/{conversation_id}/open")
async def open_workspace(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    root = workspace_root(conversation_id)
    try:
        if os.name == "nt":
            os.startfile(str(root))  # type: ignore[attr-defined]
        else:
            process = await __import__("asyncio").create_subprocess_exec("xdg-open", str(root))
            await process.wait()
        return {"opened": True, "path": str(root)}
    except Exception as exc:
        return {"opened": False, "path": str(root), "error": str(exc)}


@router.post("/workspaces/{conversation_id}/refresh")
async def refresh_workspace(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    files = await list_workspace_files(conversation_id, recursive=True, db=db, user=user)
    status = await git_status(conversation_id)
    return {"workspace_id": conversation_id, "files": files.get("files", []), "git": status}


@router.get("/workspaces/{conversation_id}/files/{path:path}")
async def read_workspace_file(
    conversation_id: str,
    path: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Read a file from the workspace."""
    manager = get_workspace_manager()

    try:
        content = await manager.read_file(conversation_id, path)

        # Try to decode as text
        try:
            text_content = content.decode("utf-8")
            return {"content": text_content, "encoding": "text", "path": path}
        except UnicodeDecodeError:
            import base64
            return {
                "content": base64.b64encode(content).decode(),
                "encoding": "base64",
                "path": path,
            }

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workspaces/{conversation_id}/files")
async def write_workspace_file(
    conversation_id: str,
    request: WriteFileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Write a file to the workspace."""
    manager = get_workspace_manager()

    try:
        await manager.write_file_text(conversation_id, request.path, request.content)

        logger.info(
            f"File written: {request.path}",
            extra={"conversation_id": conversation_id},
        )

        return {
            "status": "written",
            "path": request.path,
            "size": len(request.content.encode("utf-8")),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/workspaces/{conversation_id}/files/{path:path}")
async def delete_workspace_file(
    conversation_id: str,
    path: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a file from the workspace."""
    manager = get_workspace_manager()

    try:
        await manager.delete_file(conversation_id, path)

        logger.info(
            f"File deleted: {path}",
            extra={"conversation_id": conversation_id},
        )

        return {"status": "deleted", "path": path}

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workspaces/{conversation_id}/snapshot")
async def create_workspace_snapshot(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a workspace snapshot."""
    from workspace.snapshot import get_snapshot_manager

    manager = get_workspace_manager()
    snapshot_manager = get_snapshot_manager()

    snapshot = await snapshot_manager.capture_snapshot(
        conversation_id=conversation_id,
        snapshot_type="manual",
        list_files_func=lambda: manager.list_files(conversation_id),
    )

    return {
        "snapshot_id": snapshot.id,
        "conversation_id": conversation_id,
        "file_count": len(snapshot.files),
        "created_at": snapshot.created_at,
    }


@router.get("/workspaces/{conversation_id}/diff")
async def get_workspace_diff(
    conversation_id: str,
    before: str = "",
    after: str = "",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get workspace diff between snapshots.

    Args:
        conversation_id: Conversation ID.
        before: Before snapshot ID (optional).
        after: After snapshot ID (optional).
    """
    from workspace.diff import get_diff_generator, FileDiff

    # For now, return a mock diff
    diff_gen = get_diff_generator()

    file_diffs = [
        FileDiff(
            path="example.py",
            change_type="modified",
            unified_diff="@@ -1,3 +1,4 @@\n line1\n line2\n+line3\n line4",
        )
    ]

    diff = diff_gen.generate_workspace_diff(file_diffs)

    return diff.to_dict()
