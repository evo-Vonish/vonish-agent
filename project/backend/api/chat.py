"""SSE Streaming Chat API routes.

Provides:
- POST /api/chat/{conversation_id}/stream - SSE streaming chat
- POST /api/chat/{conversation_id}/stop - Interrupt generation
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agent.agent_loop import AgentLoop, AgentLoopConfig
from core.auth import User, get_current_user
from core.config import MODEL_CONFIGS
from core.logging import get_logger
from core.streaming import SSEStream, sse_event
from db.session import get_db
from services.api_config_service import get_default_api_config

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class ChatStreamRequest(BaseModel):
    """Request body for streaming chat."""

    message: str = Field(..., description="User message text", min_length=1)
    model: str = Field(default="deepseek-v4-pro", description="Model to use")
    enable_thinking: bool = Field(default=True, description="Enable thinking/reasoning")
    resources: list[dict[str, Any]] = Field(
        default_factory=list, description="Attached resource references"
    )


class StopRequest(BaseModel):
    """Request body for stopping generation."""

    reason: str = Field(default="user_request", description="Stop reason")


# ---------------------------------------------------------------------------
# Agent Loop Instance
# ---------------------------------------------------------------------------

_agent_loop: AgentLoop | None = None


def get_agent_loop() -> AgentLoop:
    """Get the global AgentLoop instance."""
    global _agent_loop
    if _agent_loop is None:
        _agent_loop = AgentLoop(config=AgentLoopConfig(max_rounds=10))
    return _agent_loop


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/chat/{conversation_id}/stream")
async def chat_stream(
    conversation_id: str,
    request: ChatStreamRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """SSE streaming chat endpoint.

    Streams the AI response as Server-Sent Events.
    Supports thinking, tool calls, and multi-round agent loop.
    """
    from fastapi.responses import StreamingResponse

    agent_loop = get_agent_loop()
    provider = MODEL_CONFIGS.get(request.model).provider if request.model in MODEL_CONFIGS else ""
    api_config = (
        await get_default_api_config(db, user.id, provider)
        if provider in ("deepseek", "kimi")
        else None
    )

    # Store user message
    from api.conversations import _messages as conv_messages
    conv_messages.setdefault(conversation_id, []).append({
        "role": "user",
        "content": request.message,
        "timestamp": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    })

    # Collect assistant response from SSE events
    assistant_parts: list[str] = []
    thinking_parts: list[str] = []

    async def event_generator():
        """Generate SSE events from the agent loop and collect response."""
        nonlocal assistant_parts, thinking_parts
        async for event_str in agent_loop.run(
            conversation_id=conversation_id,
            user_input=request.message,
            model_id=request.model,
            enable_thinking=True,
            api_key=api_config.api_key if api_config else None,
            api_base=api_config.api_base if api_config else None,
            resources=getattr(request, 'resources', None),
        ):
            # Collect text content from SSE events for storage
            if "text_delta" in event_str or "markdown_delta" in event_str:
                try:
                    import json as _json
                    _lines = event_str.strip().split("\n")
                    for _line in _lines:
                        if _line.startswith("data:"):
                            _data = _json.loads(_line[5:].strip())
                            _content = _data.get("content", "")
                            if _content:
                                assistant_parts.append(str(_content))
                except Exception:
                    pass
            if "thinking_delta" in event_str:
                try:
                    import json as _json
                    _lines = event_str.strip().split("\n")
                    for _line in _lines:
                        if _line.startswith("data:"):
                            _data = _json.loads(_line[5:].strip())
                            _content = _data.get("content", "")
                            if _content:
                                thinking_parts.append(str(_content))
                except Exception:
                    pass
            yield event_str

        # After streaming ends, store assistant response
        full_content = "".join(assistant_parts)
        if full_content:
            conv_messages.setdefault(conversation_id, []).append({
                "role": "assistant",
                "content": full_content,
                "thinking": "".join(thinking_parts) if thinking_parts else None,
                "timestamp": (
                    __import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    ).isoformat()
                ),
            })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/{conversation_id}/stop")
async def chat_stop(
    conversation_id: str,
    request: StopRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stop/interrupt an ongoing chat generation.

    Sends a stop signal to the running agent loop.
    """
    agent_loop = get_agent_loop()

    if not agent_loop.is_running(conversation_id):
        return {"status": "not_running", "conversation_id": conversation_id}

    await agent_loop.stop(conversation_id)

    logger.info(
        f"Chat stopped: {conversation_id}",
        extra={"reason": request.reason},
    )

    return {
        "status": "stopped",
        "conversation_id": conversation_id,
        "reason": request.reason,
    }
