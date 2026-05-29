"""Conversation CRUD API routes.

Provides:
- POST /api/conversations - Create conversation
- GET /api/conversations - List conversations
- GET /api/conversations/{id} - Get conversation details
- DELETE /api/conversations/{id} - Delete conversation
- POST /api/conversations/{id}/clear - Clear messages
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import User, get_current_user
from core.logging import get_logger
from db.session import get_db

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""

    title: str = Field(default="新对话", description="Conversation title")
    model: str = Field(default="deepseek-v4-pro", description="Model to use")
    context_profile: str = Field(default="balanced", description="Context profile")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class ConversationResponse(BaseModel):
    """Conversation response model."""

    id: str
    title: str
    model: str
    context_profile: str
    created_at: str
    updated_at: str
    message_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationListResponse(BaseModel):
    """List of conversations response."""

    conversations: list[ConversationResponse]
    total: int


# ---------------------------------------------------------------------------
# In-Memory Store (Placeholder)
# ---------------------------------------------------------------------------

_conversations: dict[str, dict[str, Any]] = {}
_messages: dict[str, list[dict[str, Any]]] = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    request: CreateConversationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new conversation."""
    import uuid

    conv_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conversation = {
        "id": conv_id,
        "user_id": user.id,
        "title": request.title,
        "model": request.model,
        "context_profile": request.context_profile,
        "workspace_path": f"/workspaces/{user.id}/{conv_id}",
        "metadata": request.metadata,
        "created_at": now,
        "updated_at": now,
    }

    _conversations[conv_id] = conversation
    _messages[conv_id] = []

    logger.info(f"Created conversation: {conv_id}")

    return ConversationResponse(
        id=conv_id,
        title=request.title,
        model=request.model,
        context_profile=request.context_profile,
        created_at=now,
        updated_at=now,
        message_count=0,
        metadata=request.metadata,
    )


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List conversations for the current user."""
    user_convs = [
        conv for conv in _conversations.values()
        if conv.get("user_id") == user.id
    ]

    # Sort by updated_at descending
    user_convs.sort(key=lambda c: c.get("updated_at", ""), reverse=True)

    total = len(user_convs)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = user_convs[start:end]

    conversations = [
        ConversationResponse(
            id=c["id"],
            title=c["title"],
            model=c["model"],
            context_profile=c["context_profile"],
            created_at=c["created_at"],
            updated_at=c["updated_at"],
            message_count=len(_messages.get(c["id"], [])),
            metadata=c.get("metadata", {}),
        )
        for c in paginated
    ]

    return ConversationListResponse(conversations=conversations, total=total)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a conversation by ID."""
    conv = _conversations.get(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationResponse(
        id=conv["id"],
        title=conv["title"],
        model=conv["model"],
        context_profile=conv["context_profile"],
        created_at=conv["created_at"],
        updated_at=conv["updated_at"],
        message_count=len(_messages.get(conversation_id, [])),
        metadata=conv.get("metadata", {}),
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a conversation."""
    conv = _conversations.pop(conversation_id, None)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    _messages.pop(conversation_id, None)

    logger.info(f"Deleted conversation: {conversation_id}")

    return {"status": "deleted", "conversation_id": conversation_id}


@router.post("/conversations/{conversation_id}/clear")
async def clear_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Clear all messages from a conversation."""
    conv = _conversations.get(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    _messages[conversation_id] = []
    conv["updated_at"] = datetime.now(timezone.utc).isoformat()

    logger.info(f"Cleared conversation: {conversation_id}")

    return {"status": "cleared", "conversation_id": conversation_id}


# ---------------------------------------------------------------------------
# Messages Endpoint
# ---------------------------------------------------------------------------


class MessageItem(BaseModel):
    """Single message in history."""

    role: str
    content: str
    thinking: str | None = None
    timestamp: str


class MessagesResponse(BaseModel):
    """Messages response model."""

    messages: list[MessageItem]
    conversation_id: str


@router.get("/conversations/{conversation_id}/messages", response_model=MessagesResponse)
async def get_conversation_messages(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get all messages for a conversation."""
    conv = _conversations.get(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    msgs = _messages.get(conversation_id, [])
    return MessagesResponse(
        conversation_id=conversation_id,
        messages=[MessageItem(**m) for m in msgs],
    )
