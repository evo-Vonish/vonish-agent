"""Tool base classes — BaseTool + ToolResult + enums.

Reference: CodeWhale/DeepSeek-TUI ToolSpec trait (crates/tui/src/tools/spec.rs)
Python/FastAPI adaptation with pydantic models and ABC.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ToolCapability(str, Enum):
    """Capability flags that describe what a tool can do."""

    READ_ONLY = "read_only"
    WRITES_FILES = "writes_files"
    REQUIRES_APPROVAL = "requires_approval"


class ApprovalRequirement(str, Enum):
    """How much user approval is needed before executing a tool.

    Auto      → read-only tools (read_file, list_dir)
    Suggest   → write tools that return a diff preview (write_file, edit_file, apply_patch)
    Required  → destructive / irreversible operations (delete_file, revert_turn)
    """

    AUTO = "auto"
    SUGGEST = "suggest"
    REQUIRED = "required"


# ---------------------------------------------------------------------------
# ToolResult
# ---------------------------------------------------------------------------


class ToolResult(BaseModel):
    """Unified result payload returned by every tool execution.

    Fields
    ------
    success:        Whether the tool completed without error.
    tool_name:      Name of the tool that produced this result.
    path:           Affected file path (if any).
    output:         Human-readable text output (or file content for read_file).
    error:          Error message when success == False.
    diff:           Unified diff for write operations (write_file, edit_file, apply_patch).
    files_changed:  List of paths modified by the tool.
    metadata:       Arbitrary structured data (hashes, line counts, patch stats, …).
    """

    success: bool
    tool_name: str
    path: Optional[str] = None
    output: str = ""
    error: Optional[str] = None
    diff: Optional[str] = None
    files_changed: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_text(self) -> str:
        """Compact text representation for model context."""
        parts = []
        if self.diff:
            parts.append(self.diff)
        if self.output:
            parts.append(self.output)
        if self.error:
            parts.append(f"[ERROR] {self.error}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# BaseTool
# ---------------------------------------------------------------------------


class BaseTool(ABC):
    """Abstract base class for every tool in the system.

    Mirrors the CodeWhale ``ToolSpec`` trait:
    - name / description / schema  →  static metadata
    - capabilities / approval_requirement / is_read_only / supports_parallel  →  behavioural flags
    - execute()                     →  core logic (async)
    - to_function_definition()      →  OpenAI function-calling wire format
    """

    # -- metadata (subclasses MUST override) --------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool identifier, e.g. ``read_file``."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description shown to the model."""
        ...

    @property
    @abstractmethod
    def schema(self) -> dict[str, Any]:
        """JSON Schema ``object`` describing the parameters this tool accepts."""
        ...

    # -- behavioural flags (sensible defaults) ------------------------------

    @property
    def capabilities(self) -> list[ToolCapability]:
        """Capability flags.  Default: read-only."""
        return [ToolCapability.READ_ONLY]

    @property
    def approval_requirement(self) -> ApprovalRequirement:
        """Approval level required before execution.

        Auto-derivation (matches CodeWhale spec.rs L627-638):
        - WritesFiles capability → Suggest
        - otherwise               → Auto
        """
        if ToolCapability.WRITES_FILES in self.capabilities:
            return ApprovalRequirement.SUGGEST
        return ApprovalRequirement.AUTO

    @property
    def is_read_only(self) -> bool:
        """True when the tool does not modify the filesystem."""
        return ToolCapability.READ_ONLY in self.capabilities and ToolCapability.WRITES_FILES not in self.capabilities

    @property
    def supports_parallel(self) -> bool:
        """Read-only tools may be executed in parallel; write tools are serialised."""
        return self.is_read_only

    # -- execution ----------------------------------------------------------

    @abstractmethod
    async def execute(self, ctx: "ToolContext", **kwargs: Any) -> ToolResult:  # type: ignore[name-defined]
        """Execute the tool.

        Parameters
        ----------
        ctx:
            Execution context (workspace root, conversation id, …).
        **kwargs:
            Arguments validated against ``self.schema`` by the executor layer.

        Returns
        -------
        ToolResult
            Unified result payload.
        """
        ...

    # -- wire-format helpers ------------------------------------------------

    def to_function_definition(self) -> dict[str, Any]:
        """Convert to OpenAI / ChatCompletion function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema,
            },
        }

    def to_prompt_spec(self) -> str:
        """Human-readable spec for prompt-based tool injection."""
        return (
            f"### {self.name}\n"
            f"{self.description}\n"
            f"Schema: {self.schema}\n"
        )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
