"""Tool Execution API routes.

Provides:
- GET /api/tools - List available tools
- POST /api/tools/execute - Direct tool execution
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agent.tool_executor import ToolCallRequest, get_tool_executor
from agent.tool_registry import ToolRegistry
from core.auth import User, get_current_user
from core.logging import get_logger
from db.session import get_db

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class ToolExecuteRequest(BaseModel):
    """Request to execute a tool directly."""

    tool: str = Field(..., description="Tool name")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Tool arguments"
    )
    conversation_id: str = Field(default="", description="Conversation context")


class ToolResponse(BaseModel):
    """Tool execution response."""

    tool: str
    success: bool
    result: Any = None
    execution_time_ms: float = 0.0
    error: str | None = None


class ToolListResponse(BaseModel):
    """List of available tools."""

    tools: list[dict[str, Any]]
    total: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/tools", response_model=ToolListResponse)
async def list_tools(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all available tools with full metadata."""
    registry = ToolRegistry()
    tools = [
        {
            "name": t.name,
            "description": t.description,
            "category": t.category,
            "requires_confirmation": t.requires_confirmation,
            "schema": t.parameters,
        }
        for t in registry.list_for_context()
    ]

    return ToolListResponse(
        tools=tools,
        total=len(tools),
    )


@router.post("/tools/execute", response_model=ToolResponse)
async def execute_tool(
    request: ToolExecuteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Execute a tool directly.

    This endpoint allows direct tool execution outside of the
    normal chat flow, useful for testing and one-off operations.
    """
    registry = ToolRegistry()

    # Validate tool exists
    tool_def = registry.get(request.tool)
    if tool_def is None:
        raise HTTPException(
            status_code=404, detail=f"Tool not found: {request.tool}"
        )

    # Validate arguments
    validation = registry.validate_call(request.tool, request.arguments)
    if not validation.valid:
        raise HTTPException(
            status_code=422,
            detail=f"Validation failed: {'; '.join(validation.errors)}",
        )

    # Execute
    executor = get_tool_executor()
    result = await executor.execute(
        ToolCallRequest(
            tool_name=request.tool,
            arguments=validation.normalized_arguments,
            conversation_id=request.conversation_id,
        )
    )

    logger.info(
        f"Tool executed: {request.tool}",
        extra={
            "success": result.success,
            "execution_time_ms": result.execution_time_ms,
        },
    )

    return ToolResponse(
        tool=request.tool,
        success=result.success,
        result=result.result,
        execution_time_ms=result.execution_time_ms,
        error=result.error_message,
    )
