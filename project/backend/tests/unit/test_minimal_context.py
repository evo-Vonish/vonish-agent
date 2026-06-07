from context.minimal_context import (
    MAX_CONTEXT_TOKENS,
    ContextLimitExceededError,
    consume_expansion_build,
    extract_key_sections,
    format_tool_result_for_context,
    is_tool_result_expanded,
    mark_all_tool_results_expanded,
    mark_tool_result_focus,
    mark_tool_result_expanded,
    truncate_tool_result,
)


def test_tool_result_truncation_keeps_head_tail_and_recovery_hint() -> None:
    content = "HEAD-" + ("x" * 1000) + "-TAIL"

    result = truncate_tool_result(
        content,
        tool_name="shell_command",
        tool_result_id="result-1",
        max_chars=300,
    )

    assert "HEAD-" in result[:40]
    assert result.endswith("-TAIL")
    assert "middle of tool result compressed" in result
    assert "result-1" in result
    assert "expand_tool_result" in result
    assert "tool_result_head" in result
    assert "tool_result_tail" in result


def test_tool_result_truncation_keeps_key_sections() -> None:
    content = (
        "HEAD\n"
        + ("filler\n" * 400)
        + "CRITICAL ERROR: fetch failed because No extracted page text\n"
        + "Evidence: content_ref research_abc123 should be cited\n"
        + ("more filler\n" * 400)
        + "TAIL"
    )

    result = truncate_tool_result(
        content,
        tool_name="deep_research",
        tool_result_id="result-key",
        max_chars=1200,
    )

    assert "CRITICAL ERROR" in result
    assert "content_ref research_abc123" in result


def test_extract_key_sections_supports_query_terms() -> None:
    content = "alpha\n\nboring paragraph\n\n关键资料: 火锅底料 research evidence\n\nomega"

    sections = extract_key_sections(content, max_chars=400, query="火锅 evidence")

    assert any("火锅底料" in section for section in sections)


def test_expansion_window_expires_after_three_context_builds() -> None:
    conversation_id = "conversation-test"
    result_id = "result-test"
    mark_tool_result_expanded(conversation_id, result_id, builds=3)

    for _ in range(3):
        assert is_tool_result_expanded(conversation_id, result_id)
        formatted = format_tool_result_for_context(
            "full content",
            conversation_id=conversation_id,
            tool_name="file_read",
            tool_result_id=result_id,
        )
        assert formatted.startswith("full content")
        consume_expansion_build(conversation_id)

    assert not is_tool_result_expanded(conversation_id, result_id)


def test_global_tool_result_expansion_expires() -> None:
    conversation_id = "conversation-global"
    mark_all_tool_results_expanded(conversation_id, builds=2)

    assert format_tool_result_for_context(
        "full global",
        conversation_id=conversation_id,
        tool_name="research_fetch",
        tool_result_id="any-result",
    ) == "full global"
    consume_expansion_build(conversation_id)
    assert is_tool_result_expanded(conversation_id, "another-result")
    consume_expansion_build(conversation_id)
    assert not is_tool_result_expanded(conversation_id, "another-result")


def test_focus_tool_result_expansion_by_query() -> None:
    conversation_id = "conversation-query"
    mark_tool_result_focus(conversation_id, query="needle source", builds=1)

    assert is_tool_result_expanded(
        conversation_id,
        "unmatched-id",
        tool_name="web_fetch",
        content="This paragraph contains needle and source.",
    )


def test_context_limit_error_reports_fixed_limit() -> None:
    error = ContextLimitExceededError(MAX_CONTEXT_TOKENS + 1)

    assert "256,000" in str(error)
    assert error.token_count == MAX_CONTEXT_TOKENS + 1
