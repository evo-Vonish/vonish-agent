"""Tool Registry for the Agent system.

Manages tool definitions, validation, and context assembly.
Uses singleton pattern for global access.
"""

from __future__ import annotations

import json
from pydantic import BaseModel, Field
from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class ToolParameter(BaseModel):
    """Single tool parameter definition."""

    name: str
    type: str
    description: str
    required: bool = True
    enum: list[str] | None = None
    default: Any = None


class ToolDefinition(BaseModel):
    """Complete tool definition for model function calling."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    handler: str = ""  # Reference to handler function path
    category: str = "general"
    requires_confirmation: bool = False

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible function schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ValidationResult(BaseModel):
    """Tool call validation result."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    normalized_arguments: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tool Registry (Singleton)
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Singleton registry for all available tools.

    Manages tool registration, lookup, validation, and context assembly.
    """

    _instance: ToolRegistry | None = None
    _initialized: bool = False

    def __new__(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if ToolRegistry._initialized:
            return
        self._tools: dict[str, ToolDefinition] = {}
        self._categories: dict[str, list[str]] = {}
        ToolRegistry._initialized = True

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition.

        Args:
            tool: ToolDefinition to register.
        """
        self._tools[tool.name] = tool
        category = tool.category
        if category not in self._categories:
            self._categories[category] = []
        if tool.name not in self._categories[category]:
            self._categories[category].append(tool.name)

        logger.info(f"Registered tool: {tool.name} ({category})")

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        if name in self._tools:
            tool = self._tools.pop(name)
            category = tool.category
            if category in self._categories and name in self._categories[category]:
                self._categories[category].remove(name)
            logger.info(f"Unregistered tool: {name}")

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name.

        Args:
            name: Tool name.

        Returns:
            ToolDefinition or None if not found.
        """
        return self._tools.get(name)

    def list_all(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def list_for_context(self, task_type: str = "default") -> list[ToolDefinition]:
        """Get tools formatted for model context injection.

        Filters tools based on task type for optimal context usage.

        Args:
            task_type: Task category hint (default, coding, research, etc.)

        Returns:
            List of ToolDefinition objects for context.
        """
        # For now, return all tools
        # Future: Filter based on task_type relevance
        tools = list(self._tools.values())

        # Sort by category for consistent ordering
        tools.sort(key=lambda t: (t.category, t.name))
        return tools

    def list_for_json_schema(self) -> list[dict[str, Any]]:
        """Get all tools as OpenAI-compatible JSON schema list."""
        return [t.to_json_schema() for t in self.list_for_context()]

    def validate_call(self, tool_name: str, arguments: dict[str, Any]) -> ValidationResult:
        """Validate a tool call against its schema.

        Args:
            tool_name: Name of the tool to validate.
            arguments: Arguments to validate.

        Returns:
            ValidationResult with valid flag and any errors.
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            return ValidationResult(
                valid=False,
                errors=[f"Unknown tool: {tool_name}"],
            )

        errors: list[str] = []
        params_schema = tool.parameters
        required = params_schema.get("required", [])
        properties = params_schema.get("properties", {})

        # Check required parameters
        for param_name in required:
            if param_name not in arguments:
                errors.append(f"Missing required parameter: {param_name}")

        # Check parameter types
        for param_name, param_value in arguments.items():
            if param_name not in properties:
                errors.append(f"Unknown parameter: {param_name}")
                continue

            param_schema = properties[param_name]
            param_type = param_schema.get("type")

            if param_type and not self._check_type(param_value, param_type):
                errors.append(
                    f"Parameter '{param_name}' should be {param_type}, "
                    f"got {type(param_value).__name__}"
                )

            # Check enum
            if "enum" in param_schema and param_value not in param_schema["enum"]:
                errors.append(
                    f"Parameter '{param_name}' must be one of {param_schema['enum']}"
                )

        normalized = dict(arguments)
        # Apply defaults for missing optional parameters
        for param_name, param_schema in properties.items():
            if param_name not in normalized and "default" in param_schema:
                normalized[param_name] = param_schema["default"]

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            normalized_arguments=normalized,
        )

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if a value matches the expected JSON Schema type."""
        type_map = {
            "string": (str,),
            "integer": (int,),
            "number": (int, float),
            "boolean": (bool,),
            "array": (list,),
            "object": (dict,),
        }
        allowed = type_map.get(expected_type, ())
        return isinstance(value, allowed)

    def get_category_tools(self, category: str) -> list[ToolDefinition]:
        """Get all tools in a category."""
        names = self._categories.get(category, [])
        return [self._tools[n] for n in names if n in self._tools]

    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()
        self._categories.clear()
        logger.info("Tool registry cleared")


# ---------------------------------------------------------------------------
# Default Tool Registration
# ---------------------------------------------------------------------------

def register_default_tools() -> None:
    """Register the default set of tools from skill schemas."""
    registry = ToolRegistry()

    # Read File
    registry.register(
        ToolDefinition(
            name="read_file",
            description="Read the contents of a file in the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file in the workspace",
                    },
                },
                "required": ["path"],
            },
            category="file_ops",
        )
    )

    # Edit File
    registry.register(
        ToolDefinition(
            name="edit_file",
            description="Edit a file in the workspace by applying specified changes.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Text to replace",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Replacement text",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
            category="file_ops",
            requires_confirmation=True,
        )
    )

    # Shell Command
    registry.register(
        ToolDefinition(
            name="shell_command",
            description="Execute a shell command in the workspace environment.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
            category="shell_ops",
            requires_confirmation=True,
        )
    )

    # IPython
    registry.register(
        ToolDefinition(
            name="ipython",
            description="Execute Python code in an IPython environment.",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute",
                    },
                },
                "required": ["code"],
            },
            category="python_ops",
        )
    )

    # Web Search
    registry.register(
        ToolDefinition(
            name="web_search",
            description="Search the web for information on a given query.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
            category="web_ops",
        )
    )

    # Web Fetch (deep extraction via AGENT ENT Fetch Mini)
    registry.register(
        ToolDefinition(
            name="web_fetch",
            description=(
                "Deeply fetch and analyze a web page. Extracts main content (text & markdown), "
                "frontend source (buttons, forms, interactive elements), and page resources "
                "(links, images, scripts, stylesheets). Supports static (HTTP) and dynamic "
                "(Playwright browser) modes. Use this when you need to understand what a "
                "web page contains beyond just raw text."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch (required)",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["static", "dynamic", "auto"],
                        "description": "Fetch mode: static (fast HTTP), dynamic (browser render), auto (default)",
                        "default": "auto",
                    },
                    "targets": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["main_content", "links", "images", "buttons", "forms", "resources", "frontend_source"]},
                        "description": "What to extract. Default: [main_content, resources, frontend_source]",
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "description": "Timeout in milliseconds (default: 20000)",
                        "default": 20000,
                    },
                },
                "required": ["url"],
            },
            category="web_ops",
        )
    )

    logger.info(f"Registered {len(registry.list_all())} default tools")


def register_workspace_tools(registry: ToolRegistry) -> None:
    """Register all workspace tools.

    These tools allow the Agent to inspect and interact with the
    per-conversation workspace (file listing, reading, summaries).
    """
    # list_workspace_files
    registry.register(
        ToolDefinition(
            name="list_workspace_files",
            description=(
                "List all files in the current conversation's workspace. "
                "Optionally filter to a subdirectory. "
                "Returns file paths, sizes, types, and MIME types."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "The active conversation ID (injected by executor)",
                    },
                    "subdir": {
                        "type": "string",
                        "description": "Subdirectory to list (default: root)",
                        "default": "",
                    },
                },
            },
            category="workspace",
        )
    )

    # read_workspace_file
    registry.register(
        ToolDefinition(
            name="read_workspace_file",
            description=(
                "Read the contents of a workspace file. "
                "Returns text (UTF-8) or base64-encoded binary. "
                "Files over 5 MB are truncated."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "The active conversation ID (injected by executor)",
                    },
                    "path": {
                        "type": "string",
                        "description": "File path relative to workspace root",
                    },
                },
                "required": ["path"],
            },
            category="workspace",
        )
    )

    # get_workspace_summary
    registry.register(
        ToolDefinition(
            name="get_workspace_summary",
            description=(
                "Get a summary of the workspace contents. "
                "Returns total files, total size, file type breakdown, "
                "directory list, and top 5 largest files."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "The active conversation ID (injected by executor)",
                    },
                },
            },
            category="workspace",
        )
    )

    logger.info(
        f"Registered {len(registry.get_category_tools('workspace'))} workspace tools"
    )
