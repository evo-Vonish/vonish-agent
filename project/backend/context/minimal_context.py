"""Minimal context policy.

The model receives an immutable conversation history until the fixed context
limit is reached. Tool results are the only content reduced for routine model
input: full values remain in the database, while the model sees a head/tail
view unless it explicitly requests a temporary expansion.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

MAX_CONTEXT_TOKENS = 256_000
THINKING_RETENTION_TURNS = 8
TOOL_RESULT_MAX_CHARS = 48_000
TOOL_RESULT_EXPANSION_BUILDS = 3

# conversation_id -> tool result id -> remaining context builds
_expansion_windows: dict[str, dict[str, int]] = defaultdict(dict)
_global_expansion_windows: dict[str, int] = defaultdict(int)
_tool_name_expansion_windows: dict[str, dict[str, int]] = defaultdict(dict)
_query_expansion_windows: dict[str, list[dict[str, Any]]] = defaultdict(list)

KEY_SECTION_PATTERNS = [
    r"\b(error|exception|traceback|failed|failure|warning|timeout|denied|invalid)\b",
    r"\b(success|completed|summary|result|evidence|source|citation|content_ref|result_ref)\b",
    r"\b(todo|next|recommend|conclusion|finding|risk|root cause|原因|结论|证据|引用|来源|错误|失败|成功|摘要)\b",
    r"^\s*(#{1,6}\s+|[-*]\s+\[|[-*]\s+|\d+[\.)]\s+)",
    r"\b(https?://|[A-Za-z]:\\|/[\w.-]+/|\.py\b|\.tsx?\b|\.md\b|\.json\b)\b",
]
KEY_SECTION_RE = re.compile("|".join(f"(?:{pattern})" for pattern in KEY_SECTION_PATTERNS), re.IGNORECASE | re.MULTILINE)


def estimate_tokens(value: Any) -> int:
    """Estimate tokens using the convention used throughout the project."""
    if value is None:
        return 0
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, default=str)
    return max(1, len(value) // 4) if value else 0


def serialize_tool_result(value: Any) -> str:
    """Serialize a tool result without losing Unicode or non-JSON values."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _compact(text: str) -> str:
    return " ".join(str(text or "").split())


def _split_sections(text: str) -> list[tuple[int, int, str]]:
    """Split long tool output into paragraph/line windows with offsets."""
    if not text:
        return []
    sections: list[tuple[int, int, str]] = []
    for match in re.finditer(r".+?(?:\n\s*\n|\Z)", text, re.DOTALL):
        block = match.group(0)
        if len(block) > 1800:
            start = match.start()
            lines = block.splitlines(keepends=True)
            cursor = start
            chunk: list[str] = []
            chunk_start = cursor
            chunk_len = 0
            for line in lines:
                if chunk and chunk_len + len(line) > 1400:
                    value = "".join(chunk)
                    sections.append((chunk_start, chunk_start + len(value), value))
                    chunk = []
                    chunk_start = cursor
                    chunk_len = 0
                chunk.append(line)
                chunk_len += len(line)
                cursor += len(line)
            if chunk:
                value = "".join(chunk)
                sections.append((chunk_start, chunk_start + len(value), value))
        else:
            sections.append((match.start(), match.end(), block))
    return sections


def _score_section(section: str, query_terms: list[str]) -> int:
    text = section.strip()
    if not text:
        return 0
    score = 0
    score += min(20, len(KEY_SECTION_RE.findall(text)) * 4)
    lower = text.lower()
    for term in query_terms:
        if term and term in lower:
            score += 8
    if len(text) < 80:
        score -= 2
    if len(text) > 1600:
        score -= 2
    if text.lstrip().startswith(("{", "[", "```")):
        score += 2
    return score


