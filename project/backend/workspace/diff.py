"""Diff generation for Workspace system.

Generates structured diffs between workspace snapshots, including
file-level change detection and text diff generation.
"""

from __future__ import annotations

import difflib
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any

from workspace.snapshot import Snapshot, SnapshotManager
from workspace.storage_provider import FileInfo
from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class FileChange(BaseModel):
    """Represents a single file change between two snapshots."""

    path: str
    old_size: int | None
    new_size: int | None
    old_hash: str | None
    new_hash: str | None
    change_type: str = ""  # "added" | "modified" | "deleted" | "renamed"
    old_path: str | None = None  # For renames: original path

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "change_type": self.change_type,
            "old_size": self.old_size,
            "new_size": self.new_size,
            "old_hash": self.old_hash,
            "new_hash": self.new_hash,
            "old_path": self.old_path,
        }


class RenameChange(BaseModel):
    """Represents a file rename operation."""

    old_path: str
    new_path: str
    size: int
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "old_path": self.old_path,
            "new_path": self.new_path,
            "size": self.size,
            "content_hash": self.content_hash,
        }


class WorkspaceDiff(BaseModel):
    """Complete diff of workspace changes between two snapshots."""

    added: list[FileChange] = Field(default_factory=list)
    modified: list[FileChange] = Field(default_factory=list)
    deleted: list[FileChange] = Field(default_factory=list)
    renamed: list[RenameChange] = Field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.deleted or self.renamed)

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.modified) + len(self.deleted) + len(self.renamed)

    @property
    def summary(self) -> str:
        parts: list[str] = []
        if self.added:
            parts.append(f"{len(self.added)} added")
        if self.deleted:
            parts.append(f"{len(self.deleted)} deleted")
        if self.modified:
            parts.append(f"{len(self.modified)} modified")
        if self.renamed:
            parts.append(f"{len(self.renamed)} renamed")
        return ", ".join(parts) if parts else "No changes"

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_changes": self.has_changes,
            "summary": self.summary,
            "total_changes": self.total_changes,
            "added": [c.to_dict() for c in self.added],
            "modified": [c.to_dict() for c in self.modified],
            "deleted": [c.to_dict() for c in self.deleted],
            "renamed": [r.to_dict() for r in self.renamed],
        }


class FileDiff(BaseModel):
    """Detailed diff for a single file (text diff output)."""

    path: str
    change_type: str  # "added" | "removed" | "modified"
    old_content: str = ""
    new_content: str = ""
    unified_diff: str = ""
    old_size: int = 0
    new_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "change_type": self.change_type,
            "old_size": self.old_size,
            "new_size": self.new_size,
            "diff": self.unified_diff if self.unified_diff else None,
        }


# ---------------------------------------------------------------------------
# Diff Generator
# ---------------------------------------------------------------------------


