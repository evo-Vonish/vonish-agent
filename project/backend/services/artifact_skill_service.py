"""Read-only access to bundled artifact production skills."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2] / "skill" / "Agent文档精美" / "improved-skills"

FORMAT_SKILLS = {"docx", "xlsx", "pdf", "pptx"}
SHARED_FILES = {
    "ARTIFACT_PLAN.md",
    "CONTEXT_RECALL.md",
    "PRIORITY_SYSTEM.md",
    "VISUAL_REVIEW.md",
    "skill.json",
}
FORMAT_FILES = {
    "SKILL.md",
    "procedure.yaml",
    "validators.yaml",
    "recovery.yaml",
    "design_tokens.yaml",
}


@dataclass(frozen=True)
class SkillFile:
    name: str
    path: str
    chars: int
    content: str


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _safe_file_name(name: str) -> str:
    cleaned = str(name or "").replace("\\", "/").split("/")[-1].strip()
    if not cleaned:
        raise ValueError("file name is required")
    return cleaned


def available_artifact_skills() -> dict[str, Any]:
    skills: dict[str, Any] = {}
    for skill in sorted(FORMAT_SKILLS):
        base = ROOT / skill
        files = [name for name in sorted(FORMAT_FILES) if (base / name).is_file()]
        skills[skill] = {
            "name": skill,
            "path": str(base),
            "available_files": files,
            "missing_files": [name for name in sorted(FORMAT_FILES) if name not in files],
        }
    shared_base = ROOT / "shared"
    return {
        "success": True,
        "root": str(ROOT),
        "skills": skills,
        "shared": {
            "path": str(shared_base),
            "available_files": [name for name in sorted(SHARED_FILES) if (shared_base / name).is_file()],
            "missing_files": [name for name in sorted(SHARED_FILES) if not (shared_base / name).is_file()],
        },
    }


def read_artifact_skill(
    skill: str,
    files: list[str] | None = None,
    include_shared: bool = True,
) -> dict[str, Any]:
    normalized = str(skill or "").strip().lower()
    if normalized not in FORMAT_SKILLS:
        return {
            "success": False,
            "error": f"Unknown artifact skill: {skill}. Allowed: {', '.join(sorted(FORMAT_SKILLS))}",
        }

    requested = files or ["SKILL.md", "procedure.yaml", "validators.yaml", "design_tokens.yaml"]
    requested = [_safe_file_name(name) for name in requested]
    allowed = set(FORMAT_FILES)
    blocked = [name for name in requested if name not in allowed]
    if blocked:
        return {
            "success": False,
            "error": f"Unsupported skill files: {', '.join(blocked)}. Allowed: {', '.join(sorted(allowed))}",
        }

    base = ROOT / normalized
    read_files: list[SkillFile] = []
    missing: list[str] = []
    for name in requested:
        path = (base / name).resolve()
        if not str(path).startswith(str(base.resolve())) or not path.is_file():
            missing.append(name)
            continue
        content = _read_text(path)
        read_files.append(SkillFile(name=name, path=str(path), chars=len(content), content=content))

    shared_read: list[SkillFile] = []
    if include_shared:
        shared_base = ROOT / "shared"
        for name in ["ARTIFACT_PLAN.md", "PRIORITY_SYSTEM.md", "VISUAL_REVIEW.md", "CONTEXT_RECALL.md"]:
            path = (shared_base / name).resolve()
            if not str(path).startswith(str(shared_base.resolve())) or not path.is_file():
                missing.append(f"shared/{name}")
                continue
            content = _read_text(path)
            shared_read.append(SkillFile(name=f"shared/{name}", path=str(path), chars=len(content), content=content))

    all_files = read_files + shared_read
    content = "\n\n".join(
        f"--- BEGIN {item.name} ---\n{item.content}\n--- END {item.name} ---"
        for item in all_files
    )
    return {
        "success": bool(read_files),
        "artifact_skill": True,
        "skill": normalized,
        "files_read": [
            {"name": item.name, "path": item.path, "chars": item.chars}
            for item in all_files
        ],
        "missing_files": missing,
        "content": content,
        "model_guidance": (
            f"You have read the {normalized.upper()} artifact skill. Follow its procedure, "
            "P0/P1 validation gates, visual review, and context recall checkpoints before delivery."
        ),
        "display": {
            "title": f"Read {normalized.upper()} artifact skill",
            "summary": f"Loaded {len(all_files)} skill/reference files for {normalized.upper()} generation.",
            "hide_raw_content": True,
        },
    }

