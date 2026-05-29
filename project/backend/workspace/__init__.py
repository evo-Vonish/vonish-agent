"""Workspace system module for backend.

Provides a complete workspace management system with:
- Session-isolated per-conversation directories
- Dual-storage mode (local + server)
- Path sandboxing for security
- Snapshot creation and restoration
- Diff generation between snapshots
- File indexing for fast search
"""

from .diff import (
    DiffGenerator,
    FileChange,
    FileDiff,
    RenameChange,
    WorkspaceDiff,
    get_diff_generator,
)
from .indexer import IndexEntry, WorkspaceIndexer
from .local_provider import LocalStorageProvider
from .permissions import PathSandbox, PathValidationResult, SecurityError
from .server_provider import ServerStorageProvider
from .snapshot import (
    FileSnapshot,
    Snapshot,
    SnapshotDiff,
    SnapshotManager,
)
from .storage_provider import FileInfo, StorageProvider, StorageStats
from .workspace_manager import (
    Workspace,
    WorkspaceManager,
    WorkspaceStorage,
    get_workspace_manager,
)

__all__ = [
    # Workspace management
    "Workspace",
    "WorkspaceManager",
    "WorkspaceStorage",
    "get_workspace_manager",
    # Storage providers
    "StorageProvider",
    "LocalStorageProvider",
    "ServerStorageProvider",
    "FileInfo",
    "StorageStats",
    # Security
    "PathSandbox",
    "PathValidationResult",
    "SecurityError",
    # Snapshots
    "Snapshot",
    "FileSnapshot",
    "SnapshotDiff",
    "SnapshotManager",
    # Diff
    "WorkspaceDiff",
    "FileChange",
    "RenameChange",
    "FileDiff",
    "DiffGenerator",
    "get_diff_generator",
    # Indexer
    "WorkspaceIndexer",
    "IndexEntry",
]
