"""Prompt Preview API — inspect what the agent actually sends to the model."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import User, get_current_user
from core.logging import get_logger
from db.session import get_db
from prompt.prompt_builder import PromptBuilder

logger = get_logger(__name__)
router = APIRouter(prefix="/api")


# ── In-memory tool config (migrate to DB later) ──────────────────────────
_tool_configs: dict[str, bool] = {
    # File Ops
    "file_read": True,
    "edit_file": True,
    "write_to_file": True,
    "delete_file": True,
    "apply_patch": True,
    # Workspace
    "list_directory": True,
    "snapshot": True,
    "search_workspace": True,
    "create_directories": True,
    # Shell / Python
    "shell_command": True,
    "ipython": True,
    # Web
    "web_fetch": True,
    "web_search": True,
    "research_search": True,
    "research_fetch": True,
    "deep_research": True,
    "research_status": True,
    # Artifact skills
    "list_artifact_skills": True,
    "read_artifact_skill": True,
    "list_presentation_options": True,
    "generate_presentation": True,
    "patch_presentation": True,
    # Human Interaction
    "set_todo_list": True,
    "expand_tool_result": True,
    "CRAZY_for_tool_results": True,
    "recall_maximum": True,
    "focus_tool_results": True,
    "context_map": True,
    "custom_context_recall": True,
    "pin_memory": True,
    "unpin_memory": True,
    "ask_user_question": True,
    "request_approval": True,
}

def _sync_tool_configs_from_registry() -> None:
    """Ensure _tool_configs covers all registered tools."""
    try:
        from agent.tool_registry import ToolRegistry
        registry = ToolRegistry()
        for name in registry.list_all():
            if name not in _tool_configs:
                _tool_configs[name] = True
                logger.info(f"Auto-registered tool in config: {name}")
    except Exception:
        pass


def get_enabled_tools() -> list[str]:
    """Return list of currently enabled tool names."""
    _sync_tool_configs_from_registry()
    return [name for name, enabled in _tool_configs.items() if enabled]


def set_tool_enabled(tool_name: str, enabled: bool) -> None:
    """Enable or disable a tool by name."""
    _sync_tool_configs_from_registry()
    _tool_configs[tool_name] = enabled
    logger.info(f"Tool {tool_name} -> {'enabled' if enabled else 'disabled'}")


def get_all_tool_configs() -> dict[str, bool]:
    """Return all tool configs."""
    _sync_tool_configs_from_registry()
    return dict(_tool_configs)


@router.get("/tools/config")
async def list_tool_configs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all tool configs with enabled state."""
    return {"tools": get_all_tool_configs()}


@router.post("/tools/{tool_name}/enable")
async def enable_tool(
    tool_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Enable a tool."""
    set_tool_enabled(tool_name, True)
    return {"tool": tool_name, "enabled": True}


@router.post("/tools/{tool_name}/disable")
async def disable_tool(
    tool_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Disable a tool."""
    set_tool_enabled(tool_name, False)
    return {"tool": tool_name, "enabled": False}


@router.get("/prompt/preview")
async def prompt_preview(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Preview the assembled system prompt with per-block token estimates."""
    builder = PromptBuilder()
    enabled = get_enabled_tools()
    built = builder.preview(enabled_tools=enabled)

    return {
        "token_estimate": built.token_estimate,
        "hash": built.hash,
        "enabled_tools": built.enabled_tools,
        "blocks": [
            {
                "id": b.id,
                "type": b.type,
                "tokens": len(b.content) // 4,
                "enabled": b.enabled,
                "source": b.source,
            }
            for b in built.blocks
        ],
        "content": built.content,
    }
