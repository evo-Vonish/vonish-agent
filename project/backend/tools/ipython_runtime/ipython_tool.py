"""
iPython Tool - Tool Call interface for Agent Python execution.

Exposes `run_ipython` tool with schema:
{
  "name": "run_ipython",
  "description": "Execute Python code in a controlled IPython kernel...",
  "parameters": {
    "code": "...",
    "session_mode": "continue" | "new" | "reset" | "ephemeral",
    "session_id": "...",
    "timeout_seconds": 30
  }
}

Orchestration flow:
1. Validate code (security check)
2. Snapshot workspace (before)
3. Execute via kernel manager
4. Snapshot workspace (after) + diff
5. Collect artifacts
6. Format tool result
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .python_kernel_manager import PythonKernelManager
from .python_sandbox import CodeValidator, SandboxPolicy, SecurityViolationError
from .python_session import ExecutionResult
from .artifact_collector import ArtifactCollector, WorkspaceSnapshot

logger = logging.getLogger(__name__)

# ── Pydantic Schema ───────────────────────────────────────────────────────────


class RunIPythonInput(BaseModel):
    """Input schema for run_ipython tool call."""

    code: str = Field(..., description="Python code to execute")
    session_mode: str = Field(
        default="continue",
        description="Session mode: continue, new, reset, or ephemeral",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional named session ID",
    )
    timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=600,
        description="Execution timeout in seconds (1-600)",
    )

    @field_validator("session_mode")
    @classmethod
    def validate_session_mode(cls, v: str) -> str:
        allowed = {"continue", "new", "reset", "ephemeral"}
        if v not in allowed:
            raise ValueError(f"session_mode must be one of {allowed}")
        return v


# ── Tool Result ───────────────────────────────────────────────────────────────


@dataclass
class IPythonToolResult:
    """Structured result from run_ipython execution."""

    success: bool = True
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    error_name: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    display_data: list[dict[str, Any]] = field(default_factory=list)
    execution_time_ms: int = 0
    kernel_restarted: bool = False

    def to_tool_response(self) -> dict[str, Any]:
        """Convert to dict for tool_result response."""
        result: dict[str, Any] = {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error": self.error,
            "error_name": self.error_name,
            "artifacts": self.artifacts,
            "display_data": self.display_data,
            "execution_time_ms": self.execution_time_ms,
        }
        if self.kernel_restarted:
            result["kernel_restarted"] = True
            result["note"] = "Kernel was restarted during execution. Variables may have been lost."
        return result


# ── Tool Schema (for Tool Registry) ──────────────────────────────────────────


TOOL_NAME = "run_ipython"
TOOL_DESCRIPTION = (
    "Execute Python code in a controlled IPython kernel bound to the current workspace. "
    "Supports data analysis, chart generation, file creation, and debugging. "
    "Variables persist across calls in the same session (like Jupyter Notebook). "
    "Generated files are saved to outputs/ and returned as artifacts."
)

TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "code": {
            "type": "string",
            "description": "Python code to execute. Can include imports, calculations, matplotlib plotting, file I/O (within workspace), etc.",
        },
        "session_mode": {
            "type": "string",
            "enum": ["continue", "new", "reset", "ephemeral"],
            "default": "continue",
            "description": (
                "continue: reuse existing kernel (variables persist); "
                "new: create a named session; "
                "reset: restart kernel (variables cleared); "
                "ephemeral: one-time execution in fresh kernel"
            ),
        },
        "session_id": {
            "type": "string",
            "description": "Optional session name for 'new' mode. Allows multiple isolated environments per conversation.",
        },
        "timeout_seconds": {
            "type": "integer",
            "default": 30,
            "minimum": 1,
            "maximum": 600,
            "description": "Maximum execution time in seconds.",
        },
    },
    "required": ["code"],
}

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": TOOL_DESCRIPTION,
    "parameters": TOOL_PARAMETERS,
}


# ── iPython Tool ──────────────────────────────────────────────────────────────


class IPythonTool:
    """The run_ipython tool implementation.

    Integrates sandbox validation, kernel execution, and artifact collection.
    """

    def __init__(
        self,
        kernel_manager: PythonKernelManager | None = None,
        sandbox_policy: SandboxPolicy | None = None,
    ) -> None:
        self.kernel_manager = kernel_manager or PythonKernelManager()
        self.policy = sandbox_policy or SandboxPolicy()
        self.validator = CodeValidator(self.policy)

    # ── Public API ────────────────────────────────────────────────────────────

    async def execute(
        self,
        conversation_id: str,
        code: str,
        session_mode: str = "continue",
        session_id: str | None = None,
        timeout_seconds: int = 30,
    ) -> IPythonToolResult:
        """Execute Python code - main entry point.

        Flow:
        1. Validate code security
        2. Snapshot workspace (before)
        3. Execute via kernel manager
        4. Snapshot workspace (after) + diff
        5. Collect artifacts and format result
        """
        workspace = self.kernel_manager._get_workspace_path(conversation_id)
        collector = ArtifactCollector(workspace)

        # Step 1: Security validation
        try:
            self.validator.validate_or_raise(code)
        except SecurityViolationError as e:
            return IPythonToolResult(
                success=False,
                error=str(e),
                error_name="SecurityViolation",
            )

        # Step 2: Snapshot before
        snapshot_before = collector.snapshot_before()

        # Step 3: Execute
        try:
            exec_result = await self.kernel_manager.execute(
                conversation_id=conversation_id,
                code=code,
                session_mode=session_mode,
                session_id=session_id,
                timeout_seconds=timeout_seconds,
            )
        except Exception as e:
            logger.exception("Kernel execution failed")
            return IPythonToolResult(
                success=False,
                error=f"Execution failed: {str(e)}",
                error_name="ExecutionError",
            )

        # Step 4: Snapshot after + diff
        snapshot_after = collector.snapshot_after()
        diff = collector.diff(snapshot_before, snapshot_after)

        # Step 5: Format result
        return self._format_result(exec_result, diff, self.policy)

    def execute_sync(
        self,
        conversation_id: str,
        code: str,
        session_mode: str = "continue",
        session_id: str | None = None,
        timeout_seconds: int = 30,
    ) -> IPythonToolResult:
        """Synchronous wrapper for execute()."""
        import asyncio
        return asyncio.run(
            self.execute(conversation_id, code, session_mode, session_id, timeout_seconds)
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _format_result(
        exec_result: ExecutionResult,
        diff: Any,
        policy: SandboxPolicy,
    ) -> IPythonToolResult:
        """Format execution result and artifacts into tool response."""
        result = IPythonToolResult(
            success=exec_result.success,
            stdout=exec_result.stdout,
            stderr=exec_result.stderr,
            error=exec_result.error,
            error_name=exec_result.error_name,
            display_data=exec_result.display_data,
            execution_time_ms=exec_result.execution_time_ms,
            kernel_restarted=exec_result.kernel_restarted,
        )

        # Truncate output to limits
        result.stdout = IPythonTool._truncate_text(result.stdout, policy.max_stdout_chars)
        result.stderr = IPythonTool._truncate_text(result.stderr, policy.max_stderr_chars)

        # Collect artifacts from diff (added files only)
        if hasattr(diff, "to_artifacts"):
            result.artifacts = diff.to_artifacts()
        else:
            result.artifacts = []

        # Also collect display_data images as artifacts
        for display in result.display_data:
            data = display.get("data", {})
            if "image/png" in data:
                result.artifacts.append({
                    "path": "<inline_image_png>",
                    "mime_type": "image/png",
                    "inline_data": data["image/png"],
                    "size": len(data["image/png"]),
                })
            elif "image/svg+xml" in data:
                result.artifacts.append({
                    "path": "<inline_image_svg>",
                    "mime_type": "image/svg+xml",
                    "inline_data": data["image/svg+xml"],
                    "size": len(data["image/svg+xml"]),
                })

        return result

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        """Truncate text to max length with indicator."""
        if len(text) > max_chars:
            return text[:max_chars] + f"\n... [{len(text) - max_chars} chars truncated]"
        return text


# ── Convenience: Tool Schema Export ───────────────────────────────────────────


def get_tool_schema() -> dict[str, Any]:
    """Return the tool schema for registration in the Tool Registry."""
    return TOOL_SCHEMA


# ── Singleton instance (for import convenience) ───────────────────────────────

_default_tool: IPythonTool | None = None
_default_manager: PythonKernelManager | None = None


async def get_default_tool() -> IPythonTool:
    """Get or create the default tool instance."""
    global _default_tool, _default_manager
    if _default_tool is None:
        _default_manager = PythonKernelManager()
        await _default_manager.start()
        _default_tool = IPythonTool(kernel_manager=_default_manager)
    return _default_tool


async def shutdown_default_tool() -> None:
    """Shutdown the default tool instance."""
    global _default_tool, _default_manager
    if _default_manager:
        await _default_manager.shutdown()
    _default_tool = None
    _default_manager = None
