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
import base64
import mimetypes
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import User, get_current_user
from core.config import settings
from core.logging import get_logger
from db.models import Conversation
from db.session import get_db
from services.git_service import ensure_workspace, git_diff, git_history, git_status, workspace_root
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


class CheckpointRequest(BaseModel):
    kind: str = Field(default="agent_milestone")
    message: str = Field(default="")
    artifacts: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RollbackPreviewRequest(BaseModel):
    turn_id: str = Field(..., description="User message id / turn id")


class TimelineTurnRequest(BaseModel):
    conversation_id: str | None = None
    message: str | None = None


class RestoreArtifactVersionRequest(BaseModel):
    version: int = Field(..., ge=1)


TEXT_PREVIEW_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".py", ".ts", ".tsx", ".js", ".jsx", ".json",
    ".css", ".scss", ".html", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".csv", ".tsv", ".log", ".sql", ".sh", ".ps1", ".bat",
}

MAX_PREVIEW_BYTES = 512 * 1024


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


def _safe_workspace_child(workspace_id: str, rel_path: str = "") -> Path:
    root = workspace_root(workspace_id)
    raw = (rel_path or "").replace("\\", "/").strip().lstrip("/")
    target = (root / raw).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(status_code=400, detail="Path escape blocked")
    return target


def _relative_path(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _file_item(root: Path, path: Path) -> dict[str, Any]:
    stat = path.stat()
    rel = _relative_path(root, path)
    mime, _ = mimetypes.guess_type(path.name)
    return {
        "name": path.name,
        "path": rel,
        "size": stat.st_size if path.is_file() else 0,
        "mime_type": mime or "inode/directory" if path.is_dir() else mime or "application/octet-stream",
        "is_directory": path.is_dir(),
        "type": "folder" if path.is_dir() else "file",
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def _iter_workspace_files(root: Path, subdir: str = "", recursive: bool = False) -> list[dict[str, Any]]:
    start = _safe_workspace_child(root.name, subdir)
    if not start.exists() or not start.is_dir():
        return []
    iterator = start.rglob("*") if recursive else start.iterdir()
    items: list[dict[str, Any]] = []
    for path in iterator:
        try:
            rel = _relative_path(root, path)
            if rel == ".workspace" or rel.startswith(".workspace/"):
                continue
            if any(part in {"__pycache__", ".git"} for part in path.relative_to(root).parts):
                continue
            items.append(_file_item(root, path))
        except OSError:
            continue
    return sorted(items, key=lambda item: (item["type"] != "folder", item["path"].lower()))


async def _workspace_summary(workspace_id: str, name: str, active_conversation_id: str | None, last_opened_at: str = "") -> dict[str, Any]:
    path = workspace_root(workspace_id)
    status = await git_status(workspace_id)
    file_count = sum(1 for p in path.rglob("*") if p.is_file() and ".git" not in p.parts and ".workspace" not in p.parts) if path.exists() else 0
    modified_count = sum(len(status.get(key, [])) for key in ("staged", "modified", "untracked", "deleted", "conflicts"))
    return {
        "id": workspace_id,
        "name": name,
        "rootPath": str(path),
        "activeConversationId": active_conversation_id,
        "isGitRepo": bool(status.get("is_git_repo")),
        "branch": status.get("branch"),
        "fileCount": file_count,
        "modifiedCount": modified_count,
        "lastOpenedAt": last_opened_at,
    }


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
        items.append(
            await _workspace_summary(
                workspace_id,
                conv.title or workspace_id[:8],
                workspace_id,
                conv.updated_at.isoformat() if conv.updated_at else "",
            )
        )
        seen.add(workspace_id)

    for child in root.iterdir():
        if not child.is_dir() or child.name in seen:
            continue
        if child.name.startswith(".") or child.name in {"__pycache__", "cache", "tmp", "temp"}:
            continue
        conv = by_id.get(child.name)
        items.append(
            await _workspace_summary(
                child.name,
                conv.title if conv else child.name,
                child.name if conv else None,
            )
        )

    return {"workspaces": sorted(items, key=lambda item: item["name"].lower()), "total": len(items)}


@router.post("/workspaces/{conversation_id}/ensure")
async def ensure_workspace_route(
    conversation_id: str,
    init_git: bool = True,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await ensure_workspace(conversation_id, init_git=init_git)
    return result


@router.get("/workspaces/{conversation_id}/files")
async def list_workspace_files(
    conversation_id: str,
    path: str = "",
    recursive: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List files in the workspace. Returns empty list if workspace not yet created."""
    root = workspace_root(conversation_id)
    files = _iter_workspace_files(root, path or "", recursive)
    return {
        "workspace_id": conversation_id,
        "path": path or "",
        "recursive": recursive,
        "files": files,
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


@router.post("/workspaces/{conversation_id}/git/checkpoint/agent")
async def workspace_agent_checkpoint(
    conversation_id: str,
    request: CheckpointRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from services.git_timeline_service import create_checkpoint, record_artifact_versions

    result = await create_checkpoint(
        conversation_id,
        request.kind,
        request.message or request.kind,
        conversation_id=conversation_id,
        created_by="agent",
        metadata=request.metadata,
        allow_agent_kind=True,
    )
    payload = result.__dict__
    if result.success and request.kind == "artifact_version":
        payload["artifact_versions"] = await record_artifact_versions(
            conversation_id,
            conversation_id,
            result.commit_hash,
            request.artifacts,
            label=request.message or "",
        )
    return payload


@router.post("/workspaces/{conversation_id}/git/milestone/user")
async def workspace_user_milestone(
    conversation_id: str,
    request: CheckpointRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from services.git_timeline_service import create_checkpoint

    result = await create_checkpoint(
        conversation_id,
        "user_milestone",
        request.message or "User milestone",
        conversation_id=conversation_id,
        created_by="user",
        metadata=request.metadata,
    )
    return result.__dict__


@router.post("/workspaces/{conversation_id}/timeline/rollback-preview")
async def workspace_rollback_preview(
    conversation_id: str,
    request: RollbackPreviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from services.git_timeline_service import rollback_preview

    return await rollback_preview(conversation_id, request.turn_id)


@router.post("/workspaces/{conversation_id}/timeline/turns/{turn_id}/edit")
async def workspace_edit_turn(
    conversation_id: str,
    turn_id: str,
    request: TimelineTurnRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from services.git_timeline_service import rollback_turn_for_replay

    actual_conversation_id = request.conversation_id or conversation_id
    result = await rollback_turn_for_replay(actual_conversation_id, conversation_id, turn_id, "edit")
    if request.message is not None and result.get("payload"):
        result["payload"]["message"] = request.message
    return result


@router.post("/workspaces/{conversation_id}/timeline/turns/{turn_id}/retry")
async def workspace_retry_turn(
    conversation_id: str,
    turn_id: str,
    request: TimelineTurnRequest = Body(default_factory=TimelineTurnRequest),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from services.git_timeline_service import rollback_turn_for_replay

    actual_conversation_id = request.conversation_id or conversation_id
    return await rollback_turn_for_replay(actual_conversation_id, conversation_id, turn_id, "retry")


@router.get("/workspaces/{conversation_id}/timeline/git")
async def workspace_git_timeline(
    conversation_id: str,
    limit: int = 80,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from services.git_timeline_service import git_timeline

    return await git_timeline(conversation_id, conversation_id=conversation_id, limit=limit)


@router.get("/workspaces/{conversation_id}/artifacts/{artifact_path:path}/versions")
async def workspace_artifact_versions(
    conversation_id: str,
    artifact_path: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from services.git_timeline_service import artifact_versions

    return await artifact_versions(conversation_id, artifact_path)


@router.post("/workspaces/{conversation_id}/artifacts/{artifact_path:path}/restore-version")
async def workspace_restore_artifact_version(
    conversation_id: str,
    artifact_path: str,
    request: RestoreArtifactVersionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from services.git_timeline_service import restore_artifact_version

    return await restore_artifact_version(conversation_id, artifact_path, request.version)


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


@router.post("/workspaces/{conversation_id}/items")
async def create_workspace_item(
    conversation_id: str,
    request: CreateWorkspaceItemRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = _safe_workspace_child(conversation_id, request.path)
    item_type = request.type.lower()
    try:
        if item_type in {"folder", "directory", "dir"}:
            target.mkdir(parents=True, exist_ok=True)
            return {"status": "created", "type": "folder", "path": request.path}
        if target.exists() and target.is_dir():
            raise HTTPException(status_code=409, detail="A folder already exists at this path")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(request.content or "", encoding="utf-8")
        return {"status": "created", "type": "file", "path": request.path, "size": target.stat().st_size}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/workspaces/{conversation_id}/upload")
async def upload_workspace_files(
    conversation_id: str,
    files: list[UploadFile] = File(...),
    subdir: str = "uploads",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_dir = _safe_workspace_child(conversation_id, subdir or "uploads")
    target_dir.mkdir(parents=True, exist_ok=True)
    root = workspace_root(conversation_id)
    saved: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for upload in files:
        safe_name = Path(upload.filename or "upload.bin").name
        if not safe_name:
            safe_name = "upload.bin"
        target = (target_dir / safe_name).resolve()
        if target != root and root not in target.parents:
            failed.append({"name": safe_name, "error": "Path escape blocked"})
            continue
        try:
            data = await upload.read()
            target.write_bytes(data)
            saved.append(_file_item(root, target))
        except Exception as exc:
            failed.append({"name": safe_name, "error": str(exc)})
    return {"uploaded": saved, "failed": failed, "total": len(files), "successful": len(saved)}


@router.get("/workspaces/{conversation_id}/preview")
async def preview_workspace_file(
    conversation_id: str,
    path: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    root = workspace_root(conversation_id)
    target = _safe_workspace_child(conversation_id, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    if target.is_dir():
        return {"path": path, "type": "folder", "is_directory": True, "children": _iter_workspace_files(root, path, False)}

    stat = target.stat()
    mime, _ = mimetypes.guess_type(target.name)
    ext = target.suffix.lower()
    preview_type = "text" if (mime or "").startswith("text/") or ext in TEXT_PREVIEW_EXTENSIONS else "binary"
    if (mime or "").startswith("image/"):
        preview_type = "image"
    elif mime == "application/pdf" or ext == ".pdf":
        preview_type = "pdf"
    elif ext in {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}:
        preview_type = "office"

    content = ""
    encoding = ""
    truncated = False
    if preview_type == "text":
        data = target.read_bytes()
        truncated = len(data) > MAX_PREVIEW_BYTES
        content = data[:MAX_PREVIEW_BYTES].decode("utf-8", errors="replace")
        encoding = "utf-8"
    elif preview_type == "image" and stat.st_size <= MAX_PREVIEW_BYTES:
        content = base64.b64encode(target.read_bytes()).decode("ascii")
        encoding = "base64"

    return {
        "path": path,
        "name": target.name,
        "type": preview_type,
        "mime_type": mime or "application/octet-stream",
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "encoding": encoding,
        "content": content,
        "truncated": truncated,
    }


@router.get("/workspaces/{conversation_id}/document")
async def document_preview(
    conversation_id: str,
    path: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Structured preview for PDF / DOCX / XLSX / PPTX (artifact renderers)."""
    from services import document_preview as dp

    target = _safe_workspace_child(conversation_id, path)
    if not target.is_file():
        return dp.error("FILE_NOT_FOUND", f"File not found: {path}", recoverable=False)
    ext = target.suffix.lower()
    try:
        if ext == ".pdf":
            return dp.preview_pdf(target)
        if ext == ".docx":
            return dp.preview_docx(target)
        if ext == ".xlsx":
            return dp.preview_xlsx(target)
        if ext == ".pptx":
            return dp.preview_pptx(target)
        return dp.error("UNSUPPORTED_DOCUMENT", f"No structured preview for {ext or 'file'}", recoverable=False)
    except Exception as exc:
        logger.error(f"Document preview failed for {path}: {exc}")
        return dp.error(
            "OFFICE_PREVIEW_FAILED",
            f"Could not convert preview: {exc}",
            recoverable=True,
            suggested_action="fallback_to_text_extract",
        )


@router.get("/workspaces/{conversation_id}/document/page")
async def document_page(
    conversation_id: str,
    path: str,
    page: int = 0,
    scale: float = 1.5,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Render a single PDF page to a PNG data URL on demand."""
    from services import document_preview as dp

    target = _safe_workspace_child(conversation_id, path)
    if not target.is_file():
        return dp.error("FILE_NOT_FOUND", f"File not found: {path}", recoverable=False)
    try:
        return dp.render_pdf_page(target, page, scale)
    except Exception as exc:
        logger.error(f"PDF page render failed for {path} p{page}: {exc}")
        return dp.error("PDF_RENDER_FAILED", f"Could not render page: {exc}", recoverable=True)


@router.get("/workspaces/{conversation_id}/files/{path:path}")
async def read_workspace_file(
    conversation_id: str,
    path: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Read a file from the workspace."""
    try:
        target = _safe_workspace_child(conversation_id, path)
        if not target.is_file():
            raise FileNotFoundError(path)
        content = target.read_bytes()

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
    try:
        target = _safe_workspace_child(conversation_id, request.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(request.content, encoding="utf-8")

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
    try:
        target = _safe_workspace_child(conversation_id, path)
        if not target.is_file():
            raise FileNotFoundError(path)
        target.unlink()

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


# ── PPT deck version history / rollback ──────────────────────────────────────
@router.get("/workspaces/{conversation_id}/presentations/versions")
async def presentation_versions(
    conversation_id: str,
    deck_path: str,
    user: User = Depends(get_current_user),
):
    """List a generated deck's saved versions (for the Workbench history UI)."""
    from ppt_engine.engine import list_deck_versions

    ws = workspace_root(conversation_id)
    try:
        versions = list_deck_versions(str(ws), deck_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"success": True, "versions": versions}


@router.post("/workspaces/{conversation_id}/presentations/revert")
async def presentation_revert(
    conversation_id: str,
    payload: dict[str, Any] = Body(...),
    user: User = Depends(get_current_user),
):
    """Roll a deck back to a saved version directly from the Workbench (no agent)."""
    import asyncio

    from ppt_engine.engine import restore_deck_version

    deck_path = str(payload.get("deck_path") or "").strip()
    version_id = str(payload.get("version_id") or "").strip()
    if not deck_path or not version_id:
        raise HTTPException(status_code=400, detail="deck_path and version_id are required")
    ws = workspace_root(conversation_id)
    try:
        result = await asyncio.to_thread(
            lambda: restore_deck_version(str(ws), deck_path, version_id, visual_qa=True))
    except (FileNotFoundError, KeyError):
        raise HTTPException(status_code=404, detail=f"version {version_id} not found")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"success": True, "manifest": result.model_dump(mode="json")}
