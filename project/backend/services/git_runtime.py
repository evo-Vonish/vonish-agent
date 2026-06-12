"""Git runtime detection and safe execution helpers."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from core.config import settings


@dataclass(frozen=True)
class GitRuntimeInfo:
    available: bool
    git_path: str
    source: str
    mode: str = ""
    version: str = ""
    error: str = ""


class GitRuntimeManager:
    """Find and run Git without relying on user global config."""

    _runtime: GitRuntimeInfo | None = None

    @classmethod
    async def detect(cls) -> GitRuntimeInfo:
        if cls._runtime is not None:
            return cls._runtime
        candidates = cls._candidates()
        for git_path, source, mode in candidates:
            code, stdout, stderr = await cls._run_raw(git_path, ["--version"], timeout=5.0)
            if code == 0:
                cls._runtime = GitRuntimeInfo(
                    available=True,
                    git_path=git_path,
                    source=source,
                    mode=mode,
                    version=stdout.strip(),
                )
                return cls._runtime
            last_error = stderr or stdout
        cls._runtime = GitRuntimeInfo(
            available=False,
            git_path="",
            source="disabled",
            mode="disabled",
            error=last_error if "last_error" in locals() else "git executable not found",
        )
        return cls._runtime

    @classmethod
    def _candidates(cls) -> list[tuple[str, str, str]]:
        roots = [
            Path(__file__).resolve().parents[3],
            Path(__file__).resolve().parents[2],
            Path(__file__).resolve().parents[1],
        ]
        candidates: list[tuple[str, str, str]] = [("git", "system_path", "system")]

        env_paths = [
            os.environ.get("VONISH_GIT_PATH"),
            os.environ.get("VONISH_BUNDLED_GIT"),
            os.environ.get("VONISH_MINGIT_PATH"),
        ]
        for value in env_paths:
            if value:
                path = Path(value)
                git_path = path / "git.exe" if path.is_dir() else path
                candidates.append((str(git_path), "env_bundled_mingit", "bundled"))

        for root in roots:
            for relative in (
                ("resources", "git", "mingit", "bin", "git.exe"),
                ("resources", "git", "mingit", "cmd", "git.exe"),
                ("resources", "git", "mingit", "mingw64", "bin", "git.exe"),
                ("resources", "git", "MinGit", "bin", "git.exe"),
                ("resources", "git", "MinGit", "cmd", "git.exe"),
                ("resources", "git", "MinGit", "mingw64", "bin", "git.exe"),
            ):
                bundled = root.joinpath(*relative)
                if bundled.exists():
                    candidates.append((str(bundled), "bundled_mingit", "bundled"))
        deduped: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for git_path, source, mode in candidates:
            key = str(Path(git_path).resolve()) if git_path != "git" else "git"
            if key in seen:
                continue
            seen.add(key)
            deduped.append((git_path, source, mode))
        return deduped

    @staticmethod
    def _env(home: Path | None = None) -> dict[str, str]:
        env = dict(os.environ)
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GCM_INTERACTIVE"] = "Never"
        safe_home = home or (Path(settings.workspace_root).resolve() / ".vonish_git_home")
        safe_home.mkdir(parents=True, exist_ok=True)
        env["HOME"] = str(safe_home)
        env["USERPROFILE"] = str(safe_home)
        return env

    @classmethod
    async def run(
        cls,
        args: Sequence[str],
        cwd: Path,
        timeout: float = 20.0,
        home: Path | None = None,
    ) -> tuple[int, str, str]:
        runtime = await cls.detect()
        if not runtime.available:
            return 127, "", runtime.error or "Git runtime unavailable"
        return await cls._run_raw(
            runtime.git_path,
            list(args),
            cwd=cwd,
            timeout=timeout,
            env=cls._env(home),
        )

    @staticmethod
    async def _run_raw(
        git_path: str,
        args: Sequence[str],
        cwd: Path | None = None,
        timeout: float = 20.0,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        try:
            process = await asyncio.create_subprocess_exec(
                git_path,
                *args,
                cwd=str(cwd) if cwd else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except (FileNotFoundError, OSError) as exc:
            return 127, "", f"git executable unavailable: {git_path}: {exc}"
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return 124, "", f"git command timed out after {timeout}s"
        return (
            int(process.returncode or 0),
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )
