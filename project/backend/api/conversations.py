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
    timestamp: str


class MessagesResponse(BaseModel):
    messages: list[MessageItem]
    conversation_id: str


def _extract_text(content: list[dict] | None) -> str:
    """Extract plain text from content blocks."""
    if not content:
        return ""
    texts = [b.get("text", "") for b in content if b.get("type") == "text"]
    return "\n".join(texts)


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
            timestamp=m.created_at.isoformat() if m.created_at else "",
        )
        for m in msgs
    ]
    return MessagesResponse(messages=items, conversation_id=conversation_id)

# Keep backward-compat alias for chat.py
_messages: dict[str, list[dict[str, Any]]] = {}
