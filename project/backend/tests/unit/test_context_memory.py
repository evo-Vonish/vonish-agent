from context.context_memory import (
    classify_tool_result,
    compress_tool_result_view,
    extract_constraints_from_text,
)


def test_classify_tool_result_by_tool_name() -> None:
    assert classify_tool_result("deep_research", {}, {}) == "search_research"
    assert classify_tool_result("file_read", {}, {}) == "code_file"
    assert classify_tool_result("shell_command", {}, {}) == "shell_log"
    assert classify_tool_result("git_diff", {}, {}) == "diff_patch"


def test_compress_tool_result_view_keeps_research_evidence() -> None:
    result = {
        "success": True,
        "query": "context recall",
        "sources": [
            {
                "title": "Paper",
                "url": "https://example.com/paper",
                "snippet": "Evidence says recall ids must be stable.",
            }
        ],
        "content_ref": "research_abc123",
    }

    view = compress_tool_result_view(
        tool_result_id="tool-1",
        tool_name="deep_research",
        arguments={"query": "context recall"},
        result=result,
    )

    assert view["type"] == "search_research"
    assert view["recall_id"] == "tool-1"
    assert "https://example.com/paper" in view["keywords"]["urls"]
    assert view["key_segments"]


def test_extract_constraints_keeps_original_requirement_text() -> None:
    text = "请务必使用真实 API，不要使用假数据。端口必须固定为 18473 和 18480。普通闲聊。"

    constraints = extract_constraints_from_text(text, source_id="msg-1")

    assert len(constraints) >= 1
    assert any("真实 API" in item["content"] for item in constraints)
    assert any(item["intensity"] == "hard" for item in constraints)

