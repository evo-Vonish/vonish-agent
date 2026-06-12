"""Hidden Shadow Git timeline for workspace rollback/checkpoints."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from core.config import settings
from db.models import ArtifactVersionRecord, Conversation, ConversationBranch, GitCommitRecord, Message, TurnGitState
from db.session import get_session_maker
from services.git_runtime import GitRuntimeManager


AGENT_ALLOWED_CHECKPOINT_KINDS = {"agent_milestone", "artifact_version", "handoff_checkpoint"}
SYSTEM_CHECKPOINT_KINDS = {"system_auto", "user_milestone", "rollback_restore", "crash_checkpoint"}
EXCLUDED_DIRS = {
    ".git",
    ".vonish",
    ".workspace",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
}


@dataclass
class CheckpointResult:
    success: bool
    workspace_id: str
    commit_hash: str = ""
    short_hash: str = ""
    kind: str = ""
    message: str = ""
    shadow_path: str = ""
    changed: bool = False
    error: str = ""
    record_id: str = ""


def workspace_path(workspace_id: str) -> Path:
    raw = (workspace_id or "").strip()
    if not raw or raw == "current":
        raise ValueError("workspace_id is required")
    base = Path(settings.workspace_root).resolve()
    root = (base / raw).resolve()
    if root != base and base not in root.parents:
        raise ValueError("workspace path escape blocked")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _shadow_root(root: Path) -> Path:
    return root / ".vonish" / "shadow_worktree"


def _shadow_home(root: Path) -> Path:
    return root / ".vonish" / "git_home"


def _is_excluded(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in EXCLUDED_DIRS for part in parts)


def _clean_shadow(shadow: Path) -> None:
    shadow.mkdir(parents=True, exist_ok=True)
    for item in shadow.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


def _copy_workspace_to_shadow(root: Path, shadow: Path) -> list[str]:
    _clean_shadow(shadow)
    copied: list[str] = []
    for source in root.rglob("*"):
        if not source.is_file() or _is_excluded(source, root):
            continue
        rel = source.relative_to(root)
        target = shadow / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(str(rel).replace("\\", "/"))
    return copied


def _copy_shadow_to_workspace(root: Path, shadow: Path) -> list[str]:
    restored: list[str] = []
    for item in root.iterdir():
        if item.name in EXCLUDED_DIRS:
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)
    for source in shadow.rglob("*"):
        if not source.is_file() or ".git" in source.relative_to(shadow).parts:
            continue
        rel = source.relative_to(shadow)
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        restored.append(str(rel).replace("\\", "/"))
    return restored


async def _git(root: Path, args: list[str], timeout: float = 30.0) -> tuple[int, str, str]:
    return await GitRuntimeManager.run(args, cwd=root, timeout=timeout, home=_shadow_home(root.parent.parent if root.name == "shadow_worktree" else root))


async def ensure_shadow_repo(workspace_id: str) -> dict[str, Any]:
    root = workspace_path(workspace_id)
    shadow = _shadow_root(root)
    shadow.mkdir(parents=True, exist_ok=True)
    runtime = await GitRuntimeManager.detect()
    if not runtime.available:
        return {"success": False, "workspace_id": workspace_id, "git_runtime": runtime.__dict__, "error": runtime.error}
    if not (shadow / ".git").exists():
        code, stdout, stderr = await GitRuntimeManager.run(["init"], cwd=shadow, timeout=10.0, home=_shadow_home(root))
        if code != 0:
            return {"success": False, "workspace_id": workspace_id, "error": stderr or stdout}
    await GitRuntimeManager.run(["config", "user.name", "VonishAgent Runtime"], cwd=shadow, timeout=5.0, home=_shadow_home(root))
    await GitRuntimeManager.run(["config", "user.email", "runtime@vonish.local"], cwd=shadow, timeout=5.0, home=_shadow_home(root))
    await GitRuntimeManager.run(["config", "commit.gpgsign", "false"], cwd=shadow, timeout=5.0, home=_shadow_home(root))
    return {
        "success": True,
        "workspace_id": workspace_id,
        "workspace_path": str(root),
        "shadow_path": str(shadow),
        "git_runtime": runtime.__dict__,
    }


async def create_checkpoint(
    workspace_id: str,
    kind: str,
    message: str,
    *,
    conversation_id: str | None = None,
    turn_id: str | None = None,
    created_by: str = "system",
    metadata: dict[str, Any] | None = None,
    allow_agent_kind: bool = False,
) -> CheckpointResult:
    if allow_agent_kind and kind not in AGENT_ALLOWED_CHECKPOINT_KINDS:
        return CheckpointResult(False, workspace_id, kind=kind, error=f"Agent cannot create checkpoint kind: {kind}")
    if not allow_agent_kind and kind not in SYSTEM_CHECKPOINT_KINDS and kind not in AGENT_ALLOWED_CHECKPOINT_KINDS:
        return CheckpointResult(False, workspace_id, kind=kind, error=f"Unsupported checkpoint kind: {kind}")

    root = workspace_path(workspace_id)
    ensured = await ensure_shadow_repo(workspace_id)
    if not ensured.get("success"):
        return CheckpointResult(False, workspace_id, kind=kind, error=str(ensured.get("error") or "Git unavailable"))
    shadow = _shadow_root(root)
    copied = await asyncio.to_thread(_copy_workspace_to_shadow, root, shadow)
    await GitRuntimeManager.run(["add", "-A"], cwd=shadow, timeout=30.0, home=_shadow_home(root))
    safe_message = (message or kind).strip()[:240] or kind
    commit_message = f"{kind}: {safe_message}"
    meta = {**(metadata or {}), "files": copied[:500], "file_count": len(copied)}
    commit_body = json.dumps(meta, ensure_ascii=False, default=str)[:8000]
    code, stdout, stderr = await GitRuntimeManager.run(
        ["commit", "--allow-empty", "-m", commit_message, "-m", commit_body],
        cwd=shadow,
        timeout=30.0,
        home=_shadow_home(root),
    )
    if code != 0:
        return CheckpointResult(False, workspace_id, kind=kind, message=safe_message, shadow_path=str(shadow), error=stderr or stdout)
    hash_code, commit_hash, hash_err = await GitRuntimeManager.run(["rev-parse", "HEAD"], cwd=shadow, timeout=5.0, home=_shadow_home(root))
    if hash_code != 0:
        return CheckpointResult(False, workspace_id, kind=kind, message=safe_message, shadow_path=str(shadow), error=hash_err or commit_hash)
    commit_hash = commit_hash.strip()
    record_id = ""
    session_maker = get_session_maker()
    async with session_maker() as db:
        record = GitCommitRecord(
            workspace_id=workspace_id,
            conversation_id=uuid.UUID(conversation_id) if conversation_id else None,
            turn_id=uuid.UUID(turn_id) if turn_id else None,
            commit_hash=commit_hash,
            short_hash=commit_hash[:10],
            kind=kind,
            message=safe_message,
            created_by=created_by,
            shadow_path=str(shadow),
            metadata_=meta,
        )
        db.add(record)
        await db.flush()
        record_id = str(record.id)
        await db.commit()
    return CheckpointResult(
        True,
        workspace_id,
        commit_hash=commit_hash,
        short_hash=commit_hash[:10],
        kind=kind,
        message=safe_message,
        shadow_path=str(shadow),
        changed=True,
        record_id=record_id,
    )


async def record_turn_start(conversation_id: str, workspace_id: str, turn_id: str, message_preview: str = "") -> dict[str, Any]:
    cp = await create_checkpoint(
        workspace_id,
        "system_auto",
        f"before turn {turn_id}",
        conversation_id=conversation_id,
        turn_id=turn_id,
        created_by="system",
        metadata={"phase": "before_turn", "message_preview": message_preview[:500]},
    )
    if not cp.success:
        return cp.__dict__
    session_maker = get_session_maker()
    async with session_maker() as db:
        state = TurnGitState(
            conversation_id=uuid.UUID(conversation_id),
            workspace_id=workspace_id,
            turn_id=uuid.UUID(turn_id),
            before_commit_hash=cp.commit_hash,
            status="running",
        )
        db.add(state)
        await db.commit()
    return cp.__dict__


async def record_turn_end(conversation_id: str, workspace_id: str, turn_id: str, status: str = "completed") -> dict[str, Any]:
    kind = "crash_checkpoint" if status in {"failed", "crashed"} else "system_auto"
    cp = await create_checkpoint(
        workspace_id,
        kind,
        f"{status} turn {turn_id}",
        conversation_id=conversation_id,
        turn_id=turn_id,
        created_by="system",
        metadata={"phase": "after_turn", "status": status},
    )
    session_maker = get_session_maker()
    async with session_maker() as db:
        row = (await db.execute(
            select(TurnGitState).where(TurnGitState.turn_id == uuid.UUID(turn_id)).order_by(TurnGitState.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        if row:
            row.after_commit_hash = cp.commit_hash if cp.success else row.after_commit_hash
            row.status = status
            row.completed_at = datetime.now(timezone.utc)
            await db.commit()
    return cp.__dict__


async def restore_checkpoint(workspace_id: str, commit_hash: str, reason: str = "rollback") -> dict[str, Any]:
    root = workspace_path(workspace_id)
    ensured = await ensure_shadow_repo(workspace_id)
    if not ensured.get("success"):
        return {"success": False, "error": ensured.get("error")}
    shadow = _shadow_root(root)
    code, stdout, stderr = await GitRuntimeManager.run(["checkout", "--force", commit_hash, "--", "."], cwd=shadow, timeout=30.0, home=_shadow_home(root))
    if code != 0:
        return {"success": False, "error": stderr or stdout}
    restored = await asyncio.to_thread(_copy_shadow_to_workspace, root, shadow)
    cp = await create_checkpoint(
        workspace_id,
        "rollback_restore",
        reason,
        created_by="system",
        metadata={"restored_from": commit_hash, "restored_files": restored[:500], "file_count": len(restored)},
    )
    return {"success": True, "workspace_id": workspace_id, "restored_from": commit_hash, "files": restored, "restore_checkpoint": cp.__dict__}


async def rollback_preview(workspace_id: str, turn_id: str) -> dict[str, Any]:
    state = await _turn_state(turn_id)
    if not state:
        return {"success": False, "error": "No git state for turn"}
    return {
        "success": True,
        "workspace_id": workspace_id,
        "turn_id": turn_id,
        "target_commit": state.before_commit_hash,
        "after_commit": state.after_commit_hash,
        "status": state.status,
    }


async def _turn_state(turn_id: str) -> TurnGitState | None:
    session_maker = get_session_maker()
    async with session_maker() as db:
        return (await db.execute(
            select(TurnGitState).where(TurnGitState.turn_id == uuid.UUID(turn_id)).order_by(TurnGitState.created_at.desc()).limit(1)
        )).scalar_one_or_none()


def _message_payload(message: Message) -> dict[str, Any]:
    text = ""
    files: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    for block in message.content if isinstance(message.content, list) else []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = str(block.get("text") or "")
        elif block.get("type") == "files" and isinstance(block.get("files"), list):
            files = block.get("files") or []
        elif block.get("type") == "references" and isinstance(block.get("references"), list):
            references = block.get("references") or []
    return {"message": text, "resources": files, "references": references}


async def rollback_turn_for_replay(conversation_id: str, workspace_id: str, turn_id: str, mode: str) -> dict[str, Any]:
    state = await _turn_state(turn_id)
    if not state or not state.before_commit_hash:
        return {"success": False, "error": "No checkpoint for turn", "turn_id": turn_id}

    session_maker = get_session_maker()
    async with session_maker() as db:
        conv = (await db.execute(select(Conversation).where(Conversation.id == uuid.UUID(conversation_id)))).scalar_one_or_none()
        msg = (await db.execute(select(Message).where(Message.id == uuid.UUID(turn_id)))).scalar_one_or_none()
        if not conv or not msg:
            return {"success": False, "error": "Conversation or message not found"}
        messages = (await db.execute(
            select(Message)
            .where(Message.conversation_id == uuid.UUID(conversation_id))
            .order_by(Message.created_at.asc())
        )).scalars().all()
        archive_started = False
        archive_ids: list[str] = []
        for item in messages:
            if str(item.id) == turn_id:
                archive_started = True
            if archive_started:
                archive_ids.append(str(item.id))
        payload = _message_payload(msg)

    restored = await restore_checkpoint(workspace_id, state.before_commit_hash, reason=f"{mode} turn {turn_id}")
    if not restored.get("success"):
        return {"success": False, "error": restored.get("error") or "Workspace restore failed", "rollback": restored}

    async with session_maker() as db:
        conv = (await db.execute(select(Conversation).where(Conversation.id == uuid.UUID(conversation_id)))).scalar_one_or_none()
        if not conv:
            return {"success": False, "error": "Conversation not found after restore"}
        meta = dict(conv.metadata_ or {})
        archived = list(dict.fromkeys([*(meta.get("archived_message_ids") or []), *archive_ids]))
        branch = ConversationBranch(
            conversation_id=uuid.UUID(conversation_id),
            parent_turn_id=uuid.UUID(turn_id),
            branch_type=mode,
            archived_message_ids=archive_ids,
            metadata_={"workspace_id": workspace_id},
        )
        db.add(branch)
        meta["archived_message_ids"] = archived
        conv.metadata_ = meta
        await db.commit()
    return {
        "success": True,
        "mode": mode,
        "conversation_id": conversation_id,
        "workspace_id": workspace_id,
        "turn_id": turn_id,
        "archived_message_ids": archive_ids,
        "payload": payload,
        "rollback": restored,
    }


async def git_timeline(workspace_id: str, conversation_id: str | None = None, limit: int = 80) -> dict[str, Any]:
    session_maker = get_session_maker()
    async with session_maker() as db:
        query = select(GitCommitRecord).where(GitCommitRecord.workspace_id == workspace_id)
        if conversation_id:
            query = query.where(GitCommitRecord.conversation_id == uuid.UUID(conversation_id))
        rows = (await db.execute(query.order_by(GitCommitRecord.created_at.desc()).limit(max(1, min(limit, 200))))).scalars().all()
    return {
        "workspace_id": workspace_id,
        "commits": [
            {
                "id": str(row.id),
                "commit_hash": row.commit_hash,
                "short_hash": row.short_hash,
                "kind": row.kind,
                "message": row.message,
                "created_by": row.created_by,
                "conversation_id": str(row.conversation_id) if row.conversation_id else None,
                "turn_id": str(row.turn_id) if row.turn_id else None,
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "metadata": row.metadata_ or {},
            }
            for row in rows
        ],
    }


async def record_artifact_versions(workspace_id: str, conversation_id: str, commit_hash: str, paths: list[str], label: str = "") -> list[dict[str, Any]]:
    if not paths:
        return []
    session_maker = get_session_maker()
    async with session_maker() as db:
        existing = (await db.execute(
            select(ArtifactVersionRecord).where(ArtifactVersionRecord.workspace_id == workspace_id)
        )).scalars().all()
        versions_by_path: dict[str, int] = {}
        for row in existing:
            versions_by_path[row.artifact_path] = max(versions_by_path.get(row.artifact_path, 0), row.version)
        created: list[dict[str, Any]] = []
        for path in paths:
            clean = str(path).replace("\\", "/").strip().lstrip("/")
            if not clean:
                continue
            version = versions_by_path.get(clean, 0) + 1
            record = ArtifactVersionRecord(
                workspace_id=workspace_id,
                conversation_id=uuid.UUID(conversation_id),
                artifact_path=clean,
                version=version,
                label=label or f"V{version}",
                commit_hash=commit_hash,
            )
            db.add(record)
            created.append({"path": clean, "version": version, "label": record.label, "commit_hash": commit_hash})
        await db.commit()
    return created


async def artifact_versions(workspace_id: str, artifact_path: str) -> dict[str, Any]:
    clean = artifact_path.replace("\\", "/").strip().lstrip("/")
    session_maker = get_session_maker()
    async with session_maker() as db:
        rows = (await db.execute(
            select(ArtifactVersionRecord)
            .where(ArtifactVersionRecord.workspace_id == workspace_id)
            .where(ArtifactVersionRecord.artifact_path == clean)
            .order_by(ArtifactVersionRecord.version.desc())
        )).scalars().all()
    return {
        "workspace_id": workspace_id,
        "artifact_path": clean,
        "versions": [
            {
                "id": str(row.id),
                "version": row.version,
                "label": row.label,
                "commit_hash": row.commit_hash,
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
            for row in rows
        ],
    }


async def restore_artifact_version(workspace_id: str, artifact_path: str, version: int) -> dict[str, Any]:
    clean = artifact_path.replace("\\", "/").strip().lstrip("/")
    session_maker = get_session_maker()
    async with session_maker() as db:
        row = (await db.execute(
            select(ArtifactVersionRecord)
            .where(ArtifactVersionRecord.workspace_id == workspace_id)
            .where(ArtifactVersionRecord.artifact_path == clean)
            .where(ArtifactVersionRecord.version == int(version))
        )).scalar_one_or_none()
    if not row:
        return {"success": False, "error": "Artifact version not found"}
    root = workspace_path(workspace_id)
    shadow = _shadow_root(root)
    ensured = await ensure_shadow_repo(workspace_id)
    if not ensured.get("success"):
        return {"success": False, "error": ensured.get("error")}
    code, stdout, stderr = await GitRuntimeManager.run(["checkout", row.commit_hash, "--", clean], cwd=shadow, timeout=20.0, home=_shadow_home(root))
    if code != 0:
        return {"success": False, "error": stderr or stdout}
    source = shadow / clean
    if not source.is_file():
        return {"success": False, "error": "Versioned file not found in shadow repo"}
    target = root / clean
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    cp = await create_checkpoint(
        workspace_id,
        "rollback_restore",
        f"restore {clean} V{version}",
        created_by="system",
        metadata={"artifact_path": clean, "version": version, "commit_hash": row.commit_hash},
    )
    return {"success": True, "artifact_path": clean, "version": version, "checkpoint": cp.__dict__}


def stable_artifact_id(path: str) -> str:
    clean = path.replace("\\", "/").strip().lstrip("/")
    digest = hashlib.sha1(clean.encode("utf-8")).hexdigest()[:12]
    return f"artifact_{digest}"
