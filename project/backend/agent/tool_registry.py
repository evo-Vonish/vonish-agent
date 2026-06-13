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

    # Write to File (create or overwrite)
    registry.register(
        ToolDefinition(
            name="write_to_file",
            description="Create or overwrite a file in the workspace with the given content. For new files, use this. For modifying existing files, use edit_file.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file (created if not exists)",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full content to write to the file",
                    },
                },
                "required": ["path", "content"],
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
                    "cwd": {
                        "type": "string",
                        "description": "Working directory within workspace (relative path, default: workspace root)",
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
            description=(
                "Execute Python code in a persistent IPython kernel bound to the current "
                "conversation workspace. Use for calculations, data analysis, chart "
                "generation, and creating files under the workspace. Returns stdout, "
                "errors, display data, and created artifacts."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute",
                    },
                    "session_mode": {
                        "type": "string",
                        "enum": ["continue", "new", "reset", "ephemeral"],
                        "description": (
                            "continue reuses the current kernel; new creates or reuses "
                            "a named session; reset restarts the kernel; ephemeral uses "
                            "a temporary fresh kernel"
                        ),
                        "default": "continue",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Optional named session id",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Execution timeout in seconds",
                        "default": 30,
                    },
                    "restart": {
                        "type": "boolean",
                        "description": "Restart the default kernel before executing",
                        "default": False,
                    },
                },
                "required": ["code"],
            },
            category="python_ops",
        )
    )

    # Open Artifact in Workbench
    registry.register(
        ToolDefinition(
            name="open_artifact",
            description=(
                "Present a generated or modified workspace artifact to the user by opening it "
                "in the right-side Workbench file preview/editor. Use after creating files such "
                "as .py, .md, .html, .pdf, .docx, .pptx, .xlsx, images, or reports so the user "
                "can inspect, select, quote, and request targeted edits."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the artifact inside the current workspace, e.g. outputs/report.pdf",
                    },
                    "title": {
                        "type": "string",
                        "description": "Optional display title for the workbench tab/card",
                    },
                    "description": {
                        "type": "string",
                        "description": "Short note explaining why this artifact is being opened",
                    },
                },
                "required": ["path"],
            },
            category="workspace",
            requires_confirmation=False,
        )
    )

    # Artifact Skill Reader
    registry.register(
        ToolDefinition(
            name="list_artifact_skills",
            description=(
                "List the bundled artifact-production skills available to the agent. "
                "Use before creating polished DOCX, XLSX, PDF, or PPTX deliverables "
                "to see which skill files can be loaded."
            ),
            parameters={
                "type": "object",
                "properties": {},
            },
            category="system",
            requires_confirmation=False,
        )
    )

    registry.register(
        ToolDefinition(
            name="read_artifact_skill",
            description=(
                "Read bundled artifact-production skill instructions for polished deliverables. "
                "Call this before producing DOCX, XLSX, PDF, or PPTX files. The model receives "
                "the full skill content, while the frontend displays only a compact read summary."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "skill": {
                        "type": "string",
                        "enum": ["docx", "xlsx", "pdf", "pptx"],
                        "description": "Artifact skill to read.",
                    },
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "SKILL.md",
                                "procedure.yaml",
                                "validators.yaml",
                                "recovery.yaml",
                                "design_tokens.yaml",
                            ],
                        },
                        "description": (
                            "Optional specific skill files to load. Defaults to entry, "
                            "procedure, validators, and design tokens."
                        ),
                    },
                    "include_shared": {
                        "type": "boolean",
                        "description": "Also load shared Artifact Plan, priority, visual review, and recall guidance.",
                        "default": True,
                    },
                },
                "required": ["skill"],
            },
            category="system",
            requires_confirmation=False,
        )
    )

    # ── PPT Artifact Engine ──────────────────────────────────────────
    registry.register(
        ToolDefinition(
            name="list_presentation_options",
            description=(
                "List the built-in presentation themes and layout recipes available to the "
                "PPT Artifact Engine. Call this before generate_presentation to choose a theme "
                "and pick a layout for each slide. Returns theme colour summaries and, for each "
                "layout, its slots and which content fields it consumes."
            ),
            parameters={"type": "object", "properties": {}},
            category="artifact",
            requires_confirmation=False,
        )
    )

    registry.register(
        ToolDefinition(
            name="generate_presentation",
            description=(
                "Generate a polished, native-editable .pptx through the VonishAgent PPT Artifact "
                "Engine. You provide ONLY a theme, and for each slide a layout + content — never "
                "pixel positions, colours, or font sizes (the engine owns geometry, the theme owns "
                "colour/typography). The engine runs DeckDesignSpec -> SlideIR -> render -> validate "
                "-> auto-repair -> PNG previews and returns the artifact, per-page previews, and a "
                "validation report. ALWAYS use this instead of hand-writing python-pptx for slide "
                "decks. Layouts: cover-center, toc-simple, chapter-break, three-cards, left-right, "
                "timeline, process, architecture, data-chart, quote-center, code-block, summary-bullets."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Deck title (used for the file name and cover fallback)."},
                    "theme_id": {
                        "type": "string",
                        "enum": ["tech-dark", "academic-white", "business-bluegray", "vonish-agent", "vonish-ocr"],
                        "description": "Design theme. tech-dark/vonish-agent = dark; academic-white/business-bluegray = light.",
                    },
                    "reference_deck_path": {
                        "type": "string",
                        "description": "Optional workspace path to a reference .pptx whose palette/fonts should style this deck (overrides theme_id's colours). Analyze it first with analyze_reference_deck if unsure.",
                    },
                    "filename": {"type": "string", "description": "Optional output file name (without extension)."},
                    "slides": {
                        "type": "array",
                        "description": "Ordered slides. Each picks a layout and supplies only the content that layout needs.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "layout": {
                                    "type": "string",
                                    "enum": ["cover-center", "toc-simple", "chapter-break", "three-cards",
                                             "left-right", "timeline", "process", "architecture",
                                             "data-chart", "quote-center", "code-block", "summary-bullets"],
                                },
                                "title": {"type": "string"},
                                "subtitle": {"type": "string"},
                                "meta": {"type": "string"},
                                "chapter_number": {"type": "string"},
                                "body": {"type": "string"},
                                "footer": {"type": "string"},
                                "bullets": {"type": "array", "items": {"type": "string"}},
                                "cards": {
                                    "type": "array",
                                    "items": {"type": "object", "properties": {
                                        "title": {"type": "string"}, "body": {"type": "string"}, "icon": {"type": "string"}}},
                                },
                                "items": {
                                    "type": "array",
                                    "description": "Steps/milestones/toc rows: {title, body, label}.",
                                    "items": {"type": "object", "properties": {
                                        "title": {"type": "string"}, "body": {"type": "string"}, "label": {"type": "string"}}},
                                },
                                "left": {"type": "object", "properties": {
                                    "title": {"type": "string"}, "body": {"type": "string"},
                                    "bullets": {"type": "array", "items": {"type": "string"}}}},
                                "right": {"type": "object", "properties": {
                                    "title": {"type": "string"}, "body": {"type": "string"},
                                    "bullets": {"type": "array", "items": {"type": "string"}}}},
                                "chart": {"type": "object", "properties": {
                                    "type": {"type": "string", "enum": ["column", "bar", "line", "pie", "area"]},
                                    "categories": {"type": "array", "items": {"type": "string"}},
                                    "series": {"type": "array", "items": {"type": "object", "properties": {
                                        "name": {"type": "string"}, "values": {"type": "array", "items": {"type": "number"}}}}},
                                    "insight": {"type": "string"}}},
                                "code": {"type": "object", "properties": {
                                    "language": {"type": "string"}, "code": {"type": "string"}, "annotation": {"type": "string"}}},
                                "quote": {"type": "object", "properties": {
                                    "text": {"type": "string"}, "author": {"type": "string"}}},
                                "diagram": {"type": "object", "properties": {
                                    "nodes": {"type": "array", "items": {"type": "object", "properties": {
                                        "id": {"type": "string"}, "label": {"type": "string"}, "group": {"type": "string"}}}},
                                    "legend": {"type": "array", "items": {"type": "string"}}}},
                            },
                            "required": ["layout"],
                        },
                    },
                },
                "required": ["title", "theme_id", "slides"],
            },
            category="artifact",
            requires_confirmation=False,
        )
    )

    registry.register(
        ToolDefinition(
            name="patch_presentation",
            description=(
                "Apply a targeted, element-level edit to a deck previously created with "
                "generate_presentation — WITHOUT regenerating the whole deck. Use this when the "
                "user selects/references a slide element in the Workbench and asks to change it "
                "(reword a title, recolour a shape, move/resize a box, delete a decoration). "
                "Identify the element by its element_id (shown on the referenced element / in the "
                "slide's element metadata). The engine re-renders only what changed, re-validates, "
                "and auto-repairs before returning the updated artifact + previews."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "deck_path": {
                        "type": "string",
                        "description": "Workspace-relative path to the deck's deck.pptx (as returned by generate_presentation / shown in the Workbench).",
                    },
                    "slide_index": {"type": "integer", "description": "0-based index of the slide to edit."},
                    "operations": {
                        "type": "array",
                        "description": "Element operations to apply to that slide.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "op": {
                                    "type": "string",
                                    "enum": ["replace_text", "update_style", "update_shape_style",
                                             "move", "resize", "add_decoration", "delete"],
                                },
                                "target": {"type": "string", "description": "element_id to edit."},
                                "value": {"type": "string", "description": "New text for replace_text."},
                                "changes": {
                                    "type": "object",
                                    "description": (
                                        "For update_style: fontSize/color/bold/italic/align/valign/fontFamily. "
                                        "For update_shape_style: fill/stroke/strokeWidth/radius. "
                                        "For move: x/y. For resize: width/height. Coordinates are canvas px."),
                                },
                            },
                            "required": ["op", "target"],
                        },
                    },
                    "reasoning": {"type": "string", "description": "Short why-note for the edit."},
                },
                "required": ["deck_path", "slide_index", "operations"],
            },
            category="artifact",
            requires_confirmation=False,
        )
    )

    registry.register(
        ToolDefinition(
            name="analyze_reference_deck",
            description=(
                "Analyze a reference .pptx (e.g. one the user uploaded) and extract a style "
                "profile: slide count, dominant palette, fonts, title positions, element mix, "
                "layout hints, plus the nearest built-in theme and suggested layouts. Use the "
                "returned profile (or pass the same path as reference_deck_path to "
                "generate_presentation) to make a new deck in that style."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "deck_path": {"type": "string", "description": "Workspace-relative path to the reference .pptx."},
                },
                "required": ["deck_path"],
            },
            category="artifact",
            requires_confirmation=False,
        )
    )

    registry.register(
        ToolDefinition(
            name="review_presentation",
            description=(
                "Run the L3 design judge over an existing generated deck and attach a structured "
                "design review (per-slide score 1-5, severity, visual_issues, suggestions) to its "
                "manifest. This is ADVISORY and never blocks delivery. Modes: mock (deterministic "
                "heuristic from the validator/visual findings — no real VLM), manual (human-review "
                "template), disabled, local (degrades to disabled if no local model). There is no "
                "real VLM/API in this environment; 'mock' is honestly heuristic."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "deck_path": {"type": "string", "description": "Workspace-relative path to the deck's deck.pptx."},
                    "mode": {"type": "string", "enum": ["mock", "manual", "disabled", "local"], "default": "mock"},
                },
                "required": ["deck_path"],
            },
            category="artifact",
            requires_confirmation=False,
        )
    )

    registry.register(
        ToolDefinition(
            name="experiment_svg_route",
            description=(
                "EXPERIMENTAL (Phase 3, not the main pipeline): render an existing deck through the "
                "SlideIR -> SVG -> native-DrawingML experimental route and return a comparison vs the "
                "production python-pptx renderer (slide/shape counts, byte sizes, limitations). Writes "
                "per-slide .svg files next to the deck. Use only to inspect the SVG middle-layer; the "
                "delivered deck still comes from the production renderer."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "deck_path": {"type": "string", "description": "Workspace-relative path to the deck's deck.pptx."},
                },
                "required": ["deck_path"],
            },
            category="artifact",
            requires_confirmation=False,
        )
    )

    registry.register(
        ToolDefinition(
            name="revert_presentation",
            description=(
                "Roll a deck (made with generate_presentation) back to an earlier saved version. "
                "Every generate/patch saves a version snapshot; the deck's manifest lists them "
                "(version_id, kind, label). Use this when the user wants to undo edits or go back "
                "to a prior state. The restore itself is recorded as a new version, so the user can "
                "always roll forward again."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "deck_path": {"type": "string", "description": "Workspace-relative path to the deck's deck.pptx."},
                    "version_id": {"type": "string", "description": "Target version id, e.g. 'v000' (from the deck's versions list)."},
                },
                "required": ["deck_path", "version_id"],
            },
            category="artifact",
            requires_confirmation=False,
        )
    )

    # Web Search
    registry.register(
        ToolDefinition(
            name="web_search",
            description=(
                "Search the web and read matching pages. This tool performs URL recall, "
                "deduplicates results, batch-crawls pages, extracts clean page text, "
                "scores passages for relevance, and returns selected evidence snippets "
                "with source URLs."
            ),
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
                    "max_time_ms": {
                        "type": "integer",
                        "description": "Overall search+crawl budget in milliseconds",
                        "default": 15000,
                    },
                    "max_content_length": {
                        "type": "integer",
                        "description": "Maximum total extracted text characters returned",
                        "default": 8000,
                    },
                    "per_url_timeout_ms": {
                        "type": "integer",
                        "description": "Per-page crawl timeout in milliseconds",
                        "default": 3000,
                    },
                    "max_per_url": {
                        "type": "integer",
                        "description": "Maximum extracted characters per page",
                        "default": 5000,
                    },
                },
                "required": ["query"],
            },
            category="web_ops",
        )
    )

    # Research Search
    registry.register(
        ToolDefinition(
            name="research_search",
            description=(
                "Search the web through the local Research Core. Performs intent routing, "
                "multi-engine recall, URL cleanup, ranking, deduplication, and returns "
                "compact source snippets. Prefer this over deprecated web_search."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Research/search query"},
                    "mode": {
                        "type": "string",
                        "enum": ["overview", "scholar", "dev", "live", "media", "deep_dive"],
                        "description": "Search intent mode. Use overview by default.",
                        "default": "overview",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum ranked results to return",
                        "default": 20,
                    },
                    "language": {"type": "string", "description": "Preferred language", "default": "auto"},
                },
                "required": ["query"],
            },
            category="research",
            requires_confirmation=False,
        )
    )

    # Research Fetch
    registry.register(
        ToolDefinition(
            name="research_fetch",
            description=(
                "Fetch one URL through the local Research Core. Returns a concise summary, "
                "content_ref, content_hash, duplicate info, and crawl stats instead of "
                "injecting full page text into the model context."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "mode": {
                        "type": "string",
                        "enum": ["auto", "fast", "balanced", "deep", "ultra"],
                        "description": "Fetch/crawl preset",
                        "default": "auto",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum extracted characters for the runtime to collect",
                        "default": 20000,
                    },
                },
                "required": ["url"],
            },
            category="research",
            requires_confirmation=False,
        )
    )

    # Deep Research
    registry.register(
        ToolDefinition(
            name="deep_research",
            description=(
                "Run the full Research Core pipeline: search, crawl, deduplicate, build "
                "evidence pack, and return compact sources/evidence/content_refs for a "
                "research report. Use for broad or current web research tasks."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Research question"},
                    "mode": {
                        "type": "string",
                        "enum": ["overview", "scholar", "dev", "live", "media", "deep_dive"],
                        "description": "Research intent mode",
                        "default": "deep_dive",
                    },
                    "max_results": {"type": "integer", "default": 15},
                    "max_pages": {"type": "integer", "default": 8},
                    "build_evidence": {"type": "boolean", "default": True},
                },
                "required": ["query"],
            },
            category="research",
            requires_confirmation=False,
        )
    )

    # Research Runtime Status
    registry.register(
        ToolDefinition(
            name="research_status",
            description="Check whether the local hollow-search-core Research runtime is healthy.",
            parameters={"type": "object", "properties": {}},
            category="research",
            requires_confirmation=False,
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

    # List Directory
    registry.register(
        ToolDefinition(
            name="list_directory",
            description="List files and directories in the workspace. Supports recursive listing up to a configurable depth.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path relative to workspace root (default: root)",
                        "default": "",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Whether to list recursively",
                        "default": False,
                    },
                },
            },
            category="workspace",
        )
    )

    # Delete File
    registry.register(
        ToolDefinition(
            name="delete_file",
            description=(
                "Delete a file in the workspace. Cannot delete the workspace root "
                "or .workspace/ system directory. Returns file content hash for "
                "potential recovery. Requires confirmation."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to workspace root",
                    },
                },
                "required": ["path"],
            },
            category="file_ops",
            requires_confirmation=True,
        )
    )

    # Apply Patch
    registry.register(
        ToolDefinition(
            name="apply_patch",
            description=(
                "Apply a unified diff patch string to one or more files. "
                "Supports multi-file patches and multi-hunk patches. "
                "All changes are transactional — if any hunk fails, "
                "everything is rolled back."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "patch": {
                        "type": "string",
                        "description": "Unified diff patch string to apply",
                    },
                },
                "required": ["patch"],
            },
            category="file_ops",
            requires_confirmation=True,
        )
    )

    # File Read (enhanced with encoding)
    registry.register(
        ToolDefinition(
            name="file_read",
            description=(
                "Read a file from workspace with encoding support. "
                "For text files (default utf-8), returns the text content. "
                "For binary files or when encoding='base64', returns base64-encoded data. "
                "Supports line offset and limit for pagination."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to workspace root",
                    },
                    "encoding": {
                        "type": "string",
                        "enum": ["utf-8", "base64"],
                        "description": "Encoding to use for reading",
                        "default": "utf-8",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Starting line number (1-based)",
                        "default": 1,
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "Maximum number of lines to read",
                        "default": 500,
                    },
                },
                "required": ["path"],
            },
            category="file_ops",
        )
    )

    # Workspace Snapshot
    registry.register(
        ToolDefinition(
            name="snapshot",
            description=(
                "Take a snapshot of the workspace file tree. "
                "Returns a list of files with their sizes and modification times. "
                "Useful for tracking changes before/after code execution."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "include_files": {
                        "type": "boolean",
                        "description": "Whether to include the file list in the result",
                        "default": True,
                    },
                },
            },
            category="workspace",
        )
    )

    # Search Workspace (grep)
    registry.register(
        ToolDefinition(
            name="search_workspace",
            description="Search text patterns across files in the workspace. Use to locate code, config, errors, or symbols before reading individual files.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Keyword or regex pattern to search"},
                    "path": {"type": "string", "description": "Relative path within workspace", "default": "."},
                    "regex": {"type": "boolean", "description": "Treat pattern as regex", "default": False},
                    "case_sensitive": {"type": "boolean", "default": False},
                    "include_globs": {"type": "array", "items": {"type": "string"}, "default": []},
                    "exclude_globs": {"type": "array", "items": {"type": "string"}},
                    "max_results": {"type": "integer", "default": 50},
                    "context_lines": {"type": "integer", "default": 2},
                },
                "required": ["pattern"],
            },
            category="workspace",
        )
    )

    # Create Directories
    registry.register(
        ToolDefinition(
            name="create_directories",
            description="Create directories in the workspace. Cross-platform safe. Prefer this over shell mkdir, especially on Windows.",
            parameters={
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Directory paths relative to workspace root",
                    },
                },
                "required": ["paths"],
            },
            category="workspace",
        )
    )

    # Git Status
    registry.register(
        ToolDefinition(
            name="git_status",
            description="Inspect the current workspace Git status. Use before summarizing changes, reviewing modifications, or preparing commits.",
            parameters={
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Workspace id. Use current conversation workspace by default.",
                        "default": "current",
                    },
                },
            },
            category="workspace",
            requires_confirmation=False,
        )
    )

    # Git Diff
    registry.register(
        ToolDefinition(
            name="git_diff",
            description="Read Git diffs for the current workspace. Supports working tree, staged changes, a file, or a commit.",
            parameters={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "default": "current"},
                    "scope": {
                        "type": "string",
                        "enum": ["working", "staged", "file", "commit"],
                        "default": "working",
                    },
                    "file_path": {"type": "string", "description": "Optional relative file path"},
                    "commit": {"type": "string", "description": "Commit hash for scope=commit"},
                    "context_lines": {"type": "integer", "default": 3},
                },
            },
            category="workspace",
            requires_confirmation=False,
        )
    )

    # Git History
    registry.register(
        ToolDefinition(
            name="git_history",
            description="Read Git history for the current workspace. Combines log and blame modes.",
            parameters={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "default": "current"},
                    "mode": {"type": "string", "enum": ["log", "blame"], "default": "log"},
                    "file_path": {"type": "string", "description": "Optional relative file path"},
                    "line_start": {"type": "integer"},
                    "line_end": {"type": "integer"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
            category="workspace",
            requires_confirmation=False,
        )
    )

    # Git Checkpoint
    registry.register(
        ToolDefinition(
            name="git_checkpoint",
            description=(
                "Create an explicit Agent checkpoint in the hidden Shadow Git timeline. "
                "Use only for meaningful milestones, handoff checkpoints, or artifact versions. "
                "This does not commit to the user's real Git repository."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "default": "current"},
                    "kind": {
                        "type": "string",
                        "enum": ["agent_milestone", "artifact_version", "handoff_checkpoint"],
                        "default": "agent_milestone",
                    },
                    "message": {
                        "type": "string",
                        "description": "Short checkpoint label explaining what changed.",
                    },
                    "artifacts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Relative artifact paths when kind=artifact_version.",
                    },
                    "metadata": {"type": "object"},
                },
                "required": ["kind", "message"],
            },
            category="workspace",
            requires_confirmation=False,
        )
    )

    # Expand Tool Result
    registry.register(
        ToolDefinition(
            name="expand_tool_result",
            description=(
                "Retrieve the complete stored content of a previously truncated tool "
                "result. Use only when the head/tail view is insufficient. Identify "
                "the result by tool_result_id when available, or by tool_name to use "
                "the latest matching result. The full result remains expanded for "
                "the next three context builds."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tool_result_id": {
                        "type": "string",
                        "description": "Stored tool result id shown in a truncation marker.",
                    },
                    "tool_name": {
                        "type": "string",
                        "description": "Fallback: expand the latest result from this tool.",
                    },
                    "builds": {
                        "type": "integer",
                        "description": "How many upcoming context builds should keep the result expanded.",
                        "default": 3,
                    },
                },
            },
            category="system",
            requires_confirmation=False,
        )
    )

    # Crazy expand all tool results
    registry.register(
        ToolDefinition(
            name="CRAZY_for_tool_results",
            description=(
                "Temporarily expand all stored tool results into the model context. "
                "Use before final synthesis, report writing, cross-source evidence "
                "review, or debugging where maximum context recall is more valuable "
                "than token economy. The expansion expires after the requested builds."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "builds": {
                        "type": "integer",
                        "description": "Upcoming context builds to keep all tool results fully expanded.",
                        "default": 2,
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why full result recall is needed now.",
                    },
                },
            },
            category="system",
            requires_confirmation=False,
        )
    )

    # Focused tool result recall
    registry.register(
        ToolDefinition(
            name="focus_tool_results",
            description=(
                "Open a targeted expansion window for tool results by id, tool name, "
                "query/grep text, status, or latest count. Use this when only specific "
                "search/fetch/command/file outputs are needed for the next step."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tool_result_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific stored tool result ids/content refs to expand.",
                    },
                    "tool_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tool names whose recent/current results should expand.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Grep-style text query; matching tool results expand.",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["any", "completed", "failed"],
                        "default": "any",
                    },
                    "latest": {
                        "type": "integer",
                        "description": "Also expand the latest N matching tool results.",
                        "default": 5,
                    },
                    "builds": {
                        "type": "integer",
                        "description": "Upcoming context builds to keep matching results expanded.",
                        "default": 3,
                    },
                },
            },
            category="system",
            requires_confirmation=False,
        )
    )

    # Context map
    registry.register(
        ToolDefinition(
            name="context_map",
            description=(
                "Inspect the current recallable context map without expanding raw content. "
                "Use this before broad recall to see available user constraints, pinned items, "
                "chat messages, tool results, compression status, and recall ids."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["all", "current_task", "recent", "pinned"],
                        "default": "all",
                    },
                },
            },
            category="system",
            requires_confirmation=False,
        )
    )

    # Custom context recall
    registry.register(
        ToolDefinition(
            name="custom_context_recall",
            description=(
                "Recall precise raw or structured context by target list. Supports tool_result, "
                "chat_message, file, file_range, grep, search_result, browser_snapshot, "
                "shell_output, diff, user_constraint, plan, and artifact_validation. Use before "
                "code edits, final reports, factual citations, or complex debugging."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "targets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "tool_result",
                                        "chat_message",
                                        "file",
                                        "file_range",
                                        "grep",
                                        "search_result",
                                        "browser_snapshot",
                                        "error_log",
                                        "shell_output",
                                        "diff",
                                        "user_constraint",
                                        "plan",
                                        "artifact_validation",
                                    ],
                                },
                                "id": {"type": "string"},
                                "path": {"type": "string"},
                                "query": {"type": "string"},
                                "startLine": {"type": "integer"},
                                "endLine": {"type": "integer"},
                            },
                            "required": ["type"],
                        },
                        "description": "One or more recall targets.",
                    },
                    "turns": {"type": "integer", "default": 1},
                    "maxTokens": {"type": "integer", "default": 4000},
                    "mode": {
                        "type": "string",
                        "enum": ["raw", "key_segments", "summary_plus_segments", "structure_only"],
                        "default": "summary_plus_segments",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why exact context is needed now.",
                    },
                },
                "required": ["targets", "reason"],
            },
            category="system",
            requires_confirmation=False,
        )
    )

    # Recall maximum
    registry.register(
        ToolDefinition(
            name="recall_maximum",
            description=(
                "Activate MAX recall mode for a short window and expand as much relevant stored "
                "context as budget allows. Use only for final synthesis, broad evidence audit, "
                "large refactors, or complex debugging. Prefer context_map and custom_context_recall "
                "for normal targeted work."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "turns": {"type": "integer", "default": 3},
                    "scope": {
                        "type": "string",
                        "enum": ["current_task", "all_recent", "research", "coding", "debugging", "artifact", "custom"],
                        "default": "current_task",
                    },
                    "maxTokens": {"type": "integer"},
                    "priority": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "user_constraints",
                                "tool_results",
                                "research_evidence",
                                "file_reads",
                                "diffs",
                                "errors",
                                "plans",
                                "chat_messages",
                            ],
                        },
                    },
                    "includeRaw": {"type": "boolean", "default": False},
                    "includeKeySegments": {"type": "boolean", "default": True},
                    "query": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["reason"],
            },
            category="system",
            requires_confirmation=False,
        )
    )

    # Pin Memory
    registry.register(
        ToolDefinition(
            name="pin_memory",
            description=(
                "Pin a user constraint, file, decision, unresolved error, plan, or note so it "
                "stays visible in context memory and is not treated as disposable history."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["user_constraint", "file", "decision", "error", "note", "plan"],
                            },
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["type"],
                    },
                    "reason": {"type": "string"},
                    "expiresAfterTurns": {"type": "integer"},
                },
                "required": ["target"],
            },
            category="system",
            requires_confirmation=False,
        )
    )

    # Unpin Memory
    registry.register(
        ToolDefinition(
            name="unpin_memory",
            description="Deactivate one pinned memory item by pin id.",
            parameters={
                "type": "object",
                "properties": {
                    "targetId": {"type": "string"},
                },
                "required": ["targetId"],
            },
            category="system",
            requires_confirmation=False,
        )
    )

    # Todo List
    registry.register(
        ToolDefinition(
            name="set_todo_list",
            description="Create, update, or read the current task todo list. Use for complex multi-step tasks.",
            parameters={
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["replace", "update", "read"]},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                                "status": {"type": "string", "enum": ["todo", "doing", "done", "blocked", "cancelled"]},
                                "note": {"type": "string"},
                            },
                            "required": ["id", "title", "status"],
                        },
                    },
                },
                "required": ["mode"],
            },
            category="system",
        )
    )

    # Ask User Question
    registry.register(
        ToolDefinition(
            name="ask_user_question",
            description="Ask the user a clarification question and pause until they respond. Use when info is insufficient.",
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "description": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["id", "label"],
                        },
                    },
                    "allow_custom_response": {"type": "boolean", "default": True},
                    "custom_placeholder": {"type": "string", "default": "Custom response…"},
                },
                "required": ["question", "options"],
            },
            category="system",
        )
    )

    # Request Approval
    registry.register(
        ToolDefinition(
            name="request_approval",
            description="Request user approval before executing a risky plan. Agent pauses until the user responds.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "risk_level": {"type": "string", "enum": ["low", "medium", "high"], "default": "medium"},
                    "plan": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "risk": {"type": "string", "enum": ["low", "medium", "high"]},
                            },
                            "required": ["id", "title"],
                        },
                    },
                    "allow_custom_response": {"type": "boolean", "default": True},
                },
                "required": ["title", "plan"],
            },
            category="system",
            requires_confirmation=False,
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

    # Create Directories
    registry.register(
        ToolDefinition(
            name="create_directories",
            description="Create directories in workspace. Cross-platform safe. Prefer over shell mkdir.",
            parameters={
                "type": "object",
                "properties": {
                    "paths": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["paths"],
            },
            category="workspace",
        )
    )

    logger.info(
        f"Registered {len(registry.get_category_tools('workspace'))} workspace tools"
    )
