"""Tool Executor for the Agent system.

Executes tool calls, manages the tool result lifecycle,
and handles error recovery.
"""

from __future__ import annotations

import asyncio
import html
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import quote_plus, urljoin

from pydantic import BaseModel, Field

from core.config import settings
from core.errors import ToolError
from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class ToolCallRequest(BaseModel):
    """A request to execute a tool."""

    tool_name: str
    arguments: dict[str, Any]
    call_id: str = ""
    conversation_id: str = ""
    workspace_id: str | None = None
    permission_mode: str = "default"
    directory_access_mode: str = "locked_workspace"


class ToolCallResult(BaseModel):
    """Result of a tool execution."""

    tool_name: str
    call_id: str
    success: bool
    result: Any
    execution_time_ms: float
    error_message: str | None = None
    requires_confirmation: bool = False
    arguments: dict[str, Any] = Field(default_factory=dict)
    tool_call_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tool Executor
# ---------------------------------------------------------------------------


class ToolExecutor:
    """Executes tool calls with lifecycle management.

    Handles:
    - Pre-execution validation
    - Actual execution with timeout
    - Post-execution result processing
    - Error handling and recovery
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., Awaitable[Any]]] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._default_timeout: float = 120.0
        self._ipython_manager: Any | None = None
        self._ipython_tool: Any | None = None
        self._ipython_managers: dict[str, Any] = {}
        self._ipython_tools: dict[str, Any] = {}

    def register_handler(
        self, tool_name: str, handler: Callable[..., Awaitable[Any]]
    ) -> None:
        """Register a handler function for a tool.

        Args:
            tool_name: Name of the tool.
            handler: Async function to handle the tool call.
        """
        self._handlers[tool_name] = handler
        logger.debug(f"Registered handler for tool: {tool_name}")

    def unregister_handler(self, tool_name: str) -> None:
        """Unregister a tool handler."""
        self._handlers.pop(tool_name, None)

    async def execute(self, request: ToolCallRequest) -> ToolCallResult:
        """Execute a single tool call.

        Args:
            request: ToolCallRequest with tool name and arguments.

        Returns:
            ToolCallResult with execution outcome.

        Raises:
            ToolError: If execution fails critically.
        """
        start_time = time.monotonic()
        call_id = request.call_id or f"tc_{int(start_time * 1000)}"

        handler = self._handlers.get(request.tool_name)
        tool_def = None

        from api.prompt import get_enabled_tools

        if request.tool_name not in get_enabled_tools():
            return ToolCallResult(
                tool_name=request.tool_name,
                call_id=call_id,
                success=False,
                result=None,
                execution_time_ms=0.0,
                error_message=f"Tool '{request.tool_name}' is disabled. Enable it in the Tool Management panel.",
            )

        if handler is None:
            from agent.tool_registry import ToolRegistry

            registry = ToolRegistry()
            tool_def = registry.get(request.tool_name)

            # Try to find a default handler
            handler = self._get_default_handler(request.tool_name)

            if handler is None:
                if tool_def is None:
                    return ToolCallResult(
                        tool_name=request.tool_name,
                        call_id=call_id,
                        success=False,
                        result=None,
                        execution_time_ms=0.0,
                        error_message=f"No handler registered for tool: {request.tool_name}",
                    )
                return ToolCallResult(
                    tool_name=request.tool_name,
                    call_id=call_id,
                    success=False,
                    result=None,
                    execution_time_ms=0.0,
                    error_message=f"Tool '{request.tool_name}' registered but no handler available",
                )

        try:
            # Validate arguments when the registry has a schema for the tool.
            if tool_def is None:
                from agent.tool_registry import ToolRegistry

                tool_def = ToolRegistry().get(request.tool_name)

            if tool_def is not None:
                validation_result = self._validate_arguments(
                    request.tool_name, request.arguments
                )
                if not validation_result.valid:
                    return ToolCallResult(
                        tool_name=request.tool_name,
                        call_id=call_id,
                        success=False,
                        result=None,
                        execution_time_ms=(time.monotonic() - start_time) * 1000,
                        error_message=f"Validation failed: {'; '.join(validation_result.errors)}",
                    )
                arguments = dict(validation_result.normalized_arguments)
            else:
                arguments = dict(request.arguments)

            # Inject conversation_id if the tool expects it
            if request.conversation_id and "conversation_id" not in arguments:
                arguments["conversation_id"] = request.conversation_id
            if request.workspace_id and "workspace_id" not in arguments:
                arguments["workspace_id"] = request.workspace_id
            if "permission_mode" not in arguments:
                arguments["permission_mode"] = request.permission_mode
            if "directory_access_mode" not in arguments:
                arguments["directory_access_mode"] = request.directory_access_mode

            # Execute with timeout
            result = await asyncio.wait_for(
                handler(**arguments),
                timeout=self._default_timeout,
            )

            execution_time = (time.monotonic() - start_time) * 1000
            result_success = not (
                isinstance(result, dict) and result.get("success") is False
            )
            result_error = (
                str(result.get("error") or result.get("error_message"))
                if isinstance(result, dict)
                and result.get("success") is False
                and (result.get("error") or result.get("error_message"))
                else None
            )

            return ToolCallResult(
                tool_name=request.tool_name,
                call_id=call_id,
                success=result_success,
                result=result,
                execution_time_ms=execution_time,
                error_message=result_error,
                metadata={"arguments": request.arguments},
            )

        except asyncio.TimeoutError:
            execution_time = (time.monotonic() - start_time) * 1000
            return ToolCallResult(
                tool_name=request.tool_name,
                call_id=call_id,
                success=False,
                result=None,
                execution_time_ms=execution_time,
                error_message=f"Tool execution timed out after {self._default_timeout}s",
            )

        except Exception as e:
            execution_time = (time.monotonic() - start_time) * 1000
            logger.error(
                f"Tool execution error: {request.tool_name}",
                extra={"error": str(e), "arguments": request.arguments},
            )
            return ToolCallResult(
                tool_name=request.tool_name,
                call_id=call_id,
                success=False,
                result=None,
                execution_time_ms=execution_time,
                error_message=str(e),
            )

    async def execute_batch(
        self, requests: list[ToolCallRequest]
    ) -> list[ToolCallResult]:
        """Execute multiple tool calls concurrently.

        Args:
            requests: List of tool call requests.

        Returns:
            List of tool call results in same order.
        """
        tasks = [self.execute(req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results: list[ToolCallResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(
                    ToolCallResult(
                        tool_name=requests[i].tool_name,
                        call_id=requests[i].call_id,
                        success=False,
                        result=None,
                        execution_time_ms=0.0,
                        error_message=str(result),
                    )
                )
            else:
                processed_results.append(result)

        return processed_results

    def cancel(self, call_id: str) -> bool:
        """Cancel a running tool call.

        Args:
            call_id: ID of the tool call to cancel.

        Returns:
            True if cancellation was initiated.
        """
        task = self._running.get(call_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    def _validate_arguments(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """Validate tool arguments against schema."""
        from agent.tool_registry import ToolRegistry

        registry = ToolRegistry()
        return registry.validate_call(tool_name, arguments)

    def _get_default_handler(
        self, tool_name: str
    ) -> Callable[..., Awaitable[Any]] | None:
        """Get a default handler for a tool if no custom one is registered."""
        default_handlers: dict[str, Callable[..., Awaitable[Any]]] = {
            "read_file": self._handle_read_file,
            "file_read": self._handle_file_read,
            "edit_file": self._handle_edit_file,
            "write_to_file": self._handle_write_to_file,
            "shell_command": self._handle_shell_command,
            "ipython": self._handle_ipython,
            "web_fetch": self._handle_web_fetch,
            "web_search": self._handle_web_search,
            "research_search": self._handle_research_search,
            "research_fetch": self._handle_research_fetch,
            "deep_research": self._handle_deep_research,
            "research_status": self._handle_research_status,
            "delete_file": self._handle_delete_file,
            "apply_patch": self._handle_apply_patch,
            "list_directory": self._handle_list_directory,
            "snapshot": self._handle_snapshot,
            "search_workspace": self._handle_search_workspace,
            "create_directories": self._handle_create_directories,
            "git_status": self._handle_git_status,
            "git_diff": self._handle_git_diff,
            "git_history": self._handle_git_history,
            "set_todo_list": self._handle_set_todo_list,
            "ask_user_question": self._handle_ask_user_question,
            "request_approval": self._handle_request_approval,
        }
        return default_handlers.get(tool_name)

    @staticmethod
    def _full_access(permission_mode: str = "default", directory_access_mode: str = "locked_workspace") -> bool:
        return permission_mode == "full_access" and directory_access_mode == "request_external"

    def _workspace_dir(self, conversation_id: str = "", workspace_id: str | None = None) -> Path:
        """Return the conversation workspace directory and ensure it exists."""
        selected_id = workspace_id or conversation_id or "default"
        root = (Path(settings.workspace_root).resolve() / selected_id).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _tool_context(
        self,
        conversation_id: str = "",
        workspace_id: str | None = None,
        permission_mode: str = "default",
        directory_access_mode: str = "locked_workspace",
    ) -> Any:
        from tools.context import ToolContext

        workspace = self._workspace_dir(conversation_id, workspace_id)
        return ToolContext(
            conversation_id=conversation_id or "default",
            workspace_root=str(workspace),
            user_id="default",
            allow_workspace_escape=self._full_access(permission_mode, directory_access_mode),
        )

    @staticmethod
    def _tool_result_payload(result: Any) -> Any:
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if hasattr(result, "dict"):
            return result.dict()
        return result

    async def _handle_read_file(
        self,
        path: str,
        conversation_id: str = "",
        workspace_id: str | None = None,
        permission_mode: str = "default",
        directory_access_mode: str = "locked_workspace",
        start_line: int = 1,
        max_lines: int = 200,
        **_: Any,
    ) -> Any:
        from tools.file_tools import ReadFileTool

        result = await ReadFileTool().execute(
            self._tool_context(conversation_id, workspace_id, permission_mode, directory_access_mode),
            path=path,
            start_line=start_line,
            max_lines=max_lines,
        )
        return self._tool_result_payload(result)

    async def _handle_edit_file(
        self,
        path: str,
        old_string: str = "",
        new_string: str = "",
        conversation_id: str = "",
        workspace_id: str | None = None,
        permission_mode: str = "default",
        directory_access_mode: str = "locked_workspace",
        **_: Any,
    ) -> Any:
        from tools.file_tools import EditFileTool

        result = await EditFileTool().execute(
            self._tool_context(conversation_id, workspace_id, permission_mode, directory_access_mode),
            path=path,
            old_text=old_string,
            new_text=new_string,
        )
        return self._tool_result_payload(result)

    async def _handle_write_to_file(
        self,
        path: str,
        content: str,
        conversation_id: str = "",
        workspace_id: str | None = None,
        permission_mode: str = "default",
        directory_access_mode: str = "locked_workspace",
        **_: Any,
    ) -> dict[str, Any]:
        """Create or overwrite a file in the workspace."""
        ws = self._workspace_dir(conversation_id, workspace_id)
        allow_escape = self._full_access(permission_mode, directory_access_mode)
        raw_path = Path(path)
        fp = raw_path.resolve() if allow_escape and raw_path.is_absolute() else (ws / raw_path).resolve()
        if not allow_escape and not str(fp).startswith(str(ws)):
            return {"success": False, "path": path, "error": "Path escape blocked"}
        try:
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
            return {
                "success": True,
                "path": path,
                "size": len(content),
                "lines": content.count("\n") + 1,
            }
        except Exception as e:
            return {"success": False, "path": path, "error": str(e)}

    async def _handle_shell_command(
        self,
        command: str,
        timeout: int = 30,
        cwd: str = "",
        conversation_id: str = "",
        workspace_id: str | None = None,
        permission_mode: str = "default",
        directory_access_mode: str = "locked_workspace",
        **_: Any,
    ) -> dict[str, Any]:
        workspace = self._workspace_dir(conversation_id, workspace_id)
        allow_escape = self._full_access(permission_mode, directory_access_mode)
        raw_cwd = Path(cwd) if cwd else workspace
        work_dir = raw_cwd.resolve() if allow_escape and raw_cwd.is_absolute() else (workspace / raw_cwd).resolve() if cwd else workspace
        if not allow_escape and not str(work_dir).startswith(str(workspace)):
            return {
                "success": False,
                "command": command,
                "error": f"cwd path escape blocked: {cwd}",
            }
        work_dir.mkdir(parents=True, exist_ok=True)

        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=max(1, min(int(timeout), int(self._default_timeout))),
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {
                "success": False,
                "command": command,
                "error": f"Command timed out after {timeout}s",
                "cwd": str(work_dir),
            }

        stdout_str = stdout.decode("utf-8", errors="replace")[:20000]
        stderr_str = stderr.decode("utf-8", errors="replace")[:20000]

        if process.returncode != 0 and not stderr_str and not stdout_str:
            stderr_str = (
                f"Command exited with code {process.returncode} and no output. "
                "The command may not exist or is not in PATH. "
                "On Windows, use PowerShell commands like 'Get-ChildItem' "
                "instead of Unix commands like 'ls'."
            )

        import platform as _plat
        result = {
            "success": process.returncode == 0,
            "command": command,
            "exit_code": process.returncode,
            "stdout": stdout_str,
            "stderr": stderr_str,
            "cwd": str(work_dir),
            "os": _plat.system(),
            "shell": "powershell" if _plat.system() == "Windows" else "bash",
        }
        if not result["success"]:
            result["hint"] = (
                "Command failed. On Windows, avoid Unix/Bash-only syntax "
                "like brace expansion {a,b}. Use Python pathlib or "
                "PowerShell-compatible commands instead."
            )
        return result

    async def _handle_ipython(
        self,
        code: str,
        session_mode: str = "continue",
        session_id: str | None = None,
        timeout_seconds: int = 30,
        restart: bool = False,
        conversation_id: str = "",
        workspace_id: str | None = None,
        permission_mode: str = "default",
        directory_access_mode: str = "locked_workspace",
        **_: Any,
    ) -> dict[str, Any]:
        from tools.ipython_runtime.ipython_tool import IPythonTool
        from tools.ipython_runtime.python_kernel_manager import PythonKernelManager
        from tools.ipython_runtime.python_sandbox import SandboxPolicy

        workspace_root = Path(settings.workspace_root).resolve()
        workspace_root.mkdir(parents=True, exist_ok=True)
        access_key = "full" if self._full_access(permission_mode, directory_access_mode) else "default"

        if access_key not in self._ipython_tools:
            policy = SandboxPolicy(
                workspace_root=workspace_root,
                allowed_output_dirs=() if access_key == "full" else ("outputs", "cache/python", "assets"),
                block_subprocess=access_key != "full",
                block_network=access_key != "full",
                block_pip_install=access_key != "full",
            )
            manager = PythonKernelManager(
                workspaces_root=workspace_root,
                sandbox_policy=policy,
                idle_timeout_seconds=3600.0,
            )
            await manager.start()
            self._ipython_managers[access_key] = manager
            self._ipython_tools[access_key] = IPythonTool(kernel_manager=manager, sandbox_policy=policy)

        mode = "reset" if restart else session_mode
        timeout = max(1, min(int(timeout_seconds), int(self._default_timeout) - 5))
        result = await self._ipython_tools[access_key].execute(
            conversation_id=workspace_id or conversation_id or "default",
            code=code,
            session_mode=mode,
            session_id=session_id,
            timeout_seconds=timeout,
        )
        payload = result.to_tool_response()
        payload["cwd"] = str(self._workspace_dir(conversation_id, workspace_id))
        payload["session_mode"] = mode
        return payload

    async def _handle_web_fetch(
        self,
        url: str,
        mode: str = "auto",
        targets: list[str] | None = None,
        timeout_ms: int = 20000,
        **_: Any,
    ) -> dict[str, Any]:
        research_mode = {
            "static": "fast",
            "dynamic": "deep",
            "auto": "auto",
            "fast": "fast",
            "balanced": "balanced",
            "deep": "deep",
            "ultra": "ultra",
        }.get(mode, "auto")
        return await self._handle_research_fetch(
            url=url,
            mode=research_mode,
            max_chars=20000,
        )

    async def _handle_legacy_web_fetch(
        self,
        url: str,
        mode: str = "auto",
        targets: list[str] | None = None,
        timeout_ms: int = 20000,
        **_: Any,
    ) -> dict[str, Any]:
        """Fetch URL using the AGENT ENT Fetch Mini Node.js tool.

        Calls the compiled CLI with JSON input and returns structured output.
        """
        fetch_tool_dir = Path(__file__).parent.parent.parent.parent.parent / "fetch_web_vonishagent_tool"
        cli_script = fetch_tool_dir / "dist" / "cli.js"

        if not cli_script.exists():
            return {
                "success": False,
                "url": url,
                "error": f"Fetch tool not found at {cli_script}",
            }

        payload = {
            "url": url,
            "mode": mode,
            "targets": targets or ["main_content", "resources", "frontend_source"],
            "timeout_ms": timeout_ms,
        }

        try:
            process = await asyncio.create_subprocess_exec(
                "node",
                str(cli_script),
                json.dumps(payload, ensure_ascii=False),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=max(timeout_ms / 1000 + 10, 30),
            )

            if process.returncode != 0:
                err = stderr.decode("utf-8", errors="replace")
                return {
                    "success": False,
                    "url": url,
                    "error": err[:2000],
                }

            import json as _json
            result = _json.loads(stdout.decode("utf-8", errors="replace"))

            # Return a summary suitable for LLM context
            summary = _json.dumps(
                {
                    "url": result.get("url"),
                    "final_url": result.get("final_url"),
                    "status": result.get("status"),
                    "title": result.get("title"),
                    "description": result.get("description"),
                    "mode_used": result.get("mode_used"),
                    "main_content": (
                        result.get("main_content", {}).get("text", "")[:8000]
                        if isinstance(result.get("main_content"), dict)
                        else None
                    ),
                    "resources": (
                        result.get("resources", {}).get("stats")
                        if isinstance(result.get("resources"), dict)
                        else None
                    ),
                    "frontend_source": {
                        "buttons": [
                            f"{b.get('text','')} ({b.get('selector','')})"
                            for b in (result.get("frontend_source", {}).get("buttons", []) or [])
                        ][:20],
                        "forms": len(result.get("frontend_source", {}).get("forms", [])),
                        "interactive_elements": len(
                            result.get("frontend_source", {}).get("interactive_elements", [])
                        ),
                    } if isinstance(result.get("frontend_source"), dict) else None,
                    "runtime_detection": result.get("runtime_detection"),
                    "warnings": result.get("warnings"),
                    "debug": result.get("debug"),
                },
                ensure_ascii=False,
                default=str,
            )
            return {
                "success": True,
                "url": url,
                "content": summary,
                "raw": result,
            }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "url": url,
                "error": f"Fetch timed out after {timeout_ms}ms",
            }
        except Exception as e:
            return {
                "success": False,
                "url": url,
                "error": str(e),
            }

    async def _handle_web_search(
        self,
        query: str,
        num_results: int = 5,
        max_time_ms: int = 15000,
        max_content_length: int = 8000,
        per_url_timeout_ms: int = 3000,
        max_per_url: int = 5000,
        **_: Any,
    ) -> dict[str, Any]:
        return await self._handle_research_search(
            query=query,
            mode="overview",
            max_results=num_results,
        )

    async def _handle_legacy_web_search(
        self,
        query: str,
        num_results: int = 5,
        max_time_ms: int = 15000,
        max_content_length: int = 8000,
        per_url_timeout_ms: int = 3000,
        max_per_url: int = 5000,
        **_: Any,
    ) -> dict[str, Any]:
        runner = (
            Path(__file__).resolve().parents[1]
            / "tool_runtimes"
            / "web_search"
            / "runner.mjs"
        )
        if not runner.exists():
            return {
                "success": False,
                "query": query,
                "error": f"web_search runner not found at {runner}",
            }

        max_results = max(1, min(int(num_results), 10))
        payload = {
            "query": query,
            "maxTime": max(3000, min(int(max_time_ms), 45000)),
            "maxContentLength": max(500, min(int(max_content_length), 50000)),
            "perUrlTimeout": max(500, min(int(per_url_timeout_ms), 15000)),
            "maxPerUrl": max(500, min(int(max_per_url), 30000)),
        }
        process = await asyncio.create_subprocess_exec(
            "node",
            str(runner),
            json.dumps(payload, ensure_ascii=False),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=payload["maxTime"] / 1000 + 15,
        )

        if process.returncode != 0:
            return {
                "success": False,
                "query": query,
                "error": stderr.decode("utf-8", errors="replace")[:4000],
            }

        data = json.loads(stdout.decode("utf-8", errors="replace"))
        results = data.get("results", [])[:max_results]
        return {
            "success": True,
            "query": query,
            "results": results,
            "stats": data.get("stats", {}),
            "source": "web-search_pipeline",
        }

    async def _handle_research_status(self, **_: Any) -> dict[str, Any]:
        from tools.research_runtime_client import HollowSearchCoreClient, ResearchRuntimeError

        try:
            health = await HollowSearchCoreClient().ensure_ready()
            return {"success": True, "status": health}
        except ResearchRuntimeError as error:
            return {"success": False, "error": error.to_dict()}

    async def _handle_research_search(
        self,
        query: str,
        mode: str = "overview",
        max_results: int = 20,
        language: str = "auto",
        **_: Any,
    ) -> dict[str, Any]:
        from tools.research_runtime_client import HollowSearchCoreClient, ResearchRuntimeError

        try:
            return await HollowSearchCoreClient().search(
                query=query,
                mode=mode,
                max_results=max_results,
                language=language,
            )
        except ResearchRuntimeError as error:
            return {"success": False, "error": error.to_dict(), "query": query}

    async def _handle_research_fetch(
        self,
        url: str,
        mode: str = "auto",
        max_chars: int = 20000,
        **_: Any,
    ) -> dict[str, Any]:
        from tools.research_runtime_client import HollowSearchCoreClient, ResearchRuntimeError

        try:
            return await HollowSearchCoreClient().fetch(
                url=url,
                mode=mode,
                max_chars=max_chars,
            )
        except ResearchRuntimeError as error:
            return {"success": False, "error": error.to_dict(), "url": url}

    async def _handle_deep_research(
        self,
        query: str,
        mode: str = "deep_dive",
        max_results: int = 15,
        max_pages: int = 8,
        build_evidence: bool = True,
        **_: Any,
    ) -> dict[str, Any]:
        from tools.research_runtime_client import HollowSearchCoreClient, ResearchRuntimeError

        try:
            return await HollowSearchCoreClient().deep_research(
                query=query,
                mode=mode,
                max_results=max_results,
                max_pages=max_pages,
                build_evidence=build_evidence,
            )
        except ResearchRuntimeError as error:
            return {"success": False, "error": error.to_dict(), "query": query}

    # ── File Read (with encoding) ──────────────────────────────────────

    async def _handle_file_read(
        self,
        path: str,
        encoding: str = "utf-8",
        start_line: int = 1,
        max_lines: int = 500,
        conversation_id: str = "",
        workspace_id: str | None = None,
        permission_mode: str = "default",
        directory_access_mode: str = "locked_workspace",
        **_: Any,
    ) -> Any:
        if encoding == "base64":
            import base64
            workspace = self._workspace_dir(conversation_id, workspace_id)
            allow_escape = self._full_access(permission_mode, directory_access_mode)
            raw_path = Path(path)
            fp = raw_path.resolve() if allow_escape and raw_path.is_absolute() else (workspace / raw_path).resolve()
            if not allow_escape and not str(fp).startswith(str(workspace)):
                return {"success": False, "path": path, "error": "Path escape blocked"}
            if not fp.is_file():
                return {"success": False, "path": path, "error": "File not found"}
            try:
                data = fp.read_bytes()
                encoded = base64.b64encode(data).decode("ascii")
                return {
                    "success": True,
                    "path": path,
                    "encoding": "base64",
                    "data": encoded,
                    "size": len(data),
                }
            except Exception as e:
                return {"success": False, "path": path, "error": str(e)}

        # Default: use _handle_read_file
        return await self._handle_read_file(
            path=path, start_line=start_line, max_lines=max_lines, conversation_id=conversation_id,
            workspace_id=workspace_id, permission_mode=permission_mode, directory_access_mode=directory_access_mode
        )

    # ── Delete File ────────────────────────────────────────────────────

    async def _handle_delete_file(
        self,
        path: str,
        conversation_id: str = "",
        workspace_id: str | None = None,
        permission_mode: str = "default",
        directory_access_mode: str = "locked_workspace",
        **_: Any,
    ) -> Any:
        from tools.file_tools import DeleteFileTool
        result = await DeleteFileTool().execute(self._tool_context(conversation_id, workspace_id, permission_mode, directory_access_mode), path=path)
        return self._tool_result_payload(result)

    # ── Apply Patch ────────────────────────────────────────────────────

    async def _handle_apply_patch(
        self,
        patch: str,
        conversation_id: str = "",
        workspace_id: str | None = None,
        permission_mode: str = "default",
        directory_access_mode: str = "locked_workspace",
        **_: Any,
    ) -> Any:
        from tools.file_tools import ApplyPatchTool
        result = await ApplyPatchTool().execute(self._tool_context(conversation_id, workspace_id, permission_mode, directory_access_mode), patch=patch)
        return self._tool_result_payload(result)

    # ── List Directory ─────────────────────────────────────────────────

    async def _handle_list_directory(
        self,
        path: str = "",
        recursive: bool = False,
        conversation_id: str = "",
        workspace_id: str | None = None,
        permission_mode: str = "default",
        directory_access_mode: str = "locked_workspace",
        **_: Any,
    ) -> dict[str, Any]:
        workspace = self._workspace_dir(conversation_id, workspace_id)
        allow_escape = self._full_access(permission_mode, directory_access_mode)
        raw_path = Path(path) if path else workspace
        target = raw_path.resolve() if allow_escape and raw_path.is_absolute() else (workspace / raw_path).resolve() if path else workspace
        if not allow_escape and not str(target).startswith(str(workspace)):
            return {"success": False, "error": "Path escape blocked"}
        if not target.is_dir():
            return {"success": False, "error": f"Not a directory: {path}"}

        entries: list[dict] = []
        if recursive:
            for root, dirs, files in __import__("os").walk(str(target)):
                rel_root = str(Path(root).relative_to(workspace)).replace("\\", "/")
                if rel_root == ".":
                    rel_root = ""
                for d in dirs:
                    entries.append({"name": d, "path": f"{rel_root}/{d}".lstrip("/"), "type": "folder"})
                for f in files:
                    fp = Path(root) / f
                    entries.append({
                        "name": f,
                        "path": f"{rel_root}/{f}".lstrip("/"),
                        "type": "file",
                        "size": fp.stat().st_size if fp.exists() else 0,
                    })
        else:
            for item in sorted(target.iterdir()):
                rel = str(item.relative_to(workspace)).replace("\\", "/")
                entry: dict = {"name": item.name, "path": rel, "type": "folder" if item.is_dir() else "file"}
                if item.is_file():
                    entry["size"] = item.stat().st_size
                entries.append(entry)

        return {"success": True, "path": path or ".", "entries": entries, "count": len(entries)}

    # ── Workspace Snapshot ─────────────────────────────────────────────

    async def _handle_snapshot(
        self,
        include_files: bool = True,
        conversation_id: str = "",
        workspace_id: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        workspace = self._workspace_dir(conversation_id, workspace_id)
        files: list[dict] = []
        total_size = 0
        if include_files:
            for root, dirs, filenames in __import__("os").walk(str(workspace)):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for f in filenames:
                    fp = Path(root) / f
                    try:
                        st = fp.stat()
                        files.append({
                            "path": str(fp.relative_to(workspace)).replace("\\", "/"),
                            "size": st.st_size,
                            "modified_at": __import__("datetime").datetime.fromtimestamp(
                                st.st_mtime
                            ).isoformat(),
                        })
                        total_size += st.st_size
                    except OSError:
                        pass

        return {
            "success": True,
            "workspace": str(workspace),
            "file_count": len(files),
            "total_size": total_size,
            "files": files[:200],
        }

    # ── Search Workspace ──────────────────────────────────────────────

    async def _handle_search_workspace(
        self,
        pattern: str = "",
        path: str = ".",
        regex: bool = False,
        case_sensitive: bool = False,
        include_globs: list[str] | None = None,
        exclude_globs: list[str] | None = None,
        max_results: int = 50,
        context_lines: int = 2,
        conversation_id: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        from agent.tool_handlers.search_workspace import handle_search_workspace
        return await handle_search_workspace(
            conversation_id=conversation_id,
            pattern=pattern,
            path=path,
            regex=regex,
            case_sensitive=case_sensitive,
            include_globs=include_globs,
            exclude_globs=exclude_globs,
            max_results=max_results,
            context_lines=context_lines,
        )

    # ── Create Directories ────────────────────────────────────────────

    async def _handle_create_directories(
        self,
        paths: list[str],
        conversation_id: str = "",
        workspace_id: str | None = None,
        permission_mode: str = "default",
        directory_access_mode: str = "locked_workspace",
        **_: Any,
    ) -> dict[str, Any]:
        ws = self._workspace_dir(conversation_id, workspace_id)
        allow_escape = self._full_access(permission_mode, directory_access_mode)
        created: list[str] = []
        already: list[str] = []
        failed: list[str] = []
        for p in paths:
            raw_path = Path(p)
            target = raw_path.resolve() if allow_escape and raw_path.is_absolute() else (ws / raw_path).resolve()
            if not allow_escape and not str(target).startswith(str(ws.resolve())):
                failed.append(p)
                continue
            try:
                if target.exists():
                    already.append(p)
                else:
                    target.mkdir(parents=True, exist_ok=True)
                    created.append(p)
            except Exception:
                failed.append(p)
        return {"created": created, "alreadyExists": already, "failed": failed}

    # ── Git Workspace Tools ───────────────────────────────────────────

    def _resolve_tool_workspace_id(self, workspace_id: str = "current", conversation_id: str = "") -> str:
        if not workspace_id or workspace_id == "current":
            return conversation_id or "default"
        return workspace_id

    async def _handle_git_status(
        self,
        workspace_id: str = "current",
        conversation_id: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        from services.git_service import git_status

        return await git_status(self._resolve_tool_workspace_id(workspace_id, conversation_id))

    async def _handle_git_diff(
        self,
        workspace_id: str = "current",
        scope: str = "working",
        file_path: str | None = None,
        context_lines: int = 3,
        commit: str | None = None,
        conversation_id: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        from services.git_service import git_diff

        return await git_diff(
            self._resolve_tool_workspace_id(workspace_id, conversation_id),
            scope=scope,
            file_path=file_path,
            context_lines=context_lines,
            commit=commit,
        )

    async def _handle_git_history(
        self,
        workspace_id: str = "current",
        mode: str = "log",
        file_path: str | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
        limit: int = 20,
        conversation_id: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        from services.git_service import git_history

        return await git_history(
            self._resolve_tool_workspace_id(workspace_id, conversation_id),
            mode=mode,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            limit=limit,
        )

    # ── Set Todo List ─────────────────────────────────────────────────

    async def _handle_set_todo_list(
        self,
        mode: str,
        conversation_id: str = "",
        items: list[dict] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        from agent.interaction_tools import handle_set_todo_list
        return await handle_set_todo_list(mode=mode, conversation_id=conversation_id, items=items or [])

    # ── Ask User Question ─────────────────────────────────────────────

    async def _handle_ask_user_question(
        self,
        conversation_id: str = "",
        question: str = "",
        description: str = "",
        options: list[dict] | None = None,
        allow_custom_response: bool = True,
        custom_placeholder: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        from agent.interaction_tools import handle_ask_user_question
        return await handle_ask_user_question(
            conversation_id=conversation_id,
            question=question,
            description=description,
            options=options or [],
            allow_custom_response=allow_custom_response,
            custom_placeholder=custom_placeholder,
        )

    # ── Request Approval ──────────────────────────────────────────────

    async def _handle_request_approval(
        self,
        conversation_id: str = "",
        title: str = "",
        description: str = "",
        risk_level: str = "medium",
        plan: list[dict] | None = None,
        allow_custom_response: bool = True,
        **_: Any,
    ) -> dict[str, Any]:
        from agent.interaction_tools import handle_request_approval
        return await handle_request_approval(
            conversation_id=conversation_id,
            title=title,
            description=description,
            risk_level=risk_level,
            plan=plan or [],
            allow_custom_response=allow_custom_response,
        )


# ---------------------------------------------------------------------------
# Workspace Tool Handlers
# ---------------------------------------------------------------------------


def register_workspace_handlers(executor: ToolExecutor) -> None:
    """Register handlers for all workspace tools.

    Each handler is wrapped so that *conversation_id* is automatically
    injected from the ToolCallRequest into the tool arguments.
    """
    # Lazy import to avoid circular dependencies
    from workspace.tools import (
        get_workspace_summary,
        list_workspace_files,
        read_workspace_file,
    )

    def _inject_conversation_id(
        handler, request_attr: str = "conversation_id"
    ):
        """Wrap a handler to inject conversation_id from the request."""

        async def _wrapper(**kwargs):
            # conversation_id is injected by execute() via the closure below
            return await handler(**kwargs)

        return _wrapper

    # Register list_workspace_files
    executor.register_handler(
        "list_workspace_files",
        list_workspace_files,
    )

    # Register read_workspace_file
    executor.register_handler(
        "read_workspace_file",
        read_workspace_file,
    )

    # Register get_workspace_summary
    executor.register_handler(
        "get_workspace_summary",
        get_workspace_summary,
    )

    logger.info("Registered 3 workspace tool handlers")


# ---------------------------------------------------------------------------
# Global Executor Instance
# ---------------------------------------------------------------------------

_executor: ToolExecutor | None = None


def get_tool_executor() -> ToolExecutor:
    """Get the global tool executor instance.

    Automatically registers workspace tool handlers on first creation.
    """
    global _executor
    if _executor is None:
        _executor = ToolExecutor()
        register_workspace_handlers(_executor)
    return _executor
