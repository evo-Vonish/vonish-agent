"""BaseSkill abstract class for the Agent system.

Defines the interface that all skills must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import Any, Awaitable, Callable


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

class SkillParameter(BaseModel):
    """Parameter definition for a skill."""

    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: list[str] | None = None


class SkillDefinition(BaseModel):
    """Complete skill definition for registration."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    handler: str = ""  # Path to handler function
    category: str = "general"
    requires_confirmation: bool = False
    long_running: bool = False  # Whether skill may take a long time

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function schema format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class SkillResult(BaseModel):
    """Result of executing a skill."""

    success: bool
    data: Any = None
    message: str = ""
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "error": self.error,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
        }


# ---------------------------------------------------------------------------
# Abstract Base Skill
# ---------------------------------------------------------------------------


class BaseSkill(ABC):
    """Abstract base class for all skills.

    All skills must implement:
    - get_definition(): Return skill metadata
    - execute(): Execute the skill with given parameters
    - validate(): Validate parameters before execution
    """

    def __init__(self) -> None:
        self._definition: SkillDefinition | None = None

    @abstractmethod
    def get_definition(self) -> SkillDefinition:
        """Get the skill's definition.

        Returns:
            SkillDefinition with metadata and parameter schema.
        """
        ...

    @abstractmethod
    async def execute(self, **params: Any) -> SkillResult:
        """Execute the skill with the given parameters.

        Args:
            **params: Parameters as defined in the skill schema.

        Returns:
            SkillResult with execution outcome.
        """
        ...

    @abstractmethod
    def validate(self, **params: Any) -> tuple[bool, list[str]]:
        """Validate parameters before execution.

        Args:
            **params: Parameters to validate.

        Returns:
            Tuple of (is_valid, list_of_error_messages).
        """
        ...

    def get_name(self) -> str:
        """Get the skill name."""
        return self.get_definition().name

    def get_description(self) -> str:
        """Get the skill description."""
        return self.get_definition().description

    def get_schema(self) -> dict[str, Any]:
        """Get the skill's JSON schema."""
        return self.get_definition().parameters

    def requires_confirmation(self) -> bool:
        """Check if skill requires user confirmation."""
        return self.get_definition().requires_confirmation

    def is_long_running(self) -> bool:
        """Check if skill may take a long time."""
        return self.get_definition().long_running

    @property
    def definition(self) -> SkillDefinition:
        """Cached skill definition."""
        if self._definition is None:
            self._definition = self.get_definition()
        return self._definition