def extract_key_sections(
    content: str,
    *,
    max_chars: int,
    query: str = "",
    max_sections: int = 10,
) -> list[str]:
    """Pick useful middle sections from a long tool result."""
    text = str(content or "")
    terms = [term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]{2,}", query or "")[:12]]
    sections = _split_sections(text)
    ranked: list[tuple[int, int, int, str]] = []
    for index, (start, _end, section) in enumerate(sections):
        score = _score_section(section, terms)
        if score <= 0:
            continue
        # Slightly prefer middle evidence over duplicating head/tail.
        if start < len(text) * 0.18 or start > len(text) * 0.82:
            score -= 3
        ranked.append((score, -len(section), index, section.strip()))

    ranked.sort(reverse=True)
    selected: list[tuple[int, str]] = []
    used = 0
    seen: set[str] = set()
    for score, _neg_len, index, section in ranked:
        if len(selected) >= max_sections or used >= max_chars:
            break
        fingerprint = _compact(section[:240]).lower()
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)
        budget = max(240, min(len(section), max_chars - used))
        selected.append((index, section[:budget]))
        used += budget
    selected.sort(key=lambda item: item[0])
    return [section for _, section in selected]


def truncate_tool_result(
    content: str,
    *,
    tool_name: str,
    tool_result_id: str,
    max_chars: int = TOOL_RESULT_MAX_CHARS,
) -> str:
    """Return a model-facing head/key-sections/tail view of a tool result."""
    text = str(content or "")
    if len(text) <= max_chars:
        return text

    marker = (
        "\n\n[... middle of tool result compressed ...]\n"
        f"[tool={tool_name}; tool_result_id={tool_result_id}; "
        f"original_chars={len(text)}]\n"
        "The model sees head + selected key sections + tail. "
        "Call focus_tool_results for targeted recall, expand_tool_result for one full result, "
        "or CRAZY_for_tool_results when a report/final synthesis needs all stored tool evidence.\n"
    )
    available = max(2, max_chars - len(marker) - 240)
    head_chars = max(1200, int(available * 0.34))
    tail_chars = max(1000, int(available * 0.26))
    key_budget = max(1200, available - head_chars - tail_chars)
    key_sections = extract_key_sections(text, max_chars=key_budget)
    if key_sections:
        key_text = "\n\n".join(
            f"[key_section_{index + 1}]\n{section}"
            for index, section in enumerate(key_sections)
        )
    else:
        midpoint = len(text) // 2
        span = min(key_budget, len(text) // 5)
        key_text = f"[middle_context]\n{text[max(0, midpoint - span // 2): midpoint + span // 2]}"
    return (
        f"[tool_result_head]\n{text[:head_chars]}"
        f"{marker}"
        f"{key_text}\n\n"
        f"[tool_result_tail]\n{text[-tail_chars:]}"
    )


def mark_tool_result_expanded(
    conversation_id: str,
    tool_result_id: str,
    builds: int = TOOL_RESULT_EXPANSION_BUILDS,
) -> None:
    """Keep one stored tool result fully visible for upcoming context builds."""
    if conversation_id and tool_result_id:
        _expansion_windows[conversation_id][tool_result_id] = max(1, int(builds))


def mark_all_tool_results_expanded(
    conversation_id: str,
    builds: int = TOOL_RESULT_EXPANSION_BUILDS,
) -> None:
    """Keep all tool results fully visible for upcoming context builds."""
    if conversation_id:
        _global_expansion_windows[conversation_id] = max(1, int(builds))


def mark_tool_result_focus(
    conversation_id: str,
    *,
    tool_result_ids: list[str] | None = None,
    tool_names: list[str] | None = None,
    query: str = "",
    builds: int = TOOL_RESULT_EXPANSION_BUILDS,
) -> None:
    """Open targeted expansion windows by id, tool name, or content query."""
    if not conversation_id:
        return
    window = max(1, int(builds))
    for result_id in tool_result_ids or []:
        if result_id:
            _expansion_windows[conversation_id][str(result_id)] = window
    for tool_name in tool_names or []:
        if tool_name:
            _tool_name_expansion_windows[conversation_id][str(tool_name)] = window
    if query.strip():
        _query_expansion_windows[conversation_id].append(
            {"query": query.strip(), "remaining": window}
        )


def expansion_state(conversation_id: str) -> dict[str, Any]:
    """Return model-facing expansion state for diagnostics/tool output."""
    return {
        "all_results_remaining": _global_expansion_windows.get(conversation_id, 0),
        "tool_result_ids": dict(_expansion_windows.get(conversation_id, {})),
        "tool_names": dict(_tool_name_expansion_windows.get(conversation_id, {})),
        "queries": list(_query_expansion_windows.get(conversation_id, [])),
    }


def _query_matches(content: str, query: str) -> bool:
    terms = [term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]{2,}", query or "")]
    if not terms:
        return False
    haystack = content.lower()
    return all(term in haystack for term in terms[:8])


def is_tool_result_expanded(
    conversation_id: str,
    tool_result_id: str,
    *,
    tool_name: str = "",
    content: str = "",
) -> bool:
    """Return whether a tool result is inside its temporary expansion window."""
    if _global_expansion_windows.get(conversation_id, 0) > 0:
        return True
    if _expansion_windows.get(conversation_id, {}).get(tool_result_id, 0) > 0:
        return True
    if tool_name and _tool_name_expansion_windows.get(conversation_id, {}).get(tool_name, 0) > 0:
        return True
    if content:
        for item in _query_expansion_windows.get(conversation_id, []):
            if int(item.get("remaining", 0)) > 0 and _query_matches(content, str(item.get("query", ""))):
                return True
    return False


def consume_expansion_build(conversation_id: str) -> None:
    """Advance temporary expansion windows after one context build."""
    windows = _expansion_windows.get(conversation_id)
    if windows:
        for result_id in list(windows):
            remaining = windows[result_id] - 1
            if remaining <= 0:
                windows.pop(result_id, None)
            else:
                windows[result_id] = remaining
        if not windows:
            _expansion_windows.pop(conversation_id, None)

    if _global_expansion_windows.get(conversation_id, 0) > 0:
        remaining = _global_expansion_windows[conversation_id] - 1
        if remaining <= 0:
            _global_expansion_windows.pop(conversation_id, None)
        else:
            _global_expansion_windows[conversation_id] = remaining

    name_windows = _tool_name_expansion_windows.get(conversation_id)
    if name_windows:
        for name in list(name_windows):
            remaining = name_windows[name] - 1
            if remaining <= 0:
                name_windows.pop(name, None)
            else:
                name_windows[name] = remaining
        if not name_windows:
            _tool_name_expansion_windows.pop(conversation_id, None)

    query_windows = _query_expansion_windows.get(conversation_id)
    if query_windows:
        next_items = []
        for item in query_windows:
            remaining = int(item.get("remaining", 0)) - 1
            if remaining > 0:
                next_items.append({**item, "remaining": remaining})
        if next_items:
            _query_expansion_windows[conversation_id] = next_items
        else:
            _query_expansion_windows.pop(conversation_id, None)


def format_tool_result_for_context(
    value: Any,
    *,
    conversation_id: str,
    tool_name: str,
    tool_result_id: str,
    force_full: bool = False,
) -> str:
    """Create the tool-result text sent to the model."""
    content = serialize_tool_result(value)
    expanded = force_full or is_tool_result_expanded(
        conversation_id,
        tool_result_id,
        tool_name=tool_name,
        content=content,
    )
    if expanded:
        query_remaining = 0
        for item in _query_expansion_windows.get(conversation_id, []):
            remaining = int(item.get("remaining", 0))
            if remaining > 0 and _query_matches(content, str(item.get("query", ""))):
                query_remaining = max(query_remaining, remaining)
        remaining = max(
            _global_expansion_windows.get(conversation_id, 0),
            _expansion_windows.get(conversation_id, {}).get(tool_result_id, 0),
            _tool_name_expansion_windows.get(conversation_id, {}).get(tool_name, 0),
            query_remaining,
        )
        suffix = ""
        if remaining == 1:
            suffix = (
                "\n\n[tool_result_expansion_notice]\n"
                "This full tool_result expansion expires after this context build. "
                "Call focus_tool_results or CRAZY_for_tool_results again if full evidence is still needed.\n"
            )
        return content + suffix
    return truncate_tool_result(
        content,
        tool_name=tool_name,
        tool_result_id=tool_result_id,
    )


class ContextLimitExceededError(ValueError):
    """Raised when the next model request would exceed the fixed context limit."""

    def __init__(self, token_count: int) -> None:
        self.token_count = token_count
        super().__init__(
            f"Context limit reached: estimated {token_count:,} tokens exceeds "
            f"the fixed {MAX_CONTEXT_TOKENS:,}-token limit. Start a new "
            "conversation or remove large tool output before continuing."
        )
