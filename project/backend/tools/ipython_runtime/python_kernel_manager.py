"""
Python Kernel Manager - Manages multiple PythonSession lifecycles.

Responsibilities:
- Create / reuse / reset / shutdown sessions per conversation
- Map (conversation_id, session_id) -> PythonSession
- Idle session cleanup
- Concurrent access safety
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from .python_session import ExecutionResult, PythonSession
from .python_sandbox import SandboxPolicy, get_kernel_startup_scripts

logger = logging.getLogger(__name__)

# ── Session Key ───────────────────────────────────────────────────────────────


def _make_session_key(conversation_id: str, session_id: str | None) -> str:
    if session_id:
        return f"{conversation_id}::{session_id}"
    return f"{conversation_id}::default"


# ── Kernel Manager ────────────────────────────────────────────────────────────


class PythonKernelManager:
    """Central manager for all Python kernel sessions."""

    def __init__(
        self,
        workspaces_root: Path = Path("/tmp/workspaces"),
        sandbox_policy: SandboxPolicy | None = None,
        idle_timeout_seconds: float = 3600.0,  # 1 hour
        cleanup_interval_seconds: float = 300.0,  # 5 minutes
    ) -> None:
        self.workspaces_root = workspaces_root.resolve()
        if not self.workspaces_root.is_absolute():
            raise ValueError(f"workspaces_root must be absolute: {self.workspaces_root}")
        self.policy = sandbox_policy or SandboxPolicy(
            workspace_root=self.workspaces_root
        )
        self.idle_timeout_seconds = idle_timeout_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds

        # Session storage: key -> PythonSession
        self._sessions: dict[str, PythonSession] = {}
        self._session_metadata: dict[str, dict[str, Any]] = {}

        # Locks: key -> asyncio.Lock (for session creation race conditions)
        self._creation_locks: dict[str, asyncio.Lock] = {}

        # Global lock for session dict access
        self._global_lock = asyncio.Lock()

        # Cleanup task
        self._cleanup_task: asyncio.Task[None] | None = None
        self._shutting_down = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the manager and background cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("PythonKernelManager started")

    async def shutdown(self) -> None:
        """Shutdown all sessions and stop cleanup."""
        self._shutting_down = True
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        async with self._global_lock:
            shutdown_tasks = []
            for key, session in list(self._sessions.items()):
                shutdown_tasks.append(session.shutdown())
            if shutdown_tasks:
                await asyncio.gather(*shutdown_tasks, return_exceptions=True)
            self._sessions.clear()
            self._session_metadata.clear()

        logger.info("PythonKernelManager shutdown complete")

    # ── Session Management ────────────────────────────────────────────────────

    async def get_or_create_session(
        self,
        conversation_id: str,
        session_mode: str = "continue",
        session_id: str | None = None,
        timeout_seconds: int | None = None,
    ) -> PythonSession:
        """Get existing session or create new one based on session_mode.

        Args:
            conversation_id: The conversation identifier
            session_mode: One of 'continue', 'new', 'reset', 'ephemeral'
            session_id: Optional named session ID (for 'new' mode)
            timeout_seconds: Override default timeout

        Returns:
            A PythonSession ready for execution (caller must hold session.lock)
        """
        if session_mode == "ephemeral":
            # Ephemeral: always create a new temporary session
            return await self._create_ephemeral_session(conversation_id, timeout_seconds)

        # For continue / new / reset, we need a session key
        key = _make_session_key(conversation_id, session_id)

        if session_mode == "new":
            # Named session: create if not exists, error if exists
            async with self._global_lock:
                if key in self._sessions:
                    pass  # Return existing named session
                else:
                    session = await self._create_persistent_session(
                        key, conversation_id, timeout_seconds
                    )
                    self._sessions[key] = session
                    self._session_metadata[key] = {
                        "conversation_id": conversation_id,
                        "session_id": session_id or "default",
                        "created_at": time.time(),
                    }
            return self._sessions[key]

        if session_mode == "reset":
            # Reset: shutdown existing and create new
            return await self._reset_session(key, conversation_id, session_id, timeout_seconds)

        # session_mode == "continue" (default)
        async with self._global_lock:
            if key in self._sessions and self._sessions[key].is_alive:
                # Update timeout if provided
                if timeout_seconds:
                    self._sessions[key].default_timeout = timeout_seconds
                return self._sessions[key]

            # Create new default session
            session = await self._create_persistent_session(
                key, conversation_id, timeout_seconds
            )
            self._sessions[key] = session
            self._session_metadata[key] = {
                "conversation_id": conversation_id,
                "session_id": session_id or "default",
                "created_at": time.time(),
            }
            return session

    async def _create_persistent_session(
        self,
        key: str,
        conversation_id: str,
        timeout_seconds: int | None,
    ) -> PythonSession:
        """Create a new persistent session."""
        workspace = self._get_workspace_path(conversation_id)
        workspace.mkdir(parents=True, exist_ok=True)

        # Create output directories
        for subdir in self.policy.allowed_output_dirs:
            (workspace / subdir).mkdir(parents=True, exist_ok=True)

        startup_scripts = get_kernel_startup_scripts(workspace, self.policy)

        session = PythonSession(
            session_id=key,
            workspace_root=workspace,
            startup_scripts=startup_scripts,
            timeout_seconds=timeout_seconds or self.policy.timeout_seconds,
            max_memory_mb=self.policy.max_memory_mb,
            ephemeral=False,
        )
        await session.start()
        logger.info(f"Created persistent session: {key}")
        return session

    async def _create_ephemeral_session(
        self,
        conversation_id: str,
        timeout_seconds: int | None,
    ) -> PythonSession:
        """Create a one-off ephemeral session (destroyed after use)."""
        ephemeral_id = f"ephemeral-{conversation_id}-{int(time.time() * 1000)}"
        workspace = self._get_workspace_path(conversation_id)
        workspace.mkdir(parents=True, exist_ok=True)

        startup_scripts = get_kernel_startup_scripts(workspace, self.policy)

        session = PythonSession(
            session_id=ephemeral_id,
            workspace_root=workspace,
            startup_scripts=startup_scripts,
            timeout_seconds=timeout_seconds or self.policy.timeout_seconds,
            max_memory_mb=self.policy.max_memory_mb,
            ephemeral=True,
        )
        await session.start()
        logger.info(f"Created ephemeral session: {ephemeral_id}")
        return session

    async def _reset_session(
        self,
        key: str,
        conversation_id: str,
        session_id: str | None,
        timeout_seconds: int | None,
    ) -> PythonSession:
        """Reset a session (shutdown existing, create new)."""
        async with self._global_lock:
            # Shutdown old session if exists
            if key in self._sessions:
                old_session = self._sessions[key]
                await old_session.shutdown()
                del self._sessions[key]

            # Create new session
            new_session = await self._create_persistent_session(
                key, conversation_id, timeout_seconds
            )
            self._sessions[key] = new_session
            self._session_metadata[key] = {
                "conversation_id": conversation_id,
                "session_id": session_id or "default",
                "created_at": time.time(),
                "reset_at": time.time(),
            }
            logger.info(f"Reset session: {key}")
            return new_session

    async def destroy_session(self, conversation_id: str, session_id: str | None = None) -> None:
        """Destroy a specific session."""
        key = _make_session_key(conversation_id, session_id)
        async with self._global_lock:
            if key in self._sessions:
                session = self._sessions[key]
                await session.shutdown()
                del self._sessions[key]
                if key in self._session_metadata:
                    del self._session_metadata[key]
                logger.info(f"Destroyed session: {key}")

    async def destroy_conversation_sessions(self, conversation_id: str) -> None:
        """Destroy all sessions for a conversation."""
        async with self._global_lock:
            keys_to_remove = [
                k for k in self._sessions.keys()
                if k.startswith(f"{conversation_id}::")
            ]
            for key in keys_to_remove:
                session = self._sessions[key]
                await session.shutdown()
                del self._sessions[key]
                if key in self._session_metadata:
                    del self._session_metadata[key]
            logger.info(f"Destroyed {len(keys_to_remove)} sessions for conversation {conversation_id}")

    async def execute(
        self,
        conversation_id: str,
        code: str,
        session_mode: str = "continue",
        session_id: str | None = None,
        timeout_seconds: int | None = None,
    ) -> ExecutionResult:
        """High-level: execute code with session management.

        This is the main entry point. It handles:
        1. Session resolution (get or create based on mode)
        2. Serial execution lock
        3. Ephemeral cleanup
        """
        # Resolve session
        session = await self.get_or_create_session(
            conversation_id=conversation_id,
            session_mode=session_mode,
            session_id=session_id,
            timeout_seconds=timeout_seconds,
        )

        # Acquire execution lock and run
        async with session.lock:
            result = await session.execute(code, timeout_seconds)

        # Cleanup ephemeral sessions after execution
        if session.ephemeral:
            try:
                await session.shutdown()
            finally:
                async with self._global_lock:
                    # Pop safely — avoids KeyError from concurrent cleanup
                    ephemeral_keys = [
                        k for k, v in self._sessions.items()
                        if v.session_id == session.session_id
                    ]
                    for key in ephemeral_keys:
                        self._sessions.pop(key, None)
                        self._session_metadata.pop(key, None)

        return result

    # ── Workspace ─────────────────────────────────────────────────────────────

    def _get_workspace_path(self, conversation_id: str) -> Path:
        """Get workspace path for a conversation.

        In production, this would include user_id:
        /workspaces/{user_id}/{conversation_id}/
        """
        # For MVP, we use conversation_id directly
        # TODO: integrate with Workspace Manager for user_id resolution
        return self.workspaces_root / conversation_id

    # ── Cleanup ───────────────────────────────────────────────────────────────

    async def _cleanup_loop(self) -> None:
        """Background task: periodically clean up idle sessions."""
        while not self._shutting_down:
            try:
                await asyncio.sleep(self.cleanup_interval_seconds)
                await self._cleanup_idle_sessions()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Cleanup loop error")

    async def _cleanup_idle_sessions(self) -> None:
        """Shutdown sessions that have been idle for too long."""
        now = time.time()
        keys_to_remove: list[str] = []

        async with self._global_lock:
            for key, session in list(self._sessions.items()):
                if session.idle_seconds > self.idle_timeout_seconds:
                    if not session.is_busy:
                        keys_to_remove.append(key)

            for key in keys_to_remove:
                session = self._sessions[key]
                await session.shutdown()
                del self._sessions[key]
                if key in self._session_metadata:
                    del self._session_metadata[key]

        if keys_to_remove:
            logger.info(f"Cleaned up {len(keys_to_remove)} idle sessions")

    # ── Health ────────────────────────────────────────────────────────────────

    def get_session_info(self) -> list[dict[str, Any]]:
        """Get info about all active sessions."""
        info = []
        for key, session in self._sessions.items():
            meta = self._session_metadata.get(key, {})
            info.append({
                "key": key,
                "conversation_id": meta.get("conversation_id"),
                "session_id": meta.get("session_id"),
                "is_alive": session.is_alive,
                "is_busy": session.is_busy,
                "idle_seconds": session.idle_seconds,
                "created_at": meta.get("created_at"),
            })
        return info
