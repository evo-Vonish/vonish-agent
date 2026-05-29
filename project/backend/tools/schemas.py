"""JSON Schema definitions for file-operation tools.

Each schema follows the JSON Schema ``object`` format used by OpenAI function
calling (and prompt-based tool injection).  They describe the *named arguments*
that each tool's ``execute()`` method receives via ``**kwargs``.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

READ_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Relative path to the file in the workspace",
        },
        "start_line": {
            "type": "integer",
            "description": "Start reading from this line (1-based, inclusive)",
            "default": 1,
            "minimum": 1,
        },
        "max_lines": {
            "type": "integer",
            "description": "Maximum lines to read (hard ceiling 500)",
            "default": 200,
            "minimum": 1,
            "maximum": 500,
        },
    },
    "required": ["path"],
}

# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------

WRITE_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Path to the file (relative to workspace root)",
        },
        "content": {
            "type": "string",
            "description": "Full content to write (overwrites existing file)",
        },
    },
    "required": ["path", "content"],
}

# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------

EDIT_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Path to the file to edit",
        },
        "old_text": {
            "type": "string",
            "description": (
                "Exact text to search for. Must match literally (no regex). "
                "If it occurs more than once the edit is rejected — refine the snippet."
            ),
        },
        "new_text": {
            "type": "string",
            "description": "Replacement text",
        },
    },
    "required": ["path", "old_text", "new_text"],
}

# ---------------------------------------------------------------------------
# apply_patch
# ---------------------------------------------------------------------------

APPLY_PATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "patch": {
            "type": "string",
            "description": (
                "Unified diff string to apply. Supports multiple files "
                "(---/+++ headers) and multiple hunks per file."
            ),
        },
    },
    "required": ["patch"],
}

# ---------------------------------------------------------------------------
# delete_file
# ---------------------------------------------------------------------------

DELETE_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Path to the file to delete (relative to workspace root)",
        },
    },
    "required": ["path"],
}
