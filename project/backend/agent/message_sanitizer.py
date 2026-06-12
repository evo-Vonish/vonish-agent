"""Provider-facing chat message sanitation.

The runtime stores rich UI segments and reconstructed tool history. Before a
provider request, every message must still obey the chat-completions contract:
assistant messages need visible content or valid tool_calls, and tool messages
must directly answer a known tool_call_id.
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.model_adapter import MessageBlock


EMPTY_ASSISTANT_PLACEHOLDER = (
    "[Historical assistant checkpoint; no visible final text was stored.]"
)


def _text_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return True


def _normalize_arguments(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value if isinstance(value, dict) else {}, ensure_ascii=False, default=str)


def sanitize_tool_calls(tool_calls: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return only provider-valid function tool calls."""
    valid: list[dict[str, Any]] = []
    for index, raw in enumerate(tool_calls or []):
        if not isinstance(raw, dict):
            continue
        fn = raw.get("function") if isinstance(raw.get("function"), dict) else {}
        name = str(fn.get("name") or raw.get("name") or "").strip()
        if not name:
            continue
        call_id = str(raw.get("id") or f"call_{uuid.uuid4().hex[:12]}")
        valid.append(
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": _normalize_arguments(fn.get("arguments", raw.get("arguments", "{}"))),
                },
            }
        )
    return valid


def sanitize_model_messages(messages: list["MessageBlock"]) -> list["MessageBlock"]:
    """Sanitize model-facing messages and drop invalid orphan tool results.

    This is intentionally conservative: it never changes user text, but it
    prevents provider 400s caused by empty assistant messages, malformed
    tool_calls, or role=tool messages without a matching assistant tool call.
    """
    sanitized: list[MessageBlock] = []
    from agent.model_adapter import MessageBlock
    pending_tool_ids: set[str] = set()

    for msg in messages:
        role = str(msg.role or "").strip()
        if role not in {"system", "user", "assistant", "tool"}:
            role = "user"

        if role == "assistant":
            tool_calls = sanitize_tool_calls(msg.tool_calls)
            if tool_calls:
                pending_tool_ids.update(str(call["id"]) for call in tool_calls)
            content = msg.content
            if not _text_present(content) and not tool_calls:
                content = EMPTY_ASSISTANT_PLACEHOLDER
            sanitized.append(
                MessageBlock(
                    role="assistant",
                    content=content,
                    thinking_content=msg.thinking_content,
                    tool_calls=tool_calls or None,
                )
            )
            continue

        if role == "tool":
            tool_call_id = str(msg.tool_call_id or "").strip()
            if not tool_call_id or tool_call_id not in pending_tool_ids:
                continue
            content = msg.content
            if not _text_present(content):
                content = "[Tool completed without stored output.]"
            sanitized.append(
                MessageBlock(
                    role="tool",
                    content=content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, default=str),
                    tool_call_id=tool_call_id,
                )
            )
            pending_tool_ids.discard(tool_call_id)
            continue

        content = msg.content
        if not _text_present(content):
            continue
        sanitized.append(
            MessageBlock(
                role=role,
                content=content,
                thinking_content=msg.thinking_content if role == "assistant" else None,
            )
        )

    return sanitized
