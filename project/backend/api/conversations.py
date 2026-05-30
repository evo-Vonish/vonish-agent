"""Conversation CRUD API routes — backed by SQLite via SQLAlchemy ORM."""

from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime, timezone
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    request: CreateConversationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = Conversation(
        user_id=_user_uuid(user),
        title=request.title,
        model=request.model,
        context_profile=request.context_profile,
        workspace_path=f"/workspaces/{user.id}/{uuid_lib.uuid4()}",
        metadata_=request.metadata,
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
    import asyncio
    import shutil
    from pathlib import Path
    from core.config import settings
    ws_path = Path(settings.workspace_root) / conversation_id
    if ws_path.exists():
        await asyncio.to_thread(shutil.rmtree, ws_path, ignore_errors=True)
        logger.info(f"Cleaned workspace: {ws_path}")

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


def _extract_text(content: list[dict] | None) -> str:
    """Extract plain text from content blocks."""
    if not content:
        return ""
    texts = [b.get("text", "") for b in content if b.get("type") == "text"]
    return "\n".join(texts)


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


# Keep backward-compat alias for chat.py
_messages: dict[str, list[dict[str, Any]]] = {}
