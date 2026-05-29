"""Memory Management API routes.

Provides:
- GET /api/memory/user - Get user memories
- POST /api/memory/user - Add memory
- DELETE /api/memory/user/{memory_id} - Delete memory
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
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


class AddMemoryRequest(BaseModel):
    """Request to add a user memory."""

    content: str = Field(..., description="Memory content", min_length=1)
    memory_type: str = Field(
        default="fact",
        description="Memory type: preference, fact, profile, task",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = Field(default="user_defined")
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryItemResponse(BaseModel):
    """Single memory item response."""

    id: str
    user_id: str
    memory_type: str
    content: str
    confidence: float
    is_active: bool
    source: str
    created_at: str


class MemoryListResponse(BaseModel):
    """List of memories response."""

    memories: list[MemoryItemResponse]
    total: int


# ---------------------------------------------------------------------------
# In-Memory Store (Placeholder)
# ---------------------------------------------------------------------------

_user_memories: dict[str, list[dict[str, Any]]] = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/memory/user", response_model=MemoryListResponse)
async def get_user_memories(
    memory_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get user long-term memories.

    Args:
        memory_type: Optional filter by memory type.
    """
    memories = _user_memories.get(user.id, [])

    if memory_type:
        memories = [m for m in memories if m["memory_type"] == memory_type]

    # Sort by created_at descending
    memories.sort(key=lambda m: m["created_at"], reverse=True)

    return MemoryListResponse(
        memories=[
            MemoryItemResponse(
                id=m["id"],
                user_id=m["user_id"],
                memory_type=m["memory_type"],
                content=m["content"],
                confidence=m["confidence"],
                is_active=m["is_active"],
                source=m["source"],
                created_at=m["created_at"],
            )
            for m in memories
        ],
        total=len(memories),
    )


@router.post("/memory/user", response_model=MemoryItemResponse)
async def add_user_memory(
    request: AddMemoryRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add a user long-term memory.

    Stores a piece of information in the user's long-term memory
    for future context retrieval.
    """
    memory_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    memory = {
        "id": memory_id,
        "user_id": user.id,
        "memory_type": request.memory_type,
        "content": request.content,
        "confidence": request.confidence,
        "is_active": True,
        "source": request.source,
        "metadata": request.metadata,
        "created_at": now,
        "updated_at": now,
    }

    if user.id not in _user_memories:
        _user_memories[user.id] = []

    _user_memories[user.id].append(memory)

    logger.info(
        f"Added memory for user {user.id}: {request.content[:50]}..."
    )

    return MemoryItemResponse(
        id=memory_id,
        user_id=user.id,
        memory_type=request.memory_type,
        content=request.content,
        confidence=request.confidence,
        is_active=True,
        source=request.source,
        created_at=now,
    )


@router.delete("/memory/user/{memory_id}")
async def delete_user_memory(
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a user memory.

    Args:
        memory_id: ID of the memory to delete.
    """
    memories = _user_memories.get(user.id, [])

    for i, memory in enumerate(memories):
        if memory["id"] == memory_id:
            memories.pop(i)
            logger.info(f"Deleted memory: {memory_id}")
            return {"status": "deleted", "memory_id": memory_id}

    raise HTTPException(status_code=404, detail=f"Memory not found: {memory_id}")
