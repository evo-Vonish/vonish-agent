"""
Python Sandbox - Security layer for iPython Tool.

Enforces:
- Workspace path isolation (no traversal outside workspace)
- Resource limits (timeout, memory, output size)
- Dangerous call blocking (subprocess, network, system calls)
- Pre-execution code validation
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Dangerous modules and calls to block ──────────────────────────────────────

_BLOCKED_MODULES: set[str] = {
    "subprocess",
    "os.system",
    "os.execv",
    "os.execve",
    "os.fork",
    "os.kill",
    "os.popen",
    "os.spawn",
    "pty",
    "socket",
    "socketserver",
    "http.server",
    "ftplib",
    "telnetlib",
    "ssl",
    "urllib.request",
    "urllib.urlopen",
    "ctypes",
    "ctypes.util",
    "mmap",
    "sysconfig",
}

_BLOCKED_CALLS: set[str] = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "input",
    "raw_input",
}


# ── Sandbox Policy Configuration ──────────────────────────────────────────────


@dataclass
class SandboxPolicy:
    """Configuration for sandbox restrictions."""

    # Time & resource limits
    timeout_seconds: int = 30
    max_memory_mb: int = 2048
    max_stdout_chars: int = 10000
    max_stderr_chars: int = 10000
    max_file_size_mb: int = 10

    # Path restrictions
    workspace_root: Path = field(default_factory=lambda: Path("/tmp/workspace"))
    allowed_output_dirs: tuple[str, ...] = ("outputs", "cache/python", "assets")

    # Feature flags
    block_subprocess: bool = True
    block_network: bool = True
    block_pip_install: bool = True


# ── Code Validator ────────────────────────────────────────────────────────────


class PathEscapeError(Exception):
    """Raised when code attempts to access files outside the workspace."""


class SecurityViolationError(Exception):
    """Raised when code contains blocked imports or calls."""


class CodeValidator:
    """Static analysis of Python code for security violations."""

    def __init__(self, policy: SandboxPolicy | None = None) -> None:
        self.policy = policy or SandboxPolicy()

    def validate(self, code: str) -> list[str]:
        """Validate code and return list of violations (empty if clean)."""
        violations: list[str] = []

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [f"Syntax error: {e}"]

        for node in ast.walk(tree):
            # Check import statements
            if isinstance(node, ast.Import):
                for alias in node.names:
                    base_module = alias.name.split(".")[0]
                    if self.policy.block_subprocess and base_module in _BLOCKED_MODULES:
                        violations.append(f"Blocked import: {alias.name}")

            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")[0]
                if self.policy.block_subprocess and module in _BLOCKED_MODULES:
                    violations.append(f"Blocked import from: {node.module}")

            # Check dangerous calls
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if self.policy.block_subprocess and node.func.id in _BLOCKED_CALLS:
                        violations.append(f"Blocked call: {node.func.id}()")
                elif isinstance(node.func, ast.Attribute):
                    # Check for os.system, subprocess.Popen, etc.
                    call_name = self._get_attribute_chain(node.func)
                    if self.policy.block_subprocess and call_name in _BLOCKED_MODULES:
                        violations.append(f"Blocked call: {call_name}()")

        # Regex-based checks for pip install patterns
        pip_patterns = [
            r"!\s*pip\s+(install|uninstall)",
            r"os\.system\s*\(\s*['\"]\s*pip",
            r"subprocess\.\w+\s*\(.*pip",
        ]
        for pattern in pip_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                if self.policy.block_pip_install:
                    violations.append("pip install is blocked in MVP")
                break

        # Check for shell escape patterns
        shell_patterns = [
            r"os\.system\s*\(",
            r"os\.popen\s*\(",
            r"subprocess\.\w+\s*\(",
            r"pty\.\w+\s*\(",
        ]
        for pattern in shell_patterns:
            if self.policy.block_subprocess and re.search(pattern, code):
                violations.append(f"Shell execution blocked: pattern '{pattern}' detected")
                break

        return violations

    def validate_or_raise(self, code: str) -> None:
        """Validate code, raise SecurityViolationError if violations found."""
        violations = self.validate(code)
        if violations:
            raise SecurityViolationError(
                f"Security violations detected ({len(violations)}): "
                + "; ".join(violations)
            )

    @staticmethod
    def _get_attribute_chain(node: ast.Attribute) -> str:
        """Extract the full dotted name from an attribute access."""
        parts: list[str] = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))


# ── Startup Scripts ───────────────────────────────────────────────────────────


def _get_safe_open_script(workspace_root: Path) -> str:
    """Generate the open() guard script — sandboxes file access."""
    _tmp = Path(tempfile.gettempdir()).resolve()
    workspace_literal = json.dumps(str(workspace_root.resolve()))
    tmp_literal = json.dumps(str(_tmp))
    return f'''
import os as __sandbox_os
import sys as __sandbox_sys
from pathlib import Path as __sandbox_Path

__WORKSPACE = __sandbox_Path({workspace_literal}).resolve()
__TMP = __sandbox_Path({tmp_literal}).resolve()
__WORKSPACE_STR = str(__WORKSPACE)
__TMP_STR = str(__TMP)

def __is_safe(path):
    try:
        p = __sandbox_Path(path)
        resolved = p.resolve() if p.is_absolute() else (__WORKSPACE / p).resolve()
        resolved_str = str(resolved)
        sep = __sandbox_os.sep
        # Within workspace — use sep suffix to avoid prefix collision
        if resolved_str == __WORKSPACE_STR or resolved_str.startswith(__WORKSPACE_STR + sep):
            return True
        # Temp dir for pandas/matplotlib temp files (cross-platform)
        if resolved_str == __TMP_STR or resolved_str.startswith(__TMP_STR + sep):
            return True
        return False
    except Exception:
        return False

import builtins as __builtins
__sandbox_os.__orig_open = open

def __safe_open(file, mode="r", *args, **kwargs):
    if not isinstance(file, (str, __sandbox_Path)):
        return __sandbox_os.__orig_open(file, mode, *args, **kwargs)

    write_modes = ("w", "a", "x", "+")
    is_write = any(m in str(mode) for m in write_modes)
    sep = __sandbox_os.sep

    if is_write and not __is_safe(file):
        raise PermissionError(
            "Write access denied: " + str(file) + ". "
            "Writes must be within workspace: " + __WORKSPACE_STR
        )

    if not is_write:
        fpath = str(file)
        if ".." in fpath:
            try:
                p = __sandbox_Path(fpath)
                resolved = p.resolve() if p.is_absolute() else (__WORKSPACE / p).resolve()
                if not (str(resolved) == __WORKSPACE_STR or str(resolved).startswith(__WORKSPACE_STR + sep)):
                    raise PermissionError("Path escape blocked: " + fpath)
            except (ValueError, OSError):
                raise PermissionError("Invalid path: " + fpath)

    return __sandbox_os.__orig_open(file, mode, *args, **kwargs)

__builtins.open = __safe_open

# Guard pathlib.Path.open
_orig_pathlib_open = __sandbox_Path.open
def __safe_path_open(self, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
    write_modes = ("w", "a", "x", "+")
    is_write = any(m in str(mode) for m in write_modes)
    p_str = str(self)
    sep = __sandbox_os.sep
    if is_write and not __is_safe(p_str):
        raise PermissionError("Write access denied: " + p_str)
    if not is_write and ".." in p_str:
        try:
            resolved = self.resolve() if self.is_absolute() else (__WORKSPACE / self).resolve()
            if not (str(resolved) == __WORKSPACE_STR or str(resolved).startswith(__WORKSPACE_STR + sep)):
                raise PermissionError("Path escape blocked: " + p_str)
        except (ValueError, OSError):
            raise PermissionError("Invalid path: " + p_str)
    return _orig_pathlib_open(self, mode, buffering, encoding, errors, newline)
__sandbox_Path.open = __safe_path_open

# Static validation blocks dangerous builtins before execution. Do not delete
# compile/eval/exec here because IPython itself needs compile() to run cells.

# Set working directory
__sandbox_os.chdir(str(__WORKSPACE))

# Configure matplotlib
import matplotlib as __mpl
__mpl.use("Agg")

print("[sandbox] ok")
'''


def _get_resource_limit_script(policy: SandboxPolicy) -> str:
    """Generate resource limit script - runs second."""
    return f'''
try:
    import resource as __rsrc
    __rsrc.setrlimit(__rsrc.RLIMIT_FSIZE, (
        {policy.max_file_size_mb} * 1024 * 1024,
        {policy.max_file_size_mb} * 1024 * 1024
    ))
    __rsrc.setrlimit(__rsrc.RLIMIT_NOFILE, (128, 128))
except Exception:
    pass
'''


def _get_socket_block_script() -> str:
    """Generate socket blocking script - runs third."""
    return '''
try:
    import socket as __sock
    __sock_orig = __sock.socket
    def __blocked_socket(*a, **k):
        raise PermissionError("Network access is disabled")
    __sock.socket = __blocked_socket
except Exception:
    pass
'''


def get_kernel_startup_scripts(workspace_root: Path, policy: SandboxPolicy) -> list[str]:
    """Return a list of small scripts to execute in order at kernel startup.

    Splitting into small chunks avoids executing library issues with large
    code blocks.
    """
    scripts = [_get_resource_limit_script(policy)]
    if policy.allowed_output_dirs:
        scripts.insert(0, _get_safe_open_script(workspace_root))
    if policy.block_network:
        scripts.append(_get_socket_block_script())
    return scripts
