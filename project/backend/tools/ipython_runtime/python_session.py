"""
Python Session - Single Kernel session wrapper.

Manages one ipykernel instance with:
- Serial execution lock (one cell at a time)
- stdout/stderr/display_data capture
- Timeout handling with interrupt
- Kernel health monitoring
- Restart on crash/memory overflow
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import signal
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Execution Result ──────────────────────────────────────────────────────────


@dataclass
class ExecutionResult:
    """Result of executing code in a Python kernel."""

    success: bool = True
    stdout: str = ""
    stderr: str = ""
    error: str | None = None  # traceback or error message
    error_name: str | None = None  # exception type name
    display_data: list[dict[str, Any]] = field(default_factory=list)
    execution_time_ms: int = 0
    kernel_restarted: bool = False  # True if kernel was restarted during execution

    def truncate_output(self, max_stdout: int = 10000, max_stderr: int = 10000) -> None:
        """Truncate stdout/stderr to limits."""
        if len(self.stdout) > max_stdout:
            self.stdout = self.stdout[:max_stdout] + f"\n... [{len(self.stdout) - max_stdout} chars truncated]"
        if len(self.stderr) > max_stderr:
            self.stderr = self.stderr[:max_stderr] + f"\n... [{len(self.stderr) - max_stderr} chars truncated]"


# ── Python Session ────────────────────────────────────────────────────────────


class PythonSession:
    """Wraps a single ipykernel lifecycle.

    Each session owns one KernelManager and KernelClient.
    All code execution is serialised via `self.lock`.
    """

    def __init__(
        self,
        session_id: str,
        workspace_root: Path,
        startup_scripts: list[str] | None = None,
        timeout_seconds: int = 30,
        max_memory_mb: int = 512,
        ephemeral: bool = False,
    ) -> None:
        self.session_id = session_id
        self.workspace_root = workspace_root
        self.startup_scripts = startup_scripts or []
        self.default_timeout = timeout_seconds
        self.max_memory_mb = max_memory_mb
        self.ephemeral = ephemeral

        # Concurrency control
        self.lock = asyncio.Lock()
        self._is_busy = False

        # Kernel references (initialized lazily)
        self._km: Any | None = None  # KernelManager
        self._kc: Any | None = None  # KernelClient
        self._kernel_alive = False

        # Metadata
        self.created_at = time.time()
        self.last_used_at = time.time()
        self._startup_script_executed = False

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_alive(self) -> bool:
        return self._kernel_alive and self._km is not None and self._km.is_alive()

    @property
    def is_busy(self) -> bool:
        return self._is_busy

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_used_at

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the kernel process."""
        try:
            from jupyter_client.manager import KernelManager

            safe_session_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", self.session_id)
            connection_file = str(
                self.workspace_root / "cache" / "python" / f"kernel-{safe_session_id}.json"
            )
            os.makedirs(os.path.dirname(connection_file), exist_ok=True)

            self._km = KernelManager(
                kernel_name="python3",
                connection_file=connection_file,
                extra_env={
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "MPLBACKEND": "Agg",
                    "PYTHONPATH": str(self.workspace_root),
                },
            )

            # Start kernel in thread to not block event loop
            await asyncio.to_thread(self._km.start_kernel)
            self._kc = self._km.client()
            self._kernel_alive = True

            logger.info(f"Session {self.session_id}: Kernel started")

            # Execute startup scripts to set up sandbox
            if self.startup_scripts and not self._startup_script_executed:
                await self._execute_startup_scripts()

        except Exception as e:
            logger.exception(f"Session {self.session_id}: Failed to start kernel")
            self._kernel_alive = False
            raise RuntimeError(f"Failed to start Python kernel: {e}") from e

    async def _execute_startup_scripts(self) -> None:
        """Run sandbox startup scripts in small chunks."""
        if not self._kc or not self.startup_scripts:
            return
        for i, script in enumerate(self.startup_scripts):
            try:
                result = await self._execute_code(script, timeout=10)
                if not result.success:
                    logger.warning(
                        f"Session {self.session_id}: Startup script {i} failed: {result.error}"
                    )
                else:
                    logger.debug(f"Session {self.session_id}: Startup script {i} executed")
            except Exception as e:
                logger.warning(f"Session {self.session_id}: Startup script {i} error: {e}")
        self._startup_script_executed = True

    async def shutdown(self) -> None:
        """Shutdown the kernel and clean up resources."""
        self._kernel_alive = False
        try:
            if self._kc:
                await asyncio.to_thread(self._kc.stop_channels)
                self._kc = None
            if self._km:
                if self._km.is_alive():
                    await asyncio.to_thread(self._km.shutdown_kernel, now=True)
                await asyncio.to_thread(self._km.cleanup_connection_file)
                self._km = None
            logger.info(f"Session {self.session_id}: Kernel shutdown")
        except Exception:
            logger.exception(f"Session {self.session_id}: Error during shutdown")

    async def restart(self) -> None:
        """Restart the kernel (variables will be lost)."""
        logger.info(f"Session {self.session_id}: Restarting kernel")
        self._kernel_alive = False
        try:
            if self._km and self._km.is_alive():
                await asyncio.to_thread(self._km.restart_kernel, now=True)
            else:
                await self.shutdown()
                await self.start()
                return

            # Re-create client after restart
            if self._kc:
                await asyncio.to_thread(self._kc.stop_channels)
            self._kc = self._km.client()
            self._kernel_alive = True
            self._startup_script_executed = False

            # Re-run startup scripts
            if self.startup_scripts:
                await self._execute_startup_scripts()

            logger.info(f"Session {self.session_id}: Kernel restarted")
        except Exception:
            logger.exception(f"Session {self.session_id}: Restart failed, creating new kernel")
            await self.shutdown()
            await self.start()

    async def interrupt(self) -> None:
        """Send interrupt signal to the kernel."""
        try:
            if self._km and self._km.is_alive():
                await asyncio.to_thread(self._km.interrupt_kernel)
                logger.info(f"Session {self.session_id}: Kernel interrupted")
        except Exception:
            logger.exception(f"Session {self.session_id}: Interrupt failed")

    # ── Code Execution ────────────────────────────────────────────────────────

    async def execute(
        self,
        code: str,
        timeout_seconds: int | None = None,
    ) -> ExecutionResult:
        """Execute Python code in the kernel.

        This method is NOT thread-safe by itself;
        callers must hold `self.lock`.
        """
        self.last_used_at = time.time()
        timeout = timeout_seconds or self.default_timeout

        if not self.is_alive:
            logger.info(f"Session {self.session_id}: Kernel not alive, restarting")
            await self.restart()

        if not self._kc:
            return ExecutionResult(
                success=False,
                error="Kernel client not available",
            )

        self._is_busy = True
        start_time = time.time()

        try:
            result = await self._execute_code(code, timeout)
            result.execution_time_ms = int((time.time() - start_time) * 1000)
            return result
        except Exception as e:
            logger.exception(f"Session {self.session_id}: Execution error")
            return ExecutionResult(
                success=False,
                error=f"Execution failed: {str(e)}",
                execution_time_ms=int((time.time() - start_time) * 1000),
            )
        finally:
            self._is_busy = False
            self.last_used_at = time.time()

    async def _execute_code(
        self,
        code: str,
        timeout: int,
    ) -> ExecutionResult:
        """Internal: execute code via jupyter_client with timeout handling."""
        assert self._kc is not None

        # Use a thread for the blocking jupyter_client call
        loop = asyncio.get_event_loop()

        # We'll use execute_interactive for better control
        result = ExecutionResult()
        msg_id: str | None = None

        try:
            # Submit execution request
            msg_id = await asyncio.to_thread(
                self._kc.execute,
                code,
                silent=False,
                store_history=True,
                allow_stdin=False,
            )

            # Collect all messages until idle
            await self._collect_messages(msg_id, result, timeout)

        except asyncio.TimeoutError:
            result.success = False
            result.error = f"Execution timed out after {timeout} seconds"
            result.error_name = "TimeoutError"

            # Try to interrupt
            await self.interrupt()
            # Drain remaining messages
            try:
                await asyncio.wait_for(
                    self._drain_messages(msg_id),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                # Interrupt failed, restart kernel
                logger.warning(f"Session {self.session_id}: Interrupt failed, restarting kernel")
                await self.restart()
                result.kernel_restarted = True

        except Exception as e:
            result.success = False
            result.error = str(e)
            # Check if kernel is still alive
            if not self.is_alive:
                result.kernel_restarted = True
                result.error = f"Kernel crashed: {e}. Kernel has been restarted, variables are lost."

        # Post-process: if no explicit error but stderr contains traceback patterns,
        # it means IPython's traceback formatting failed (e.g., executing.MemoryError)
        if result.success and result.stderr and ("Traceback" in result.stderr or "exception" in result.stderr.lower()):
            result.success = False
            if not result.error:
                result.error = result.stderr.strip()
                result.error_name = "Exception"

        return result

    async def _collect_messages(
        self,
        msg_id: str | None,
        result: ExecutionResult,
        timeout: int,
    ) -> None:
        """Collect IOPub messages until idle or timeout."""
        assert self._kc is not None
        deadline = time.time() + timeout

        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise asyncio.TimeoutError()

            try:
                msg = await asyncio.to_thread(
                    self._kc.get_iopub_msg,
                    timeout=min(remaining, 0.5),
                )
            except Exception:
                # Timeout on get_iopub_msg, check deadline
                if time.time() >= deadline:
                    raise asyncio.TimeoutError()
                continue

            if msg["parent_header"].get("msg_id") != msg_id:
                continue

            msg_type = msg["msg_type"]
            content = msg["content"]

            if msg_type == "stream":
                stream_name = content.get("name", "stdout")
                text = content.get("text", "")
                if stream_name == "stderr":
                    result.stderr += text
                else:
                    result.stdout += text

            elif msg_type == "display_data":
                result.display_data.append({
                    "data": content.get("data", {}),
                    "metadata": content.get("metadata", {}),
                })

            elif msg_type == "execute_result":
                data = content.get("data", {})
                text_repr = data.get("text/plain", "")
                if text_repr:
                    result.stdout += f"{text_repr}\n"
                result.display_data.append({"data": data, "metadata": {}})

            elif msg_type == "error":
                result.success = False
                result.error_name = content.get("ename", "Error")
                traceback_lines = content.get("traceback", [])
                # Clean ANSI codes from traceback
                import re
                ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
                clean_traceback = [ansi_escape.sub("", line) for line in traceback_lines]
                result.error = "\n".join(clean_traceback)

            elif msg_type == "status":
                execution_state = content.get("execution_state", "")
                if execution_state == "idle":
                    break

            elif msg_type == "execute_input":
                pass  # Ignore execution input notifications

        if time.time() >= deadline:
            raise asyncio.TimeoutError()

    async def _drain_messages(self, msg_id: str | None) -> None:
        """Drain remaining IOPub messages after interrupt."""
        assert self._kc is not None
        deadline = time.time() + 5.0

        while time.time() < deadline:
            try:
                msg = await asyncio.to_thread(
                    self._kc.get_iopub_msg,
                    timeout=0.5,
                )
                if msg["msg_type"] == "status" and msg["content"].get("execution_state") == "idle":
                    break
            except Exception:
                if time.time() >= deadline:
                    break
