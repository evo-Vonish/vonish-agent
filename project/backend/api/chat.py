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


class ThinkingSummaryRequest(BaseModel):
    """Request body for summarizing a thinking block."""

    content: str = Field(..., description="Thinking content to summarize", min_length=1)
    model: str = Field(default="deepseek-v4-pro", description="Model to use")


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

    # Store user message to DB
    import json as _json
    import uuid as _uuid
    from db.models import Message as MessageModel

    conv_uuid = _uuid.UUID(conversation_id) if conversation_id != "test" else _uuid.uuid4()
    user_msg = MessageModel(
        conversation_id=conv_uuid,
        role="user",
        content=[{"type": "text", "text": request.message}],
        model=request.model,
    )
    db.add(user_msg)
    await db.commit()

    # Collect assistant response from SSE events
    assistant_parts: list[str] = []
    thinking_parts: list[str] = []

    # Streaming XML tool-call filter state machine
    _xml_buf = ""       # buffered partial text for filtering
    _xml_suppress = 0   # >0 = inside tool_call XML, swallow text

    def _filter_text_chunk(raw: str) -> str:
        """Streaming filter: strip leaked <tool_calls>/<invoke> XML from text output."""
        nonlocal _xml_buf, _xml_suppress
        _xml_buf += raw
        clean = ""
        i = 0
        while i < len(_xml_buf):
            if _xml_suppress > 0:
                # Inside a tool_call XML block — swallow until matching >
                gt = _xml_buf.find(">", i)
                if gt == -1:
                    _xml_buf = _xml_buf[i:]
                    return clean
                # Check if this > closes the tool_call block
                tag_text = _xml_buf[i:gt+1]
                # Count nested < and > to track depth
                opens = tag_text.count("<") - tag_text.count("</")
                closes = tag_text.count("/>") + (1 if _xml_buf[gt-1:gt+1] == "/>" else 0)
                _xml_suppress += opens
                _xml_suppress -= 1  # this >
                if _xml_suppress <= 0:
                    _xml_suppress = 0
                i = gt + 1
                continue
            # Not suppressing — look for tool_call XML start
            lt = _xml_buf.find("<", i)
            if lt == -1:
                clean += _xml_buf[i:]
                _xml_buf = ""
                return clean
            if lt > i:
                clean += _xml_buf[i:lt]
            # Check if this is a tool_call or invoke tag
            tag_start = _xml_buf[lt:]
            if (tag_start.startswith("<tool_calls") or
                tag_start.startswith("</tool_calls") or
                tag_start.startswith("<invoke") or
                tag_start.startswith("</invoke") or
                tag_start.startswith("<parameter")):
                _xml_suppress = 1
                i = lt + 1  # start scanning from after <
            else:
                clean += _xml_buf[lt]
                i = lt + 1
        _xml_buf = ""
        return clean

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
            if "text_delta" in event_str or "markdown_delta" in event_str:
                try:
                    _lines = event_str.strip().split("\n")
                    filtered_lines: list[str] = []
                    for _line in _lines:
                        if _line.startswith("data:"):
                            _data = _json.loads(_line[5:].strip())
                            _content = _data.get("content", "")
                            if _content:
                                filtered = _filter_text_chunk(str(_content))
                                if filtered:
                                    assistant_parts.append(filtered)
                                if filtered or not _content:
                                    new_data = _json.dumps({"content": filtered}, ensure_ascii=False)
                                    filtered_lines.append(f"data: {new_data}")
                                else:
                                    # Suppressed entirely — skip this line
                                    filtered_lines.append(f"data: {_json.dumps({'content': ''})}")
                            else:
                                filtered_lines.append(_line)
                        else:
                            filtered_lines.append(_line)
                    yield "\n".join(filtered_lines) + "\n\n"
                except Exception:
                    yield event_str
                continue
            if "thinking_delta" in event_str:
                try:
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

        # After streaming ends, store assistant response to DB
        full_content = "".join(assistant_parts)
        if full_content:
            assistant_msg = MessageModel(
                conversation_id=conv_uuid,
                role="assistant",
                content=[{"type": "text", "text": full_content}],
                thinking_content="".join(thinking_parts) if thinking_parts else None,
                model=request.model,
            )
            db.add(assistant_msg)
            await db.commit()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/thinking-summary")
async def thinking_summary(
    request: ThinkingSummaryRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Summarize a raw thinking block into a short UI phrase."""
    from services.llm_summary_service import summarize_thinking_phrase

    summary = await summarize_thinking_phrase(
        db=db,
        user_id=user.id,
        model=request.model,
        thinking=request.content,
    )
    return {"summary": summary}


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


# ── Interaction Resume ────────────────────────────────────────────────────

class ResumeRequest(BaseModel):
    choice: str = Field(..., description="User's choice: approve / reject_revise / reject_exit / custom / option id")
    message: str | None = Field(default=None, description="Optional custom response text")


@router.post("/agent-runs/{conversation_id}/interactions/{interaction_id}/resume")
async def resume_interaction(
    conversation_id: str,
    interaction_id: str,
    request: ResumeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Resume an agent run that is waiting for user interaction."""
    agent_loop = get_agent_loop()

    if not agent_loop.is_waiting(conversation_id):
        return {"status": "not_waiting", "conversation_id": conversation_id}

    # Handle reject_exit → cancel the run
    if request.choice == "reject_exit":
        agent_loop.cancel_interaction(conversation_id)
        logger.info(f"Interaction {interaction_id} cancelled by user (reject_exit)")
        return {"status": "cancelled", "conversation_id": conversation_id}

    await agent_loop.resume_from_interaction(conversation_id, {
        "choice": request.choice,
        "message": request.message,
    })
    logger.info(f"Interaction {interaction_id} resumed with choice: {request.choice}")
    return {"status": "resumed", "conversation_id": conversation_id}
