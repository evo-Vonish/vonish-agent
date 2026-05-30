"""
Artifact Collector - Workspace snapshot diff and artifact capture.

Detects file changes (added, modified, deleted) by comparing filesystem
snapshots before and after code execution.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── File Snapshots ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FileSnapshot:
    """Immutable snapshot of a file's state."""

    path: Path  # relative to workspace root
    size: int
    mtime: float
    content_hash: str  # SHA-256 of content (for detecting modifications)

    @classmethod
    def from_path(cls, absolute_path: Path, workspace_root: Path) -> FileSnapshot | None:
        """Create a snapshot from an absolute file path."""
        try:
            stat = absolute_path.stat()
            # Compute hash for small files (< 10MB), skip for large files
            if stat.st_size < 10 * 1024 * 1024:
                content_hash = hashlib.sha256(absolute_path.read_bytes()).hexdigest()[:16]
            else:
                content_hash = f"size-{stat.st_size}-{stat.st_mtime_ns}"

            relative = absolute_path.relative_to(workspace_root)
            return cls(
                path=relative,
                size=stat.st_size,
                mtime=stat.st_mtime,
                content_hash=content_hash,
            )
        except (OSError, ValueError):
            return None


# ── Snapshot ──────────────────────────────────────────────────────────────────


@dataclass
class WorkspaceSnapshot:
    """Snapshot of workspace state at a point in time."""

    timestamp: float
    files: dict[Path, FileSnapshot]  # relative path -> snapshot

    @classmethod
    def capture(cls, workspace_root: Path) -> WorkspaceSnapshot:
        """Capture current state of the workspace."""
        files: dict[Path, FileSnapshot] = {}
        if not workspace_root.exists():
            return cls(timestamp=time.time(), files=files)

        for path in workspace_root.rglob("*"):
            if path.is_file():
                snapshot = FileSnapshot.from_path(path, workspace_root)
                if snapshot:
                    files[snapshot.path] = snapshot

        return cls(timestamp=time.time(), files=files)


# ── Diff Result ───────────────────────────────────────────────────────────────


@dataclass
class FileChange:
    """A single file change detected by diff."""

    path: str  # relative path string
    change_type: str  # "added", "modified", "deleted"
    size: int = 0
    mime_type: str = ""


@dataclass
class WorkspaceDiff:
    """Result of comparing two workspace snapshots."""

    added: list[FileChange] = field(default_factory=list)
    modified: list[FileChange] = field(default_factory=list)
    deleted: list[FileChange] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.deleted)

    @property
    def all_changes(self) -> list[FileChange]:
        return self.added + self.modified + self.deleted

    def to_artifacts(self) -> list[dict[str, Any]]:
        """Convert added files to artifact entries for tool result."""
        artifacts = []
        for change in self.added:
            artifacts.append({
                "path": change.path,
                "mime_type": change.mime_type or "application/octet-stream",
                "size": change.size,
                "change_type": change.change_type,
            })
        return artifacts


# ── Artifact Collector ────────────────────────────────────────────────────────


# File extensions that we recognize and support
_SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".json", ".csv", ".html",
    ".xlsx", ".xls",
    ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".pdf", ".zip",
}


def _get_mime_type(file_path: Path) -> str:
    """Get MIME type for a file."""
    mime, _ = mimetypes.guess_type(str(file_path))
    return mime or "application/octet-stream"


def _is_artifact_file(relative_path: Path) -> bool:
    """Check if a file should be reported as an artifact."""
    # Normalise to forward-slash for cross-platform checks
    path_str = relative_path.as_posix()
    # Skip files in cache/ (internal kernel files)
    if path_str.startswith("cache/"):
        return False
    # All other files: outputs/, assets/, or workspace root
    return True


class ArtifactCollector:
    """Collects artifacts by diffing workspace snapshots."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    def snapshot_before(self) -> WorkspaceSnapshot:
        """Capture snapshot before code execution."""
        return WorkspaceSnapshot.capture(self.workspace_root)

    def snapshot_after(self) -> WorkspaceSnapshot:
        """Capture snapshot after code execution."""
        return WorkspaceSnapshot.capture(self.workspace_root)

    def diff(self, before: WorkspaceSnapshot, after: WorkspaceSnapshot) -> WorkspaceDiff:
        """Compare two snapshots and return the diff."""
        result = WorkspaceDiff()

        before_paths = set(before.files.keys())
        after_paths = set(after.files.keys())

        # Added files
        for path in after_paths - before_paths:
            snapshot = after.files[path]
            if _is_artifact_file(path):
                result.added.append(FileChange(
                    path=str(path),
                    change_type="added",
                    size=snapshot.size,
                    mime_type=_get_mime_type(path),
                ))

        # Modified files
        for path in before_paths & after_paths:
            before_snap = before.files[path]
            after_snap = after.files[path]
            if before_snap.content_hash != after_snap.content_hash:
                result.modified.append(FileChange(
                    path=str(path),
                    change_type="modified",
                    size=after_snap.size,
                    mime_type=_get_mime_type(path),
                ))

        # Deleted files
        for path in before_paths - after_paths:
            before_snap = before.files[path]
            result.deleted.append(FileChange(
                path=str(path),
                change_type="deleted",
                size=before_snap.size,
                mime_type=_get_mime_type(path),
            ))

        return result

    def collect_artifacts(self) -> list[dict[str, Any]]:
        """One-shot: capture current artifacts from outputs/ directory.

        Useful when we don't have a before snapshot.
        """
        artifacts = []
        outputs_dir = self.workspace_root / "outputs"
        if not outputs_dir.exists():
            return artifacts

        for path in outputs_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in _SUPPORTED_EXTENSIONS:
                try:
                    stat = path.stat()
                    relative = path.relative_to(self.workspace_root)
                    artifacts.append({
                        "path": str(relative),
                        "mime_type": _get_mime_type(path),
                        "size": stat.st_size,
                    })
                except OSError:
                    continue

        return artifacts
