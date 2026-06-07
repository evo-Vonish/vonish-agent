"""Context memory map and recall helpers.

This module builds a structured, recall-first view over the raw conversation
records already stored in Message, ToolCall, and ConversationMemory. It does
not delete or rewrite raw content; it only creates compact views and recall
indexes for ContextBuilder and recall tools.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from core.config import settings
from context.minimal_context import estimate_tokens, extract_key_sections, serialize_tool_result
from db.models import ConversationMemory, Message, ToolCall
from db.session import get_session_maker
from services.git_service import workspace_root


PIN_TYPES = {"user_constraint", "file", "decision", "error", "note", "plan"}
RECALL_MODES = {"raw", "key_segments", "summary_plus_segments", "structure_only"}
TARGET_TYPES = {
    "tool_result",
    "chat_message",
    "file",
    "file_range",
    "grep",
    "search_result",
    "browser_snapshot",
    "error_log",
    "shell_output",
    "diff",
    "user_constraint",
    "plan",
    "artifact_validation",
}
CONTEXT_MAP_TOOL_INDEX_LIMIT = 80
CONTEXT_MAP_MESSAGE_INDEX_LIMIT = 160
CONTEXT_MAP_QUERY_SCAN_LIMIT = 200


@dataclass
class RecallWindow:
    conversation_id: str
    item_ids: list[str]
    turns: int


_context_recall_windows: dict[str, dict[str, int]] = {}


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _json_dumps(value: Any, *, limit: int | None = None) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str, indent=2)
    if limit is not None and len(text) > limit:
        return text[:limit] + f"\n[truncated chars={len(text) - limit}]"
    return text


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                elif "text" in block:
                    parts.append(str(block.get("text") or ""))
                else:
                    parts.append(_json_dumps(block, limit=800))
            else:
                parts.append(str(block))
        return "\n".join(part for part in parts if part)
    return _json_dumps(content, limit=4000)


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _terms(query: str) -> list[str]:
    return [term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]{2,}", query or "")[:16]]


def _matches_query(text: str, query: str) -> bool:
    terms = _terms(query)
    if not terms:
        return True
    lower = text.lower()
    return all(term in lower for term in terms[:8])


def _extract_urls(text: str, limit: int = 8) -> list[str]:
    urls = re.findall(r"https?://[^\s\"'<>),]+", text or "")
    seen: list[str] = []
    for url in urls:
        clean = url.rstrip(".,;")
        if clean not in seen:
            seen.append(clean)
        if len(seen) >= limit:
            break
    return seen


def _extract_paths(text: str, limit: int = 10) -> list[str]:
    patterns = [
        r"[A-Za-z]:\\[^\s\"'<>|]+",
        r"(?:^|\s)(?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]+",
        r"\b[\w.-]+\.(?:py|ts|tsx|js|jsx|json|md|txt|log|css|html|yml|yaml|toml)\b",
    ]
    found: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text or "", flags=re.MULTILINE):
            value = match.strip()
            if value and value not in found:
                found.append(value)
            if len(found) >= limit:
                return found
    return found


def _extract_code_outline(text: str, limit: int = 30) -> list[str]:
    outline: list[str] = []
    code_patterns = [
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+[\w$]+\s*\(",
        r"^\s*(?:export\s+)?class\s+[\w$]+",
        r"^\s*(?:export\s+)?interface\s+[\w$]+",
        r"^\s*(?:export\s+)?type\s+[\w$]+\s*=",
        r"^\s*(?:def|class)\s+[\w_]+\s*[\(:]",
        r"^\s*import\s+.+",
        r"^\s*from\s+[\w.]+\s+import\s+.+",
    ]
    compiled = re.compile("|".join(f"(?:{p})" for p in code_patterns), re.MULTILINE)
    for match in compiled.finditer(text or ""):
        line = match.group(0).strip()
        if line and line not in outline:
            outline.append(line[:240])
        if len(outline) >= limit:
            break
    return outline


def classify_tool_result(tool_name: str, result: Any, arguments: dict[str, Any] | None = None) -> str:
    name = (tool_name or "").lower()
    if name in {"research_search", "research_fetch", "deep_research", "web_search", "web_fetch"}:
        return "search_research"
    if name in {"file_read", "read_file"}:
        return "code_file"
    if name in {"search_workspace"}:
        return "grep_result"
    if name in {"shell_command", "ipython"}:
        return "shell_log"
    if name in {"git_diff", "apply_patch"}:
        return "diff_patch"
    if name in {"write_to_file", "edit_file", "delete_file", "create_directories"}:
        return "artifact_result"
    if name.startswith("git_"):
        return "git_result"
    return "tool_result"


def _summary_for_tool(
    *,
    tool_name: str,
    content_type: str,
    arguments: dict[str, Any],
    result: Any,
    serialized: str,
) -> str:
    if isinstance(result, dict):
        success = result.get("success")
        error = result.get("error") or result.get("error_message")
        output = result.get("output") or result.get("summary") or result.get("message")
        status_bits = []
        if success is not None:
            status_bits.append(f"success={bool(success)}")
        if result.get("tool_name"):
            status_bits.append(f"tool={result.get('tool_name')}")
        if error:
            status_bits.append(f"error={str(error)[:220]}")
        if output:
            status_bits.append(f"output={str(output)[:220]}")
        if status_bits:
            return "; ".join(status_bits)

    if content_type == "search_research":
        query = arguments.get("query") or arguments.get("url") or ""
        urls = _extract_urls(serialized, limit=3)
        return f"{tool_name} query/url={query!r}; urls={len(urls)}; chars={len(serialized)}"
    if content_type == "code_file":
        path = arguments.get("path") or arguments.get("file_path") or ""
        outline_count = len(_extract_code_outline(serialized, limit=100))
        return f"file={path}; outline_items={outline_count}; chars={len(serialized)}"
    if content_type == "shell_log":
        command = arguments.get("command") or arguments.get("code") or ""
        errors = len(re.findall(r"\b(error|exception|failed|traceback)\b", serialized, re.IGNORECASE))
        return f"command/code={str(command)[:180]!r}; error_markers={errors}; chars={len(serialized)}"
    if content_type == "diff_patch":
        hunks = serialized.count("@@")
        paths = _extract_paths(serialized, limit=4)
        return f"diff/patch paths={paths}; hunks={hunks}; chars={len(serialized)}"
    return f"{tool_name}; type={content_type}; chars={len(serialized)}"


def compress_tool_result_view(
    *,
    tool_result_id: str,
    tool_name: str,
    arguments: dict[str, Any] | None,
    result: Any,
    max_key_chars: int = 5000,
) -> dict[str, Any]:
    """Create a local compressed view for a stored tool result."""
    args = arguments or {}
    serialized = serialize_tool_result(result if result is not None else {})
    content_type = classify_tool_result(tool_name, result, args)
    key_sections = extract_key_sections(serialized, max_chars=max_key_chars, query=_json_dumps(args, limit=1000))
    return {
        "id": tool_result_id,
        "recall_id": tool_result_id,
        "type": content_type,
        "tool_name": tool_name,
        "summary": _summary_for_tool(
            tool_name=tool_name,
            content_type=content_type,
            arguments=args,
            result=result,
            serialized=serialized,
        ),
        "token_count": estimate_tokens(serialized),
        "checksum": _fingerprint(serialized),
        "keywords": {
            "urls": _extract_urls(serialized),
            "paths": _extract_paths(serialized),
            "outline": _extract_code_outline(serialized),
        },
        "key_segments": [
            {
                "description": f"key segment {index + 1}",
                "content": section[:1400],
                "token_count": estimate_tokens(section),
            }
            for index, section in enumerate(key_sections[:8])
        ],
        "hidden_map": [
            {
                "label": "raw_tool_result",
                "original_chars": len(serialized),
                "recall": f"custom_context_recall(type=tool_result,id={tool_result_id})",
            }
        ],
    }


def _looks_like_constraint(text: str) -> bool:
    if not text:
        return False
    patterns = [
        r"\b(must|never|always|required|forbidden|don't|do not|only|without asking)\b",
        r"(必须|务必|不要|不能|禁止|只允许|不允许|无需确认|不用确认|记住|要求|一定|不要问)",
        r"([A-Za-z]:\\|/[\w.-]+/|端口|port|API|key|workspace|工作区)",
    ]
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def extract_constraints_from_text(text: str, *, source_id: str, max_items: int = 8) -> list[dict[str, Any]]:
    """Extract likely user constraints without rewriting the original wording."""
    chunks = re.split(r"(?:\n\s*\n|\n[-*]\s+|\n\d+[\.)]\s+|[。；;])", text or "")
    constraints: list[dict[str, Any]] = []
    for raw in chunks:
        value = raw.strip()
        if len(value) < 6 or not _looks_like_constraint(value):
            continue
        intensity = "hard" if re.search(r"(必须|务必|禁止|不能|never|required|forbidden|must)", value, re.IGNORECASE) else "soft"
        constraints.append(
            {
                "id": f"constraint_{source_id}_{len(constraints) + 1}",
                "source": source_id,
                "intensity": intensity,
                "content": value[:500],
            }
        )
        if len(constraints) >= max_items:
            break
    return constraints


async def _load_rows(conversation_id: str) -> tuple[list[Message], list[ToolCall], list[ConversationMemory]]:
    conv_uuid = uuid.UUID(conversation_id)
    session_maker = get_session_maker()
    async with session_maker() as db:
        messages = list(
            (
                await db.execute(
                    select(Message)
                    .where(Message.conversation_id == conv_uuid)
                    .order_by(Message.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        tools = list(
            (
                await db.execute(
                    select(ToolCall)
                    .where(ToolCall.conversation_id == conv_uuid)
                    .order_by(ToolCall.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        memories = list(
            (
                await db.execute(
                    select(ConversationMemory)
                    .where(ConversationMemory.conversation_id == conv_uuid)
                    .where(ConversationMemory.is_active == True)  # noqa: E712
                    .order_by(ConversationMemory.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
    return messages, tools, memories


def _memory_json(memory: ConversationMemory) -> dict[str, Any]:
    try:
        value = json.loads(memory.content)
        return value if isinstance(value, dict) else {"content": memory.content}
    except Exception:
        return {"content": memory.content}


def _pin_items(memories: list[ConversationMemory]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for memory in memories:
        if not memory.memory_type.startswith("pin_"):
            continue
        data = _memory_json(memory)
        items.append(
            {
                "id": str(memory.id),
                "type": memory.memory_type.removeprefix("pin_"),
                "content": str(data.get("content") or data.get("target", {}).get("content") or "")[:800],
                "reason": data.get("reason") or "",
                "created_at": memory.created_at.isoformat() if memory.created_at else None,
            }
        )
    return items


async def build_context_map(conversation_id: str, scope: str = "all") -> dict[str, Any]:
    """Return a compact map of recallable context without expanding raw content."""
    messages, tools, memories = await _load_rows(conversation_id)
    constraints: list[dict[str, Any]] = []
    indexed_messages = messages[-CONTEXT_MAP_MESSAGE_INDEX_LIMIT:]
    indexed_tools = tools[-CONTEXT_MAP_TOOL_INDEX_LIMIT:]
    for msg in indexed_messages:
        if msg.role == "user":
            constraints.extend(extract_constraints_from_text(_message_text(msg.content), source_id=str(msg.id), max_items=4))

    tool_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    latest_tools: list[dict[str, Any]] = []
    for tool in tools:
        tool_counts[tool.tool_name] = tool_counts.get(tool.tool_name, 0) + 1
        content_type = classify_tool_result(tool.tool_name, None, tool.arguments)
        type_counts[content_type] = type_counts.get(content_type, 0) + 1

    for tool in indexed_tools:
        view = compress_tool_result_view(
            tool_result_id=str(tool.id),
            tool_name=tool.tool_name,
            arguments=tool.arguments,
            result=tool.result,
            max_key_chars=1200,
        )
        latest_tools.append(
            {
                "id": str(tool.id),
                "tool_name": tool.tool_name,
                "type": view["type"],
                "status": tool.status,
                "summary": view["summary"],
                "token_count": view["token_count"],
                "created_at": tool.created_at.isoformat() if tool.created_at else None,
            }
        )

    pin_items = _pin_items(memories)
    sampled_raw_tokens = sum(
        estimate_tokens(_message_text(msg.content)) + estimate_tokens(msg.thinking_content or "")
        for msg in indexed_messages
    )
    sampled_raw_tokens += sum(estimate_tokens(tool.result or {}) for tool in indexed_tools)
    compressed_tokens = sum(estimate_tokens(item.get("summary", "")) for item in latest_tools)
    omitted_messages = max(0, len(messages) - len(indexed_messages))
    omitted_tools = max(0, len(tools) - len(indexed_tools))

    return {
        "success": True,
        "scope": scope,
        "availableMemory": {
            "userConstraints": {"total": len(constraints), "pinned": sum(1 for item in pin_items if item["type"] == "user_constraint")},
            "toolResults": tool_counts,
            "toolResultTypes": type_counts,
            "chatMessages": {
                "total": len(messages),
                "user": sum(1 for msg in messages if msg.role == "user"),
                "assistant": sum(1 for msg in messages if msg.role == "assistant"),
                "indexedForPreview": len(indexed_messages),
            },
            "pinnedItems": {
                "total": len(pin_items),
                "byType": {kind: sum(1 for item in pin_items if item["type"] == kind) for kind in PIN_TYPES},
            },
        },
        "latestToolResults": list(reversed(latest_tools[-12:])),
        "constraintsPreview": constraints[:12],
        "pinnedPreview": pin_items[:12],
        "recallStats": {
            "activeWindows": dict(_context_recall_windows.get(conversation_id, {})),
        },
        "compressionStatus": {
            "sampledRawTokens": sampled_raw_tokens,
            "currentCompressedTokens": compressed_tokens,
            "compressionRatio": round(1 - (compressed_tokens / max(sampled_raw_tokens, 1)), 4),
            "pendingCompaction": 0,
            "omittedOlderMessagesFromPreview": omitted_messages,
            "omittedOlderToolResultsFromPreview": omitted_tools,
            "note": "Context map indexes recent previews only; raw records remain stored and recallable by targeted tools.",
        },
    }


def _workspace_file_path(workspace_id: str, rel_path: str) -> Path:
    root = workspace_root(workspace_id)
    raw = (rel_path or "").replace("\\", "/").strip().lstrip("/")
    target = (root / raw).resolve()
    if target != root and root not in target.parents:
        raise ValueError("Path escapes workspace")
    return target


def _read_file_target(workspace_id: str, rel_path: str, start_line: int | None, end_line: int | None, max_chars: int) -> tuple[str, bool]:
    path = _workspace_file_path(workspace_id, rel_path)
    if not path.exists() or not path.is_file():
        return f"File not found: {rel_path}", False
    data = path.read_text(encoding="utf-8", errors="replace")
    if start_line or end_line:
        lines = data.splitlines()
        start = max(1, int(start_line or 1))
        end = min(len(lines), int(end_line or len(lines)))
        data = "\n".join(f"{idx}: {line}" for idx, line in enumerate(lines[start - 1:end], start=start))
    return _json_dumps(data, limit=max_chars), True


def _grep_workspace(workspace_id: str, query: str, max_chars: int) -> tuple[str, bool]:
    root = workspace_root(workspace_id)
    if not root.exists():
        return f"Workspace not found: {workspace_id}", False
    terms = _terms(query)
    if not terms:
        return "grep query is required", False
    matches: list[str] = []
    allowed_suffixes = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".txt", ".log", ".css", ".html", ".yml", ".yaml", ".toml"}
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in allowed_suffixes:
            continue
        if any(part in {".git", "__pycache__", "node_modules", "dist"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lower = text.lower()
        if not all(term in lower for term in terms[:6]):
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        for idx, line in enumerate(text.splitlines(), start=1):
            if any(term in line.lower() for term in terms):
                matches.append(f"{rel}:{idx}: {line[:300]}")
                break
        if len("\n".join(matches)) >= max_chars:
            break
    return _json_dumps("\n".join(matches) or "No matches.", limit=max_chars), True


def _shape_recalled_content(raw: str, mode: str, max_tokens: int, query: str = "") -> str:
    max_chars = max(1000, max_tokens * 4)
    if mode == "raw":
        return _json_dumps(raw, limit=max_chars)
    if mode == "structure_only":
        structure = {
            "chars": len(raw),
            "tokens": estimate_tokens(raw),
            "urls": _extract_urls(raw),
            "paths": _extract_paths(raw),
            "outline": _extract_code_outline(raw),
            "checksum": _fingerprint(raw),
        }
        return _json_dumps(structure, limit=max_chars)
    key_sections = extract_key_sections(raw, max_chars=max_chars, query=query)
    if mode == "key_segments":
        return "\n\n".join(key_sections)[:max_chars]
    summary = {
        "chars": len(raw),
        "tokens": estimate_tokens(raw),
        "checksum": _fingerprint(raw),
        "key_segments": key_sections[:8],
    }
    return _json_dumps(summary, limit=max_chars)


async def custom_context_recall(
    *,
    conversation_id: str,
    workspace_id: str,
    targets: list[dict[str, Any]],
    turns: int = 1,
    max_tokens: int = 4000,
    mode: str = "summary_plus_segments",
    reason: str = "",
) -> dict[str, Any]:
    """Recall targeted raw or compact context into the current conversation window."""
    if not targets:
        return {
            "success": False,
            "error": "targets is required. Use context_map first, then pass exact recall targets.",
        }
    if mode not in RECALL_MODES:
        mode = "summary_plus_segments"
    safe_turns = _clamp_int(turns, 1, 1, 10)
    safe_tokens = _clamp_int(max_tokens, 4000, 500, 80_000)
    messages, tools, memories = await _load_rows(conversation_id)
    tool_by_id = {str(row.id): row for row in tools}
    message_by_id = {str(row.id): row for row in messages}
    pin_items = _pin_items(memories)
    recalled_items: list[dict[str, Any]] = []
    active_ids: list[str] = []

    for target in targets[:20]:
        target_type = str(target.get("type") or "")
        if target_type not in TARGET_TYPES:
            recalled_items.append({"target": target, "found": False, "content": f"Unsupported target type: {target_type}", "tokensUsed": 0})
            continue
        raw = ""
        found = False
        recall_id = str(target.get("id") or "").removeprefix("history_")
        query = str(target.get("query") or "")

        if target_type in {"tool_result", "search_result", "shell_output", "diff", "error_log", "browser_snapshot", "artifact_validation"}:
            row = tool_by_id.get(recall_id)
            if row is None and query:
                for candidate in reversed(tools[-CONTEXT_MAP_QUERY_SCAN_LIMIT:]):
                    payload = f"{candidate.tool_name}\n{candidate.arguments}\n{serialize_tool_result(candidate.result or {})}"
                    if _matches_query(payload, query):
                        row = candidate
                        break
            if row is not None:
                found = True
                active_ids.append(str(row.id))
                raw = serialize_tool_result(row.result if row.result is not None else {})
                if mode != "raw":
                    view = compress_tool_result_view(
                        tool_result_id=str(row.id),
                        tool_name=row.tool_name,
                        arguments=row.arguments,
                        result=row.result,
                    )
                    raw = _json_dumps(view)

        elif target_type == "chat_message":
            row = message_by_id.get(recall_id)
            if row is None and query:
                for candidate in reversed(messages):
                    text = _message_text(candidate.content)
                    if _matches_query(text, query):
                        row = candidate
                        break
            if row is not None:
                found = True
                active_ids.append(str(row.id))
                raw = _message_text(row.content)
                if row.thinking_content:
                    raw += "\n\n[thinking]\n" + row.thinking_content

        elif target_type in {"file", "file_range"}:
            raw, found = _read_file_target(
                workspace_id,
                str(target.get("path") or ""),
                target.get("startLine"),
                target.get("endLine"),
                safe_tokens * 4,
            )
            if found:
                active_ids.append(f"file:{target.get('path')}")

        elif target_type == "grep":
            raw, found = _grep_workspace(workspace_id, query, safe_tokens * 4)
            if found:
                active_ids.append(f"grep:{query}")

        elif target_type in {"user_constraint", "plan"}:
            candidates = [item for item in pin_items if item["type"] in {"user_constraint", "plan", "note"}]
            if recall_id:
                candidates = [item for item in candidates if item["id"] == recall_id]
            if query:
                candidates = [item for item in candidates if _matches_query(item.get("content", ""), query)]
            found = bool(candidates)
            raw = _json_dumps(candidates[:10])
            active_ids.extend([item["id"] for item in candidates[:10]])

        content = _shape_recalled_content(raw, mode, safe_tokens, query=query) if found else raw
        recalled_items.append(
            {
                "target": target,
                "found": found,
                "content": content,
                "tokensUsed": estimate_tokens(content),
                "hasMore": found and estimate_tokens(raw) > estimate_tokens(content),
            }
        )

    if active_ids:
        _context_recall_windows.setdefault(conversation_id, {})
        for item_id in active_ids:
            _context_recall_windows[conversation_id][item_id] = safe_turns

    return {
        "success": True,
        "reason": reason,
        "mode": mode,
        "turns": safe_turns,
        "recalledItems": recalled_items,
        "totalTokensUsed": sum(int(item.get("tokensUsed") or 0) for item in recalled_items),
    }


async def pin_memory(
    *,
    conversation_id: str,
    target: dict[str, Any],
    reason: str = "",
    expires_after_turns: int | None = None,
) -> dict[str, Any]:
    pin_type = str(target.get("type") or "note")
    if pin_type not in PIN_TYPES:
        pin_type = "note"
    content = str(target.get("content") or target.get("id") or "")
    if not content:
        return {"success": False, "error": "Pin content or id is required."}
    payload = {
        "target": target,
        "content": content,
        "reason": reason,
        "expires_after_turns": expires_after_turns,
    }
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        return {"success": False, "error": "Invalid conversation_id"}
    session_maker = get_session_maker()
    async with session_maker() as db:
        row = ConversationMemory(
            conversation_id=conv_uuid,
            memory_type=f"pin_{pin_type}",
            content=json.dumps(payload, ensure_ascii=False),
            is_active=True,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return {"success": True, "pinId": str(row.id), "type": pin_type, "content": content, "reason": reason}


async def unpin_memory(*, conversation_id: str, target_id: str) -> dict[str, Any]:
    try:
        conv_uuid = uuid.UUID(conversation_id)
        target_uuid = uuid.UUID(target_id)
    except ValueError:
        return {"success": False, "error": "Invalid conversation_id or targetId"}
    session_maker = get_session_maker()
    async with session_maker() as db:
        row = (
            await db.execute(
                select(ConversationMemory)
                .where(ConversationMemory.conversation_id == conv_uuid)
                .where(ConversationMemory.id == target_uuid)
            )
        ).scalar_one_or_none()
        if row is None:
            return {"success": False, "error": f"Pin not found: {target_id}"}
        row.is_active = False
        await db.commit()
    return {"success": True, "unpinned": target_id}


async def build_vccs_context(conversation_id: str, *, max_tools: int = 10, max_constraints: int = 10) -> str:
    """Build a small VCCS-style context map for the system prompt."""
    try:
        context_map = await build_context_map(conversation_id, scope="current_task")
    except Exception:
        return ""
    constraints = context_map.get("constraintsPreview", [])[:max_constraints]
    pins = context_map.get("pinnedPreview", [])[:max_constraints]
    tools = context_map.get("latestToolResults", [])[:max_tools]
    compression = context_map.get("compressionStatus", {})
    lines: list[str] = [
        "<context_compaction_notice>",
        "Some history may be represented as compact maps. Raw messages and tool results remain stored and can be recalled.",
        "Compressed summaries are maps, not source text. Recall exact raw content before code edits, final reports, factual citations, or complex debugging.",
        "</context_compaction_notice>",
        "<task_state>",
        "  <goal>Continue the current user task without losing constraints, files, tool evidence, or unresolved errors.</goal>",
        "  <current_phase>auto_detect_from_conversation</current_phase>",
        "</task_state>",
        '<user_constraints pinned="true">',
    ]
    for item in constraints:
        lines.append(f'  <constraint intensity="{item.get("intensity", "soft")}" source="{item.get("source", "")}">{_xml_escape(item.get("content", ""))}</constraint>')
    for item in pins:
        lines.append(f'  <constraint intensity="pinned" source="pin:{item.get("id", "")}">{_xml_escape(item.get("content", ""))}</constraint>')
    lines.extend(["</user_constraints>", "<tool_result_index>"])
    for item in tools:
        lines.append(
            f'  <tool_result id="{item.get("id")}" type="{item.get("type")}" tool="{item.get("tool_name")}" '
            f'status="{item.get("status")}" recall="custom_context_recall(type=tool_result,id={item.get("id")})">'
            f'{_xml_escape(item.get("summary", ""))}</tool_result>'
        )
    lines.extend(
        [
            "</tool_result_index>",
            "<recall_instructions>",
            "Use context_map before broad recall. Use custom_context_recall for exact raw messages, tool results, files, file ranges, grep, shell output, diffs, and evidence.",
            "Use recall_maximum or CRAZY_for_tool_results only for final synthesis, broad evidence audit, or complex debugging.",
            "</recall_instructions>",
            f'<compression_status sampled_raw_tokens="{compression.get("sampledRawTokens", 0)}" compressed_tokens="{compression.get("currentCompressedTokens", 0)}" ratio="{compression.get("compressionRatio", 0)}"/>',
        ]
    )
    return "\n".join(lines)


def _xml_escape(value: Any) -> str:
    text = str(value or "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )[:1200]


def consume_context_recall_turn(conversation_id: str) -> None:
    windows = _context_recall_windows.get(conversation_id)
    if not windows:
        return
    for key in list(windows):
        remaining = int(windows[key]) - 1
        if remaining <= 0:
            windows.pop(key, None)
        else:
            windows[key] = remaining
    if not windows:
        _context_recall_windows.pop(conversation_id, None)
