"""Global exception handling and custom exception classes."""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


# ---------------------------------------------------------------------------
# Custom Exception Classes
# ---------------------------------------------------------------------------

class AgentError(Exception):
    """Base exception for Agent system errors."""

    def __init__(
        self,
        detail: str = "Agent error occurred",
        status_code: int = 500,
        error_code: str = "AGENT_ERROR",
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.detail = detail
        self.status_code = status_code
        self.error_code = error_code
        self.extra = extra or {}
        super().__init__(self.detail)


class ToolError(AgentError):
    """Exception for tool execution errors."""

    def __init__(
        self,
        detail: str = "Tool execution failed",
        error_code: str = "TOOL_ERROR",
        tool_name: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        merged_extra = {"tool_name": tool_name, **(extra or {})}
        super().__init__(
            detail=detail,
            status_code=500,
            error_code=error_code,
            extra=merged_extra,
        )


class WorkspaceError(AgentError):
    """Exception for workspace operation errors."""

    def __init__(
        self,
        detail: str = "Workspace operation failed",
        error_code: str = "WORKSPACE_ERROR",
        path: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        merged_extra = {"path": path, **(extra or {})}
        super().__init__(
            detail=detail,
            status_code=400,
            error_code=error_code,
            extra=merged_extra,
        )


class ContextError(AgentError):
    """Exception for context building errors."""

    def __init__(
        self,
        detail: str = "Context building failed",
        error_code: str = "CONTEXT_ERROR",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=500,
            error_code=error_code,
            extra=extra,
        )


class AuthenticationError(AgentError):
    """Exception for authentication errors."""

    def __init__(
        self,
        detail: str = "Authentication failed",
        error_code: str = "AUTH_ERROR",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=401,
            error_code=error_code,
            extra=extra,
        )


class ValidationError(AgentError):
    """Exception for input validation errors."""

    def __init__(
        self,
        detail: str = "Validation failed",
        error_code: str = "VALIDATION_ERROR",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=422,
            error_code=error_code,
            extra=extra,
        )


class ResourceNotFoundError(AgentError):
    """Exception for resource not found errors."""

    def __init__(
        self,
        detail: str = "Resource not found",
        error_code: str = "NOT_FOUND",
        resource_type: str = "",
        resource_id: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        merged_extra = {
            "resource_type": resource_type,
            "resource_id": resource_id,
            **(extra or {}),
        }
        super().__init__(
            detail=detail,
            status_code=404,
            error_code=error_code,
            extra=merged_extra,
        )


# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------

def agent_error_handler(request: Request, exc: AgentError) -> JSONResponse:
    """Handle all AgentError subclasses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "detail": exc.detail,
                "extra": exc.extra,
            }
        },
    )


def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle uncaught exceptions."""
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "detail": "An unexpected error occurred",
                "extra": {"traceback": traceback.format_exc()},
            }
        },
    )


def register_exception_handlers(app) -> None:
    """Register all exception handlers with the FastAPI app."""
    app.add_exception_handler(AgentError, agent_error_handler)
    app.add_exception_handler(Exception, general_exception_handler)
