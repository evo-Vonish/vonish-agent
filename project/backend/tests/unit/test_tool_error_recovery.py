from agent.agent_loop import AgentLoop
from agent.message_sanitizer import EMPTY_ASSISTANT_PLACEHOLDER, sanitize_model_messages
from agent.model_adapter import DeepSeekAdapter, KimiAdapter, MessageBlock
from agent.tool_executor import ToolCallResult, ToolExecutor


def test_failed_tool_error_falls_back_to_stderr_stdout_hint_or_exit_code() -> None:
    assert (
        ToolExecutor._extract_tool_error(
            {"success": False, "exit_code": 1, "stdout": "", "stderr": "", "hint": "Use PowerShell"}
        )
        == "Use PowerShell"
    )
    assert (
        ToolExecutor._extract_tool_error(
            {"success": False, "exit_code": 127, "stderr": "head not found"}
        )
        == "head not found"
    )
    assert ToolExecutor._extract_tool_error({"success": False, "exit_code": 2}) == "Tool exited with code 2."


def test_research_degraded_mode_keeps_web_fetch_as_fallback() -> None:
    loop = AgentLoop()
    conversation_id = "budget-test"
    state = loop._budget_state(conversation_id)
    state["degraded"] = True

    assert loop._budget_skip_reason(conversation_id, "research_fetch", {"url": "https://api.github.com/repos/x/y"})
    assert loop._budget_skip_reason(conversation_id, "web_fetch", {"url": "https://api.github.com/repos/x/y"}) is None

    state["domain_failures"]["api.github.com"] = 2
    assert "api.github.com" in (
        loop._budget_skip_reason(conversation_id, "web_fetch", {"url": "https://api.github.com/repos/x/y"}) or ""
    )


def test_repeated_open_artifact_failures_are_budgeted_by_path() -> None:
    loop = AgentLoop()
    conversation_id = "artifact-budget-test"
    args = {"path": "outputs/missing.pptx"}

    for _ in range(2):
        result = ToolCallResult(
            tool_name="open_artifact",
            call_id="call",
            success=False,
            result={"success": False, "error": "Artifact file does not exist"},
            error_message="Artifact file does not exist",
            arguments=args,
            execution_time_ms=0,
        )
        loop._record_budget_result(conversation_id, result)

    assert "open_artifact" in (loop._budget_skip_reason(conversation_id, "open_artifact", args) or "")
    assert loop._budget_skip_reason(conversation_id, "open_artifact", {"path": "outputs/other.pptx"}) is None


def test_tool_call_assistant_messages_always_get_reasoning_content() -> None:
    messages = [
        MessageBlock(
            role="assistant",
            content=None,
            thinking_content=None,
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "expand_tool_result", "arguments": "{}"},
                }
            ],
        )
    ]

    for adapter in (
        DeepSeekAdapter("deepseek-v4-pro", api_key="x", api_base="http://example.test"),
        KimiAdapter("kimi-k2-6", api_key="x", api_base="http://example.test"),
    ):
        body = adapter._build_request_body(messages, "system", [], True, False)
        assistant_message = body["messages"][1]
        assert assistant_message["tool_calls"]
        assert assistant_message["reasoning_content"] == "Tool calls prepared."


def test_message_sanitizer_repairs_empty_assistant_messages() -> None:
    cleaned = sanitize_model_messages(
        [
            MessageBlock(role="user", content="continue"),
            MessageBlock(role="assistant", content=None, thinking_content=None, tool_calls=None),
        ]
    )

    assert len(cleaned) == 2
    assert cleaned[-1].role == "assistant"
    assert cleaned[-1].content == EMPTY_ASSISTANT_PLACEHOLDER


def test_message_sanitizer_drops_orphan_tool_messages() -> None:
    cleaned = sanitize_model_messages(
        [
            MessageBlock(role="user", content="continue"),
            MessageBlock(role="tool", content="orphan", tool_call_id="missing_call"),
        ]
    )

    assert [message.role for message in cleaned] == ["user"]


def test_message_sanitizer_normalizes_malformed_tool_calls() -> None:
    cleaned = sanitize_model_messages(
        [
            MessageBlock(
                role="assistant",
                content=None,
                tool_calls=[
                    {"id": "bad_1", "function": {"arguments": {"x": 1}}},
                    {"id": "good_1", "function": {"name": "expand_tool_result", "arguments": {"tool_name": "ipython"}}},
                ],
            ),
            MessageBlock(role="tool", content='{"ok": true}', tool_call_id="good_1"),
        ]
    )

    assert cleaned[0].role == "assistant"
    assert len(cleaned[0].tool_calls or []) == 1
    assert cleaned[0].tool_calls[0]["function"]["name"] == "expand_tool_result"
    assert cleaned[0].tool_calls[0]["function"]["arguments"] == '{"tool_name": "ipython"}'
    assert cleaned[1].role == "tool"


def test_adapter_request_body_uses_message_sanitizer() -> None:
    messages = [
        MessageBlock(role="user", content="continue"),
        MessageBlock(role="assistant", content=None),
        MessageBlock(role="tool", content="orphan", tool_call_id="missing_call"),
    ]

    body = DeepSeekAdapter("deepseek-v4-pro", api_key="x", api_base="http://example.test")._build_request_body(
        messages,
        "system",
        [],
        True,
        False,
    )

    assert [message["role"] for message in body["messages"]] == ["system", "user", "assistant"]
    assert body["messages"][-1]["content"] == EMPTY_ASSISTANT_PLACEHOLDER
