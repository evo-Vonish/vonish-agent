"""File operation tools — read, write, edit, patch, delete.

Reference implementations:
    - CodeWhale file.rs (ReadFileTool, WriteFileTool, EditFileTool)
    - CodeWhale apply_patch.rs (ApplyPatchTool)
    - CodeWhale diff_format.rs (unified diff generation)

Security: every path goes through ToolContext.resolve_path() before any IO.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from core.logging import get_logger

from .base import ApprovalRequirement, BaseTool, ToolCapability, ToolResult
from .context import ToolContext
from .schemas import (
    APPLY_PATCH_SCHEMA,
    DELETE_FILE_SCHEMA,
    EDIT_FILE_SCHEMA,
    READ_FILE_SCHEMA,
    WRITE_FILE_SCHEMA,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants (mirroring CodeWhale file.rs)
# ---------------------------------------------------------------------------

DEFAULT_READ_LINES = 200
HARD_MAX_READ_LINES = 500
MAX_VISIBLE_BYTES = 16 * 1024
SMALL_FILE_LINES = 200
SMALL_FILE_BYTES = 16 * 1024

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def compute_content_hash(content: str) -> str:
    """SHA-256 truncated to 16 hex chars — used as a content fingerprint."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def make_unified_diff(path: str, old: str, new: str, context: int = 3) -> str:
    """Generate a git-style unified diff string.

    Uses ``difflib.unified_diff`` with ``--- a/{path}`` / ``+++ b/{path}``
    headers and *context* lines of surrounding context.
    """
    if old == new:
        return ""
    diff = list(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=context,
        )
    )
    return "".join(diff)


