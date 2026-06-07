"""Conversation CRUD API routes — backed by SQLite via SQLAlchemy ORM."""

from __future__ import annotations

import html
import re
import uuid as uuid_lib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.auth import User, get_current_user
from core.logging import get_logger
from db.models import Conversation, Message
from db.session import get_db

logger = get_logger(__name__)

router = APIRouter(prefix="/api")

# Fixed mock user UUID (matches mock User.id = "mock-user-001")
_MOCK_USER_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000001")


def _user_uuid(user: User) -> UUID:
    """Convert mock user id to a UUID for DB queries."""
    return _MOCK_USER_UUID


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class CreateConversationRequest(BaseModel):
    title: str = Field(default="新对话")
    model: str = Field(default="deepseek-v4-pro")
    context_profile: str = Field(default="balanced")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationResponse(BaseModel):
    id: str
    title: str
    model: str
    context_profile: str
    created_at: str
    updated_at: str
    message_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationListResponse(BaseModel):
    conversations: list[ConversationResponse]
    total: int


class SummarizeTitleRequest(BaseModel):
    model: str = Field(default="deepseek-v4-pro")


class SummarizeTitleResponse(BaseModel):
    title: str


class RenameProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    directory_path: str | None = Field(default=None)
    model: str = Field(default="deepseek-v4-pro")
    first_conversation_title: str = Field(default="新对话")


class ProjectResponse(BaseModel):
    id: str
    name: str
    conversation_count: int
    updated_at: str = ""
    workspace_id: str | None = None
    workspace_path: str | None = None
    directory_path: str | None = None
    first_conversation: ConversationResponse | None = None


def _conv_to_response(conv: Conversation, msg_count: int = 0) -> ConversationResponse:
    return ConversationResponse(
        id=str(conv.id),
        title=conv.title,
        model=conv.model,
        context_profile=conv.context_profile,
        created_at=conv.created_at.isoformat() if conv.created_at else "",
        updated_at=conv.updated_at.isoformat() if conv.updated_at else "",
        message_count=msg_count,
        metadata=conv.metadata_ or {},
    )


async def _delete_conversation_workspace(conversation_id: str) -> None:
    import asyncio
    import shutil
    from pathlib import Path
    from core.config import settings

    ws_path = Path(settings.workspace_root) / conversation_id
    if ws_path.exists():
        await asyncio.to_thread(shutil.rmtree, ws_path, ignore_errors=True)
        logger.info(f"Cleaned workspace: {ws_path}")


def _project_id(conv: Conversation) -> str:
    return str((conv.metadata_ or {}).get("project_id") or "")


def _project_name(conv: Conversation) -> str:
    meta = conv.metadata_ or {}
    return str(meta.get("project_name") or meta.get("project_id") or "")


def _project_workspace_id(conv: Conversation) -> str:
    meta = conv.metadata_ or {}
    return str(meta.get("workspace_id") or meta.get("project_id") or "")


