"""SSE StreamingResponse infrastructure for the Agent system.

Implements 18 SSE event types as defined in SPEC.md Section 5.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Callable

from fastapi.responses import StreamingResponse


# ---------------------------------------------------------------------------
# SSE Event Types (SPEC.md Section 5)
# ---------------------------------------------------------------------------

SSE_EVENT_TYPES = {
    "message_start",
    "thinking_start",
    "thinking_delta",
    "thinking_end",
    "text_delta",
    "markdown_delta",
    "tool_call_start",
    "tool_call_delta",
    "tool_call_end",
    "tool_result",
    "file_created",
    "file_modified",
    "workspace_snapshot",
    "workspace_diff",
    "context_usage",
    "message_end",
    "error",
    "aborted",
    # Human Interaction events
    "interaction_required",
    # Error events
    "workflow_failure",
    "agent_paused",
    "agent_resumed",
    "todo_updated",
    "approval_requested",
    "ask_requested",
    # Structured execution segment events
    "segment_start",
    "segment_update",
    "segment_end",
    "step_start",
    "step_delta",
    "step_end",
    "workflow_error",
}


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def sse_event(event_type: str, data: dict[str, Any]) -> str:
    """Format a single SSE event.

    Args:
        event_type: One of the 18 SSE event types.
        data: Event payload data.

    Returns:
        Formatted SSE event string.
    """
    if event_type not in SSE_EVENT_TYPES:
        raise ValueError(f"Unknown SSE event type: {event_type}")

    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"


async def sse_stream_wrapper(
    generator: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """Wrap an async generator for SSE streaming."""
    async for chunk in generator:
        yield chunk


# ---------------------------------------------------------------------------
# SSE Stream Class
# ---------------------------------------------------------------------------

class SSEStream:
    """Manages an asynchronous SSE event stream.

    Provides a queue-based interface for producing SSE events
    and a generator interface for consumption by StreamingResponse.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._closed: bool = False
        self._event_count: int = 0

    async def send(self, event_type: str, data: dict[str, Any]) -> None:
        """Send an SSE event to the stream.

        Args:
            event_type: The SSE event type.
            data: Event payload.
        """
        if self._closed:
            return
        event = sse_event(event_type, data)
        self._event_count += 1
        await self._queue.put(event)

    async def send_text_delta(self, text: str) -> None:
        """Convenience: send a text_delta event."""
        await self.send("text_delta", {"content": text})

    async def send_thinking_start(self) -> None:
        """Convenience: send thinking_start event."""
        await self.send("thinking_start", {})

    async def send_thinking_delta(self, text: str) -> None:
        """Convenience: send a thinking_delta event."""
        await self.send("thinking_delta", {"content": text})

    async def send_thinking_end(self) -> None:
        """Convenience: send thinking_end event."""
        await self.send("thinking_end", {})

    async def send_tool_call_start(self, tool_name: str, call_id: str = "") -> None:
        """Convenience: send tool_call_start event."""
        await self.send("tool_call_start", {"tool": tool_name, "call_id": call_id})

    async def send_tool_call_delta(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Convenience: send tool_call_delta event."""
        await self.send("tool_call_delta", {"tool": tool_name, "arguments": arguments})

    async def send_tool_call_end(self, tool_name: str, call_id: str = "") -> None:
        """Convenience: send tool_call_end event."""
        await self.send("tool_call_end", {"tool": tool_name, "call_id": call_id})

    async def send_tool_result(
        self, tool_name: str, result: Any, success: bool = True
    ) -> None:
        """Convenience: send tool_result event."""
        await self.send(
            "tool_result",
            {
                "tool": tool_name,
                "result": result if isinstance(result, (str, int, float, bool, dict, list)) else str(result),
                "success": success,
            },
        )

    async def send_file_event(self, event_type: str, file_path: str, file_name: str = "") -> None:
        """Convenience: send file_created or file_modified event."""
        if event_type not in ("file_created", "file_modified"):
            raise ValueError(f"Invalid file event type: {event_type}")
        await self.send(event_type, {"path": file_path, "name": file_name or file_path})

    async def send_workspace_snapshot(self, snapshot_data: dict[str, Any]) -> None:
        """Convenience: send workspace_snapshot event."""
        await self.send("workspace_snapshot", snapshot_data)

    async def send_workspace_diff(self, diff_data: dict[str, Any]) -> None:
        """Convenience: send workspace_diff event."""
        await self.send("workspace_diff", diff_data)

    async def send_context_usage(self, usage: dict[str, Any]) -> None:
        """Convenience: send context_usage event."""
        await self.send("context_usage", usage)

    async def send_message_start(self, message_id: str = "") -> None:
        """Convenience: send message_start event."""
        await self.send("message_start", {"message_id": message_id})

    async def send_message_end(self, extra: dict[str, Any] | None = None) -> None:
        """Convenience: send message_end event."""
        await self.send("message_end", extra or {})

    async def send_error(self, detail: str, error_code: str = "STREAM_ERROR") -> None:
        """Convenience: send error event."""
        await self.send("error", {"detail": detail, "code": error_code})

    async def send_aborted(self, reason: str = "user_request") -> None:
        """Convenience: send aborted event."""
        await self.send("aborted", {"reason": reason})

    async def close(self) -> None:
        """Close the stream."""
        self._closed = True
        await self._queue.put(None)

    async def event_generator(self) -> AsyncGenerator[str, None]:
        """Async generator yielding SSE events for StreamingResponse.

        Usage:
            stream = SSEStream()
            return StreamingResponse(
                stream.event_generator(),
                media_type="text/event-stream",
            )
        """
        while True:
            event = await self._queue.get()
            if event is None:
                break
            yield event

    def to_streaming_response(self) -> StreamingResponse:
        """Convert this stream to a FastAPI StreamingResponse."""
        return StreamingResponse(
            self.event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )


# ---------------------------------------------------------------------------
# Utility: Merge multiple SSE generators
# ---------------------------------------------------------------------------

async def merge_sse_generators(
    *generators: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """Merge multiple SSE async generators into a single stream.

    Events are yielded in arrival order across all generators.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    tasks: list[asyncio.Task] = []

    async def _consume(gen: AsyncGenerator[str, None]) -> None:
        try:
            async for item in gen:
                await queue.put(item)
        except Exception:
            pass
        finally:
            await queue.put(None)

    for gen in generators:
        tasks.append(asyncio.create_task(_consume(gen)))

    active = len(generators)
    while active > 0:
        item = await queue.get()
        if item is None:
            active -= 1
        else:
            yield item

    for task in tasks:
        task.cancel()
