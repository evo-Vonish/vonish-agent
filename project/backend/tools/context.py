"""Tool execution context + path resolution security.

Reference: CodeWhale ToolContext (crates/tui/src/tools/spec.rs L359-466)
Simplified adaptation — validates paths but does NOT duplicate the full
PathSandbox feature set (that lives in backend/workspace/permissions.py).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Security exception
# ---------------------------------------------------------------------------


class PathEscapeError(PermissionError):
    """Raised when a requested path would leave the workspace sandbox."""

    def __init__(self, message: str, path: str = "") -> None:
        self.path = path
        super().__init__(f"PathEscape: {message} (path={path!r})")


# ---------------------------------------------------------------------------
# ToolContext
# ---------------------------------------------------------------------------


class ToolContext:
    """Per-execution context passed to every tool ``execute()`` call.

    Holds conversation-scoped identity and workspace bounds.  The
    ``resolve_path()`` method is the *single chokepoint* for all file-path
    security in the tool layer.
    """

    def __init__(
        self,
        conversation_id: str,
        workspace_root: str,
        user_id: str,
    ) -> None:
        self.conversation_id = conversation_id
        self.workspace_root = Path(workspace_root).resolve()
        self.user_id = user_id

    # -- path resolution ----------------------------------------------------

    def resolve_path(self, raw: str) -> Path:
        """Resolve *raw* to a safe absolute path inside the workspace.

        Security checks (in order):
        1. Null-byte rejection.
        2. Path traversal: literal ``..`` as a path component is blocked.
        3. Normalise via ``os.path.normpath`` to collapse inner ``..`` / ``.``.
        4. Absolute-path check: if *raw* is absolute it must already start with
           the workspace prefix (no ``/etc/passwd`` shortcuts).
        5. Join relative paths to ``workspace_root``.
        6. ``resolve()`` (canonicalise) to chase symlinks — then verify the
            resolved path still starts with ``workspace_root``.
        7. Non-existent paths: walk up to the deepest existing ancestor,
           canonicalise it, and ensure it lies inside the workspace.

        Raises
        ------
        PathEscapeError
            If any check fails.
        """
        if not raw:
            raise PathEscapeError("Empty path is not allowed", raw)

        # 1. Null bytes
        if "\x00" in raw:
            raise PathEscapeError("Path contains null bytes", raw)

        # 2. Literal .. as a path component (fast reject before normpath)
        #    Covers 'foo/../bar', '../foo', 'foo/..', '..\\foo' on Windows, etc.
        raw_normalized = raw.replace("\\", "/")
        if ".." in [p for p in raw_normalized.split("/") if p]:
            raise PathEscapeError("Path traversal (..) is not allowed", raw)

        # 3. os.path.normpath — collapse inner '.' / '..' that are NOT components
        raw_norm = os.path.normpath(raw)
        if raw_norm.startswith("..") or "/../" in raw_norm.replace("\\", "/"):
            # Double-check after normalisation
            parts = raw_norm.replace("\\", "/").split("/")
            if ".." in parts:
                raise PathEscapeError("Path traversal (..) is not allowed after normalisation", raw)

        candidate = Path(raw_norm)

        # 4. Absolute path — must be inside workspace already
        if candidate.is_absolute():
            candidate_resolved = candidate.resolve()
            if not self._is_under_workspace(candidate_resolved):
                raise PathEscapeError(
                    f"Absolute path {candidate_resolved} is outside workspace "
                    f"{self.workspace_root}",
                    raw,
                )
            return candidate_resolved

        # 5. Relative path — join with workspace root
        joined = (self.workspace_root / candidate).resolve()

        # 6. Post-resolve workspace check (catches symlink escapes)
        if not self._is_under_workspace(joined):
            raise PathEscapeError(
                f"Resolved path {joined} escapes workspace {self.workspace_root}",
                raw,
            )

        # 7. Non-existent path: validate via deepest existing ancestor
        if not joined.exists():
            ancestor = joined.parent
            while ancestor and not ancestor.exists():
                ancestor = ancestor.parent

            if ancestor is not None and ancestor.exists():
                resolved_ancestor = ancestor.resolve()
                if not self._is_under_workspace(resolved_ancestor):
                    raise PathEscapeError(
                        f"Parent directory {resolved_ancestor} escapes workspace", raw
                    )

        return joined

    # -- internal helpers ---------------------------------------------------

    def _is_under_workspace(self, path: Path) -> bool:
        """True when *path* is inside (or equal to) ``self.workspace_root``."""
        try:
            path.relative_to(self.workspace_root)
            return True
        except ValueError:
            return False

    def get_relative_path(self, full_path: Path) -> str:
        """Return the portion of *full_path* relative to the workspace root."""
        try:
            return str(full_path.relative_to(self.workspace_root))
        except ValueError:
            return str(full_path)

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"workspace={self.workspace_root!s} "
            f"conv={self.conversation_id!r}>"
        )