def _project_directory_path(conv: Conversation) -> str:
    meta = conv.metadata_ or {}
    return str(meta.get("directory_path") or "")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    request: CreateConversationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    meta = dict(request.metadata or {})
    workspace_id = str(meta.get("workspace_id") or meta.get("project_id") or "")
    workspace_path = f"/workspaces/{user.id}/{uuid_lib.uuid4()}"
    if workspace_id:
        from services.git_service import ensure_workspace, workspace_root

        await ensure_workspace(workspace_id, init_git=True)
        workspace_path = str(workspace_root(workspace_id))
        meta["workspace_id"] = workspace_id
    conv = Conversation(
        user_id=_user_uuid(user),
        title=request.title,
        model=request.model,
        context_profile=request.context_profile,
        workspace_path=workspace_path,
        metadata_=meta,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    logger.info(f"Created conversation: {conv.id}")
    return _conv_to_response(conv, 0)


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    uid = _user_uuid(user)
    # Count total
    count_q = select(func.count(Conversation.id)).where(Conversation.user_id == uid)
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch page with message count
    q = (
        select(Conversation)
        .where(Conversation.user_id == uid)
        .order_by(Conversation.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(q)).scalars().all()

    # Get message counts in one query
    msg_counts: dict[UUID, int] = {}
    if rows:
        from sqlalchemy import case
        counts_q = (
            select(Message.conversation_id, func.count(Message.id))
            .where(Message.conversation_id.in_([r.id for r in rows]))
            .group_by(Message.conversation_id)
        )
        for cid, cnt in (await db.execute(counts_q)).all():
            msg_counts[cid] = cnt

    convs = [
        _conv_to_response(c, msg_counts.get(c.id, 0))
        for c in rows
    ]
    return ConversationListResponse(conversations=convs, total=total)


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    uid = _user_uuid(user)
    rows = (await db.execute(
        select(Conversation).where(Conversation.user_id == uid).order_by(Conversation.updated_at.desc())
    )).scalars().all()
    grouped: dict[str, ProjectResponse] = {}
    for conv in rows:
        pid = _project_id(conv)
        if not pid:
            continue
        item = grouped.get(pid)
        updated = conv.updated_at.isoformat() if conv.updated_at else ""
        if item is None:
            grouped[pid] = ProjectResponse(
                id=pid,
                name=_project_name(conv) or pid,
                conversation_count=1,
                updated_at=updated,
                workspace_id=_project_workspace_id(conv) or pid,
                workspace_path=conv.workspace_path,
                directory_path=_project_directory_path(conv) or None,
            )
        else:
            item.conversation_count += 1
            if updated > item.updated_at:
                item.updated_at = updated
    return sorted(grouped.values(), key=lambda item: item.updated_at, reverse=True)


@router.post("/projects", response_model=ProjectResponse)
async def create_project(
    request: CreateProjectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from services.git_service import ensure_workspace, workspace_root

    name = request.name.strip()
    raw_slug = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-").lower() or "project"
    project_id = f"project-{raw_slug[:36]}-{uuid_lib.uuid4().hex[:8]}"
    workspace_id = project_id
    workspace = workspace_root(workspace_id)
    await ensure_workspace(workspace_id, init_git=True)
    marker_dir = workspace / ".workspace"
    marker_dir.mkdir(parents=True, exist_ok=True)
    (marker_dir / "project.json").write_text(
        __import__("json").dumps(
            {
                "project_id": project_id,
                "project_name": name,
                "workspace_id": workspace_id,
                "directory_path": request.directory_path or "",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    conv = Conversation(
        user_id=_user_uuid(user),
        title=request.first_conversation_title.strip() or "新对话",
        model=request.model,
        context_profile="balanced",
        workspace_path=str(workspace),
        metadata_={
            "project_id": project_id,
            "project_name": name,
            "workspace_id": workspace_id,
            "directory_path": request.directory_path or "",
        },
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return ProjectResponse(
        id=project_id,
        name=name,
        conversation_count=1,
        updated_at=conv.updated_at.isoformat() if conv.updated_at else "",
        workspace_id=workspace_id,
        workspace_path=str(workspace),
        directory_path=request.directory_path or None,
        first_conversation=_conv_to_response(conv, 0),
    )


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def rename_project(
    project_id: str,
    request: RenameProjectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    uid = _user_uuid(user)
    rows = (await db.execute(select(Conversation).where(Conversation.user_id == uid))).scalars().all()
    matched = [conv for conv in rows if _project_id(conv) == project_id]
    if not matched:
        raise HTTPException(status_code=404, detail="Project not found")
    now = datetime.now(timezone.utc)
    for conv in matched:
        meta = dict(conv.metadata_ or {})
        meta["project_id"] = project_id
        meta["project_name"] = request.name.strip()
        conv.metadata_ = meta
        conv.updated_at = now
    await db.commit()
    return ProjectResponse(
        id=project_id,
        name=request.name.strip(),
        conversation_count=len(matched),
        updated_at=now.isoformat(),
        workspace_id=_project_workspace_id(matched[0]) or project_id,
        workspace_path=matched[0].workspace_path,
        directory_path=_project_directory_path(matched[0]) or None,
    )


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    import asyncio
    import shutil
    from core.config import settings

    uid = _user_uuid(user)
    rows = (await db.execute(select(Conversation).where(Conversation.user_id == uid))).scalars().all()
    matched = [conv for conv in rows if _project_id(conv) == project_id]
    workspace_ids = {
        _project_workspace_id(conv) or project_id
        for conv in matched
        if (_project_workspace_id(conv) or project_id)
    }
    for conv in matched:
        await db.delete(conv)
    await db.commit()
    base = Path(settings.workspace_root).resolve()
    for workspace_id in workspace_ids:
        target = (base / workspace_id).resolve()
        if target == base or base not in target.parents:
            continue
        if target.exists():
            await asyncio.to_thread(shutil.rmtree, target, ignore_errors=True)
    return {"status": "deleted", "project_id": project_id, "conversation_count": len(matched)}


@router.delete("/conversations-all")
async def delete_all_conversations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    import asyncio
    import shutil
    from core.config import settings

    uid = _user_uuid(user)
    rows = (await db.execute(select(Conversation).where(Conversation.user_id == uid))).scalars().all()
    base = Path(settings.workspace_root).resolve()
    project_workspace_ids = {
        _project_workspace_id(conv)
        for conv in rows
        if _project_workspace_id(conv)
    }
    for conv in rows:
        await db.delete(conv)
        await _delete_conversation_workspace(str(conv.id))
    await db.commit()
    for workspace_id in project_workspace_ids:
        target = (base / workspace_id).resolve()
        if target == base or base not in target.parents:
            continue
        if target.exists():
            await asyncio.to_thread(shutil.rmtree, target, ignore_errors=True)
    return {"status": "deleted", "conversation_count": len(rows)}


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(Conversation).where(Conversation.id == UUID(conversation_id))
    conv = (await db.execute(q)).scalar()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    cnt_q = select(func.count(Message.id)).where(Message.conversation_id == conv.id)
    msg_count = (await db.execute(cnt_q)).scalar() or 0
    return _conv_to_response(conv, msg_count)


@router.post("/conversations/{conversation_id}/summarize-title", response_model=SummarizeTitleResponse)
async def summarize_title(
    conversation_id: str,
    request: SummarizeTitleRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from services.llm_summary_service import summarize_conversation_title

    conv_id = UUID(conversation_id)
    q = select(Conversation).where(Conversation.id == conv_id)
    conv = (await db.execute(q)).scalar()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs_q = (
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at.asc())
        .limit(4)
    )
    msgs = (await db.execute(msgs_q)).scalars().all()
    msg_data = [
        {"role": m.role, "content": _extract_text(m.content)}
        for m in msgs
    ]

    title = await summarize_conversation_title(
        db=db, user_id=user.id, model=request.model, messages=msg_data
    )
    conv.title = title
    await db.commit()
    return SummarizeTitleResponse(title=title)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv_id = UUID(conversation_id)
    q = select(Conversation).where(Conversation.id == conv_id)
    conv = (await db.execute(q)).scalar()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await db.delete(conv)
    await db.commit()

    # Clean up workspace directory on disk
    await _delete_conversation_workspace(conversation_id)

    logger.info(f"Deleted conversation: {conversation_id}")
    return {"status": "deleted", "conversation_id": conversation_id}


@router.post("/conversations/{conversation_id}/clear")
async def clear_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv_id = UUID(conversation_id)
    q = select(Conversation).where(Conversation.id == conv_id)
    conv = (await db.execute(q)).scalar()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    del_q = delete(Message).where(Message.conversation_id == conv_id)
    await db.execute(del_q)
    conv.updated_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info(f"Cleared conversation: {conversation_id}")
    return {"status": "cleared", "conversation_id": conversation_id}


# ---------------------------------------------------------------------------
# Messages Endpoint
# ---------------------------------------------------------------------------


class MessageItem(BaseModel):
    role: str
    content: str
    thinking: str | None = None
    segments: list[dict[str, Any]] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    files: list[dict[str, Any]] | None = None
    references: list[dict[str, Any]] | None = None
    timestamp: str


class MessagesResponse(BaseModel):
    messages: list[MessageItem]
    conversation_id: str


class SearchMatch(BaseModel):
    message_id: str
    role: str
    snippet: str
    highlight_ranges: list[list[int]] = Field(default_factory=list)


class ConversationSearchResult(BaseModel):
    conversation_id: str
    title: str
    updated_at: str
    matches: list[SearchMatch]


class ConversationSearchResponse(BaseModel):
    results: list[ConversationSearchResult]
    total: int


def _extract_text(content: Any) -> str:
    """Extract plain text from content blocks, segments, or return string directly."""
    try:
        return _extract_text_unsafe(content)
    except Exception:
        logger.exception(f"_extract_text crashed for content type={type(content).__name__}")
        return str(content) if content else ""


def _extract_text_unsafe(content: Any) -> str:
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for block in content:
            try:
                if not isinstance(block, dict):
                    continue
                btype = str(block.get("type", ""))
                if btype == "text":
                    texts.append(str(block.get("text", "")))
                elif btype == "files":
                    files = block.get("files")
                    if isinstance(files, list):
                        for file in files:
                            if isinstance(file, dict):
                                name = file.get("originalName") or file.get("title") or file.get("workspacePath") or "file"
                                path = file.get("workspacePath") or file.get("uri") or ""
                                texts.append(f"[文件] {name} {path}")
                elif btype == "references":
                    refs = block.get("references")
                    if isinstance(refs, list):
                        for ref in refs:
                            if isinstance(ref, dict):
                                title = ref.get("title") or ref.get("sourceType") or "reference"
                                preview = str(ref.get("preview") or "")[:1200]
                                texts.append(f"[引用] {title}\n{preview}")
                elif btype == "segments":
                    segs = block.get("segments")
                    if not isinstance(segs, list):
                        continue
                    for seg in segs:
                        if not isinstance(seg, dict):
                            continue
                        try:
                            stype = str(seg.get("type", ""))
                            if stype == "text":
                                texts.append(str(seg.get("content", "")))
                            elif stype == "thinking":
                                texts.append(f"[思考] {str(seg.get('content', ''))}")
                            elif stype == "tool":
                                tc = seg.get("tool")
                                if isinstance(tc, dict):
                                    _append_tool_result(texts, tc)
                            elif stype == "execution":
                                exe = seg.get("execution")
                                if isinstance(exe, dict):
                                    summary = exe.get("summary")
                                    if summary:
                                        texts.append(f"[区间] {str(summary)}")
                                    # Recurse into execution steps
                                    steps = exe.get("steps")
                                    if isinstance(steps, list):
                                        for step in steps:
                                            if isinstance(step, dict):
                                                _append_step(texts, step)
                        except Exception:
                            continue
                elif btype == "tool_calls":
                    tcs = block.get("tool_calls")
                    if isinstance(tcs, list):
                        for tc in tcs:
                            if isinstance(tc, dict):
                                _append_tool_result(texts, tc)
            except Exception:
                continue
        return "\n\n".join(t for t in texts if t.strip())
    return str(content)


def _append_tool_result(texts: list[str], tc: dict) -> None:
    tname = str(tc.get("name", ""))
    tstatus = str(tc.get("status", ""))
    if tstatus == "success":
        tresult = tc.get("result")
        if tresult is not None:
            texts.append(f"[工具 {tname}] {str(tresult)[:500]}")
        else:
            texts.append(f"[工具 {tname}] (empty result)")
    elif tstatus == "error":
        texts.append(f"[工具 {tname} 失败] {str(tc.get('error', ''))}")
    elif tstatus == "running":
        texts.append(f"[工具 {tname}] (interrupted)")
    else:
        texts.append(f"[工具调用] {tname}")


def _append_step(texts: list[str], step: dict) -> None:
    st = str(step.get("type", ""))
    title = str(step.get("title", ""))
    content = str(step.get("content", "") or "")
    output = str(step.get("outputPreview", "") or "")
    body = output or content
    body_short = body[:300] if body else ""

    if st == "tool_call":
        tn = str(step.get("toolName", ""))
        texts.append(f"[工具 {tn}: {title}] {body_short}")
    elif st == "thinking":
        texts.append(f"[思考: {title}] {body_short}")
    elif st == "command":
        texts.append(f"[命令: {title}] {body_short}")
    elif st in ("file_read", "file_write", "file_edit"):
        texts.append(f"[文件: {title}] {body_short}")
    elif st in ("web_search", "web_fetch"):
        texts.append(f"[网页: {title}] {body_short}")
    elif st == "user_interaction":
        texts.append(f"[交互: {title}]")
    elif st == "system_notice":
        texts.append(f"[系统: {title}]")
    elif st == "error_notice":
        texts.append(f"[错误: {title}]")


def _extract_segments(content: list[dict] | None) -> list[dict[str, Any]] | None:
    """Extract persisted ordered assistant timeline segments."""
    if not content:
        return None
    for block in content:
        if block.get("type") == "segments" and isinstance(block.get("segments"), list):
            return block["segments"]
    return None


def _extract_tool_calls(content: list[dict] | None) -> list[dict[str, Any]] | None:
    """Extract persisted tool calls for compatibility with older UI paths."""
    if not content:
        return None
    for block in content:
        if block.get("type") == "tool_calls" and isinstance(block.get("tool_calls"), list):
            return block["tool_calls"]
    return None


def _extract_files(content: list[dict] | None) -> list[dict[str, Any]] | None:
    """Extract files attached to a message."""
    if not content:
        return None
    for block in content:
        if block.get("type") == "files" and isinstance(block.get("files"), list):
            return block["files"]
    return None


def _extract_references(content: list[dict] | None) -> list[dict[str, Any]] | None:
    """Extract user-selected references attached to a message."""
    if not content:
        return None
    for block in content:
        if block.get("type") == "references" and isinstance(block.get("references"), list):
            return block["references"]
    return None


def _make_snippet(text: str, query_lower: str, snippet_len: int = 60) -> tuple[str, list[list[int]]]:
    """Extract snippet around first match and compute highlight ranges.

    Returns (snippet_text, [[start, end], ...]).
    """
    text_lower = text.lower()
    idx = text_lower.find(query_lower)
    if idx == -1:
        return (text[:snippet_len] + "..." if len(text) > snippet_len else text), []

    start = max(0, idx - snippet_len // 2)
    end = min(len(text), idx + len(query_lower) + snippet_len // 2)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    # Recompute highlight positions within snippet
    ranges: list[list[int]] = []
    s_lower = snippet.lower()
    pos = 0
    while True:
        p = s_lower.find(query_lower, pos)
        if p == -1:
            break
        ranges.append([p, p + len(query_lower)])
        pos = p + len(query_lower)
    return snippet, ranges


@router.get("/conversations/{conversation_id}/messages", response_model=MessagesResponse)
async def get_conversation_messages(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv_id = UUID(conversation_id)
    q = select(Conversation).where(Conversation.id == conv_id)
    conv = (await db.execute(q)).scalar()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs_q = (
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at.asc())
    )
    msgs = (await db.execute(msgs_q)).scalars().all()

    items = [
        MessageItem(
            role=m.role,
            content=_extract_text(m.content),
            thinking=m.thinking_content,
            segments=_extract_segments(m.content),
            tool_calls=_extract_tool_calls(m.content),
            files=_extract_files(m.content),
            references=_extract_references(m.content),
            timestamp=m.created_at.isoformat() if m.created_at else "",
        )
        for m in msgs
    ]
    return MessagesResponse(messages=items, conversation_id=conversation_id)

@router.get("/conversations/search", response_model=ConversationSearchResponse)
async def search_conversations(
    q: str = Query(..., min_length=1, description="Search query"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search conversations by title and message content.

    Returns conversations whose title or any message content matches the query,
    along with matching message snippets and highlight ranges.
    """
    uid = _user_uuid(user)
    query_lower = q.lower().strip()
    if not query_lower:
        return ConversationSearchResponse(results=[], total=0)

    # Fetch all conversations for this user
    conv_q = select(Conversation).where(Conversation.user_id == uid)
    conv_rows = (await db.execute(conv_q)).scalars().all()
    conv_map: dict[UUID, Conversation] = {c.id: c for c in conv_rows}

    if not conv_map:
        return ConversationSearchResponse(results=[], total=0)

    # Fetch all messages for these conversations
    msg_q = (
        select(Message)
        .where(Message.conversation_id.in_(conv_map.keys()))
        .order_by(Message.created_at.asc())
    )
    msg_rows = (await db.execute(msg_q)).scalars().all()

    results: list[ConversationSearchResult] = []
    matched_conv_ids: set[UUID] = set()
    conv_matches: dict[UUID, list[SearchMatch]] = {}

    for m in msg_rows:
        text = _extract_text(m.content)
        if not text:
            continue
        if query_lower not in text.lower():
            continue
        matched_conv_ids.add(m.conversation_id)
        snippet, ranges = _make_snippet(text, query_lower)
        match = SearchMatch(
            message_id=str(m.id),
            role=m.role,
            snippet=snippet,
            highlight_ranges=ranges,
        )
        conv_matches.setdefault(m.conversation_id, []).append(match)

    # Also match conversation titles
    for cid, conv in conv_map.items():
        if query_lower in conv.title.lower():
            matched_conv_ids.add(cid)

    # Build results sorted by updated_at desc
    for cid in sorted(
        matched_conv_ids,
        key=lambda x: conv_map[x].updated_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    ):
        conv = conv_map[cid]
        results.append(
            ConversationSearchResult(
                conversation_id=str(cid),
                title=conv.title,
                updated_at=conv.updated_at.isoformat() if conv.updated_at else "",
                matches=conv_matches.get(cid, []),
            )
        )

    return ConversationSearchResponse(results=results, total=len(results))


# ── Export ──────────────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    format: str = Field(default="md", description="Export format: md, html, txt")
    anonymize: bool = Field(default=False)
    includeBasicInfo: bool = Field(default=True)
    includeModelName: bool = Field(default=True)
    modelNameMode: str = Field(default="actual", description="actual, generic, custom, hidden")
    customModelName: str | None = None
    includeUserMessages: bool = Field(default=True)
    includeAssistantMessages: bool = Field(default=True)
    includeFinalText: bool = Field(default=True)
    includeThinking: bool = Field(default=True)
    includeExecution: bool = Field(default=True)
    includeToolCalls: bool = Field(default=True)
    includeToolPayload: bool = Field(default=False)
    includeToolResult: bool = Field(default=True)
    includeToolErrors: bool = Field(default=True)
    includeAttachments: bool = Field(default=True)
    includeWorkspace: bool = Field(default=True)
    includeSystemEvents: bool = Field(default=True)
    customTitle: str | None = None


def _anonymize(text: str, conversation_id: str) -> str:
    text = re.sub(r'[F-Zf-z]:[\\/].+?workspaces[\\/][^ \n\r,;:"]+', '<LOCAL_WORKSPACE_PATH>', text)
    text = re.sub(r'[A-Za-z]:[\\/][^\n ]{10,}', '<LOCAL_PATH>', text)
    text = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', '<UUID>', text, flags=re.IGNORECASE)
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '<EMAIL>', text)
    text = re.sub(r'(api[_-]?key|token|secret|password)["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', r'\1=<REDACTED>', text, flags=re.IGNORECASE)
    text = text.replace(conversation_id, '<CONVERSATION_ID>')
    return text


def _export_value(value: Any, limit: int = 2500) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        import json
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return text if len(text) <= limit else text[:limit] + "\n... <truncated>"


def _message_plain_text(message: Message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    texts: list[str] = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = str(block.get("type", ""))
            if btype == "text":
                texts.append(str(block.get("text", "")))
            elif btype == "segments":
                for seg in block.get("segments") or []:
                    if isinstance(seg, dict) and seg.get("type") == "text":
                        texts.append(str(seg.get("content", "")))
    return "\n\n".join(text for text in texts if text.strip())


def _model_label(conversation: Conversation, opts: dict[str, Any]) -> str:
    if not opts.get("includeModelName", True):
        return ""
    mode = str(opts.get("modelNameMode") or "actual")
    if mode == "hidden":
        return ""
    if mode == "generic":
        return "Agent model"
    if mode == "custom":
        return str(opts.get("customModelName") or "Custom model")
    return conversation.model


def _maybe_anonymize(text: str, conversation: Conversation, opts: dict[str, Any]) -> str:
    if opts.get("anonymize"):
        return _anonymize(text, str(conversation.id))
    return text


def _md_code(text: str) -> list[str]:
    return ["```text", text.rstrip(), "```", ""] if text.strip() else []


def _append_tool_md(lines: list[str], tool: dict[str, Any], conversation: Conversation, opts: dict[str, Any], title: str = "Tool") -> None:
    if not opts.get("includeToolCalls", True):
        return
    name = str(tool.get("name") or tool.get("toolName") or title)
    status = str(tool.get("status") or "")
    lines += [f"#### {title}: `{name}`", "", f"- 状态: {status or 'unknown'}"]
    if opts.get("includeToolPayload"):
        args = _maybe_anonymize(_export_value(tool.get("arguments") or tool.get("input") or {}), conversation, opts)
        lines += ["- 参数:", "", *_md_code(args)]
    if status == "error" and opts.get("includeToolErrors", True):
        error = _maybe_anonymize(str(tool.get("error") or ""), conversation, opts)
        lines += ["- 错误:", "", *_md_code(error)]
    elif opts.get("includeToolResult", True):
        result = _maybe_anonymize(_export_value(tool.get("result") or tool.get("outputPreview") or ""), conversation, opts)
        if result.strip():
            lines += ["- 结果:", "", *_md_code(result)]


def _append_execution_step_md(lines: list[str], step: dict[str, Any], conversation: Conversation, opts: dict[str, Any]) -> None:
    stype = str(step.get("type") or "")
    if stype == "thinking" and not opts.get("includeThinking", True):
        return
    if stype in {"tool_call", "tool_result", "command", "web_search", "web_fetch", "file_read", "file_write", "file_edit"} and not opts.get("includeToolCalls", True):
        return
    if stype in {"system_notice", "error_notice", "user_interaction"} and not opts.get("includeSystemEvents", True):
        return
    title = str(step.get("title") or stype or "step")
    status = str(step.get("status") or "")
    lines += [f"#### {title}", "", f"- 类型: `{stype or 'unknown'}`", f"- 状态: {status or 'unknown'}"]
    if step.get("durationMs") is not None:
        lines.append(f"- 耗时: {step.get('durationMs')}ms")
    body = str(step.get("content") or step.get("outputPreview") or step.get("error") or "")
    if body.strip():
        body = _maybe_anonymize(body, conversation, opts)
        lines += ["", *_md_code(body)]
    if opts.get("includeToolPayload") and step.get("metadata"):
        meta = _maybe_anonymize(_export_value(step.get("metadata")), conversation, opts)
        lines += ["- 元数据:", "", *_md_code(meta)]


def _append_segment_md(lines: list[str], segment: dict[str, Any], conversation: Conversation, opts: dict[str, Any]) -> None:
    stype = str(segment.get("type") or "")
    if stype == "text":
        if opts.get("includeFinalText", True):
            text = _maybe_anonymize(str(segment.get("content") or ""), conversation, opts)
            if text.strip():
                lines += [text, ""]
        return
    if stype == "thinking":
        if opts.get("includeThinking", True):
            text = _maybe_anonymize(str(segment.get("content") or ""), conversation, opts)
            lines += ["#### Thinking", "", *_md_code(text)]
        return
    if stype == "tool":
        tool = segment.get("tool") if isinstance(segment.get("tool"), dict) else {}
        _append_tool_md(lines, tool, conversation, opts)
        return
    if stype == "workflow_error":
        if opts.get("includeSystemEvents", True):
            error = segment.get("error") if isinstance(segment.get("error"), dict) else {}
            text = _maybe_anonymize(str(error.get("message") or ""), conversation, opts)
            lines += [f"#### Workflow Error: {error.get('title') or '工作流异常'}", "", *_md_code(text)]
        return
    if stype == "execution" and opts.get("includeExecution", True):
        execution = segment.get("execution") if isinstance(segment.get("execution"), dict) else {}
        title = str(execution.get("title") or execution.get("summary") or "处理回合")
        lines += [f"### {title}", ""]
        goal = str(execution.get("goal") or "")
        if goal:
            lines += [f"- 目标: {_maybe_anonymize(goal, conversation, opts)}"]
        if execution.get("durationMs") is not None:
            lines += [f"- 耗时: {execution.get('durationMs')}ms"]
        lines.append("")
        for step in execution.get("steps") or []:
            if isinstance(step, dict):
                _append_execution_step_md(lines, step, conversation, opts)
        return


def _format_md(conversation: Conversation, msgs: list[Message], opts: dict[str, Any]) -> str:
    title = opts.get("customTitle") or (conversation.title or "export")
    now = datetime.now(timezone.utc).isoformat()
    model_label = _model_label(conversation, opts)
    lines = [
        f"# {title}",
        "",
        "> VonishAgent conversation export",
        "",
    ]
    if opts.get("includeBasicInfo"):
        lines += [
            "## Overview",
            "",
            f"- 会话标题: {title}",
            f"- 会话 ID: <CONVERSATION_ID>" if opts["anonymize"] else f"- 会话 ID: {conversation.id}",
            f"- 创建时间: {conversation.created_at.isoformat() if conversation.created_at else '—'}",
            f"- 导出时间: {now}",
            f"- 匿名化: {'是' if opts['anonymize'] else '否'}",
        ]
        if model_label:
            lines.append(f"- 模型: {model_label}")
        if opts.get("includeWorkspace"):
            meta = conversation.metadata_ or {}
            workspace_id = meta.get("workspace_id") or meta.get("project_id") or str(conversation.id)
            directory_path = meta.get("directory_path") or ""
            lines.append(f"- Workspace: {_maybe_anonymize(str(workspace_id), conversation, opts)}")
            if directory_path:
                lines.append(f"- 目录: {_maybe_anonymize(str(directory_path), conversation, opts)}")
        lines += ["", "---", ""]

    lines += ["## Conversation", ""]
    for i, m in enumerate(msgs):
        if m.role == "user" and not opts.get("includeUserMessages", True):
            continue
        if m.role == "assistant" and not opts.get("includeAssistantMessages", True):
            continue
        if m.role not in {"user", "assistant"} and not opts.get("includeSystemEvents", True):
            continue
        role = "User" if m.role == "user" else "Assistant" if m.role == "assistant" else m.role.title()
        lines += [
            f"### {i + 1}. {role}",
            "",
            f"**时间**: {m.created_at.isoformat() if m.created_at else '—'}",
            "",
        ]
        text = _maybe_anonymize(_message_plain_text(m), conversation, opts)
        if text and (m.role != "assistant" or opts.get("includeFinalText", True)):
            lines += [text, ""]
        if opts.get("includeThinking") and m.thinking_content:
            thinking = _maybe_anonymize(m.thinking_content, conversation, opts)
            lines += ["#### Thinking", "", *_md_code(thinking)]
        segments = _extract_segments(m.content)
        if segments:
            for seg in segments:
                if isinstance(seg, dict):
                    _append_segment_md(lines, seg, conversation, opts)
        elif opts.get("includeToolCalls", True):
            for tool in _extract_tool_calls(m.content) or []:
                if isinstance(tool, dict):
                    _append_tool_md(lines, tool, conversation, opts)
        if opts.get("includeAttachments", True):
            files = _extract_files(m.content) or []
            if files:
                lines += ["#### Attachments", ""]
                for file in files:
                    if not isinstance(file, dict):
                        continue
                    name = _maybe_anonymize(str(file.get("originalName") or file.get("file_name") or "file"), conversation, opts)
                    path = _maybe_anonymize(str(file.get("workspacePath") or file.get("workspace_path") or ""), conversation, opts)
                    lines.append(f"- {name}{f' ({path})' if path else ''}")
                lines.append("")
        lines += ["---", ""]
    return "\n".join(lines)


def _format_txt(conversation: Conversation, msgs: list[Message], opts: dict[str, Any]) -> str:
    md = _format_md(conversation, msgs, opts)
    text = re.sub(r"```text\n|```", "", md)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    return text.replace("**", "")


def _format_html(conversation: Conversation, msgs: list[Message], opts: dict[str, Any]) -> str:
    md = _format_md(conversation, msgs, opts)
    safe_title = html.escape(str(opts.get("customTitle") or conversation.title or "export"))
    body = html.escape(md)
    body = re.sub(r"^# (.+)$", r"<h1>\1</h1>", body, flags=re.MULTILINE)
    body = re.sub(r"^## (.+)$", r"<h2>\1</h2>", body, flags=re.MULTILINE)
    body = re.sub(r"^### (.+)$", r"<h3>\1</h3>", body, flags=re.MULTILINE)
    body = re.sub(r"^#### (.+)$", r"<h4>\1</h4>", body, flags=re.MULTILINE)
    body = body.replace("&gt; VonishAgent conversation export", "<p class=\"badge\">VonishAgent conversation export</p>")
    body = body.replace("```text\n", "<pre>").replace("\n```", "</pre>")
    body = body.replace("\n", "<br />\n")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{safe_title}</title>
  <style>
    body {{ margin: 0; background: #0d0d0d; color: #e8e8e8; font: 15px/1.7 Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; }}
    main {{ max-width: 880px; margin: 0 auto; padding: 48px 32px 72px; }}
    h1 {{ font-size: 30px; line-height: 1.2; margin: 0 0 10px; letter-spacing: 0; }}
    h2 {{ margin-top: 34px; padding-top: 22px; border-top: 1px solid #2f2f2f; color: #f5f5f5; }}
    h3 {{ margin-top: 28px; color: #ffffff; }}
    h4 {{ margin: 18px 0 8px; color: #c7b7ff; }}
    .badge {{ display: inline-block; border: 1px solid #3b3b3b; border-radius: 999px; padding: 4px 10px; color: #a6a6a6; background: #181818; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #191919; border: 1px solid #333; border-radius: 10px; padding: 14px; color: #d6d6d6; }}
    code {{ background: #252525; border-radius: 5px; padding: 1px 5px; }}
    hr {{ border: 0; border-top: 1px solid #262626; margin: 24px 0; }}
  </style>
</head>
<body><main>{body}</main></body>
</html>"""


@router.post("/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    request: ExportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv_id = UUID(conversation_id)
    q = select(Conversation).where(Conversation.id == conv_id)
    conv = (await db.execute(q)).scalar()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs_q = (
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at.asc())
    )
    msgs = (await db.execute(msgs_q)).scalars().all()

    try:
        opts = request.model_dump()
    except Exception:
        opts = {k: getattr(request, k, None) for k in request.model_fields}
    try:
        fmt = request.format.lower().strip()
        if fmt == "txt":
            content = _format_txt(conv, msgs, opts)
            mime = "text/plain"
            ext = "txt"
        elif fmt == "html":
            content = _format_html(conv, msgs, opts)
            mime = "text/html"
            ext = "html"
        else:
            content = _format_md(conv, msgs, opts)
            mime = "text/markdown"
            ext = "md"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export formatting failed: {str(e)}")

    from urllib.parse import quote
    raw_title = request.customTitle or conv.title or "export"
    display_title = "".join(c for c in raw_title if c.isalnum() or c in " _-").strip()[:40] or "conversation"
    ascii_title = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_title).strip("_")[:40] or "conversation"
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{display_title}_{ts}.{ext}"
    ascii_filename = f"{ascii_title}_{ts}.{ext}"

    from fastapi.responses import Response
    return Response(
        content=content.encode("utf-8"),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{quote(filename)}'},
    )


# Keep backward-compat alias for chat.py
_messages: dict[str, list[dict[str, Any]]] = {}
