"""Tool Executor for the Agent system.

Executes tool calls, manages the tool result lifecycle,
and handles error recovery.
"""

from __future__ import annotations

import asyncio
import html
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
        self._default_timeout: float = 60.0

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

            # Execute with timeout
            result = await asyncio.wait_for(
                handler(**arguments),
                timeout=self._default_timeout,
            )

            execution_time = (time.monotonic() - start_time) * 1000

            return ToolCallResult(
                tool_name=request.tool_name,
                call_id=call_id,
                success=True,
                result=result,
                execution_time_ms=execution_time,
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
            "edit_file": self._handle_edit_file,
            "shell_command": self._handle_shell_command,
            "ipython": self._handle_ipython,
            "web_fetch": self._handle_web_fetch,
            "web_search": self._handle_web_search,
        }
        return default_handlers.get(tool_name)

    def _workspace_dir(self, conversation_id: str = "") -> Path:
        """Return the conversation workspace directory and ensure it exists."""
        workspace_id = conversation_id or "default"
        root = (Path(settings.workspace_root).resolve() / workspace_id).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _tool_context(self, conversation_id: str = "") -> Any:
        from tools.context import ToolContext

        workspace = self._workspace_dir(conversation_id)
        return ToolContext(
            conversation_id=conversation_id or "default",
            workspace_root=str(workspace),
            user_id="default",
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
        start_line: int = 1,
        max_lines: int = 200,
        **_: Any,
    ) -> Any:
        from tools.file_tools import ReadFileTool

        result = await ReadFileTool().execute(
            self._tool_context(conversation_id),
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
        **_: Any,
    ) -> Any:
        from tools.file_tools import EditFileTool

        result = await EditFileTool().execute(
            self._tool_context(conversation_id),
            path=path,
            old_text=old_string,
            new_text=new_string,
        )
        return self._tool_result_payload(result)

    async def _handle_shell_command(
        self,
        command: str,
        timeout: int = 30,
        conversation_id: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        workspace = self._workspace_dir(conversation_id)
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(workspace),
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
                "cwd": str(workspace),
            }

        return {
            "success": process.returncode == 0,
            "command": command,
            "exit_code": process.returncode,
            "stdout": stdout.decode("utf-8", errors="replace")[:20000],
            "stderr": stderr.decode("utf-8", errors="replace")[:20000],
            "cwd": str(workspace),
        }

    async def _handle_ipython(
        self,
        code: str,
        conversation_id: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        workspace = self._workspace_dir(conversation_id)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=self._default_timeout,
        )
        return {
            "success": process.returncode == 0,
            "exit_code": process.returncode,
            "stdout": stdout.decode("utf-8", errors="replace")[:20000],
            "stderr": stderr.decode("utf-8", errors="replace")[:20000],
            "cwd": str(workspace),
        }

    async def _handle_web_fetch(
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
        **_: Any,
    ) -> dict[str, Any]:
        import httpx

        max_results = max(1, min(int(num_results), 10))
        search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, trust_env=False) as client:
            response = await client.get(
                search_url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
        response.raise_for_status()

        results: list[dict[str, str]] = []
        for match in re.finditer(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            response.text,
            re.IGNORECASE | re.DOTALL,
        ):
            href = html.unescape(match.group(1))
            title = re.sub(r"<[^>]+>", "", match.group(2))
            title = html.unescape(re.sub(r"\s+", " ", title)).strip()
            results.append({"title": title, "url": urljoin(str(response.url), href)})
            if len(results) >= max_results:
                break

        return {
            "success": True,
            "query": query,
            "results": results,
            "source": "duckduckgo_html",
        }


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
