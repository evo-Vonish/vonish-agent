"""Human Interaction Tools — set_todo_list, ask_user_question, request_approval.

These tools pause the agent loop and yield interaction cards to the frontend.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncio

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# ── Todo Tool ────────────────────────────────────────────────────────────────

TODO_STATES = ["todo", "doing", "done", "blocked", "cancelled"]


def _todo_dir(workspace_root: str, conversation_id: str) -> Path:
    return (Path(workspace_root) / conversation_id / ".agent").resolve()


def _todo_path(workspace_root: str, conversation_id: str) -> Path:
    return _todo_dir(workspace_root, conversation_id) / "todo.json"


async def handle_set_todo_list(
    mode: str,
    conversation_id: str = "",
    items: list[dict] | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Create, update, or read the conversation todo list."""
    ws_root = settings.workspace_root
    todo_dir = _todo_dir(ws_root, conversation_id)
    todo_dir.mkdir(parents=True, exist_ok=True)
    todo_file = _todo_path(ws_root, conversation_id)

    # Read existing
    existing: dict[str, dict] = {}
    if todo_file.exists():
        try:
            raw = json.loads(todo_file.read_text(encoding="utf-8"))
            existing = {it["id"]: it for it in raw.get("items", [])}
        except (json.JSONDecodeError, KeyError):
            pass

    if mode == "read":
        items_list = list(existing.values())
        items_list.sort(key=lambda x: x.get("updated_at", ""))
        return {"success": True, "mode": "read", "items": items_list, "count": len(items_list)}

    if mode == "replace":
        result_items = items or []
    elif mode == "update" and items:
        for it in items:
            tid = it["id"]
            if tid in existing:
                existing[tid].update(it)
                existing[tid]["updated_at"] = datetime.now(timezone.utc).isoformat()
            else:
                it["updated_at"] = datetime.now(timezone.utc).isoformat()
                existing[tid] = it
        result_items = list(existing.values())
    else:
        result_items = list(existing.values())

    # Save
    payload = {"items": result_items, "updated_at": datetime.now(timezone.utc).isoformat()}
    todo_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Also write markdown version
    md_path = todo_dir / "todo.md"
    md_lines = ["# Todo", ""]
    for it in result_items:
        icon = {"todo": "[ ]", "doing": "[-]", "done": "[x]", "blocked": "[!]", "cancelled": "[~]"}.get(it.get("status", "todo"), "[ ]")
        md_lines.append(f"{icon} {it.get('title', '')}")
        if it.get("note"):
            md_lines.append(f"  > {it['note']}")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    return {"success": True, "mode": mode, "items": result_items, "count": len(result_items)}


# ── Ask User Question ────────────────────────────────────────────────────────


async def handle_ask_user_question(
    conversation_id: str = "",
    question: str = "",
    description: str = "",
    options: list[dict] | None = None,
    allow_custom_response: bool = True,
    custom_placeholder: str = "",
    **_kwargs: Any,
) -> dict[str, Any]:
    """Trigger an ask_user_question interaction card.

    This sets the agent into waiting_user state and returns the interaction
    payload which will be yielded as SSE events.
    """
    options = options or []
    if allow_custom_response:
        options.append({"id": "custom", "label": custom_placeholder or "Custom response…"})

    interaction_id = f"ask_{uuid.uuid4().hex[:8]}"
    payload = {
        "id": interaction_id,
        "type": "ask_user_question",
        "title": question or "Clarification needed",
        "description": description,
        "options": options,
        "allow_custom_response": allow_custom_response,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Set agent into waiting state
    from agent.agent_loop import AgentLoop
    loop = AgentLoop.__new__(AgentLoop)
    # We need to signal via the SSE context — this is handled in the agent_loop.run() method
    # by checking is_waiting(). The handler returns the interaction payload which the
    # caller (tool_executor) returns as the tool result.

    return {
        "success": True,
        "interaction_required": True,
        "interaction": payload,
    }


# ── Request Approval ──────────────────────────────────────────────────────────


async def handle_request_approval(
    conversation_id: str = "",
    title: str = "",
    description: str = "",
    risk_level: str = "medium",
    plan: list[dict] | None = None,
    allow_custom_response: bool = True,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Trigger a request_approval interaction card."""
    plan = plan or []
    interaction_id = f"approval_{uuid.uuid4().hex[:8]}"

    fixed_options = [
        {"id": "approve", "label": "Approve"},
        {"id": "reject_revise", "label": "Reject & Revise"},
        {"id": "reject_exit", "label": "Reject & Exit"},
    ]
    if allow_custom_response:
        fixed_options.append({"id": "custom", "label": "Custom response"})

    payload = {
        "id": interaction_id,
        "type": "request_approval",
        "title": title or "Approval required",
        "description": description,
        "risk_level": risk_level,
        "plan": plan,
        "options": fixed_options,
        "allow_custom_response": allow_custom_response,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "success": True,
        "interaction_required": True,
        "interaction": payload,
    }