def _read_text_silent(path: Path) -> str:
    """Read UTF-8 text, return empty string on any error."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# ReadFileTool
# ---------------------------------------------------------------------------


class ReadFileTool(BaseTool):
    """Read a UTF-8 file from the workspace with automatic pagination."""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read a UTF-8 file from the workspace. "
            "Small files (<=200 lines, <=16 KB) are returned as-is. "
            "Large files are paginated with line numbers. "
            "Use start_line to read a specific range."
        )

    @property
    def schema(self) -> dict[str, Any]:
        return READ_FILE_SCHEMA

    @property
    def capabilities(self) -> list[ToolCapability]:
        return [ToolCapability.READ_ONLY]

    async def execute(
        self,
        ctx: ToolContext,
        path: str,
        start_line: int = 1,
        max_lines: int = DEFAULT_READ_LINES,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            file_path = ctx.resolve_path(path)
        except Exception as e:
            return ToolResult(
                success=False, tool_name=self.name, path=path,
                error=f"Path validation failed: {e}",
            )

        # Guard: file must exist
        if not file_path.exists():
            return ToolResult(
                success=False,
                tool_name=self.name,
                path=str(file_path),
                error=f"File not found: {path}",
            )

        if not file_path.is_file():
            return ToolResult(
                success=False,
                tool_name=self.name,
                path=str(file_path),
                error=f"Not a regular file: {path}",
            )

        # Read content
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResult(
                success=False,
                tool_name=self.name,
                path=str(file_path),
                error=f"File is not valid UTF-8: {path}",
            )

        total_lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        total_bytes = len(content.encode("utf-8"))

        # Clamp max_lines
        max_lines = min(max(max_lines, 1), HARD_MAX_READ_LINES)

        # ---- small-file fast path ----------------------------------------
        if total_lines <= SMALL_FILE_LINES and total_bytes <= SMALL_FILE_BYTES:
            return ToolResult(
                success=True,
                tool_name=self.name,
                path=str(file_path),
                output=content,
                metadata={
                    "total_lines": total_lines,
                    "shown_lines": total_lines,
                    "truncated": False,
                },
            )

        # ---- large-file pagination ---------------------------------------
        lines = content.splitlines()
        zero_start = start_line - 1

        if start_line > total_lines:
            return ToolResult(
                success=True,
                tool_name=self.name,
                path=str(file_path),
                output=f"[NO CONTENT] start_line {start_line} beyond total_lines {total_lines}",
                metadata={
                    "total_lines": total_lines,
                    "shown_lines": 0,
                    "truncated": False,
                },
            )

        zero_end = min(zero_start + max_lines, total_lines)
        shown_count = zero_end - zero_start

        # Numbered lines
        numbered_lines: list[str] = []
        for i, line in enumerate(lines[zero_start:zero_end], start=start_line):
            numbered_lines.append(f"{i:>6}| {line}")
        body = "\n".join(numbered_lines)

        truncated = zero_end < total_lines
        meta: dict[str, Any] = {
            "total_lines": total_lines,
            "shown_lines": shown_count,
            "truncated": truncated,
        }
        if truncated:
            meta["next_start_line"] = zero_end + 1

        # Build XML-like wrapper
        rel_path = ctx.get_relative_path(file_path)
        output = (
            f'<file path="{rel_path}" total_lines="{total_lines}" '
            f'shown_lines="{start_line}-{zero_end}" truncated="{truncated}">\n'
            f"{body}\n"
            f"</file>"
        )
        if truncated:
            output += (
                f"\n[TRUNCATED] Showing lines {start_line}-{zero_end} of {total_lines}. "
                f'To continue, call read_file with path="{rel_path}" '
                f"start_line={zero_end + 1} max_lines={max_lines}"
            )

        return ToolResult(
            success=True,
            tool_name=self.name,
            path=str(file_path),
            output=output,
            metadata=meta,
        )


# ---------------------------------------------------------------------------
# WriteFileTool
# ---------------------------------------------------------------------------


class WriteFileTool(BaseTool):
    """Write (create or overwrite) a UTF-8 file in the workspace."""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Write content to a UTF-8 file in the workspace. "
            "Creates parent directories automatically. "
            "Overwrites existing files. Returns a unified diff preview."
        )

    @property
    def schema(self) -> dict[str, Any]:
        return WRITE_FILE_SCHEMA

    @property
    def capabilities(self) -> list[ToolCapability]:
        return [ToolCapability.WRITES_FILES, ToolCapability.REQUIRES_APPROVAL]

    async def execute(
        self,
        ctx: ToolContext,
        path: str,
        content: str,
        **kwargs: Any,
    ) -> ToolResult:
        file_path = ctx.resolve_path(path)

        # 1. Snapshot old content for diff
        existed_before = file_path.exists()
        prior_contents = _read_text_silent(file_path) if existed_before else ""
        old_hash = compute_content_hash(prior_contents) if existed_before else ""

        # 2. Auto-create parent directories
        if file_path.parent:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        # 3. Write
        try:
            file_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(
                success=False,
                tool_name=self.name,
                path=str(file_path),
                error=f"Failed to write {path}: {exc}",
            )

        # 4. Diff
        new_hash = compute_content_hash(content)
        diff = make_unified_diff(path, prior_contents, content)

        rel_path = ctx.get_relative_path(file_path)
        summary = (
            f"Created {rel_path} ({len(content)} bytes)"
            if not existed_before
            else f"Wrote {len(content)} bytes to {rel_path}"
        )

        return ToolResult(
            success=True,
            tool_name=self.name,
            path=str(file_path),
            output=f"{diff}\n{summary}" if diff else summary,
            diff=diff or None,
            files_changed=[str(file_path)],
            metadata={
                "existed_before": existed_before,
                "old_content_hash": old_hash,
                "new_content_hash": new_hash,
                "bytes_written": len(content.encode("utf-8")),
            },
        )


# ---------------------------------------------------------------------------
# EditFileTool
# ---------------------------------------------------------------------------


class EditFileTool(BaseTool):
    """Precise search/replace edit of a single file.

    * Strict literal matching — **no regex**.
    * old_text == new_text → rejected immediately.
    * 0 matches → error (ask model to refine search text).
    * >1 matches → error (ask model to use a more unique snippet).
    * Exactly 1 match → replace, return unified diff.
    """

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "Make a precise edit to a file. Provide the exact old_text to search "
            "and the new_text to replace it with. The search must match exactly ONE "
            "location; zero or multiple matches will be rejected. Returns a unified diff."
        )

    @property
    def schema(self) -> dict[str, Any]:
        return EDIT_FILE_SCHEMA

    @property
    def capabilities(self) -> list[ToolCapability]:
        return [ToolCapability.WRITES_FILES, ToolCapability.REQUIRES_APPROVAL]

    async def execute(
        self,
        ctx: ToolContext,
        path: str,
        old_text: str,
        new_text: str,
        **kwargs: Any,
    ) -> ToolResult:
        # 1. old == new guard
        if old_text == new_text:
            return ToolResult(
                success=False,
                tool_name=self.name,
                path=path,
                error="old_text and new_text are identical — no change intended.",
            )

        try:
            file_path = ctx.resolve_path(path)
        except Exception as e:
            return ToolResult(
                success=False, tool_name=self.name, path=path,
                error=f"Path validation failed: {e}",
            )

        if not file_path.exists():
            return ToolResult(
                success=False,
                tool_name=self.name,
                path=str(file_path),
                error=f"File not found: {path}",
            )

        # 2. Read original
        try:
            original = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            return ToolResult(
                success=False,
                tool_name=self.name,
                path=str(file_path),
                error=f"Cannot read file: {exc}",
            )

        # 3. Strict match count
        count = original.count(old_text)

        if count == 0:
            return ToolResult(
                success=False,
                tool_name=self.name,
                path=str(file_path),
                error=(
                    f"Search text not found in {path}. "
                    f"Provide a longer, unique snippet that exists exactly once in the file."
                ),
            )

        if count > 1:
            return ToolResult(
                success=False,
                tool_name=self.name,
                path=str(file_path),
                error=(
                    f"Search text matched {count} locations in {path}. "
                    f"Use a more specific (longer) snippet that appears only once."
                ),
            )

        # 4. Replace (exactly once)
        updated = original.replace(old_text, new_text, 1)

        # 5. Write
        try:
            file_path.write_text(updated, encoding="utf-8")
        except OSError as exc:
            return ToolResult(
                success=False,
                tool_name=self.name,
                path=str(file_path),
                error=f"Failed to write {path}: {exc}",
            )

        # 6. Diff
        rel_path = ctx.get_relative_path(file_path)
        diff = make_unified_diff(rel_path, original, updated)

        return ToolResult(
            success=True,
            tool_name=self.name,
            path=str(file_path),
            output=f"{diff}\nReplaced 1 occurrence in {rel_path}",
            diff=diff or None,
            files_changed=[str(file_path)],
            metadata={
                "replacements": 1,
                "old_content_hash": compute_content_hash(original),
                "new_content_hash": compute_content_hash(updated),
            },
        )


# ---------------------------------------------------------------------------
# ApplyPatchTool — unified diff parser + transactional application
# ---------------------------------------------------------------------------


class _Hunk:
    """Represents a single hunk within a patch."""

    def __init__(self) -> None:
        self.old_start: int = 0
        self.old_count: int = 0
        self.new_start: int = 0
        self.new_count: int = 0
        self.lines: list[str] = []  # raw diff lines including prefixes


class _FilePatch:
    """Represents all hunks for a single file."""

    def __init__(self, old_path: str, new_path: str) -> None:
        self.old_path = old_path
        self.new_path = new_path
        self.hunks: list[_Hunk] = []


class ApplyPatchTool(BaseTool):
    """Apply a unified diff patch string to one or more files.

    Supports multi-file patches (---/+++ headers) and multi-hunk patches.
    All writes are **transactional**: if any hunk fails, all prior changes
    in this patch are rolled back.
    """

    @property
    def name(self) -> str:
        return "apply_patch"

    @property
    def description(self) -> str:
        return (
            "Apply a unified diff patch string. Supports multiple files and "
            "multiple hunks per file. All changes are applied atomically — "
            "if any part fails, everything is rolled back."
        )

    @property
    def schema(self) -> dict[str, Any]:
        return APPLY_PATCH_SCHEMA

    @property
    def capabilities(self) -> list[ToolCapability]:
        return [ToolCapability.WRITES_FILES, ToolCapability.REQUIRES_APPROVAL]

    # ---- public execute ---------------------------------------------------

    async def execute(
        self,
        ctx: ToolContext,
        patch: str,
        **kwargs: Any,
    ) -> ToolResult:
        # 1. Parse the patch into structured hunks
        try:
            file_patches = self._parse_patch(patch)
        except ValueError as exc:
            return ToolResult(
                success=False,
                tool_name=self.name,
                error=f"Failed to parse patch: {exc}",
            )

        if not file_patches:
            return ToolResult(
                success=False,
                tool_name=self.name,
                error="No valid file patches found in the diff string.",
            )

        # 2. Resolve target paths and load originals (for rollback + diff)
        pending: list[dict[str, Any]] = []  # [{path, original, new_content}, ...]

        for fp in file_patches:
            # Determine target path
            target_path = self._resolve_target_path(ctx, fp.old_path, fp.new_path)

            # Load original (empty string if new file)
            original = _read_text_silent(target_path) if target_path.exists() else ""

            # Apply hunks to produce new content
            try:
                new_content = self._apply_hunks_to_file(original, fp.hunks)
            except ValueError as exc:
                return ToolResult(
                    success=False,
                    tool_name=self.name,
                    path=str(target_path),
                    error=f"Failed to apply patch to {fp.new_path}: {exc}",
                )

            pending.append({
                "path": target_path,
                "original": original,
                "new_content": new_content,
                "hunks": len(fp.hunks),
            })

        # 3. Transactional write with rollback
        applied: list[dict[str, Any]] = []
        try:
            for entry in pending:
                target: Path = entry["path"]
                new_content: str = entry["new_content"]

                # Ensure parent directories exist
                if target.parent:
                    target.parent.mkdir(parents=True, exist_ok=True)

                target.write_text(new_content, encoding="utf-8")
                applied.append(entry)
        except OSError as exc:
            # ---- ROLLBACK ----
            self._rollback(applied)
            return ToolResult(
                success=False,
                tool_name=self.name,
                error=f"Write failed mid-patch — rolled back. Cause: {exc}",
            )

        # 4. Build unified diff for all changed files
        diffs: list[str] = []
        files_changed: list[str] = []
        total_hunks = sum(e["hunks"] for e in applied)

        for entry in applied:
            target = entry["path"]
            rel = ctx.get_relative_path(target)
            diff = make_unified_diff(rel, entry["original"], entry["new_content"])
            if diff:
                diffs.append(diff)
            files_changed.append(str(target))

        return ToolResult(
            success=True,
            tool_name=self.name,
            output=(
                f"Applied patch to {len(applied)} file(s), {total_hunks} hunk(s).\n"
                f"{'\n'.join(diffs)}"
            ),
            diff="\n".join(diffs) if diffs else None,
            files_changed=files_changed,
            metadata={
                "files_applied": len(applied),
                "hunks_applied": total_hunks,
                "hunks_total": total_hunks,
            },
        )

    # ---- patch parser -----------------------------------------------------

    @staticmethod
    def _parse_patch(patch_text: str) -> list[_FilePatch]:
        """Parse a unified diff string into a list of ``_FilePatch`` objects."""
        lines = patch_text.splitlines(keepends=False)
        file_patches: list[_FilePatch] = []
        current_fp: Optional[_FilePatch] = None
        current_hunk: Optional[_Hunk] = None
        i = 0

        while i < len(lines):
            line = lines[i]

            # New file header: --- a/foo
            if line.startswith("--- "):
                old_path = line[4:].split("\t")[0].strip()
                # Look ahead for +++
                if i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
                    new_path = lines[i + 1][4:].split("\t")[0].strip()
                    i += 1
                else:
                    new_path = old_path

                current_fp = _FilePatch(old_path, new_path)
                file_patches.append(current_fp)
                current_hunk = None
                i += 1
                continue

            # Hunk header: @@ -old_start,old_count +new_start,new_count @@
            if line.startswith("@@") and current_fp is not None:
                m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
                if m:
                    h = _Hunk()
                    h.old_start = int(m.group(1))
                    h.old_count = int(m.group(2)) if m.group(2) else 1
                    h.new_start = int(m.group(3))
                    h.new_count = int(m.group(4)) if m.group(4) else 1
                    current_fp.hunks.append(h)
                    current_hunk = h
                i += 1
                continue

            # Hunk body lines
            if current_hunk is not None and (
                line.startswith(" ") or line.startswith("-") or line.startswith("+") or line.startswith("\\")
            ):
                current_hunk.lines.append(line)
                i += 1
                continue

            # Git 'diff --git' line — skip
            if line.startswith("diff --git"):
                i += 1
                continue

            # Index / mode lines — skip
            if line.startswith("index ") or line.startswith("mode ") or line.startswith("new file mode"):
                i += 1
                continue

            # Binary patch marker — not supported
            if "Binary files" in line:
                i += 1
                continue

            i += 1

        return file_patches

    # ---- hunk applier -----------------------------------------------------

    @staticmethod
    def _apply_hunks_to_file(original: str, hunks: list[_Hunk]) -> str:
        """Apply parsed hunks to *original* content.

        Uses a simple line-based splice algorithm with cumulative offset tracking.
        """
        lines = original.splitlines(keepends=False) if original else []
        cumulative_offset = 0

        for hunk in hunks:
            # Extract old and new lines from the hunk
            old_lines: list[str] = []
            new_lines: list[str] = []
            for hl in hunk.lines:
                if hl.startswith(" "):
                    old_lines.append(hl[1:])
                    new_lines.append(hl[1:])
                elif hl.startswith("-"):
                    old_lines.append(hl[1:])
                elif hl.startswith("+"):
                    new_lines.append(hl[1:])
                elif hl.startswith("\\"):
                    # "\ No newline at end of file" — skip metadata line
                    continue

            # Calculate position in the current (possibly already modified) content
            # The hunk's old_start is 1-based in the ORIGINAL file.
            pos = (hunk.old_start - 1) + cumulative_offset

            # Verify context lines match
            context_before = [l for l in hunk.lines if l.startswith(" ")]
            if pos < 0 or pos > len(lines):
                raise ValueError(
                    f"Hunk at line {hunk.old_start} out of range (file has {len(lines)} lines)"
                )

            # Find the actual position by matching the first old/context line
            if old_lines:
                # Try exact position first
                match_found = False
                for attempt in range(max(0, pos - 3), min(len(lines), pos + 4)):
                    # Check if the sequence of old_lines matches at this position
                    end_attempt = attempt + len(old_lines)
                    if end_attempt <= len(lines) and lines[attempt:end_attempt] == old_lines:
                        pos = attempt
                        match_found = True
                        break

                if not match_found:
                    # Fallback: try to find by context lines
                    if context_before:
                        first_context = context_before[0][1:]
                        for try_pos in range(len(lines)):
                            if lines[try_pos] == first_context:
                                # Verify full context
                                match = True
                                for ci, cl in enumerate(context_before):
                                    if try_pos + ci >= len(lines) or lines[try_pos + ci] != cl[1:]:
                                        match = False
                                        break
                                if match:
                                    pos = try_pos
                                    match_found = True
                                    break

                    if not match_found:
                        raise ValueError(
                            f"Could not find hunk context at line {hunk.old_start}"
                        )

            # Remove old lines and insert new lines
            old_len = len(old_lines)
            new_len = len(new_lines)

            if pos + old_len > len(lines):
                # If at end of file, just extend
                lines[pos:] = new_lines
            else:
                lines[pos : pos + old_len] = new_lines

            cumulative_offset += new_len - old_len

        return "\n".join(lines)

    # ---- rollback ---------------------------------------------------------

    @staticmethod
    def _rollback(applied: list[dict[str, Any]]) -> None:
        """Rollback all applied changes in reverse order.

        Restores original content for modified files, removes newly-created files.
        """
        for entry in reversed(applied):
            target: Path = entry["path"]
            original: str = entry["original"]
            if original:
                try:
                    target.write_text(original, encoding="utf-8")
                except OSError:
                    logger.warning("Rollback: failed to restore %s", target)
            else:
                # New file — remove it
                try:
                    target.unlink()
                except OSError:
                    logger.warning("Rollback: failed to remove %s", target)

    # ---- path helpers -----------------------------------------------------

    @staticmethod
    def _resolve_target_path(ctx: ToolContext, old_path: str, new_path: str) -> Path:
        """Determine which file to edit from ---/+++ headers.

        /dev/null on the --- side → create new file (use +++).
        /dev/null on the +++ side → delete file (use ---).
        Otherwise use +++ path.
        """
        # Strip 'a/' and 'b/' prefixes if present
        clean_old = old_path
        if clean_old.startswith("a/"):
            clean_old = clean_old[2:]
        if clean_old == "/dev/null":
            clean_old = ""

        clean_new = new_path
        if clean_new.startswith("b/"):
            clean_new = clean_new[2:]
        if clean_new == "/dev/null":
            clean_new = ""

        target = clean_new or clean_old
        if not target:
            raise ValueError(f"Cannot resolve target path from --- {old_path} +++ {new_path}")

        return ctx.resolve_path(target)


# ---------------------------------------------------------------------------
# DeleteFileTool
# ---------------------------------------------------------------------------


class DeleteFileTool(BaseTool):
    """Delete a file from the workspace.

    *Cannot* delete the workspace root itself, nor the ``.workspace/`` system directory.
    Approval level: ``REQUIRED`` (destructive and irreversible).
    """

    @property
    def name(self) -> str:
        return "delete_file"

    @property
    def description(self) -> str:
        return (
            "Delete a file in the workspace. "
            "Cannot delete the workspace root or the .workspace/ system directory. "
            "Returns metadata including the file's content hash for potential recovery."
        )

    @property
    def schema(self) -> dict[str, Any]:
        return DELETE_FILE_SCHEMA

    @property
    def capabilities(self) -> list[ToolCapability]:
        return [ToolCapability.WRITES_FILES, ToolCapability.REQUIRES_APPROVAL]

    @property
    def approval_requirement(self) -> ApprovalRequirement:
        return ApprovalRequirement.REQUIRED

    async def execute(
        self,
        ctx: ToolContext,
        path: str,
        **kwargs: Any,
    ) -> ToolResult:
        file_path = ctx.resolve_path(path)

        # 1. Existence check
        if not file_path.exists():
            return ToolResult(
                success=False,
                tool_name=self.name,
                path=str(file_path),
                error=f"File not found: {path}",
            )

        # 2. Protect workspace root (BEFORE is_file check, since '.' resolves to dir)
        if file_path == ctx.workspace_root:
            return ToolResult(
                success=False,
                tool_name=self.name,
                path=str(file_path),
                error="Cannot delete the workspace root directory.",
            )

        # 3. Protect .workspace/ system directory
        rel = ctx.get_relative_path(file_path)
        if rel == ".workspace" or rel.startswith(".workspace/"):
            return ToolResult(
                success=False,
                tool_name=self.name,
                path=str(file_path),
                error="Cannot delete files in the .workspace/ system directory.",
            )

        # 4. Must be a regular file (not a directory)
        if not file_path.is_file():
            return ToolResult(
                success=False,
                tool_name=self.name,
                path=str(file_path),
                error=f"Not a regular file (cannot delete directories): {path}",
            )

        # 5. Snapshot metadata before deletion
        content = _read_text_silent(file_path)
        file_hash = compute_content_hash(content) if content else ""

        # 6. Delete
        try:
            file_path.unlink()
        except OSError as exc:
            return ToolResult(
                success=False,
                tool_name=self.name,
                path=str(file_path),
                error=f"Failed to delete {path}: {exc}",
            )

        return ToolResult(
            success=True,
            tool_name=self.name,
            path=str(file_path),
            output=f"Deleted {rel}",
            metadata={
                "deleted": True,
                "file_hash": file_hash,
                "bytes": len(content.encode("utf-8")) if content else 0,
            },
        )
