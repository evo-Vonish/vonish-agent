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
    import time as _time
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
    assistant_segments: list[dict[str, Any]] = []
    tool_calls_by_id: dict[str, dict[str, Any]] = {}
    active_thinking_segment: dict[str, Any] | None = None
    active_text_segment: dict[str, Any] | None = None

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

    def _parse_sse_event(event_str: str) -> tuple[str | None, dict[str, Any]]:
        """Parse the single-event SSE payload emitted by the agent loop."""
        event_name: str | None = None
        data: dict[str, Any] = {}
        for line in event_str.strip().split("\n"):
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                try:
                    parsed = _json.loads(line[5:].strip())
                    if isinstance(parsed, dict):
                        data = parsed
                except Exception:
                    data = {}
        return event_name, data

    def _append_thinking_delta(delta: str) -> None:
        nonlocal active_thinking_segment, active_text_segment
        if not active_thinking_segment:
            active_thinking_segment = {
                "id": f"thinking-{len(assistant_segments) + 1}",
                "type": "thinking",
                "content": "",
                "summary": "Thinking",
                "status": "streaming",
            }
            assistant_segments.append(active_thinking_segment)
        active_text_segment = None
        active_thinking_segment["content"] = (
            str(active_thinking_segment.get("content", "")) + delta
        )

    def _finish_thinking() -> None:
        nonlocal active_thinking_segment
        if active_thinking_segment:
            active_thinking_segment["status"] = "complete"
        active_thinking_segment = None

    def _append_text_delta(delta: str) -> None:
        nonlocal active_text_segment, active_thinking_segment
        if not delta:
            return
        if not active_text_segment:
            active_text_segment = {
                "id": f"text-{len(assistant_segments) + 1}",
                "type": "text",
                "content": "",
            }
            assistant_segments.append(active_text_segment)
        active_thinking_segment = None
        active_text_segment["content"] = str(active_text_segment.get("content", "")) + delta

    def _start_tool_call(data: dict[str, Any]) -> None:
        nonlocal active_text_segment, active_thinking_segment
        call_id = str(data.get("call_id") or f"tool-{len(tool_calls_by_id) + 1}")
        arguments = data.get("arguments") if isinstance(data.get("arguments"), dict) else {}
        tool_call = {
            "id": call_id,
            "name": str(data.get("tool") or ""),
            "arguments": arguments,
            "status": "running",
            "startTime": int(_time.time() * 1000),
        }
        tool_calls_by_id[call_id] = tool_call
        assistant_segments.append(
            {
                "id": f"tool-{call_id}",
                "type": "tool",
                "tool": tool_call,
            }
        )
        active_text_segment = None
        active_thinking_segment = None

    def _finish_tool_call(data: dict[str, Any]) -> None:
        call_id = str(data.get("call_id") or "")
        if not call_id:
            return
        tool_call = tool_calls_by_id.get(call_id)
        if not tool_call:
            tool_call = {
                "id": call_id,
                "name": str(data.get("tool") or ""),
                "arguments": {},
                "status": "running",
                "startTime": int(_time.time() * 1000),
            }
            tool_calls_by_id[call_id] = tool_call
            assistant_segments.append(
                {
                    "id": f"tool-{call_id}",
                    "type": "tool",
                    "tool": tool_call,
                }
            )
        success = bool(data.get("success"))
        tool_call["status"] = "success" if success else "error"
        tool_call["result"] = data.get("result")
        if data.get("error") is not None:
            tool_call["error"] = str(data.get("error"))
        if data.get("duration_ms") is not None:
            tool_call["duration"] = data.get("duration_ms")

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
            event_name, event_data = _parse_sse_event(event_str)
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
                                    _append_text_delta(filtered)
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
            if event_name == "thinking_start":
                _append_thinking_delta("")
            elif event_name == "thinking_delta":
                try:
                    _content = event_data.get("content", "")
                    if _content:
                        delta = str(_content)
                        thinking_parts.append(delta)
                        _append_thinking_delta(delta)
                except Exception:
                    pass
            elif event_name == "thinking_end":
                _finish_thinking()
            elif event_name == "tool_call_start":
                _start_tool_call(event_data)
            elif event_name == "tool_result":
                _finish_tool_call(event_data)
            elif event_name in {"message_end", "aborted", "error"}:
                _finish_thinking()
            yield event_str

        # After streaming ends, store assistant response to DB
        _finish_thinking()
        full_content = "".join(assistant_parts)
        if full_content or assistant_segments or thinking_parts:
            content_blocks: list[dict[str, Any]] = []
            if full_content:
                content_blocks.append({"type": "text", "text": full_content})
            if assistant_segments:
                content_blocks.append({"type": "segments", "segments": assistant_segments})
            if tool_calls_by_id:
                content_blocks.append(
                    {"type": "tool_calls", "tool_calls": list(tool_calls_by_id.values())}
                )
            assistant_msg = MessageModel(
                conversation_id=conv_uuid,
                role="assistant",
                content=content_blocks,
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


# ── Polish Text ─────────────────────────────────────────────────────────────

class PolishRequest(BaseModel):
    text: str = Field(..., description="Text to polish")
    model: str = Field(default="deepseek-chat")


@router.post("/polish")
async def polish_text(
    request: PolishRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Polish user input: fix grammar, improve clarity, keep meaning intact."""
    try:
        import openai

        config = await get_default_api_config(db, user.id, request.model)
        client = openai.AsyncOpenAI(api_key=config.api_key, base_url=config.api_base)

        response = await client.chat.completions.create(
            model=request.model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Polish the following text. Fix grammar, improve clarity and flow, "
                        "but keep the meaning, tone, and language exactly the same. "
                        "Do not add information or change technical terms. "
                        "Return ONLY the polished text, no explanations.\n\n"
                        f"Text: {request.text}"
                    ),
                }
            ],
            max_tokens=500,
            temperature=0.3,
        )
        polished = response.choices[0].message.content.strip()
        return {"polished": polished, "original": request.text}
    except Exception as e:
        logger.error(f"Polish failed: {e}")
        return {"polished": request.text, "original": request.text, "error": str(e)}

