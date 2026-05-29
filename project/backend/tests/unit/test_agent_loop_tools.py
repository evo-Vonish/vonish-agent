import json
import shutil
import uuid
from pathlib import Path

import pytest

from agent.agent_loop import AgentContext, AgentLoop
from agent.model_adapter import MessageBlock
from agent.tool_executor import ToolCallRequest, ToolCallResult, ToolExecutor
from core.config import settings


@pytest.mark.anyio
async def test_text_tool_results_are_returned_as_user_context():
    loop = AgentLoop()
    context = AgentContext(
        messages=[MessageBlock(role="user", content="list files")],
        system_prompt="system",
        tools=[],
    )
    tool_result = ToolCallResult(
        tool_name="shell_command",
        call_id="call_123",
        success=True,
        result={"stdout": "README.md\n"},
        execution_time_ms=12.0,
    )

    updated = await loop._update_context_with_results(
        context,
        '{"type":"tool_calls","calls":[{"tool":"shell_command","arguments":{}}]}',
        [tool_result],
    )

    assert [message.role for message in updated.messages] == [
        "user",
        "assistant",
        "user",
    ]
    assert updated.messages[-1].tool_call_id is None
    assert "Tool execution results" in updated.messages[-1].content
    assert '"tool": "shell_command"' in updated.messages[-1].content

    json_start = updated.messages[-1].content.index("[")
    json_end = updated.messages[-1].content.index("]\n\n") + 1
    payload = json.loads(updated.messages[-1].content[json_start:json_end])
    assert payload[0]["call_id"] == "call_123"
    assert payload[0]["result"] == {"stdout": "README.md\n"}


@pytest.mark.anyio
async def test_default_shell_command_handler_executes_in_workspace():
    conversation_id = f"test-{uuid.uuid4().hex}"
    workspace = Path(settings.workspace_root).resolve() / conversation_id
    try:
        result = await ToolExecutor().execute(
            ToolCallRequest(
                tool_name="shell_command",
                arguments={"command": "echo tool-ok", "timeout": 5},
                call_id="call_shell",
                conversation_id=conversation_id,
            )
        )

        assert result.success is True
        assert result.result["exit_code"] == 0
        assert "tool-ok" in result.result["stdout"]
        assert result.result["cwd"] == str(workspace)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
