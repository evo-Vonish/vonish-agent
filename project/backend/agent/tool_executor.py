"""Tool Executor for the Agent system.

Executes tool calls, manages the tool result lifecycle,
and handles error recovery.
"""

from __future__ import annotations

import asyncio
import html
import json
import mimetypes
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
            result_error = self._extract_tool_error(result)

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
            "open_artifact": self._handle_open_artifact,
            "list_artifact_skills": self._handle_list_artifact_skills,
            "read_artifact_skill": self._handle_read_artifact_skill,
            "generate_presentation": self._handle_generate_presentation,
            "list_presentation_options": self._handle_list_presentation_options,
            "delete_file": self._handle_delete_file,
            "apply_patch": self._handle_apply_patch,
            "list_directory": self._handle_list_directory,
            "snapshot": self._handle_snapshot,
            "search_workspace": self._handle_search_workspace,
            "create_directories": self._handle_create_directories,
            "git_status": self._handle_git_status,
            "git_diff": self._handle_git_diff,
            "git_history": self._handle_git_history,
            "git_checkpoint": self._handle_git_checkpoint,
            "expand_tool_result": self._handle_expand_tool_result,
            "CRAZY_for_tool_results": self._handle_crazy_for_tool_results,
            "recall_maximum": self._handle_recall_maximum,
            "focus_tool_results": self._handle_focus_tool_results,
            "context_map": self._handle_context_map,
            "custom_context_recall": self._handle_custom_context_recall,
            "pin_memory": self._handle_pin_memory,
            "unpin_memory": self._handle_unpin_memory,
            "set_todo_list": self._handle_set_todo_list,
            "ask_user_question": self._handle_ask_user_question,
            "request_approval": self._handle_request_approval,
        }
        return default_handlers.get(tool_name)

    @staticmethod
    def _extract_tool_error(result: Any) -> str | None:
        """Extract a readable error from a failed structured tool payload."""
        if not isinstance(result, dict) or result.get("success") is not False:
            return None
        for key in ("error", "error_message", "message", "stderr", "stdout", "hint"):
            value = result.get(key)
            if value:
                text = str(value).strip()
                if text:
                    return text[:2000]
        exit_code = result.get("exit_code")
        if exit_code is not None:
            return f"Tool exited with code {exit_code}."
        return "Tool reported success=false but did not provide an error message."

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
        if not payload.get("success") and payload.get("error_name") == "SecurityViolation":
            payload["guidance"] = (
                "Python sandbox blocked this code under locked workspace permissions. "
                "For network/ssl/subprocess work, use web_fetch/research_fetch/shell_command, "
                "or switch directory access to full access if the user explicitly allows it."
            )
        return payload

    async def _handle_open_artifact(
        self,
        path: str,
        title: str = "",
        description: str = "",
        conversation_id: str = "",
        workspace_id: str | None = None,
        permission_mode: str = "default",
        directory_access_mode: str = "locked_workspace",
        **_: Any,
    ) -> dict[str, Any]:
        """Ask the frontend to open a workspace artifact in the Workbench."""
        ws = self._workspace_dir(conversation_id, workspace_id)
        allow_escape = self._full_access(permission_mode, directory_access_mode)
        raw_path = Path(str(path or "").strip())
        if not str(path or "").strip():
            return {"success": False, "error": "path is required"}
        fp = raw_path.resolve() if allow_escape and raw_path.is_absolute() else (ws / raw_path).resolve()
        if not allow_escape and not str(fp).startswith(str(ws)):
            return {"success": False, "path": path, "error": "Path escape blocked"}
        if not fp.exists() or not fp.is_file():
            return {"success": False, "path": path, "error": "Artifact file does not exist"}

        rel_path = str(fp.relative_to(ws)).replace("\\", "/") if str(fp).startswith(str(ws)) else str(fp)
        mime_type, _ = mimetypes.guess_type(str(fp))
        stat = fp.stat()
        artifact = {
            "id": f"artifact_{conversation_id}_{rel_path}".replace("\\", "/"),
            "title": title or fp.name,
            "path": rel_path,
            "workspaceId": workspace_id or conversation_id,
            "mimeType": mime_type or "application/octet-stream",
            "size": stat.st_size,
            "description": description,
        }
        return {
            "success": True,
            "open_artifact": True,
            "artifact": artifact,
            "guidance": (
                "The artifact has been handed to the frontend Workbench. Tell the user what to inspect "
                "and invite targeted edits using selections/references."
            ),
        }

    async def _handle_list_artifact_skills(self, **_: Any) -> dict[str, Any]:
        """List bundled artifact production skills."""
        from services.artifact_skill_service import available_artifact_skills

        return available_artifact_skills()

    async def _handle_list_presentation_options(self, **_: Any) -> dict[str, Any]:
        """List PPT engine themes + layouts for the agent to choose from."""
        from ppt_engine.registry import get_layout_registry, get_theme_registry

        return {
            "success": True,
            "themes": get_theme_registry().summaries(),
            "layouts": get_layout_registry().summaries(),
            "guidance": (
                "Pick one theme_id for the whole deck and a layout per slide, then call "
                "generate_presentation. Provide only content — the engine computes geometry, "
                "colour, and font sizes, and validates/auto-repairs before delivery."
            ),
        }

    async def _handle_generate_presentation(
        self,
        title: str = "",
        theme_id: str = "tech-dark",
        slides: list[dict[str, Any]] | None = None,
        filename: str = "",
        conversation_id: str = "",
        workspace_id: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        """Run the PPT Artifact Engine and hand the deck to the Workbench."""
        from ppt_engine.builder import build_deck_spec
        from ppt_engine.engine import generate_deck

        if not slides:
            return {"success": False, "error": "slides is required (at least one slide)."}

        ws = self._workspace_dir(conversation_id, workspace_id)
        import re as _re

        base = _re.sub(r"[^\w\-]+", "-", (filename or title or "deck").strip()).strip("-").lower() or "deck"
        deck_id = f"{base[:40]}-{int(time.time())}"
        try:
            spec = build_deck_spec(title=title, theme_id=theme_id, slides=slides, deck_id=deck_id)
            result = await asyncio.to_thread(generate_deck, spec, str(ws))
        except Exception as exc:  # never crash the agent loop on a bad deck
            logger.exception("generate_presentation failed")
            return {"success": False, "error": f"Presentation generation failed: {exc}"}

        v = result.validation
        artifact = {
            "id": result.artifact_id,
            "title": result.title or title or "Presentation",
            "path": result.pptx_path,
            "workspaceId": workspace_id or conversation_id,
            "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "kind": "presentation",
            "deckId": result.deck_id,
            "themeId": result.theme_id,
            "slideCount": result.slide_count,
            "previews": [p.model_dump() for p in result.previews],
            "manifestPath": result.manifest_path,
            "deckSpecPath": result.deck_spec_path,
            "slideIrPath": result.slide_ir_path,
            "validation": {
                "grade": v.delivery_grade,
                "deliverable": v.deliverable,
                "errors": v.summary.error_count,
                "warnings": v.summary.warning_count,
                "autoFixed": v.summary.auto_fixed,
                "repairRounds": v.repair_rounds,
                "blocking": v.blocking_issue_types,
            },
        }
        unresolved = [i.model_dump() for i in v.issues
                      if i.severity.value == "error" and not i.auto_fixed]
        return {
            "success": True,
            "open_artifact": True,
            "artifact": artifact,
            "validation_report": {
                "grade": v.delivery_grade,
                "deliverable": v.deliverable,
                "summary": v.summary.model_dump(),
                "blocking_issue_types": v.blocking_issue_types,
                "unresolved_errors": unresolved[:20],
            },
            "previews": [p.model_dump() for p in result.previews],
            "generation_log": result.generation_log,
            "guidance": (
                f"Deck delivered: {result.slide_count} slides, theme '{result.theme_id}', "
                f"grade '{v.delivery_grade}' ({v.summary.error_count} errors, "
                f"{v.summary.warning_count} warnings, {v.summary.auto_fixed} auto-fixed). "
                + ("All blocking checks passed; the PPTX and per-page previews are in the Workbench."
                   if v.deliverable else
                   "NOT deliverable — blocking errors remain; tell the user which slides need rework "
                   "and offer to regenerate. Do not present this as finished.")
            ),
        }

    async def _handle_read_artifact_skill(
        self,
        skill: str,
        files: list[str] | None = None,
        include_shared: bool = True,
        **_: Any,
    ) -> dict[str, Any]:
        """Read a bundled artifact production skill for model guidance."""
        from services.artifact_skill_service import read_artifact_skill

        return read_artifact_skill(skill=skill, files=files, include_shared=include_shared)

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
            client = HollowSearchCoreClient()
            health = await client.ensure_ready()
            pipeline = await client.pipeline_health()
            pipeline_ok = all(
                bool(pipeline.get(key))
                for key in ("service_alive", "search_ok", "fetch_ok", "extract_ok", "result_store_ok")
            )
            return {
                "success": True,
                "status": "ok" if pipeline_ok else "degraded",
                "health": health,
                "pipeline": pipeline,
            }
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

    async def _handle_git_checkpoint(
        self,
        workspace_id: str = "current",
        kind: str = "agent_milestone",
        message: str = "",
        artifacts: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        conversation_id: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        from services.git_timeline_service import create_checkpoint, record_artifact_versions

        resolved_workspace_id = self._resolve_tool_workspace_id(workspace_id, conversation_id)
        result = await create_checkpoint(
            resolved_workspace_id,
            kind,
            message or kind,
            conversation_id=conversation_id or None,
            created_by="agent",
            metadata=metadata or {},
            allow_agent_kind=True,
        )
        payload = result.__dict__
        if result.success and kind == "artifact_version" and conversation_id:
            payload["artifact_versions"] = await record_artifact_versions(
                resolved_workspace_id,
                conversation_id,
                result.commit_hash,
                artifacts or [],
                label=message,
            )
        return payload

    # ── Tool Result Expansion ─────────────────────────────────────────

    async def _handle_expand_tool_result(
        self,
        tool_result_id: str = "",
        tool_name: str = "",
        builds: int = 3,
        conversation_id: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        """Return one complete stored tool result and open a 3-build window."""
        import uuid as _uuid

        from sqlalchemy import select

        from context.minimal_context import (
            TOOL_RESULT_EXPANSION_BUILDS,
            mark_tool_result_expanded,
        )
        from db.models import ToolCall
        from db.session import get_session_maker

        if not conversation_id:
            return {"success": False, "error": "conversation_id is required"}
        if not tool_result_id and not tool_name:
            return {"success": False, "error": "Provide tool_result_id or tool_name."}

        if tool_result_id.startswith("research_"):
            from context.minimal_context import (
                TOOL_RESULT_EXPANSION_BUILDS,
                mark_tool_result_expanded,
            )
            from tools.research_runtime_client import get_research_result_store

            stored = get_research_result_store().get(tool_result_id)
            if stored is None:
                return {
                    "success": False,
                    "error": f"Stored research content not found: {tool_result_id}",
                    "hint": "The reference may be from an older backend process or another conversation.",
                }
            mark_tool_result_expanded(
                conversation_id,
                tool_result_id,
                builds=builds or TOOL_RESULT_EXPANSION_BUILDS,
            )
            return {
                "success": True,
                "tool_result_id": tool_result_id,
                "content_ref": tool_result_id,
                "tool_name": "research_content",
                "expanded_for_context_builds": builds or TOOL_RESULT_EXPANSION_BUILDS,
                "url": stored.url,
                "title": stored.title,
                "content_hash": stored.content_hash,
                "content": stored.content,
                "metadata": stored.metadata,
            }

        try:
            conv_uuid = _uuid.UUID(conversation_id)
        except ValueError:
            return {"success": False, "error": "Invalid conversation_id"}

        session_maker = get_session_maker()
        async with session_maker() as db:
            query = select(ToolCall).where(ToolCall.conversation_id == conv_uuid)
            if tool_result_id:
                normalized_id = tool_result_id.removeprefix("history_")
                try:
                    result_uuid = _uuid.UUID(normalized_id)
                except ValueError:
                    return {"success": False, "error": f"Invalid tool_result_id: {tool_result_id}"}
                query = query.where(ToolCall.id == result_uuid)
            else:
                query = query.where(ToolCall.tool_name == tool_name)
            query = query.order_by(ToolCall.created_at.desc()).limit(1)
            row = (await db.execute(query)).scalar_one_or_none()

        if row is None:
            target = tool_result_id or tool_name
            return {"success": False, "error": f"Stored tool result not found: {target}"}

        result_id = str(row.id)
        mark_tool_result_expanded(
            conversation_id,
            result_id,
            builds=builds or TOOL_RESULT_EXPANSION_BUILDS,
        )
        return {
            "success": True,
            "tool_result_id": result_id,
            "tool_name": row.tool_name,
            "expanded_for_context_builds": builds or TOOL_RESULT_EXPANSION_BUILDS,
            "content": row.result,
        }

    async def _handle_crazy_for_tool_results(
        self,
        builds: int = 2,
        reason: str = "",
        conversation_id: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        """Expand every tool result for upcoming context builds."""
        if not conversation_id:
            return {"success": False, "error": "conversation_id is required"}
        from context.minimal_context import expansion_state, mark_all_tool_results_expanded

        safe_builds = max(1, min(int(builds or 2), 8))
        mark_all_tool_results_expanded(conversation_id, safe_builds)
        return {
            "success": True,
            "mode": "all_tool_results",
            "expanded_for_context_builds": safe_builds,
            "reason": reason,
            "guidance": (
                "All stored tool results will be full in upcoming context builds. "
                "Use this for final report synthesis or broad evidence review, then continue directly."
            ),
            "state": expansion_state(conversation_id),
        }

    async def _handle_recall_maximum(
        self,
        turns: int = 3,
        scope: str = "current_task",
        maxTokens: int | None = None,
        priority: list[str] | None = None,
        includeRaw: bool = False,
        includeKeySegments: bool = True,
        query: str = "",
        reason: str = "",
        conversation_id: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        """Activate a broad recall window and return the current context map."""
        if not conversation_id:
            return {"success": False, "error": "conversation_id is required"}
        from context.context_memory import activate_max_recall_window, build_context_map
        from context.minimal_context import expansion_state, mark_all_tool_results_expanded, mark_tool_result_focus

        safe_turns = max(1, min(int(turns or 3), 10))
        safe_tokens = max(4_000, min(int(maxTokens or 80_000), 180_000))
        recall_window = await activate_max_recall_window(
            conversation_id=conversation_id,
            turns=safe_turns,
            scope=scope,
            max_tokens=safe_tokens,
            priority=priority,
            include_raw=includeRaw,
            include_key_segments=includeKeySegments,
            query=query,
            reason=reason,
        )
        if includeRaw or scope in {"research", "debugging", "coding", "artifact", "all_recent", "current_task"}:
            if query:
                mark_tool_result_focus(conversation_id, query=query, builds=safe_turns)
            else:
                mark_all_tool_results_expanded(conversation_id, safe_turns)
        context_map = await build_context_map(conversation_id, scope=scope)
        return {
            "success": True,
            "status": "active",
            "scope": scope,
            "turnsRemaining": safe_turns,
            "maxTokens": safe_tokens,
            "priority": priority or [
                "user_constraints",
                "tool_results",
                "research_evidence",
                "file_reads",
                "diffs",
                "errors",
                "plans",
                "chat_messages",
            ],
            "includeRaw": bool(includeRaw),
            "includeKeySegments": bool(includeKeySegments),
            "query": query,
            "reason": reason,
            "recallWindow": recall_window,
            "contextMap": context_map,
            "toolResultExpansionState": expansion_state(conversation_id),
            "guidance": (
                "MAX recall is active for upcoming context builds. Use the map to target exact recalls; "
                "do not assume compressed summaries are raw source text."
            ),
        }

    async def _handle_focus_tool_results(
        self,
        tool_result_ids: list[str] | None = None,
        tool_names: list[str] | None = None,
        query: str = "",
        status: str = "any",
        latest: int = 5,
        builds: int = 3,
        conversation_id: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        """Expand matching tool results by id, name, query, status, and recency."""
        if not conversation_id:
            return {"success": False, "error": "conversation_id is required"}

        import uuid as _uuid
        from sqlalchemy import select

        from context.minimal_context import (
            expansion_state,
            mark_tool_result_focus,
            serialize_tool_result,
        )
        from db.models import ToolCall
        from db.session import get_session_maker

        try:
            conv_uuid = _uuid.UUID(conversation_id)
        except ValueError:
            return {"success": False, "error": "Invalid conversation_id"}

        safe_builds = max(1, min(int(builds or 3), 12))
        safe_latest = max(0, min(int(latest or 0), 50))
        requested_ids = [str(item).removeprefix("history_") for item in (tool_result_ids or []) if item]
        names = [str(item) for item in (tool_names or []) if item]
        status_filter = status if status in {"completed", "failed"} else "any"
        query_text = str(query or "").strip()

        matches: list[dict[str, Any]] = []
        matched_ids: list[str] = []
        session_maker = get_session_maker()
        async with session_maker() as db:
            db_query = select(ToolCall).where(ToolCall.conversation_id == conv_uuid)
            if status_filter != "any":
                db_query = db_query.where(ToolCall.status == status_filter)
            if names:
                db_query = db_query.where(ToolCall.tool_name.in_(names))
            db_query = db_query.order_by(ToolCall.created_at.desc()).limit(max(safe_latest, len(requested_ids), 1) + 40)
            rows = list((await db.execute(db_query)).scalars().all())

        requested_set = set(requested_ids)
        terms = [term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]{2,}", query_text)[:12]]
        for row in rows:
            row_id = str(row.id)
            serialized = serialize_tool_result(row.result if row.result is not None else {})
            haystack = f"{row.tool_name}\n{row.arguments}\n{serialized}".lower()
            id_match = row_id in requested_set
            query_match = bool(terms) and all(term in haystack for term in terms[:8])
            name_match = bool(names) and row.tool_name in names
            recency_match = safe_latest > 0 and len(matches) < safe_latest and not requested_set and not terms and not names
            if not (id_match or query_match or name_match or recency_match):
                continue
            matched_ids.append(row_id)
            matches.append(
                {
                    "tool_result_id": row_id,
                    "tool_name": row.tool_name,
                    "status": row.status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "preview": serialized[:500],
                }
            )
            if len(matches) >= max(safe_latest, len(requested_set), 1):
                break

        mark_tool_result_focus(
            conversation_id,
            tool_result_ids=matched_ids + requested_ids,
            tool_names=names,
            query=query_text,
            builds=safe_builds,
        )
        return {
            "success": True,
            "mode": "focused_tool_results",
            "expanded_for_context_builds": safe_builds,
            "matched_count": len(matches),
            "matches": matches,
            "query": query_text,
            "tool_names": names,
            "state": expansion_state(conversation_id),
            "guidance": (
                "Matching tool results will be full in upcoming context builds. "
                "Continue the current analysis/synthesis using those recalled details."
            ),
        }

    async def _handle_context_map(
        self,
        scope: str = "all",
        conversation_id: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        """Return a compact map of recallable conversation memory."""
        if not conversation_id:
            return {"success": False, "error": "conversation_id is required"}
        from context.context_memory import build_context_map

        return await build_context_map(conversation_id, scope=scope)

    async def _handle_custom_context_recall(
        self,
        targets: list[dict[str, Any]] | None = None,
        turns: int = 1,
        maxTokens: int = 4000,
        mode: str = "summary_plus_segments",
        reason: str = "",
        workspace_id: str = "current",
        conversation_id: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        """Recall exact or structured content from messages, tools, files, or grep."""
        if not conversation_id:
            return {"success": False, "error": "conversation_id is required"}
        from context.context_memory import custom_context_recall

        resolved_workspace_id = self._resolve_tool_workspace_id(workspace_id, conversation_id)
        return await custom_context_recall(
            conversation_id=conversation_id,
            workspace_id=resolved_workspace_id,
            targets=targets or [],
            turns=turns,
            max_tokens=maxTokens,
            mode=mode,
            reason=reason,
        )

    async def _handle_pin_memory(
        self,
        target: dict[str, Any] | None = None,
        reason: str = "",
        expiresAfterTurns: int | None = None,
        conversation_id: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        """Pin a constraint, file, decision, error, plan, or note into context memory."""
        if not conversation_id:
            return {"success": False, "error": "conversation_id is required"}
        from context.context_memory import pin_memory

        return await pin_memory(
            conversation_id=conversation_id,
            target=target or {},
            reason=reason,
            expires_after_turns=expiresAfterTurns,
        )

    async def _handle_unpin_memory(
        self,
        targetId: str = "",
        conversation_id: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        """Deactivate one pinned memory item."""
        if not conversation_id:
            return {"success": False, "error": "conversation_id is required"}
        if not targetId:
            return {"success": False, "error": "targetId is required"}
        from context.context_memory import unpin_memory

        return await unpin_memory(conversation_id=conversation_id, target_id=targetId)

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
