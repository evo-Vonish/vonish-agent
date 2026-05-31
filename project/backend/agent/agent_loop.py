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
import time
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field
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

    model_config = ConfigDict(populate_by_name=True)

    uri: str
    mime_type: str = Field(default="", alias="mimeType")
    title: str = ""
    original_name: str = Field(default="", alias="originalName")
    workspace_path: str = Field(default="", alias="workspacePath")
    context_text: str = Field(default="", alias="contextText")
    context_policy: str = Field(default="none", alias="contextPolicy")
    status: str = ""
    error: str | None = None


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
        self._pause_events: dict[str, asyncio.Event] = {}
        self._interactions: dict[str, dict[str, Any]] = {}

    # ── Human Interaction State Management ──────────────────────

    def set_waiting(self, conversation_id: str, interaction: dict) -> None:
        """Set agent into waiting_user state with an interaction payload."""
        self._interactions[conversation_id] = interaction
        pe = asyncio.Event()
        self._pause_events[conversation_id] = pe
        logger.info(f"Agent waiting for user response: {conversation_id}")

    def is_waiting(self, conversation_id: str) -> bool:
        return conversation_id in self._pause_events

    def get_interaction(self, conversation_id: str) -> dict | None:
        return self._interactions.get(conversation_id)

    async def resume_from_interaction(self, conversation_id: str, response: dict) -> None:
        """Resume agent loop with user response."""
        self._interactions[conversation_id] = {
            **(self._interactions.get(conversation_id) or {}),
            "response": response,
        }
        pe = self._pause_events.pop(conversation_id, None)
        if pe:
            pe.set()
            logger.info(f"Agent resumed: {conversation_id}")

    def cancel_interaction(self, conversation_id: str) -> None:
        """Cancel waiting and abort agent loop."""
        pe = self._pause_events.pop(conversation_id, None)
        if pe:
            pe.set()
        if conversation_id in self._active_loops:
            self._active_loops[conversation_id].set()
        self._interactions.pop(conversation_id, None)
        logger.info(f"Agent interaction cancelled: {conversation_id}")

    async def run(
        self,
        conversation_id: str,
        user_input: str,
        resources: list[ResourceRef] | None = None,
        model_id: str = "deepseek-v4-pro",
        enable_thinking: bool | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        context_profile: str = "balanced",
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
        segment_id: str | None = None
        segment_started_at: float = 0.0
        segment_stats: dict[str, int] = {}
        thinking_step_id: str | None = None
        thinking_step_started_at: float = 0.0

        def _now_iso() -> str:
            return datetime.now(timezone.utc).isoformat()

        def _duration_ms(start: float) -> int:
            return int((time.perf_counter() - start) * 1000)

        def _reset_segment_stats() -> dict[str, int]:
            return {
                "thinkingCount": 0,
                "toolCallCount": 0,
                "commandCount": 0,
                "fileReadCount": 0,
                "fileWriteCount": 0,
                "fileEditCount": 0,
                "webRequestCount": 0,
                "recallCount": 0,
                "errorCount": 0,
                "totalTokens": 0,
            }

        def _tool_step_type(tool_name: str) -> str:
            if tool_name in {"file_read", "read_file"}:
                return "file_read"
            if tool_name in {"write_to_file"}:
                return "file_write"
            if tool_name in {"edit_file", "apply_patch"}:
                return "file_edit"
            if tool_name in {"shell_command", "ipython"}:
                return "command"
            if tool_name == "web_search":
                return "web_search"
            if tool_name == "web_fetch":
                return "web_fetch"
            if tool_name in {"ask_user_question", "request_approval"}:
                return "user_interaction"
            if tool_name in {"git_status", "git_diff", "git_history"}:
                return "tool_call"
            return "tool_call"

        def _tool_title(tool_name: str, args: dict[str, Any]) -> tuple[str, str]:
            if tool_name in {"file_read", "read_file"}:
                return "正在读取文件", str(args.get("path") or "")
            if tool_name == "write_to_file":
                return "正在写入文件", str(args.get("path") or "")
            if tool_name in {"edit_file", "apply_patch"}:
                return "正在修改文件", str(args.get("path") or args.get("file") or "")
            if tool_name == "shell_command":
                return "正在运行命令", str(args.get("command") or "")
            if tool_name == "web_search":
                return "正在搜索资料", str(args.get("query") or args.get("queries") or "")
            if tool_name == "web_fetch":
                return "正在抓取网页", str(args.get("url") or "")
            if tool_name == "ipython":
                return "正在运行 Python 代码", ""
            if tool_name == "git_status":
                return "Git Status", "检查当前仓库状态"
            if tool_name == "git_diff":
                return "Git Diff", str(args.get("file_path") or args.get("scope") or "working")
            if tool_name == "git_history":
                return "Git History", str(args.get("file_path") or args.get("mode") or "log")
            if tool_name == "ask_user_question":
                return "等待用户回答", str(args.get("question") or "")
            if tool_name == "request_approval":
                return "等待用户确认", str(args.get("title") or "")
            return f"正在使用 {tool_name}", ""

        def _bump_tool_stats(tool_name: str) -> None:
            step_type = _tool_step_type(tool_name)
            segment_stats["toolCallCount"] += 1
            if step_type == "command":
                segment_stats["commandCount"] += 1
            elif step_type == "file_read":
                segment_stats["fileReadCount"] += 1
            elif step_type == "file_write":
                segment_stats["fileWriteCount"] += 1
            elif step_type == "file_edit":
                segment_stats["fileEditCount"] += 1
            elif step_type in {"web_search", "web_fetch"}:
                segment_stats["webRequestCount"] += 1

        # Create model adapter
        adapter = ModelAdapterFactory.create(
            model_id,
            api_key=api_key,
            api_base=api_base,
        )
        normalized_resources = [
            item if isinstance(item, ResourceRef) else ResourceRef.model_validate(item)
            for item in (resources or [])
        ]

        try:
            yield sse_event("message_start", {"message_id": loop_id})

            # Build initial context
            context = await self._build_context(
                conversation_id=conversation_id,
                user_input=user_input,
                model_id=model_id,
                resources=normalized_resources,
                context_profile=context_profile,
                system_prompt=system_prompt,
            )

            # Multi-round loop
            for round_num in range(self.config.max_rounds):
                if stop_event.is_set():
                    yield sse_event("aborted", {"reason": "user_request"})
                    return

                # ── Check for human interaction pause ─────────────────
                if self.is_waiting(conversation_id):
                    # Yield interaction card to frontend
                    interaction = self.get_interaction(conversation_id) or {}
                    yield sse_event("interaction_required", {
                        "interaction_id": interaction.get("id", ""),
                        "type": interaction.get("type", ""),
                        "title": interaction.get("title", ""),
                        "description": interaction.get("description", ""),
                        "options": interaction.get("options", []),
                        "payload": interaction.get("payload"),
                    })
                    yield sse_event("agent_paused", {
                        "reason": interaction.get("type", "interaction"),
                    })
                    # Wait for resume or cancel
                    pe = self._pause_events.get(conversation_id)
                    if pe:
                        await pe.wait()
                    # Check if cancelled
                    if stop_event.is_set():
                        yield sse_event("aborted", {"reason": "interaction_cancelled"})
                        return
                    # Get user response
                    interaction = self.get_interaction(conversation_id) or {}
                    response = interaction.get("response", {})
                    yield sse_event("agent_resumed", {
                        "choice": response.get("choice", ""),
                        "message": response.get("message", ""),
                    })
                    # Inject response as context for the next round
                    resp_text = response.get("choice", "custom")
                    if response.get("message"):
                        resp_text += f": {response['message']}"
                    user_resp_msg = MessageBlock(
                        role="user",
                        content=f"[User Response — {interaction.get('type', 'interaction')}]: {resp_text}",
                    )
                    context.messages.append(user_resp_msg)

                logger.debug(
                    f"Agent loop round {round_num + 1}/{self.config.max_rounds}",
                    extra={"conversation_id": conversation_id},
                )

                accumulated_text = ""
                thinking_buffer = ""
                in_thinking = False
                # Collect tool_calls from native function calling
                native_tool_calls: list[dict] = []
                tool_step_started_at: dict[str, float] = {}
                tool_step_ids: dict[str, str] = {}

                # ── Inject todo reminder ──────────────────────────────
                todo_reminder = self._get_todo_reminder(conversation_id)
                effective_prompt = context.system_prompt
                if todo_reminder:
                    effective_prompt = (effective_prompt or "") + todo_reminder

                # Stream from model — pass tools natively, NOT in prompt text
                async for chunk in adapter.stream_chat(
                    messages=context.messages,
                    system_prompt=effective_prompt,
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
                            if segment_id is None:
                                segment_id = f"seg_{uuid.uuid4().hex[:10]}"
                                segment_started_at = time.perf_counter()
                                segment_stats = _reset_segment_stats()
                                yield sse_event(
                                    "segment_start",
                                    {
                                        "segmentId": segment_id,
                                        "status": "running",
                                        "startedAt": _now_iso(),
                                        "collapsible": True,
                                        "defaultCollapsed": False,
                                    },
                                )
                            thinking_step_id = f"step_{uuid.uuid4().hex[:10]}"
                            thinking_step_started_at = time.perf_counter()
                            segment_stats["thinkingCount"] += 1
                            yield sse_event(
                                "step_start",
                                {
                                    "segmentId": segment_id,
                                    "stepId": thinking_step_id,
                                    "stepType": "thinking",
                                    "title": "正在思考中",
                                    "startedAt": _now_iso(),
                                    "collapsible": True,
                                    "defaultCollapsed": False,
                                },
                            )
                            yield sse_event("thinking_start", {})
                        thinking_buffer += str(content or "")
                        if segment_id and thinking_step_id:
                            yield sse_event(
                                "step_delta",
                                {
                                    "segmentId": segment_id,
                                    "stepId": thinking_step_id,
                                    "delta": str(content or ""),
                                },
                            )
                        yield sse_event("thinking_delta", {"content": str(content or "")})

                    elif chunk_type == "text_delta":
                        if in_thinking:
                            in_thinking = False
                            if segment_id and thinking_step_id:
                                yield sse_event(
                                    "step_end",
                                    {
                                        "segmentId": segment_id,
                                        "stepId": thinking_step_id,
                                        "status": "completed",
                                        "durationMs": _duration_ms(thinking_step_started_at),
                                        "outputPreview": "思考完成",
                                    },
                                )
                                thinking_step_id = None
                            yield sse_event("thinking_end", {})
                        if segment_id is not None:
                            yield sse_event(
                                "segment_end",
                                {
                                    "segmentId": segment_id,
                                    "status": "completed",
                                    "durationMs": _duration_ms(segment_started_at),
                                    **segment_stats,
                                    "endedAt": _now_iso(),
                                    "collapsible": True,
                                    "defaultCollapsed": True,
                                },
                            )
                            segment_id = None
                            segment_stats = {}
                        accumulated_text += str(content or "")
                        # Stream text immediately — with native tool_calls,
                        # text and tool_calls are mutually exclusive
                        clean = str(content or "")
                        # Strip leaked XML tool-call artifacts (reasoning_effort max side-effect)
                        if clean.strip().startswith("<") and any(tag in clean for tag in ("</invoke>", "<invoke", "</tool_calls>", "<tool_calls>", "<parameter")):
                            import re
                            clean = re.sub(r'</?tool_calls>', '', clean)
                            clean = re.sub(r'<invoke[^>]*>|</invoke>', '', clean)
                            clean = re.sub(r'<parameter[^>]*/?>', '', clean)
                            if not clean.strip():
                                continue
                        yield sse_event("text_delta", {"content": clean})

                    elif chunk_type == "usage":
                        usage = chunk.get("usage")
                        if usage:
                            if segment_stats is not None:
                                segment_stats["totalTokens"] = int(
                                    usage.get("input_tokens", 0) or 0
                                ) + int(usage.get("output_tokens", 0) or 0)
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
                    if segment_id and thinking_step_id:
                        yield sse_event(
                            "step_end",
                            {
                                "segmentId": segment_id,
                                "stepId": thinking_step_id,
                                "status": "completed",
                                "durationMs": _duration_ms(thinking_step_started_at),
                                "outputPreview": "思考完成",
                            },
                        )
                        thinking_step_id = None
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
                        if segment_id is None:
                            segment_id = f"seg_{uuid.uuid4().hex[:10]}"
                            segment_started_at = time.perf_counter()
                            segment_stats = _reset_segment_stats()
                            yield sse_event(
                                "segment_start",
                                {
                                    "segmentId": segment_id,
                                    "status": "running",
                                    "startedAt": _now_iso(),
                                    "collapsible": True,
                                    "defaultCollapsed": False,
                                },
                            )
                        call_id = str(tc.get("id", "") or f"call_{uuid.uuid4().hex[:8]}")
                        tool_name = str(fn.get("name", ""))
                        step_id = f"step_{call_id}"
                        tool_step_ids[call_id] = step_id
                        tool_step_started_at[call_id] = time.perf_counter()
                        _bump_tool_stats(tool_name)
                        title, subtitle = _tool_title(tool_name, args)
                        yield sse_event(
                            "step_start",
                            {
                                "segmentId": segment_id,
                                "stepId": step_id,
                                "stepType": _tool_step_type(tool_name),
                                "title": title,
                                "subtitle": subtitle,
                                "toolName": tool_name,
                                "toolCallId": call_id,
                                "startedAt": _now_iso(),
                                "collapsible": True,
                                "defaultCollapsed": False,
                                "inputPreview": json.dumps(args, ensure_ascii=False)[:1000],
                            },
                        )
                        yield sse_event(
                            "tool_call_start",
                            {
                                "call_id": call_id,
                                "tool": tool_name,
                                "arguments": args,
                            },
                        )

                    # 2. Execute tools (may take time, but frontend already shows spinners)
                    tool_results = await self._execute_native_tool_calls(
                        conversation_id, context, native_tool_calls
                    )

                    # 2b. Persist tool calls to database
                    await self._persist_tool_calls(
                        conversation_id, native_tool_calls, tool_results
                    )

                    # 3. Send results to frontend
                    for result in tool_results:
                        step_id = tool_step_ids.get(result.call_id, f"step_{result.call_id}")
                        duration_ms = (
                            result.execution_time_ms
                            if result.execution_time_ms is not None
                            else _duration_ms(tool_step_started_at.get(result.call_id, time.perf_counter()))
                        )
                        yield sse_event(
                            "step_end",
                            {
                                "segmentId": segment_id,
                                "stepId": step_id,
                                "status": "completed" if result.success else "failed",
                                "durationMs": duration_ms,
                                "outputPreview": self._preview_tool_result(result),
                                "metadata": {
                                    "toolName": result.tool_name,
                                    "toolCallId": result.call_id,
                                },
                                "error": result.error_message if not result.success else None,
                            },
                        )
                        if not result.success and segment_stats:
                            segment_stats["errorCount"] += 1
                            yield sse_event(
                                "workflow_error",
                                {
                                    "segmentId": segment_id,
                                    "stepId": step_id,
                                    "errorId": f"err_{uuid.uuid4().hex[:10]}",
                                    "severity": "error",
                                    "errorType": "tool_failed",
                                    "title": "工具执行失败",
                                    "message": result.error_message or f"{result.tool_name} 执行失败",
                                    "recoverable": True,
                                    "actions": [
                                        {"id": "retry_step", "label": "重试此步骤", "style": "primary"},
                                        {"id": "skip_step", "label": "跳过并继续", "style": "secondary"},
                                        {"id": "stop_task", "label": "停止任务", "style": "danger"},
                                        {"id": "view_details", "label": "查看详情", "style": "secondary"},
                                    ],
                                },
                            )
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

                    # 4. Check for interaction-required tools (ask_user_question, request_approval)
                    for result in tool_results:
                        if isinstance(result.result, dict) and result.result.get("interaction_required"):
                            interaction = result.result.get("interaction", {})
                            self.set_waiting(conversation_id, interaction)
                            if segment_id is not None:
                                yield sse_event(
                                    "segment_end",
                                    {
                                        "segmentId": segment_id,
                                        "status": "waiting_user",
                                        "durationMs": _duration_ms(segment_started_at),
                                        **segment_stats,
                                        "endedAt": _now_iso(),
                                        "collapsible": True,
                                        "defaultCollapsed": False,
                                    },
                                )
                                segment_id = None
                                segment_stats = {}
                            break

                    if segment_id is not None:
                        yield sse_event(
                            "segment_end",
                            {
                                "segmentId": segment_id,
                                "status": "completed" if segment_stats.get("errorCount", 0) == 0 else "failed",
                                "durationMs": _duration_ms(segment_started_at),
                                **segment_stats,
                                "endedAt": _now_iso(),
                                "collapsible": True,
                                "defaultCollapsed": True,
                            },
                        )
                        segment_id = None
                        segment_stats = {}

                    # 5. Feed results back as native tool-response messages
                    context = await self._update_context_with_native_results(
                        context, native_tool_calls, tool_results
                    )
                    # Continue to next round — model will synthesize answer OR pause for user
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

    @staticmethod
    def _preview_tool_result(result: ToolCallResult) -> str:
        """Create a short semantic preview for UI step cards."""
        if not result.success:
            return result.error_message or f"{result.tool_name} failed"
        payload = result.result
        if isinstance(payload, dict):
            if payload.get("output"):
                return str(payload.get("output"))[:500]
            if payload.get("path"):
                return f"完成：{payload.get('path')}"
            if payload.get("count") is not None:
                return f"完成，共 {payload.get('count')} 项"
            if payload.get("success") is True:
                return "执行完成"
        if isinstance(payload, str):
            return payload[:500]
        return "执行完成"

    async def _build_context(
        self,
        conversation_id: str,
        user_input: str,
        model_id: str,
        resources: list[ResourceRef] | None,
        context_profile: str,
        system_prompt: str | None,
    ) -> "AgentContext":
        """Build agent context using ContextBuilder for budget-aware prompts.

        Only enabled tools get prompt blocks AND API schemas.
        Disabled tools are invisible to the model.
        """
        from agent.tool_registry import ToolRegistry
        from api.prompt import get_enabled_tools

        # Determine which tools are enabled
        enabled_names = get_enabled_tools() if system_prompt is None else []
        # Allow explicit system_prompt override to bypass PromptBuilder
        if system_prompt:
            prompt = system_prompt
            enabled_names = list(ToolRegistry().list_all())
            history_messages = await self._get_conversation_history(conversation_id)
            messages = history_messages + [MessageBlock(role="user", content=user_input)]
            registry = ToolRegistry()
            all_schemas = registry.list_for_json_schema()
            enabled_schemas = [
                t for t in all_schemas
                if t["function"]["name"] in enabled_names
            ]
        else:
            from context.context_builder import ContextBuilder

            builder = ContextBuilder()
            built = await builder.build(
                conversation_id=conversation_id,
                user_query=user_input,
                model_id=model_id,
                profile_name=context_profile,
            )
            prompt = self._append_resource_context(built.system_prompt, resources or [])
            messages = []
            for msg in built.messages:
                if msg.get("role") == "system":
                    continue
                messages.append(
                    MessageBlock(
                        role=str(msg.get("role", "user")),
                        content=msg.get("content"),
                        thinking_content=msg.get("thinking_content"),
                        tool_calls=msg.get("tool_calls"),
                        tool_call_id=msg.get("tool_call_id"),
                    )
                )
            enabled_schemas = [
                item
                for item in built.tools
                if isinstance(item, dict) and isinstance(item.get("function"), dict)
            ]

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
            model_id=model_id,
            context_profile=context_profile,
            resources=resources or [],
        )

    def _append_resource_context(self, system_prompt: str, resources: list[ResourceRef]) -> str:
        """Append uploaded file context to the system prompt."""
        if not resources:
            return system_prompt

        lines: list[str] = [
            "",
            "## Uploaded Files",
            "User uploaded files into the current workspace. Do not assume file contents.",
            "Use read_file, shell_command, ipython, or other workspace tools to inspect files when needed.",
        ]

        for resource in resources:
            name = resource.original_name or resource.title or resource.workspace_path or resource.uri
            path = resource.workspace_path or resource.uri
            mime = resource.mime_type or 'unknown'
            size = f"{resource.size / 1024:.0f} KB" if hasattr(resource, 'size') and resource.size else ''
            lines.append(f"- {path}  ({mime}{', ' + size if size else ''})")

        return f"{system_prompt}\n" + "\n".join(lines)

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

    async def _persist_tool_calls(
        self,
        conversation_id: str,
        native_tool_calls: list[dict],
        tool_results: list[ToolCallResult],
    ) -> None:
        """Save tool call records to the database.

        Args:
            conversation_id: Current conversation ID.
            native_tool_calls: Original tool call definitions from the model.
            tool_results: Executed results.
        """
        import uuid as _uuid
        from datetime import datetime, timezone
        from db.models import ToolCall as ToolCallModel
        from db.session import get_session_maker

        try:
            conv_uuid = _uuid.UUID(conversation_id)
        except ValueError:
            return

        session_maker = get_session_maker()
        async with session_maker() as db:
            for tc, result in zip(native_tool_calls, tool_results):
                fn = tc.get("function", {})
                tool_name = fn.get("name", result.tool_name)
                arguments = result.arguments or {}
                now = datetime.now(timezone.utc)

                tool_call = ToolCallModel(
                    conversation_id=conv_uuid,
                    tool_name=tool_name,
                    arguments=arguments,
                    status="completed" if result.success else "failed",
                    result=result.result if result.success else {"error": result.error_message},
                    started_at=now,
                    completed_at=now,
                )
                db.add(tool_call)

            await db.commit()

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

    async def _update_context_with_results(
        self,
        context: "AgentContext",
        assistant_content: str,
        tool_results: list[ToolCallResult],
    ) -> "AgentContext":
        """Compatibility path for text/XML tool-call flows.

        Native tool calls use role="tool" messages. Older parser-driven flows
        feed a compact tool-result JSON block back as a user message.
        """
        context.messages.append(
            MessageBlock(
                role="assistant",
                content=assistant_content,
            )
        )
        payload = [
            {
                "call_id": result.call_id,
                "tool": result.tool_name,
                "success": result.success,
                "result": result.result if result.success else None,
                "error": result.error_message if not result.success else None,
                "duration_ms": result.execution_time_ms,
            }
            for result in tool_results
        ]
        context.messages.append(
            MessageBlock(
                role="user",
                content=(
                    "Tool execution results:\n"
                    f"{json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
                    "Use these results to continue the answer."
                ),
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

    def _get_todo_reminder(self, conversation_id: str) -> str:
        """Weak reminder: inject current todo state from workspace/.agent/todo.json."""
        import json as _json
        from pathlib import Path as _Path
        from core.config import settings

        todo_path = _Path(settings.workspace_root) / conversation_id / ".agent" / "todo.json"
        if not todo_path.exists():
            return ""

        try:
            data = _json.loads(todo_path.read_text(encoding="utf-8"))
        except Exception:
            return ""

        items = data.get("items", [])
        if not items:
            return ""

        # Count statuses
        counts = {}
        for it in items:
            s = it.get("status", "todo")
            counts[s] = counts.get(s, 0) + 1

        pending = counts.get("todo", 0) + counts.get("doing", 0)
        done = counts.get("done", 0)
        blocked = counts.get("blocked", 0)

        lines = ["\n[Current Todo Status]"]
        if done > 0:
            lines.append(f"✅ {done} done")
        if pending > 0:
            lines.append(f"⏳ {pending} pending (todo/doing)")
        if blocked > 0:
            lines.append(f"🚫 {blocked} blocked")

        lines.append("Items:")
        for it in items[:8]:
            icon = {"done": "✅", "doing": "➡️", "blocked": "🚫"}.get(it["status"], "⬜")
            lines.append(f"  {icon} [{it['status']}] {it['title']}")

        if pending == 0 and done > 0:
            lines.append("\nAll items are done. If you are about to give a final summary, you may.")
        elif pending > 0:
            lines.append(f"\n{pending} item(s) still pending. Update todo status as you progress.")

        return "\n".join(lines) + "\n"

    def _default_system_prompt(self) -> str:
        """Get the default system prompt.

        CRITICAL: Tools are passed natively via the API tools parameter.
        DO NOT output <tool_calls>, <invoke>, or <parameter> XML in text.
        Just call the tools directly through function calling.
        """
        return (
            "You are a helpful AI assistant. You have tools available — "
            "call them directly through function calling, NOT by writing "
            "<tool_calls> or <invoke> XML in your text output. "
            "Never describe tool calls in text — just use them. "
            "After using a tool, synthesize results into a clear response."
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
