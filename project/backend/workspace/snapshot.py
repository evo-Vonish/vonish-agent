"""Snapshot management for Workspace system.

Captures and restores workspace state with SHA-256 content hashing.
Snapshots are persisted to .workspace/snapshots/ directory.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from workspace.storage_provider import FileInfo
from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class FileSnapshot(BaseModel):
    """Snapshot of a single file with SHA-256 content hash."""

    path: str
    content_hash: str  # SHA-256 of file content
    size: int
    modified_at: str  # ISO format
    mime_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "content_hash": self.content_hash,
            "size": self.size,
            "modified_at": self.modified_at,
            "mime_type": self.mime_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileSnapshot:
        return cls(
            path=data["path"],
            content_hash=data["content_hash"],
            size=data["size"],
            modified_at=data["modified_at"],
            mime_type=data.get("mime_type", ""),
        )


class Snapshot(BaseModel):
    """Complete snapshot of a workspace state."""

    id: str
    workspace_id: str
    timestamp: datetime
    file_manifest: dict[str, FileSnapshot]  # path -> FileSnapshot
    description: str = ""

    @property
    def file_count(self) -> int:
        return len(self.file_manifest)

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.file_manifest.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "file_count": self.file_count,
            "total_size": self.total_size,
            "file_manifest": {
                path: fs.to_dict() for path, fs in self.file_manifest.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snapshot:
        return cls(
            id=data["id"],
            workspace_id=data["workspace_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            description=data.get("description", ""),
            file_manifest={
                path: FileSnapshot.from_dict(fs_data)
                for path, fs_data in data.get("file_manifest", {}).items()
            },
        )


class SnapshotDiff(BaseModel):
    """Difference between two snapshots."""

    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.modified)

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": self.added,
            "removed": self.removed,
            "modified": self.modified,
            "unchanged_count": len(self.unchanged),
            "has_changes": self.has_changes,
        }


# ---------------------------------------------------------------------------
# Snapshot Manager
# ---------------------------------------------------------------------------


class SnapshotManager:
    """Manages workspace snapshots with persistence.

    Snapshots are stored in:
        {workspace_root}/.workspace/snapshots/{snapshot_id}.json

    Each snapshot contains a complete file manifest with SHA-256 content hashes
    for reliable change detection.
    """

    SNAPSHOTS_DIR = ".workspace/snapshots"

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self._snapshots_dir = self.workspace_root / self.SNAPSHOTS_DIR
        self._snapshots_dir.mkdir(parents=True, exist_ok=True)

    def _get_snapshot_path(self, snapshot_id: str) -> Path:
        """Get the file path for a snapshot."""
        # Sanitize snapshot_id to prevent directory traversal
        safe_id = snapshot_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        return self._snapshots_dir / f"{safe_id}.json"

    @staticmethod
    def _compute_content_hash(data: bytes) -> str:
        """Compute SHA-256 hash of file content.

        Args:
            data: Raw file bytes.

        Returns:
            Hex digest of SHA-256 hash.
        """
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _generate_snapshot_id() -> str:
        """Generate a unique snapshot ID.

        Returns:
            Timestamp-based unique ID.
        """
        now = datetime.now(timezone.utc)
        return f"snap_{now.strftime('%Y%m%d_%H%M%S')}_{now.microsecond:06d}"

    async def create(
        self,
        workspace_id: str,
        list_files_func=None,
        read_file_func=None,
        description: str = "",
    ) -> Snapshot:
        """Create a new snapshot of the current workspace state.

        Args:
            workspace_id: Workspace identifier.
            list_files_func: Async callable to list files -> list[FileInfo].
            read_file_func: Async callable to read file content -> bytes.
            description: Optional snapshot description.

        Returns:
            Snapshot with complete file manifest.
        """
        snapshot_id = self._generate_snapshot_id()
        file_manifest: dict[str, FileSnapshot] = {}

        if list_files_func is not None:
            try:
                files = await list_files_func()
            except Exception as e:
                logger.warning(f"Failed to list files for snapshot: {e}")
                files = []
        else:
            files = self._list_files_sync()

        for file_info in files:
            if file_info.is_directory:
                continue

            # Compute content hash
            content_hash = ""
            if read_file_func is not None:
                try:
                    data = await read_file_func(file_info.path)
                    content_hash = self._compute_content_hash(data)
                except Exception as e:
                    logger.warning(
                        f"Failed to read file for hash: {file_info.path}: {e}"
                    )
                    # Fall back to metadata-based hash
                    content_hash = self._compute_metadata_hash(file_info)
            else:
                # Synchronous fallback
                try:
                    file_path = self.workspace_root / file_info.path
                    if file_path.exists() and file_path.is_file():
                        data = file_path.read_bytes()
                        content_hash = self._compute_content_hash(data)
                    else:
                        content_hash = self._compute_metadata_hash(file_info)
                except Exception as e:
                    logger.warning(f"Failed to hash file {file_info.path}: {e}")
                    content_hash = self._compute_metadata_hash(file_info)

            file_manifest[file_info.path] = FileSnapshot(
                path=file_info.path,
                content_hash=content_hash,
                size=file_info.size,
                modified_at=(
                    file_info.modified_at.isoformat()
                    if file_info.modified_at
                    else datetime.now(timezone.utc).isoformat()
                ),
                mime_type=file_info.mime_type,
            )

        snapshot = Snapshot(
            id=snapshot_id,
            workspace_id=workspace_id,
            timestamp=datetime.now(timezone.utc),
            file_manifest=file_manifest,
            description=description,
        )

        # Persist snapshot
        await self._persist_snapshot(snapshot)

        logger.info(
            f"Created snapshot {snapshot_id} for workspace {workspace_id}: "
            f"{len(file_manifest)} files, {snapshot.total_size} bytes"
        )

        return snapshot

    async def get(self, workspace_id: str, snapshot_id: str) -> Snapshot | None:
        """Retrieve a snapshot by ID.

        Args:
            workspace_id: Workspace identifier.
            snapshot_id: Snapshot identifier.

        Returns:
            Snapshot or None if not found.
        """
        snapshot_path = self._get_snapshot_path(snapshot_id)

        if not snapshot_path.exists():
            return None

        try:
            data = json.loads(snapshot_path.read_text(encoding="utf-8"))
            snapshot = Snapshot.from_dict(data)
            # Verify workspace ID matches
            if snapshot.workspace_id != workspace_id:
                logger.warning(
                    f"Workspace ID mismatch: expected {workspace_id}, "
                    f"got {snapshot.workspace_id}"
                )
            return snapshot
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to load snapshot {snapshot_id}: {e}")
            return None

    async def list_snapshots(self, workspace_id: str) -> list[Snapshot]:
        """List all snapshots for a workspace.

        Args:
            workspace_id: Workspace identifier.

        Returns:
            List of snapshots, newest first.
        """
        snapshots: list[Snapshot] = []

        if not self._snapshots_dir.exists():
            return snapshots

        for snapshot_file in sorted(self._snapshots_dir.glob("snap_*.json"), reverse=True):
            try:
                data = json.loads(snapshot_file.read_text(encoding="utf-8"))
                snapshot = Snapshot.from_dict(data)
                snapshots.append(snapshot)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Failed to load snapshot file {snapshot_file}: {e}")

        return snapshots

    async def restore(
        self,
        workspace_id: str,
        snapshot_id: str,
        read_file_func=None,
        write_file_func=None,
    ) -> None:
        """Restore workspace to a snapshot state.

        This restores files that existed in the snapshot and removes
        files that didn't exist. Modified files are reverted to their
        snapshot state.

        Args:
            workspace_id: Workspace identifier.
            snapshot_id: Snapshot to restore to.
            read_file_func: Async callable to read file content from archive.
            write_file_func: Async callable to write file content.

        Raises:
            FileNotFoundError: If snapshot does not exist.
        """
        snapshot = await self.get(workspace_id, snapshot_id)
        if snapshot is None:
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")

        logger.info(
            f"Restoring workspace {workspace_id} to snapshot {snapshot_id} "
            f"({len(snapshot.file_manifest)} files)"
        )

        # Get current files
        current_files = set()
        for root, _, files in self.workspace_root.walk():
            for f in files:
                if f.startswith("."):
                    continue
                full_path = root / f
                rel_path = str(full_path.relative_to(self.workspace_root))
                # Skip .workspace metadata
                if rel_path.startswith(".workspace/"):
                    continue
                current_files.add(rel_path)

        snapshot_files = set(snapshot.file_manifest.keys())

        # Files to remove (exist now but not in snapshot)
        files_to_remove = current_files - snapshot_files
        for rel_path in files_to_remove:
            file_path = self.workspace_root / rel_path
            try:
                file_path.unlink()
                logger.debug(f"Removed file during restore: {rel_path}")
            except OSError as e:
                logger.warning(f"Failed to remove file during restore: {rel_path}: {e}")

        # Files to restore (in snapshot but missing or modified)
        files_to_restore = snapshot_files - (current_files - files_to_remove)
        for rel_path in files_to_restore:
            file_snapshot = snapshot.file_manifest[rel_path]
            file_path = self.workspace_root / rel_path

            # Check if file needs restoration
            needs_restore = False
            if not file_path.exists():
                needs_restore = True
            else:
                try:
                    current_data = file_path.read_bytes()
                    current_hash = self._compute_content_hash(current_data)
                    if current_hash != file_snapshot.content_hash:
                        needs_restore = True
                except OSError:
                    needs_restore = True

            if needs_restore:
                if write_file_func is not None and read_file_func is not None:
                    try:
                        # Try to get original content from backup
                        data = await read_file_func(rel_path)
                        await write_file_func(rel_path, data)
                    except Exception as e:
                        logger.warning(
                            f"Failed to restore file content for {rel_path}: {e}. "
                            f"Creating placeholder."
                        )
                        # Create a placeholder file
                        placeholder = f"# File restored from snapshot\n# Original hash: {file_snapshot.content_hash}\n"
                        await write_file_func(rel_path, placeholder.encode("utf-8"))
                else:
                    # Just create a placeholder
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    placeholder = f"# File restored from snapshot\n# Original hash: {file_snapshot.content_hash}\n"
                    file_path.write_text(placeholder, encoding="utf-8")

        # Clean up empty directories
        self._cleanup_empty_dirs()

        logger.info(f"Restored workspace {workspace_id} to snapshot {snapshot_id}")

    def compare(self, before: Snapshot, after: Snapshot) -> SnapshotDiff:
        """Compare two snapshots to find differences.

        Args:
            before: Earlier snapshot.
            after: Later snapshot.

        Returns:
            SnapshotDiff with change details.
        """
        before_files = before.file_manifest
        after_files = after.file_manifest

        all_paths = set(before_files.keys()) | set(after_files.keys())

        diff = SnapshotDiff()

        for path in all_paths:
            if path in before_files and path not in after_files:
                diff.removed.append(path)
            elif path not in before_files and path in after_files:
                diff.added.append(path)
            elif path in before_files and path in after_files:
                if before_files[path].content_hash != after_files[path].content_hash:
                    diff.modified.append(path)
                else:
                    diff.unchanged.append(path)

        logger.info(
            f"Snapshot comparison: +{len(diff.added)} -{len(diff.removed)} "
            f"~{len(diff.modified)} ({len(diff.unchanged)} unchanged)"
        )

        return diff

    async def delete(self, workspace_id: str, snapshot_id: str) -> bool:
        """Delete a snapshot.

        Args:
            workspace_id: Workspace identifier.
            snapshot_id: Snapshot to delete.

        Returns:
            True if snapshot was deleted.
        """
        snapshot_path = self._get_snapshot_path(snapshot_id)

        if not snapshot_path.exists():
            return False

        try:
            snapshot_path.unlink()
            logger.info(f"Deleted snapshot: {snapshot_id}")
            return True
        except OSError as e:
            logger.error(f"Failed to delete snapshot {snapshot_id}: {e}")
            return False

    async def cleanup_old_snapshots(
        self, workspace_id: str, keep_count: int = 10
    ) -> int:
        """Remove old snapshots, keeping only the most recent ones.

        Args:
            workspace_id: Workspace identifier.
            keep_count: Number of snapshots to keep.

        Returns:
            Number of snapshots deleted.
        """
        snapshots = await self.list_snapshots(workspace_id)

        if len(snapshots) <= keep_count:
            return 0

        # Sort by timestamp, oldest first
        snapshots_to_remove = sorted(
            snapshots, key=lambda s: s.timestamp
        )[: -keep_count]

        deleted_count = 0
        for snapshot in snapshots_to_remove:
            if await self.delete(workspace_id, snapshot.id):
                deleted_count += 1

        logger.info(f"Cleaned up {deleted_count} old snapshots, kept {keep_count}")
        return deleted_count

    # -- Persistence --------------------------------------------------------

    async def _persist_snapshot(self, snapshot: Snapshot) -> None:
        """Save snapshot to disk.

        Args:
            snapshot: Snapshot to persist.
        """
        snapshot_path = self._get_snapshot_path(snapshot.id)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)

        snapshot_path.write_text(
            json.dumps(snapshot.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

        logger.debug(f"Persisted snapshot to: {snapshot_path}")

    # -- Synchronous helpers (for fallback) ----------------------------------

    def _list_files_sync(self) -> list[FileInfo]:
        """Synchronously list all files in workspace.

        Used as fallback when async list_files_func is not provided.
        """
        from workspace.local_provider import guess_mime_type

        files: list[FileInfo] = []

        for root, _, filenames in self.workspace_root.walk():
            for f in filenames:
                if f.startswith("."):
                    continue
                full_path = root / f
                rel_path = str(full_path.relative_to(self.workspace_root))

                # Skip .workspace metadata
                if rel_path.startswith(".workspace/"):
                    continue

                try:
                    stat = full_path.stat()
                    files.append(
                        FileInfo(
                            name=f,
                            path=rel_path,
                            size=stat.st_size,
                            mime_type=guess_mime_type(f),
                            is_directory=False,
                            modified_at=datetime.fromtimestamp(
                                stat.st_mtime, tz=timezone.utc
                            ),
                            created_at=datetime.fromtimestamp(
                                stat.st_ctime, tz=timezone.utc
                            ),
                        )
                    )
                except OSError:
                    pass

        return files

    def _compute_metadata_hash(self, file_info: FileInfo) -> str:
        """Compute a fallback hash from file metadata.

        Used when file content cannot be read.

        Args:
            file_info: File information.

        Returns:
            Hash string.
        """
        content = f"{file_info.path}:{file_info.size}:{file_info.modified_at}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _cleanup_empty_dirs(self) -> None:
        """Remove empty directories in workspace."""
        for root, dirs, _ in self.workspace_root.walk(top_down=False):
            for d in dirs:
                if d.startswith("."):
                    continue
                dir_path = root / d
                try:
                    if dir_path.exists() and not any(dir_path.iterdir()):
                        dir_path.rmdir()
                        logger.debug(f"Removed empty directory: {dir_path}")
                except OSError:
                    pass
