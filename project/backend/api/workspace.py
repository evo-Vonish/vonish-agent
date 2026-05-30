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

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import User, get_current_user
from core.logging import get_logger
from db.session import get_db
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
                "modified_at": f.modified_at.isoformat() if f.modified_at else None,
            }
            for f in files
        ],
        "total": len(files),
    }


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
