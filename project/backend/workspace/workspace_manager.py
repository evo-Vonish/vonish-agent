"""Workspace Manager for the Agent system.

Manages per-conversation workspace directories with:
- Full CRUD file operations
- Dual-storage mode (Server + Local)
- Session isolation via PathSandbox
- Snapshot creation/restoration
- Diff generation
- File indexing for fast search
"""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspace.diff import DiffGenerator, WorkspaceDiff
from workspace.indexer import WorkspaceIndexer
from workspace.local_provider import LocalStorageProvider
from workspace.permissions import PathSandbox, SecurityError
from workspace.server_provider import ServerStorageProvider
from workspace.snapshot import Snapshot, SnapshotManager
from workspace.storage_provider import FileInfo, StorageProvider, StorageStats
from core.config import settings
from core.errors import WorkspaceError
from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
READ_TIMEOUT = 30.0  # seconds

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class Workspace(BaseModel):
    """Workspace metadata."""

    id: str
    conversation_id: str
    user_id: str
    root_path: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "root_path": self.root_path,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Workspace Storage (Dual Storage)
# ---------------------------------------------------------------------------


class WorkspaceStorage:
    """Dual-storage wrapper combining Server and Local providers.

    Default mode is dual-write: writes go to both Server and Local,
    reads prefer Local with fallback to Server (and backfill).
    """

    def __init__(
        self,
        workspace_path: Path,
        server_root: str | Path | None = None,
    ) -> None:
        self.workspace_path = workspace_path
        self.local_provider = LocalStorageProvider(workspace_path)
        self.server_provider = ServerStorageProvider(
            server_root=server_root or f"{workspace_path}_server",
            workspace_id=str(workspace_path.name),
        )
        self._sandbox = PathSandbox(workspace_path)

    async def read_file(self, path: str) -> bytes:
        """Read a file, preferring Local with Server fallback.

        Args:
            path: Relative path within workspace.

        Returns:
            File contents as bytes.

        Raises:
            FileNotFoundError: If file not found in either storage.
            SecurityError: If path is invalid.
            TimeoutError: If read exceeds timeout.
        """
        # Validate path
        self._sandbox.validate_path(path)

        # Try Local first
        try:
            data = await asyncio.wait_for(
                self.local_provider.read_file(path),
                timeout=READ_TIMEOUT,
            )
            logger.debug(f"Read from local: {path}")
            return data
        except (FileNotFoundError, TimeoutError):
            pass

        # Fallback to Server
        data = await asyncio.wait_for(
            self.server_provider.read_file(path),
            timeout=READ_TIMEOUT,
        )

        # Backfill to Local for future reads
        try:
            await self.local_provider.write_file(path, data)
            logger.debug(f"Backfilled local from server: {path}")
        except Exception as e:
            logger.warning(f"Failed to backfill local cache: {e}")

        return data

    async def write_file(self, path: str, data: bytes) -> None:
        """Write a file to both Local and Server storage.

        Args:
            path: Relative path within workspace.
            data: File contents as bytes.

        Raises:
            SecurityError: If path is invalid.
            ValueError: If file exceeds size limit.
        """
        # Check file size
        if len(data) > MAX_FILE_SIZE:
            raise ValueError(
                f"File size {len(data)} exceeds maximum of {MAX_FILE_SIZE} bytes"
            )

        # Validate path
        self._sandbox.validate_create_path(path)

        # Write to both storages (server first, then local)
        errors: list[str] = []

        try:
            await self.server_provider.write_file(path, data)
        except Exception as e:
            errors.append(f"Server write failed: {e}")

        try:
            await self.local_provider.write_file(path, data)
        except Exception as e:
            errors.append(f"Local write failed: {e}")

        if len(errors) == 2:
            raise WorkspaceError(
                detail=f"Failed to write to both storages: {'; '.join(errors)}",
                error_code="DUAL_WRITE_ERROR",
                path=path,
            )

        if errors:
            logger.warning(f"Partial dual-write success for {path}: {'; '.join(errors)}")

    async def delete_file(self, path: str) -> None:
        """Delete a file from both Local and Server storage.

        Args:
            path: Relative path within workspace.

        Raises:
            FileNotFoundError: If file not found.
            SecurityError: If path is invalid.
        """
        self._sandbox.validate_path(path)

        # Delete from both (ignore errors from the one that might not have it)
        errors: list[str] = []

        try:
            await self.local_provider.delete_file(path)
        except FileNotFoundError:
            pass
        except Exception as e:
            errors.append(f"Local delete failed: {e}")

        try:
            await self.server_provider.delete_file(path)
        except FileNotFoundError:
            pass
        except Exception as e:
            errors.append(f"Server delete failed: {e}")

        if len(errors) == 2:
            raise WorkspaceError(
                detail=f"Failed to delete from both storages: {'; '.join(errors)}",
                error_code="DUAL_DELETE_ERROR",
                path=path,
            )

    async def file_exists(self, path: str) -> bool:
        """Check if file exists in either storage.

        Args:
            path: Relative path within workspace.

        Returns:
            True if file exists in Local or Server.
        """
        try:
            self._sandbox.validate_path(path)
        except SecurityError:
            return False

        local_exists = await self.local_provider.file_exists(path)
        if local_exists:
            return True

        return await self.server_provider.file_exists(path)

    async def get_file_info(self, path: str) -> FileInfo | None:
        """Get file info, preferring Local.

        Args:
            path: Relative path within workspace.

        Returns:
            FileInfo or None.
        """
        try:
            self._sandbox.validate_path(path)
        except SecurityError:
            return None

        info = await self.local_provider.get_file_info(path)
        if info is not None:
            return info

        return await self.server_provider.get_file_info(path)

    async def list_files(self, subdir: str = "") -> list[FileInfo]:
        """List files from Local storage (authoritative).

        Args:
            subdir: Subdirectory to list (empty for root).

        Returns:
            List of FileInfo objects.
        """
        try:
            if subdir:
                self._sandbox.validate_path(subdir)
        except SecurityError:
            return []

        return await self.local_provider.list_files(subdir, recursive=False)

    async def list_files_recursive(self, subdir: str = "") -> list[FileInfo]:
        """List files recursively from Local storage.

        Args:
            subdir: Subdirectory to list (empty for root).

        Returns:
            List of FileInfo objects.
        """
        try:
            if subdir:
                self._sandbox.validate_path(subdir)
        except SecurityError:
            return []

        return await self.local_provider.list_files(subdir, recursive=True)

    async def move_file(self, old_path: str, new_path: str) -> None:
        """Move/rename a file in both storages.

        Args:
            old_path: Source relative path.
            new_path: Destination relative path.

        Raises:
            FileNotFoundError: If source not found.
            SecurityError: If either path is invalid.
        """
        self._sandbox.validate_path(old_path)
        self._sandbox.validate_create_path(new_path)

        # Move in local
        await self.local_provider.move_file(old_path, new_path)

        # Move in server (best effort)
        try:
            await self.server_provider.move_file(old_path, new_path)
        except Exception as e:
            logger.warning(f"Server move failed (local succeeded): {e}")

    async def close(self) -> None:
        """Close storage providers."""
        await self.server_provider.close()