class DiffGenerator:
    """Generates structured diffs between workspace snapshots.

    Uses snapshot-based comparison for file-level changes and
    Python's difflib for text diff generation.
    """

    def __init__(self, max_diff_lines: int = 500) -> None:
        self.max_diff_lines = max_diff_lines

    async def generate(
        self, before: Snapshot, after: Snapshot
    ) -> WorkspaceDiff:
        """Generate a WorkspaceDiff from two snapshots.

        Compares file manifests to detect added, modified, deleted,
        and potentially renamed files.

        Args:
            before: Earlier snapshot.
            after: Later snapshot.

        Returns:
            WorkspaceDiff with all changes categorized.
        """
        before_files = before.file_manifest
        after_files = after.file_manifest

        all_paths = set(before_files.keys()) | set(after_files.keys())

        diff = WorkspaceDiff()

        # Track potential renames: files with same hash but different paths
        before_hashes: dict[str, str] = {
            fs.content_hash: path for path, fs in before_files.items()
        }
        after_hashes: dict[str, str] = {
            fs.content_hash: path for path, fs in after_files.items()
        }

        renamed_before: set[str] = set()
        renamed_after: set[str] = set()

        for path in all_paths:
            # Detect renames: file deleted from before and added in after with same hash
            if path in before_files and path not in after_files:
                before_hash = before_files[path].content_hash
                # Check if this hash exists in after with a different path
                if before_hash in after_hashes:
                    after_path = after_hashes[before_hash]
                    if after_path != path and after_path not in before_files:
                        # This is a rename
                        diff.renamed.append(
                            RenameChange(
                                old_path=path,
                                new_path=after_path,
                                size=before_files[path].size,
                                content_hash=before_hash,
                            )
                        )
                        renamed_before.add(path)
                        renamed_after.add(after_path)
                        continue

                # Regular deletion
                if path not in renamed_before:
                    diff.deleted.append(
                        FileChange(
                            path=path,
                            old_size=before_files[path].size,
                            new_size=None,
                            old_hash=before_files[path].content_hash,
                            new_hash=None,
                            change_type="deleted",
                        )
                    )

            elif path not in before_files and path in after_files:
                # Skip if this path was already handled as a rename target
                if path in renamed_after:
                    continue

                # Check if this is a rename target
                after_hash = after_files[path].content_hash
                if after_hash in before_hashes:
                    before_path = before_hashes[after_hash]
                    if before_path != path and before_path not in after_files:
                        # Already handled above
                        continue

                # Regular addition
                diff.added.append(
                    FileChange(
                        path=path,
                        old_size=None,
                        new_size=after_files[path].size,
                        old_hash=None,
                        new_hash=after_files[path].content_hash,
                        change_type="added",
                    )
                )

            elif path in before_files and path in after_files:
                # Both exist: check if modified
                if before_files[path].content_hash != after_files[path].content_hash:
                    diff.modified.append(
                        FileChange(
                            path=path,
                            old_size=before_files[path].size,
                            new_size=after_files[path].size,
                            old_hash=before_files[path].content_hash,
                            new_hash=after_files[path].content_hash,
                            change_type="modified",
                        )
                    )

        logger.info(
            f"Generated diff: +{len(diff.added)} -{len(diff.deleted)} "
            f"~{len(diff.modified)} ->{len(diff.renamed)}"
        )

        return diff

    def generate_text_diff(
        self,
        old_content: str,
        new_content: str,
        path: str = "",
        context_lines: int = 3,
    ) -> str:
        """Generate unified diff for text content.

        Args:
            old_content: Original text content.
            new_content: Modified text content.
            path: File path for diff header.
            context_lines: Number of context lines in diff.

        Returns:
            Unified diff string.
        """
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        # Ensure lines end with newline for proper diff
        old_lines = [l if l.endswith("\n") else l + "\n" for l in old_lines]
        new_lines = [l if l.endswith("\n") else l + "\n" for l in new_lines]

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=context_lines,
        )

        result = "".join(diff)

        # Truncate if too long
        lines = result.split("\n")
        if len(lines) > self.max_diff_lines:
            lines = lines[: self.max_diff_lines]
            lines.append(f"\n... [diff truncated at {self.max_diff_lines} lines]")
            result = "\n".join(lines)

        return result

    def generate_binary_diff(
        self,
        old_size: int,
        new_size: int,
        path: str = "",
    ) -> str:
        """Generate a simple diff description for binary files.

        Args:
            old_size: Original file size.
            new_size: New file size.
            path: File path.

        Returns:
            Diff description string.
        """
        size_diff = new_size - old_size
        sign = "+" if size_diff >= 0 else ""
        return f"Binary file {path}: {old_size} -> {new_size} bytes ({sign}{size_diff})"

    def create_file_diff(
        self,
        path: str,
        change_type: str,
        old_content: str | bytes = "",
        new_content: str | bytes = "",
    ) -> FileDiff:
        """Create a FileDiff object with optional unified diff.

        Args:
            path: File path.
            change_type: Type of change.
            old_content: Original content.
            new_content: Modified content.

        Returns:
            FileDiff object.
        """
        old_text = (
            old_content.decode("utf-8", errors="replace")
            if isinstance(old_content, bytes)
            else old_content
        )
        new_text = (
            new_content.decode("utf-8", errors="replace")
            if isinstance(new_content, bytes)
            else new_content
        )

        unified_diff = ""
        if change_type == "modified" and old_text and new_text:
            unified_diff = self.generate_text_diff(old_text, new_text, path)

        return FileDiff(
            path=path,
            change_type=change_type,
            old_content=old_text,
            new_content=new_text,
            unified_diff=unified_diff,
            old_size=len(old_content) if isinstance(old_content, (str, bytes)) else 0,
            new_size=len(new_content) if isinstance(new_content, (str, bytes)) else 0,
        )

    def generate_file_diffs(
        self,
        workspace_diff: WorkspaceDiff,
        old_contents: dict[str, str] | None = None,
        new_contents: dict[str, str] | None = None,
    ) -> list[FileDiff]:
        """Generate detailed FileDiff objects from a WorkspaceDiff.

        Args:
            workspace_diff: High-level workspace diff.
            old_contents: Optional map of path -> content for deleted/modified files.
            new_contents: Optional map of path -> content for added/modified files.

        Returns:
            List of FileDiff objects with unified diffs where applicable.
        """
        old_contents = old_contents or {}
        new_contents = new_contents or {}

        file_diffs: list[FileDiff] = []

        for change in workspace_diff.added:
            file_diffs.append(
                self.create_file_diff(
                    change.path,
                    "added",
                    "",
                    new_contents.get(change.path, ""),
                )
            )

        for change in workspace_diff.deleted:
            file_diffs.append(
                self.create_file_diff(
                    change.path,
                    "removed",
                    old_contents.get(change.path, ""),
                    "",
                )
            )

        for change in workspace_diff.modified:
            file_diffs.append(
                self.create_file_diff(
                    change.path,
                    "modified",
                    old_contents.get(change.path, ""),
                    new_contents.get(change.path, ""),
                )
            )

        for rename in workspace_diff.renamed:
            file_diffs.append(
                FileDiff(
                    path=rename.new_path,
                    change_type="renamed",
                    old_content=f"Renamed from {rename.old_path}",
                    new_content=f"Renamed to {rename.new_path}",
                    unified_diff=f"Renamed: {rename.old_path} -> {rename.new_path}",
                    old_size=0,
                    new_size=rename.size,
                )
            )

        return file_diffs

    def generate_quick_summary(
        self,
        added: list[str],
        removed: list[str],
        modified: list[str],
    ) -> str:
        """Generate a quick text summary of changes.

        Args:
            added: List of added file paths.
            removed: List of removed file paths.
            modified: List of modified file paths.

        Returns:
            Summary string.
        """
        lines = []
        if added:
            lines.append(f"Added ({len(added)}):")
            for path in added:
                lines.append(f"  + {path}")
        if removed:
            lines.append(f"Removed ({len(removed)}):")
            for path in removed:
                lines.append(f"  - {path}")
        if modified:
            lines.append(f"Modified ({len(modified)}):")
            for path in modified:
                lines.append(f"  ~ {path}")

        return "\n".join(lines) if lines else "No changes"


# ---------------------------------------------------------------------------
# Global Instance
# ---------------------------------------------------------------------------

_diff_generator: DiffGenerator | None = None


def get_diff_generator() -> DiffGenerator:
    """Get the global diff generator."""
    global _diff_generator
    if _diff_generator is None:
        _diff_generator = DiffGenerator()
    return _diff_generator
