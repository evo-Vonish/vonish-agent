"""Agent Loop for the Agent system.

Orchestrates the multi-round conversation flow:
1. Receive user input
2. Build context (ContextBuilder)
3. Stream from model (ModelAdapter)
4. Parse tool calls (ToolCallParser)
5. Execute tools (ToolExecutor)
6. Stream results back
7. Continue until no more tool calls or max rounds reached
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pydantic import BaseModel, Field
from typing import Any, AsyncGenerator

from agent.model_adapter import (
    MessageBlock,
    ModelAdapter,
    ModelAdapterFactory,
    ToolDefinition,
)
from agent.tool_executor import ToolCallRequest, ToolCallResult, ToolExecutor
from core.config import settings
from core.errors import AgentError
from core.logging import get_logger
from core.streaming import SSEStream, sse_event

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class AgentLoopConfig(BaseModel):
    """Configuration for the Agent Loop."""

    max_rounds: int = 10
    enable_thinking: bool = True
    json_mode: bool = False
    max_tool_calls_per_step: int = 4


class ResourceRef(BaseModel):
    """Reference to a resource attached to the conversation."""

    uri: str
    mime_type: str
    title: str = ""


# ---------------------------------------------------------------------------
# Agent Loop
# ---------------------------------------------------------------------------


class AgentLoop:
    """Multi-round Agent conversation loop.

    Flow:
    1. Receive user_input + optional resources
    2. Build context via ContextBuilder
    3. Stream model response
    4. If tool calls detected -> execute -> feed back to model
    5. Repeat until no tool calls or max rounds reached
    6. Stream final response to user
    """

    def __init__(self, config: AgentLoopConfig | None = None) -> None:
        self.config = config or AgentLoopConfig()
        self._active_loops: dict[str, asyncio.Event] = {}

    async def run(
        self,
        conversation_id: str,
        user_input: str,
        resources: list[ResourceRef] | None = None,
        model_id: str = "deepseek-v4-pro",
        enable_thinking: bool | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Run the agent loop and yield SSE events.

        Args:
            conversation_id: Current conversation ID.
            user_input: User's message text.
            resources: Optional attached resources.
            model_id: Model to use.
            system_prompt: Optional system prompt override.

        Yields:
            SSE event strings for StreamingResponse.
        """
        loop_id = f"{conversation_id}_{uuid.uuid4().hex[:8]}"
        stop_event = asyncio.Event()
        self._active_loops[conversation_id] = stop_event

        # Create model adapter
        adapter = ModelAdapterFactory.create(
            model_id,
            api_key=api_key,
            api_base=api_base,
        )

        try:
            yield sse_event("message_start", {"message_id": loop_id})

            # Build initial context
            context = await self._build_context(
                conversation_id=conversation_id,
                user_input=user_input,
                model_id=model_id,
                resources=resources,
                system_prompt=system_prompt,
            )

            # Multi-round loop
            for round_num in range(self.config.max_rounds):
                if stop_event.is_set():
                    yield sse_event("aborted", {"reason": "user_request"})
                    return

                logger.debug(
                    f"Agent loop round {round_num + 1}/{self.config.max_rounds}",
                    extra={"conversation_id": conversation_id},
                )

                accumulated_text = ""
                thinking_buffer = ""
                in_thinking = False
                # Collect tool_calls from native function calling
                native_tool_calls: list[dict] = []

                # Stream from model — pass tools natively, NOT in prompt text
                async for chunk in adapter.stream_chat(
                    messages=context.messages,
                    system_prompt=context.system_prompt,
                    tools=context.tools,
                    enable_thinking=(
                        self.config.enable_thinking
                        if enable_thinking is None
                        else enable_thinking
                    ),
                    json_mode=self.config.json_mode,
                ):
                    if stop_event.is_set():
                        yield sse_event("aborted", {"reason": "user_request"})
                        return

                    chunk_type = chunk["type"]
                    content = chunk.get("content")

                    if chunk_type == "thinking_delta":
                        if not in_thinking:
                            in_thinking = True
                            yield sse_event("thinking_start", {})
                        thinking_buffer += str(content or "")
                        yield sse_event("thinking_delta", {"content": str(content or "")})

                    elif chunk_type == "text_delta":
                        if in_thinking:
                            in_thinking = False
                            yield sse_event("thinking_end", {})
                        accumulated_text += str(content or "")
                        # Stream text immediately — with native tool_calls,
                        # text and tool_calls are mutually exclusive
                        yield sse_event("text_delta", {"content": str(content or "")})

                    elif chunk_type == "usage":
                        usage = chunk.get("usage")
                        if usage:
                            yield sse_event(
                                "context_usage",
                                {
                                    "input_tokens": usage.get("input_tokens", 0),
                                    "output_tokens": usage.get("output_tokens", 0),
                                },
                            )

                    elif chunk_type == "done":
                        if content and isinstance(content, dict) and content.get("error"):
                            if in_thinking:
                                in_thinking = False
                                yield sse_event("thinking_end", {})
                            yield sse_event("error", {"detail": content["error"]})
                            return
                        # Check for native tool_calls assembled by the adapter
                        tc = chunk.get("tool_calls")
                        if tc:
                            native_tool_calls = tc
                        break

                if in_thinking:
                    yield sse_event("thinking_end", {})

                # --- Decide: tool calls or final text? ---
                if native_tool_calls:
                    # --- Tool execution path ---
                    # 1. Yield loading state immediately so frontend shows "running"
                    for tc in native_tool_calls:
                        fn = tc.get("function", {})
                        raw_args = fn.get("arguments", "{}")
                        try:
                            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        except json.JSONDecodeError:
                            args = {}
                        yield sse_event(
                            "tool_call_start",
                            {
                                "call_id": tc.get("id", ""),
                                "tool": fn.get("name", ""),
                                "arguments": args,
                            },
                        )

                    # 2. Execute tools (may take time, but frontend already shows spinners)
                    tool_results = await self._execute_native_tool_calls(
                        conversation_id, context, native_tool_calls
                    )

                    # 3. Send results to frontend
                    for result in tool_results:
                        yield sse_event(
                            "tool_result",
                            {
                                "call_id": result.call_id,
                                "tool": result.tool_name,
                                "success": result.success,
                                "result": (
                                    result.result
                                    if result.success and result.result is not None
                                    else None
                                ),
                                "error": (
                                    result.error_message if not result.success else None
                                ),
                                "duration_ms": result.execution_time_ms,
                            },
                        )

                    # 4. Feed results back as native tool-response messages
                    context = await self._update_context_with_native_results(
                        context, native_tool_calls, tool_results
                    )
                    # Continue to next round — model will synthesize answer
                    continue

                else:
                    # --- Final text response ---
                    # Text was already streamed inline; just break
                    break

            # End message
            yield sse_event("message_end", {"rounds": round_num + 1})

        except Exception as e:
            logger.error(
                f"Agent loop error: {e}",
                extra={"conversation_id": conversation_id},
            )
            yield sse_event("error", {"detail": str(e), "code": "AGENT_LOOP_ERROR"})

        finally:
            await adapter.close()
            self._active_loops.pop(conversation_id, None)

    async def stop(self, conversation_id: str) -> None:
        """Stop a running agent loop.

        Args:
            conversation_id: Conversation to stop.
        """
        stop_event = self._active_loops.get(conversation_id)
        if stop_event:
            stop_event.set()
            logger.info(f"Stop signal sent to conversation: {conversation_id}")

    def is_running(self, conversation_id: str) -> bool:
        """Check if an agent loop is running for a conversation."""
        return conversation_id in self._active_loops

    # ------------------------------------------------------------------
    # Internal Methods
    # ------------------------------------------------------------------

    async def _build_context(
        self,
        conversation_id: str,
        user_input: str,
        model_id: str,
        resources: list[ResourceRef] | None,
        system_prompt: str | None,
    ) -> "AgentContext":
        """Build agent context using PromptBuilder for tool-aware prompts.

        Only enabled tools get prompt blocks AND API schemas.
        Disabled tools are invisible to the model.
        """
        from agent.tool_registry import ToolRegistry
        from api.prompt import get_enabled_tools
        from prompt.prompt_builder import PromptBuilder

        # Determine which tools are enabled
        enabled_names = get_enabled_tools() if system_prompt is None else []
        # Allow explicit system_prompt override to bypass PromptBuilder
        if system_prompt:
            prompt = system_prompt
            enabled_names = list(ToolRegistry().list_all())
        else:
            builder = PromptBuilder()
            built = builder.build(enabled_tools=enabled_names, model_id=model_id)
            prompt = built.content

        # Only pass enabled tool schemas to the model
        registry = ToolRegistry()
        all_schemas = registry.list_for_json_schema()
        enabled_schemas = [
            t for t in all_schemas
            if t["function"]["name"] in enabled_names
        ]

        history_messages = await self._get_conversation_history(conversation_id)
        current_message = MessageBlock(role="user", content=user_input)
        messages = history_messages + [current_message]

        return AgentContext(
            messages=messages,
            system_prompt=prompt,
            tools=[
                ToolDefinition(
                    name=t["function"]["name"],
                    description=t["function"]["description"],
                    parameters=t["function"]["parameters"],
                )
                for t in enabled_schemas
            ],
            conversation_id=conversation_id,
        )

    async def _execute_native_tool_calls(
        self,
        conversation_id: str,
        context: "AgentContext",
        native_tool_calls: list[dict],
    ) -> list[ToolCallResult]:
        """Execute native DeepSeek-format tool calls.

        Parses the native tool_calls format (with function.name + function.arguments)
        into ToolCallRequest objects and executes them.

        Returns results with arguments populated for frontend SSE events.
        """
        from agent.tool_executor import get_tool_executor

        executor = get_tool_executor()
        calls_with_args: list[tuple[dict, dict]] = []

        for tc in native_tool_calls:
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            raw_args = fn.get("arguments", "{}")

            # Parse arguments (may be JSON string or dict)
            if isinstance(raw_args, str):
                try:
                    arguments = json.loads(raw_args)
                except json.JSONDecodeError:
                    arguments = {}
            else:
                arguments = raw_args if isinstance(raw_args, dict) else {}

            call_id = tc.get("id", str(uuid.uuid4()))
            calls_with_args.append((call_id, tool_name, arguments))

        requests = [
            ToolCallRequest(
                tool_name=name,
                arguments=args,
                call_id=cid,
                conversation_id=conversation_id,
            )
            for cid, name, args in calls_with_args
        ]

        results = await executor.execute_batch(requests)

        # Attach arguments to results for frontend SSE notification
        arg_map = {cid: args for cid, _, args in calls_with_args}
        for r in results:
            r.arguments = arg_map.get(r.call_id, {})
            r.tool_call_id = r.call_id

        return results

    async def _update_context_with_native_results(
        self,
        context: "AgentContext",
        native_tool_calls: list[dict],
        tool_results: list[ToolCallResult],
    ) -> "AgentContext":
        """Update context using native tool-call messages.

        Per DeepSeek docs: for each tool call, add:
        1. An assistant message with the tool_calls array
        2. A tool-result message with role="tool", tool_call_id, content
        """
        # Add assistant message with native tool_calls
        context.messages.append(
            MessageBlock(
                role="assistant",
                content=None,
                tool_calls=[
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        },
                    }
                    for tc in native_tool_calls
                ],
            )
        )

        # Add tool result messages
        for result in tool_results:
            content = (
                json.dumps(result.result, ensure_ascii=False, default=str)
                if result.success
                else f"Error: {result.error_message}"
            )
            context.messages.append(
                MessageBlock(
                    role="tool",
                    content=content,
                    tool_call_id=result.call_id,
                )
            )

        return context

    async def _get_conversation_history(
        self, conversation_id: str
    ) -> list[MessageBlock]:
        """Get conversation history from the database."""
        import uuid as _uuid
        from db.models import Message as MessageModel
        from db.session import get_session_maker
        from sqlalchemy import select

        history: list[MessageBlock] = []
        try:
            conv_uuid = _uuid.UUID(conversation_id)
        except ValueError:
            return history

        session_maker = get_session_maker()
        async with session_maker() as db:
            q = (
                select(MessageModel)
                .where(MessageModel.conversation_id == conv_uuid)
                .order_by(MessageModel.created_at.asc())
                .limit(20)
            )
            rows = (await db.execute(q)).scalars().all()
            for m in rows:
                if m.role not in ("user", "assistant"):
                    continue
                text = ""
                if m.content and isinstance(m.content, list):
                    text = "".join(b.get("text", "") for b in m.content if b.get("type") == "text")
                history.append(
                    MessageBlock(
                        role=m.role,
                        content=text,
                        thinking_content=m.thinking_content,
                    )
                )
        return history

    def _default_system_prompt(self) -> str:
        """Get the default system prompt.

        No text-based tool formatting — tools are passed natively via the
        tools API parameter. Keep the prompt clean and simple.
        """
        return (
            "You are a helpful AI assistant with access to tools. "
            "Use the provided tools when they help answer the user's question. "
            "After using a tool, synthesize the results into a clear, "
            "natural-language response directly addressing what the user asked."
        )


# ---------------------------------------------------------------------------
# Agent Context Dataclass
# ---------------------------------------------------------------------------


class AgentContext(BaseModel):
    """Context for a single agent loop iteration."""

    messages: list[MessageBlock]
    system_prompt: str
    tools: list[ToolDefinition]
    conversation_id: str = ""
    model_id: str = "deepseek-v4-pro"
    context_profile: str = "balanced"
    resources: list[ResourceRef] = Field(default_factory=list)