# ---------------------------------------------------------------------------
# Workspace Manager
# ---------------------------------------------------------------------------


class WorkspaceManager:
    """Manages workspace directories and file operations.

    Each conversation gets its own workspace:
        {workspace_root}/{user_id}/{conversation_id}/

    All file operations are sandboxed via PathSandbox.
    Dual-storage mode writes to both Local and Server providers.
    """

    def __init__(
        self,
        workspace_root: str | None = None,
        local_cache_root: str | None = None,
    ) -> None:
        self.workspace_root = Path(
            workspace_root or settings.workspace_root
        ).resolve()
        self.local_cache_root = Path(
            local_cache_root or settings.workspace_local_cache
        ).resolve()

        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.local_cache_root.mkdir(parents=True, exist_ok=True)

        # Track active workspaces
        self._workspaces: dict[str, Workspace] = {}
        self._storages: dict[str, WorkspaceStorage] = {}

    # -- Workspace Lifecycle ------------------------------------------------

    def _get_workspace_path(self, conversation_id: str, user_id: str = "") -> Path:
        """Get the workspace directory path.

        Layout: {workspace_root}/{user_id}/{conversation_id}/
        """
        if user_id:
            return self.workspace_root / user_id / conversation_id
        return self.workspace_root / conversation_id

    def _get_storage(self, workspace_id: str) -> WorkspaceStorage:
        """Get or create the dual storage for a workspace."""
        if workspace_id not in self._storages:
            # Resolve workspace path from tracked workspaces
            workspace = self._workspaces.get(workspace_id)
            if workspace is None:
                raise WorkspaceError(
                    detail=f"Workspace not found: {workspace_id}",
                    error_code="WORKSPACE_NOT_FOUND",
                )

            workspace_path = Path(workspace.root_path)
            server_root = self.local_cache_root / workspace_id

            self._storages[workspace_id] = WorkspaceStorage(
                workspace_path=workspace_path,
                server_root=server_root,
            )

        return self._storages[workspace_id]

    async def create_workspace(
        self, conversation_id: str, user_id: str = ""
    ) -> Workspace:
        """Create a new workspace with full directory structure.

        Directory structure:
            {workspace_root}/{user_id}/{conversation_id}/
            ├── uploads/
            ├── outputs/
            ├── cache/
            │   ├── crawl/
            │   └── tool_cache/
            ├── assets/
            │   ├── thumbnails/
            │   └── extracted_images/
            ├── project/
            └── .workspace/
                ├── manifest.json
                ├── index.json
                ├── metadata.json
                └── snapshots/

        Args:
            conversation_id: Conversation identifier.
            user_id: User identifier for session isolation.

        Returns:
            Workspace metadata.
        """
        workspace_path = self._get_workspace_path(conversation_id, user_id)
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Create standard subdirectories
        directories = [
            "uploads",
            "outputs",
            "cache/crawl",
            "cache/tool_cache",
            "assets/thumbnails",
            "assets/extracted_images",
            "project",
            ".workspace/snapshots",
        ]

        for subdir in directories:
            (workspace_path / subdir).mkdir(parents=True, exist_ok=True)

        # Create metadata files
        workspace_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)

        manifest = {
            "workspace_id": workspace_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "created_at": created_at.isoformat(),
            "version": 1,
        }
        (workspace_path / ".workspace" / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        metadata = {
            "workspace_id": workspace_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "created_at": created_at.isoformat(),
            "last_accessed": created_at.isoformat(),
            "file_count": 0,
            "total_size": 0,
        }
        (workspace_path / ".workspace" / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

        # Initialize empty index
        (workspace_path / ".workspace" / "index.json").write_text(
            json.dumps(
                {"version": 1, "updated_at": created_at.isoformat(), "entries": {}},
                indent=2,
            ),
            encoding="utf-8",
        )

        workspace = Workspace(
            id=workspace_id,
            conversation_id=conversation_id,
            user_id=user_id,
            root_path=str(workspace_path),
            created_at=created_at.isoformat(),
            metadata={"user_id": user_id},
        )

        self._workspaces[workspace_id] = workspace

        logger.info(
            f"Created workspace {workspace_id} for conversation {conversation_id}, "
            f"user {user_id} at {workspace_path}"
        )

        return workspace

    async def delete_workspace(self, workspace_id: str) -> None:
        """Delete a workspace and all its data.

        Args:
            workspace_id: Workspace identifier.

        Raises:
            WorkspaceError: If workspace not found.
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceError(
                detail=f"Workspace not found: {workspace_id}",
                error_code="WORKSPACE_NOT_FOUND",
            )

        workspace_path = Path(workspace.root_path)

        # Clean up storage
        if workspace_id in self._storages:
            await self._storages[workspace_id].close()
            del self._storages[workspace_id]

        # Delete local workspace directory
        if workspace_path.exists():
            await asyncio.to_thread(shutil.rmtree, workspace_path)

        # Delete server cache
        server_path = self.local_cache_root / workspace_id
        if server_path.exists():
            await asyncio.to_thread(shutil.rmtree, server_path)

        del self._workspaces[workspace_id]

        logger.info(f"Deleted workspace {workspace_id}")

    async def get_workspace(self, workspace_id: str) -> Workspace | None:
        """Get workspace metadata.

        Args:
            workspace_id: Workspace identifier.

        Returns:
            Workspace or None if not found.
        """
        return self._workspaces.get(workspace_id)

    async def workspace_exists(self, conversation_id: str, user_id: str = "") -> bool:
        """Check if a workspace directory exists.

        Args:
            conversation_id: Conversation identifier.
            user_id: User identifier.

        Returns:
            True if workspace directory exists.
        """
        workspace_path = self._get_workspace_path(conversation_id, user_id)
        return workspace_path.exists()

    # -- File Operations ----------------------------------------------------

    async def read_file(self, workspace_id: str, path: str) -> bytes:
        """Read a file from the workspace.

        Args:
            workspace_id: Workspace identifier.
            path: Relative file path within workspace.

        Returns:
            File contents as bytes.

        Raises:
            WorkspaceError: If file cannot be read.
        """
        try:
            storage = self._get_storage(workspace_id)
            return await storage.read_file(path)
        except FileNotFoundError:
            raise WorkspaceError(
                detail=f"File not found: {path}",
                error_code="FILE_NOT_FOUND",
                path=path,
            )
        except SecurityError as e:
            raise WorkspaceError(
                detail=f"Security violation: {e}",
                error_code="SECURITY_VIOLATION",
                path=path,
            )
        except TimeoutError:
            raise WorkspaceError(
                detail=f"Read timeout for file: {path}",
                error_code="READ_TIMEOUT",
                path=path,
            )
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to read file: {e}",
                error_code="READ_ERROR",
                path=path,
            )

    async def write_file(self, workspace_id: str, path: str, data: bytes) -> None:
        """Write a file to the workspace.

        Args:
            workspace_id: Workspace identifier.
            path: Relative file path within workspace.
            data: File contents as bytes.

        Raises:
            WorkspaceError: If file cannot be written.
        """
        try:
            storage = self._get_storage(workspace_id)
            await storage.write_file(path, data)
        except SecurityError as e:
            raise WorkspaceError(
                detail=f"Security violation: {e}",
                error_code="SECURITY_VIOLATION",
                path=path,
            )
        except ValueError as e:
            raise WorkspaceError(
                detail=f"Invalid file: {e}",
                error_code="INVALID_FILE",
                path=path,
            )
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to write file: {e}",
                error_code="WRITE_ERROR",
                path=path,
            )

    async def delete_file(self, workspace_id: str, path: str) -> None:
        """Delete a file from the workspace.

        Args:
            workspace_id: Workspace identifier.
            path: Relative file path within workspace.

        Raises:
            WorkspaceError: If file cannot be deleted.
        """
        try:
            storage = self._get_storage(workspace_id)
            await storage.delete_file(path)
        except FileNotFoundError:
            raise WorkspaceError(
                detail=f"File not found: {path}",
                error_code="FILE_NOT_FOUND",
                path=path,
            )
        except SecurityError as e:
            raise WorkspaceError(
                detail=f"Security violation: {e}",
                error_code="SECURITY_VIOLATION",
                path=path,
            )
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to delete file: {e}",
                error_code="DELETE_ERROR",
                path=path,
            )

    async def rename_file(
        self, workspace_id: str, old_path: str, new_path: str
    ) -> None:
        """Rename a file in the workspace.

        Args:
            workspace_id: Workspace identifier.
            old_path: Current relative file path.
            new_path: New relative file path.

        Raises:
            WorkspaceError: If rename fails.
        """
        try:
            storage = self._get_storage(workspace_id)
            await storage.move_file(old_path, new_path)
        except FileNotFoundError:
            raise WorkspaceError(
                detail=f"File not found: {old_path}",
                error_code="FILE_NOT_FOUND",
                path=old_path,
            )
        except SecurityError as e:
            raise WorkspaceError(
                detail=f"Security violation: {e}",
                error_code="SECURITY_VIOLATION",
                path=old_path,
            )
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to rename file: {e}",
                error_code="RENAME_ERROR",
                path=old_path,
            )

    async def list_files(
        self, workspace_id: str, subdir: str = ""
    ) -> list[FileInfo]:
        """List files in the workspace.

        Args:
            workspace_id: Workspace identifier.
            subdir: Subdirectory path (empty for root).

        Returns:
            List of FileInfo objects.
        """
        try:
            storage = self._get_storage(workspace_id)
            return await storage.list_files(subdir)
        except WorkspaceError:
            raise
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to list files: {e}",
                error_code="LIST_ERROR",
                path=subdir,
            )

    async def list_files_recursive(
        self, workspace_id: str, subdir: str = ""
    ) -> list[FileInfo]:
        """List files recursively in the workspace.

        Args:
            workspace_id: Workspace identifier.
            subdir: Subdirectory path (empty for root).

        Returns:
            List of FileInfo objects.
        """
        try:
            storage = self._get_storage(workspace_id)
            return await storage.list_files_recursive(subdir)
        except WorkspaceError:
            raise
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to list files recursively: {e}",
                error_code="LIST_ERROR",
                path=subdir,
            )

    async def search_files(self, workspace_id: str, query: str) -> list[FileInfo]:
        """Search files in the workspace by name/path.

        Uses the file index for fast searching.

        Args:
            workspace_id: Workspace identifier.
            query: Search query string.

        Returns:
            List of matching FileInfo objects.
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceError(
                detail=f"Workspace not found: {workspace_id}",
                error_code="WORKSPACE_NOT_FOUND",
            )

        try:
            indexer = WorkspaceIndexer(workspace.root_path)
            return await indexer.search_index(workspace_id, query)
        except Exception as e:
            logger.warning(f"Index search failed, falling back to filesystem: {e}")
            # Fallback: search through filesystem listing
            all_files = await self.list_files_recursive(workspace_id)
            query_lower = query.lower()
            return [
                f
                for f in all_files
                if query_lower in f.name.lower() or query_lower in f.path.lower()
            ]

    async def get_file_info(self, workspace_id: str, path: str) -> FileInfo:
        """Get information about a file.

        Args:
            workspace_id: Workspace identifier.
            path: Relative file path.

        Returns:
            FileInfo object.

        Raises:
            WorkspaceError: If file not found.
        """
        try:
            storage = self._get_storage(workspace_id)
            info = await storage.get_file_info(path)
            if info is None:
                raise WorkspaceError(
                    detail=f"File not found: {path}",
                    error_code="FILE_NOT_FOUND",
                    path=path,
                )
            return info
        except WorkspaceError:
            raise
        except SecurityError as e:
            raise WorkspaceError(
                detail=f"Security violation: {e}",
                error_code="SECURITY_VIOLATION",
                path=path,
            )
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to get file info: {e}",
                error_code="INFO_ERROR",
                path=path,
            )

    async def file_exists(self, workspace_id: str, path: str) -> bool:
        """Check if a file exists in the workspace.

        Args:
            workspace_id: Workspace identifier.
            path: Relative file path.

        Returns:
            True if file exists.
        """
        try:
            storage = self._get_storage(workspace_id)
            return await storage.file_exists(path)
        except Exception:
            return False

    # -- Directory Operations -----------------------------------------------

    async def create_directory(self, workspace_id: str, path: str) -> None:
        """Create a directory in the workspace.

        Args:
            workspace_id: Workspace identifier.
            path: Relative directory path.

        Raises:
            WorkspaceError: If creation fails.
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceError(
                detail=f"Workspace not found: {workspace_id}",
                error_code="WORKSPACE_NOT_FOUND",
            )

        try:
            storage = self._get_storage(workspace_id)
            await storage.local_provider.create_directory(path)
        except SecurityError as e:
            raise WorkspaceError(
                detail=f"Security violation: {e}",
                error_code="SECURITY_VIOLATION",
                path=path,
            )
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to create directory: {e}",
                error_code="MKDIR_ERROR",
                path=path,
            )

    async def delete_directory(
        self, workspace_id: str, path: str, recursive: bool = False
    ) -> None:
        """Delete a directory from the workspace.

        Args:
            workspace_id: Workspace identifier.
            path: Relative directory path.
            recursive: Whether to delete contents recursively.

        Raises:
            WorkspaceError: If deletion fails.
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceError(
                detail=f"Workspace not found: {workspace_id}",
                error_code="WORKSPACE_NOT_FOUND",
            )

        try:
            storage = self._get_storage(workspace_id)
            await storage.local_provider.delete_directory(path, recursive)
        except FileNotFoundError:
            raise WorkspaceError(
                detail=f"Directory not found: {path}",
                error_code="DIR_NOT_FOUND",
                path=path,
            )
        except SecurityError as e:
            raise WorkspaceError(
                detail=f"Security violation: {e}",
                error_code="SECURITY_VIOLATION",
                path=path,
            )
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to delete directory: {e}",
                error_code="RMDIR_ERROR",
                path=path,
            )

    # -- Snapshot Operations ------------------------------------------------

    async def create_snapshot(self, workspace_id: str, description: str = "") -> Snapshot:
        """Create a snapshot of the current workspace state.

        Args:
            workspace_id: Workspace identifier.
            description: Optional snapshot description.

        Returns:
            Snapshot object.

        Raises:
            WorkspaceError: If snapshot creation fails.
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceError(
                detail=f"Workspace not found: {workspace_id}",
                error_code="WORKSPACE_NOT_FOUND",
            )

        try:
            snapshot_manager = SnapshotManager(workspace.root_path)
            storage = self._get_storage(workspace_id)

            snapshot = await snapshot_manager.create(
                workspace_id=workspace_id,
                list_files_func=lambda: storage.list_files_recursive(),
                read_file_func=lambda p: storage.read_file(p),
                description=description,
            )

            # Update workspace metadata
            await self._update_metadata(workspace_id, snapshot)

            return snapshot
        except WorkspaceError:
            raise
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to create snapshot: {e}",
                error_code="SNAPSHOT_ERROR",
            )

    async def restore_snapshot(
        self, workspace_id: str, snapshot_id: str
    ) -> None:
        """Restore workspace to a snapshot state.

        Args:
            workspace_id: Workspace identifier.
            snapshot_id: Snapshot to restore.

        Raises:
            WorkspaceError: If restore fails.
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceError(
                detail=f"Workspace not found: {workspace_id}",
                error_code="WORKSPACE_NOT_FOUND",
            )

        try:
            snapshot_manager = SnapshotManager(workspace.root_path)
            storage = self._get_storage(workspace_id)

            await snapshot_manager.restore(
                workspace_id=workspace_id,
                snapshot_id=snapshot_id,
                read_file_func=None,  # Will create placeholders
                write_file_func=lambda p, d: storage.write_file(p, d),
            )

            logger.info(
                f"Restored workspace {workspace_id} to snapshot {snapshot_id}"
            )
        except FileNotFoundError:
            raise WorkspaceError(
                detail=f"Snapshot not found: {snapshot_id}",
                error_code="SNAPSHOT_NOT_FOUND",
            )
        except WorkspaceError:
            raise
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to restore snapshot: {e}",
                error_code="RESTORE_ERROR",
            )

    async def list_snapshots(self, workspace_id: str) -> list[Snapshot]:
        """List all snapshots for a workspace.

        Args:
            workspace_id: Workspace identifier.

        Returns:
            List of snapshots, newest first.

        Raises:
            WorkspaceError: If workspace not found.
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceError(
                detail=f"Workspace not found: {workspace_id}",
                error_code="WORKSPACE_NOT_FOUND",
            )

        try:
            snapshot_manager = SnapshotManager(workspace.root_path)
            return await snapshot_manager.list_snapshots(workspace_id)
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to list snapshots: {e}",
                error_code="SNAPSHOT_LIST_ERROR",
            )

    async def delete_snapshot(self, workspace_id: str, snapshot_id: str) -> bool:
        """Delete a snapshot.

        Args:
            workspace_id: Workspace identifier.
            snapshot_id: Snapshot to delete.

        Returns:
            True if snapshot was deleted.

        Raises:
            WorkspaceError: If workspace not found.
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceError(
                detail=f"Workspace not found: {workspace_id}",
                error_code="WORKSPACE_NOT_FOUND",
            )

        try:
            snapshot_manager = SnapshotManager(workspace.root_path)
            return await snapshot_manager.delete(workspace_id, snapshot_id)
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to delete snapshot: {e}",
                error_code="SNAPSHOT_DELETE_ERROR",
            )

    # -- Diff Operations ----------------------------------------------------

    async def get_diff(
        self, workspace_id: str, before_id: str, after_id: str
    ) -> WorkspaceDiff:
        """Get diff between two snapshots.

        Args:
            workspace_id: Workspace identifier.
            before_id: Earlier snapshot ID.
            after_id: Later snapshot ID.

        Returns:
            WorkspaceDiff with all changes.

        Raises:
            WorkspaceError: If diff generation fails.
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceError(
                detail=f"Workspace not found: {workspace_id}",
                error_code="WORKSPACE_NOT_FOUND",
            )

        try:
            snapshot_manager = SnapshotManager(workspace.root_path)

            before = await snapshot_manager.get(workspace_id, before_id)
            if before is None:
                raise WorkspaceError(
                    detail=f"Snapshot not found: {before_id}",
                    error_code="SNAPSHOT_NOT_FOUND",
                )

            after = await snapshot_manager.get(workspace_id, after_id)
            if after is None:
                raise WorkspaceError(
                    detail=f"Snapshot not found: {after_id}",
                    error_code="SNAPSHOT_NOT_FOUND",
                )

            diff_generator = DiffGenerator()
            return await diff_generator.generate(before, after)
        except WorkspaceError:
            raise
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to generate diff: {e}",
                error_code="DIFF_ERROR",
            )

    # -- Index Operations ---------------------------------------------------

    async def rebuild_index(self, workspace_id: str) -> dict[str, Any]:
        """Rebuild the file index for a workspace.

        Args:
            workspace_id: Workspace identifier.

        Returns:
            Statistics about the rebuild.

        Raises:
            WorkspaceError: If workspace not found.
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceError(
                detail=f"Workspace not found: {workspace_id}",
                error_code="WORKSPACE_NOT_FOUND",
            )

        try:
            indexer = WorkspaceIndexer(workspace.root_path)
            storage = self._get_storage(workspace_id)
            return await indexer.rebuild_index(
                workspace_id, lambda: storage.list_files_recursive()
            )
        except WorkspaceError:
            raise
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to rebuild index: {e}",
                error_code="INDEX_ERROR",
            )

    async def get_index_stats(self, workspace_id: str) -> dict[str, Any]:
        """Get file index statistics.

        Args:
            workspace_id: Workspace identifier.

        Returns:
            Index statistics.

        Raises:
            WorkspaceError: If workspace not found.
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceError(
                detail=f"Workspace not found: {workspace_id}",
                error_code="WORKSPACE_NOT_FOUND",
            )

        try:
            indexer = WorkspaceIndexer(workspace.root_path)
            return await indexer.get_stats(workspace_id)
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to get index stats: {e}",
                error_code="INDEX_ERROR",
            )

    # -- Utility Methods ----------------------------------------------------

    async def read_file_text(self, workspace_id: str, path: str) -> str:
        """Read a file as UTF-8 text.

        Args:
            workspace_id: Workspace identifier.
            path: Relative file path.

        Returns:
            File contents as string.
        """
        data = await self.read_file(workspace_id, path)
        return data.decode("utf-8", errors="replace")

    async def write_file_text(
        self, workspace_id: str, path: str, content: str
    ) -> None:
        """Write a text file as UTF-8.

        Args:
            workspace_id: Workspace identifier.
            path: Relative file path.
            content: Text content.
        """
        await self.write_file(workspace_id, path, content.encode("utf-8"))

    async def get_stats(self, workspace_id: str) -> StorageStats:
        """Get workspace storage statistics.

        Args:
            workspace_id: Workspace identifier.

        Returns:
            StorageStats with usage information.

        Raises:
            WorkspaceError: If workspace not found.
        """
        try:
            storage = self._get_storage(workspace_id)
            return await storage.local_provider.get_stats()
        except WorkspaceError:
            raise
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to get stats: {e}",
                error_code="STATS_ERROR",
            )

    async def sync_to_server(self, workspace_id: str) -> dict[str, Any]:
        """Synchronize local files to server storage.

        Args:
            workspace_id: Workspace identifier.

        Returns:
            Sync statistics.
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceError(
                detail=f"Workspace not found: {workspace_id}",
                error_code="WORKSPACE_NOT_FOUND",
            )

        try:
            storage = self._get_storage(workspace_id)
            return await storage.server_provider.sync_from_local(
                Path(workspace.root_path)
            )
        except Exception as e:
            raise WorkspaceError(
                detail=f"Failed to sync to server: {e}",
                error_code="SYNC_ERROR",
            )

    async def close(self) -> None:
        """Close all workspace storages and clean up."""
        for storage in self._storages.values():
            await storage.close()
        self._storages.clear()

    # -- Internal Methods ---------------------------------------------------

    async def _update_metadata(
        self, workspace_id: str, snapshot: Snapshot
    ) -> None:
        """Update workspace metadata after snapshot creation.

        Args:
            workspace_id: Workspace identifier.
            snapshot: Created snapshot.
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            return

        metadata_path = Path(workspace.root_path) / ".workspace" / "metadata.json"
        if not metadata_path.exists():
            return

        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
            data["last_snapshot"] = snapshot.id
            data["last_snapshot_time"] = snapshot.timestamp.isoformat()
            data["file_count"] = snapshot.file_count
            data["total_size"] = snapshot.total_size
            data["last_accessed"] = datetime.now(timezone.utc).isoformat()

            metadata_path.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to update metadata: {e}")


# ---------------------------------------------------------------------------
# Global Instance
# ---------------------------------------------------------------------------

_workspace_manager: WorkspaceManager | None = None


def get_workspace_manager() -> WorkspaceManager:
    """Get the global workspace manager instance."""
    global _workspace_manager
    if _workspace_manager is None:
        _workspace_manager = WorkspaceManager()
    return _workspace_manager
