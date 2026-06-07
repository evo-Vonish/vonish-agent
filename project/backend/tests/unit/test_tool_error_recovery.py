from agent.agent_loop import AgentLoop
from agent.model_adapter import DeepSeekAdapter, KimiAdapter, MessageBlock
from agent.tool_executor import ToolExecutor


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
