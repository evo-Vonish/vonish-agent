"""backend/tools — File operation tools and registry.

Usage::

    from . import ToolRegistry, ToolContext
    from .file_tools import (
        ReadFileTool, WriteFileTool, EditFileTool,
        ApplyPatchTool, DeleteFileTool,
    )

    registry = ToolRegistry()
    registry.register_all(
        ReadFileTool(),
        WriteFileTool(),
        EditFileTool(),
        ApplyPatchTool(),
        DeleteFileTool(),
    )

    ctx = ToolContext(
        conversation_id="conv-123",
        workspace_root="/workspace",
        user_id="user-456",
    )

    result = await registry.get("read_file").execute(ctx, path="main.py")
"""

from .base import (
    ApprovalRequirement,
    BaseTool,
    ToolCapability,
    ToolResult,
)
from .context import PathEscapeError, ToolContext
from .registry import ToolRegistry
from .schemas import (
    APPLY_PATCH_SCHEMA,
    DELETE_FILE_SCHEMA,
    EDIT_FILE_SCHEMA,
    READ_FILE_SCHEMA,
    WRITE_FILE_SCHEMA,
)

__all__ = [
    # base
    "BaseTool",
    "ToolResult",
    "ToolCapability",
    "ApprovalRequirement",
    # context
    "ToolContext",
    "PathEscapeError",
    # registry
    "ToolRegistry",
    # schemas
    "READ_FILE_SCHEMA",
    "WRITE_FILE_SCHEMA",
    "EDIT_FILE_SCHEMA",
    "APPLY_PATCH_SCHEMA",
    "DELETE_FILE_SCHEMA",
    # file_tools (imported on demand to avoid heavy init)
    # "ReadFileTool", "WriteFileTool", "EditFileTool",
    # "ApplyPatchTool", "DeleteFileTool",
]
