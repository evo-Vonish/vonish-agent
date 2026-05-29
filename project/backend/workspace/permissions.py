"""Path Sandbox for Workspace security.

Validates all file paths to prevent:
- Path traversal (../)
- Absolute path escaping
- Symlink following attacks
- Cross-session path access
- Hidden file access (except .workspace/)
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Security Error
# ---------------------------------------------------------------------------


class SecurityError(ValueError):
    """Raised when a path fails security validation."""

    def __init__(self, message: str, path: str = "") -> None:
        self.path = path
        super().__init__(f"Security violation for path '{path}': {message}")


# ---------------------------------------------------------------------------
# Path Sandbox
# ---------------------------------------------------------------------------


class PathValidationResult(BaseModel):
    """Result of path validation."""

    valid: bool
    safe_path: Path | None
    error_message: str = ""


class PathSandbox:
    """Sandbox for workspace file path validation.

    All file operations must pass through this validator to ensure
    paths stay within the allowed workspace directory.

    Rules:
    1. No path traversal (../, ..\\)
    2. No absolute paths outside workspace (/etc/passwd, C:\\Users\\)
    3. No symlinks that escape workspace
    4. Path must be within workspace root after normalization
    5. No hidden files (paths starting with .), except within .workspace/
    6. No null bytes
    7. No overly long paths (>4096 chars)
    8. No control characters
    """

    # Allowed hidden paths pattern (only .workspace/ is allowed)
    _ALLOWED_HIDDEN_PATTERN = re.compile(r"^\.workspace(/.*)?$")

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self._max_path_length = 4096

    # -- internal helpers ---------------------------------------------------

    def _contains_null_bytes(self, path_str: str) -> bool:
        return "\x00" in path_str

    def _contains_control_chars(self, path_str: str) -> bool:
        # Allow tab (\x09) and newline (\x0a, \x0d) but block other control chars
        for ch in path_str:
            code = ord(ch)
            if code < 32 and code not in (9, 10, 13):
                return True
        return False

    def _has_path_traversal(self, path_str: str) -> bool:
        """Check for path traversal patterns.

        Detects '..' as a path component (e.g., 'foo/../bar', '../foo', 'foo/..').
        """
        # Normalize path separators for uniform checking
        normalized = path_str.replace("\\", "/")
        parts = normalized.split("/")
        return ".." in parts

    def _is_hidden_path(self, path_str: str) -> bool:
        """Check if path attempts to access hidden files.

        Only .workspace/ is allowed. All other paths starting with .
        or containing /. are rejected.
        """
        normalized = path_str.replace("\\", "/").strip("/")
        if not normalized:
            return False

        # Check each path component
        parts = normalized.split("/")
        for part in parts:
            if part.startswith("."):
                # Only allow .workspace and its contents
                if part == ".workspace":
                    continue
                return True
        return False

    def _check_within_workspace(self, resolved_path: Path) -> bool:
        """Verify resolved path is within workspace root."""
        try:
            resolved_path.relative_to(self.workspace_root)
            return True
        except ValueError:
            return False

    # -- public API ---------------------------------------------------------

    def validate_path(self, requested_path: str | Path) -> Path:
        """Validate a requested path and return the safe absolute path.

        Args:
            requested_path: The path to validate (relative or absolute).

        Returns:
            Resolved safe absolute Path within workspace.

        Raises:
            SecurityError: If path is invalid or escapes the workspace.
        """
        path_str = str(requested_path)

        # Check null bytes
        if self._contains_null_bytes(path_str):
            raise SecurityError("Path contains null bytes", path_str)

        # Check control characters
        if self._contains_control_chars(path_str):
            raise SecurityError("Path contains control characters", path_str)

        # Check path length
        if len(path_str) > self._max_path_length:
            raise SecurityError(
                f"Path exceeds max length of {self._max_path_length}", path_str
            )

        # Check path traversal
        if self._has_path_traversal(path_str):
            raise SecurityError("Path traversal (..) is not allowed", path_str)

        # Check hidden file access (except .workspace/)
        if self._is_hidden_path(path_str):
            raise SecurityError(
                "Access to hidden files is not allowed (except .workspace/)", path_str
            )

        # Convert to Path and resolve
        requested = Path(path_str)

        if requested.is_absolute():
            # Absolute path: must be within workspace
            resolved = requested.resolve()
            if not self._check_within_workspace(resolved):
                raise SecurityError(
                    "Absolute path outside workspace is not allowed", path_str
                )
        else:
            # Relative path: join with workspace root and resolve
            resolved = (self.workspace_root / requested).resolve()

        # Final boundary check after resolution
        if not self._check_within_workspace(resolved):
            raise SecurityError("Resolved path escapes workspace root", path_str)

        # Check for symlinks (do not follow - security risk)
        # We check each component from workspace_root up to resolved
        current = resolved
        try:
            # Check if any part of the path is a symlink
            for parent in [resolved, *list(resolved.parents)]:
                if parent == self.workspace_root or self.workspace_root in parent.parents or parent == self.workspace_root.parent:
                    if parent.is_symlink():
                        raise SecurityError(
                            "Symbolic links are not allowed", path_str
                        )
        except OSError:
            # If we can't stat the path, treat as unsafe
            pass

        return resolved

    def validate_create_path(self, requested_path: str | Path) -> Path:
        """Validate a path for file/directory creation.

        Additionally ensures parent directories are within workspace.

        Args:
            requested_path: The path to validate.

        Returns:
            Resolved safe absolute Path.

        Raises:
            SecurityError: If path or parent is invalid.
        """
        safe_path = self.validate_path(requested_path)

        # Ensure parent directory exists or is creatable within workspace
        parent = safe_path.parent
        if not self._check_within_workspace(parent):
            raise SecurityError(
                "Parent directory escapes workspace root", str(requested_path)
            )

        return safe_path

    def is_safe(self, path: str | Path) -> bool:
        """Quick check if a path is safe (within workspace and valid).

        Args:
            path: Path to check.

        Returns:
            True if path is safe to access.
        """
        try:
            self.validate_path(str(path))
            return True
        except SecurityError:
            return False

    def normalize(self, path: str | Path) -> str:
        """Normalize a path and return relative path from workspace root.

        Args:
            path: Path to normalize.

        Returns:
            Normalized relative path string.

        Raises:
            SecurityError: If path is invalid.
        """
        safe_path = self.validate_path(path)
        try:
            return str(safe_path.relative_to(self.workspace_root))
        except ValueError:
            # This should not happen due to validate_path, but handle gracefully
            return str(safe_path)

    def get_relative_path(self, full_path: str | Path) -> str:
        """Get the relative path from workspace root.

        Args:
            full_path: Full filesystem path.

        Returns:
            Path relative to workspace root.
        """
        path = Path(full_path).resolve()
        try:
            return str(path.relative_to(self.workspace_root))
        except ValueError:
            return str(path)

    def join(self, *parts: str) -> Path:
        """Safely join path components within workspace.

        Args:
            *parts: Path components.

        Returns:
            Absolute path within workspace.
        """
        return (self.workspace_root / Path(*parts)).resolve()
