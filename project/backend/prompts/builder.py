"""
PromptBuilder — Prompt 工程引擎

负责从模板文件组装完整的 System Prompt，支持：
- 模板变量替换 {{variable}}
- Feature Flag 控制（工具调用规范注入）
- Prompt 版本控制（文件名中的 v1, v2）
- 模块化组装（按需注入各模块）

Usage:
    from app.prompts.builder import PromptBuilder

    builder = PromptBuilder()
    system_prompt = builder.build_system_prompt(
        profile=ContextProfile(name="standard", max_tokens=8192),
        enable_tools=False,
    )
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ContextProfile(BaseModel):
    """上下文档位配置"""

    name: str = "standard"
    max_input_tokens: int = 8192
    recent_turns: int = 4


class ToolDefinition(BaseModel):
    """工具定义"""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)

    def to_markdown(self) -> str:
        """转为 Markdown 格式的工具说明"""
        lines = [f"### {self.name}", "", f"{self.description}", ""]
        if self.parameters:
            lines.append("参数：")
            for param_name, param_info in self.parameters.items():
                if isinstance(param_info, dict):
                    ptype = param_info.get("type", "any")
                    pdesc = param_info.get("description", "")
                    required = "（必填）" if param_info.get("required") else ""
                    lines.append(f'- `{param_name}` ({ptype}){required}: {pdesc}')
                else:
                    lines.append(f'- `{param_name}`: {param_info}')
            lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------


class PromptBuilder(BaseModel):
    """
    Prompt 组装引擎。

    从 prompts/ 目录下的 Markdown 模板文件加载并组装 System Prompt，
    支持变量替换、Feature Flag 和版本控制。
    """

    # 默认 prompts 目录（相对于本文件）
    DEFAULT_PROMPTS_DIR: str = str(Path(__file__).parent)

    # Feature Flag 环境变量名
    ENV_ENABLE_TOOLS: str = "ENABLE_TOOLS"

    # 默认最大工具调用数
    DEFAULT_MAX_TOOL_CALLS: int = 5

    # 版本标记正则（从文件名提取，如 base_v1.md -> v1）
    VERSION_PATTERN: re.Pattern = re.compile(r"_v(\d+)")

    def __init__(self, prompts_dir: str | None = None) -> None:
        """
        初始化 PromptBuilder。

        Args:
            prompts_dir: prompts 根目录路径。默认为本文件所在目录。
        """
        self.prompts_dir: Path = Path(prompts_dir or self.DEFAULT_PROMPTS_DIR)
        self._cache: dict[str, str] = {}  # 模板缓存

        # 子目录路径
        self.system_dir: Path = self.prompts_dir / "system"
        self.agent_dir: Path = self.prompts_dir / "agent"
        self.tool_dir: Path = self.prompts_dir / "tool"
        self.context_dir: Path = self.prompts_dir / "context"

        logger.debug("PromptBuilder initialized, prompts_dir=%s", self.prompts_dir)

    # ------------------------------------------------------------------
    # 模板加载 / 渲染（底层）
    # ------------------------------------------------------------------

    def _load_template(self, path: str) -> str:
        """
        从文件加载模板内容，带缓存。

        Args:
            path: 模板文件的绝对或相对路径。相对路径基于 prompts_dir。

        Returns:
            模板文件内容字符串。

        Raises:
            FileNotFoundError: 文件不存在。
        """
        # 尝试作为绝对路径或相对路径解析
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = self.prompts_dir / path

        cache_key = str(file_path.resolve())

        if cache_key not in self._cache:
            if not file_path.exists():
                raise FileNotFoundError(f"Prompt template not found: {file_path}")
            content = file_path.read_text(encoding="utf-8")
            self._cache[cache_key] = content
            logger.debug("Loaded template: %s", file_path)

        return self._cache[cache_key]

    def _render_template(self, template: str, **kwargs: Any) -> str:
        """
        简单变量替换渲染模板。

        将模板中的 {{variable}} 替换为 kwargs 中对应的值。
        如果变量未提供，保留原始占位符并记录警告。

        Args:
            template: 模板字符串。
            **kwargs: 替换变量名 -> 值。

        Returns:
            渲染后的字符串。
        """
        if not kwargs:
            return template

        def _replacer(match: re.Match) -> str:
            var_name = match.group(1).strip()
            if var_name in kwargs:
                value = kwargs[var_name]
                return str(value) if value is not None else ""
            logger.warning("Template variable '%s' not provided, keeping placeholder", var_name)
            return match.group(0)

        rendered = re.sub(r"\{\{(\w+)\}\}", _replacer, template)
        return rendered

    def _load_and_render(self, path: str, **kwargs: Any) -> str:
        """
        加载模板并渲染变量（便捷方法）。

        Args:
            path: 模板文件路径。
            **kwargs: 渲染变量。

        Returns:
            渲染后的模板内容。
        """
        template = self._load_template(path)
        return self._render_template(template, **kwargs)

    # ------------------------------------------------------------------
    # 模块加载器（按类别）
    # ------------------------------------------------------------------

    def _load_base_prompt(self, version: str = "v1") -> str:
        """加载基础系统 Prompt。"""
        return self._load_template(f"system/base_{version}.md")

    def _load_markdown_guide(self) -> str:
        """加载 Markdown 输出规范。"""
        return self._load_template("system/markdown_guide.md")

    def _load_tool_call_guide(self) -> str:
        """加载工具调用 JSON 规范。"""
        return self._load_template("system/tool_call_guide.md")

    def _load_workspace_guide(self) -> str:
        """加载 Workspace 使用规范。"""
        return self._load_template("system/workspace_guide.md")

    def _load_context_budget_guide(self) -> str:
        """加载上下文预算说明。"""
        return self._load_template("system/context_budget_guide.md")

    def _load_agent_loop_start(self) -> str:
        """加载 Agent Loop 启动 Prompt。"""
        return self._load_template("agent/loop_start.md")

    def _load_agent_loop_continue(self) -> str:
        """加载 Agent Loop 继续 Prompt。"""
        return self._load_template("agent/loop_continue.md")

    def _load_agent_loop_final(self) -> str:
        """加载 Agent Loop 最终总结 Prompt。"""
        return self._load_template("agent/loop_final.md")

    def _load_agent_self_check(self) -> str:
        """加载自检 Prompt。"""
        return self._load_template("agent/self_check.md")

    # ------------------------------------------------------------------
    # Feature Flag
    # ------------------------------------------------------------------

    def _is_tools_enabled(self, explicit: bool | None = None) -> bool:
        """
        检查工具调用功能是否启用。

        优先级：显式参数 > 环境变量 > 默认值(False)

        Args:
            explicit: 显式传入的开关值。None 表示使用环境变量。

        Returns:
            是否启用工具调用。
        """
        if explicit is not None:
            return explicit
        env_val = os.environ.get(self.ENV_ENABLE_TOOLS, "").lower()
        return env_val in ("1", "true", "yes", "on")

    # ------------------------------------------------------------------
    # 公共构建方法
    # ------------------------------------------------------------------

    def build_system_prompt(
        self,
        profile: ContextProfile | None = None,
        active_tools: list[ToolDefinition] | None = None,
        user_memory: list[str] | None = None,
        workspace_summary: dict | None = None,
        uploaded_files: list[dict] | None = None,
        enable_tools: bool = False,
        base_version: str = "v1",
    ) -> str:
        """
        组装完整的 System Prompt。

        组装顺序：
            1. base_v{version}.md — 基础系统 Prompt
            2. markdown_guide.md — Markdown 输出规范
            3. tool_call_guide.md — 工具调用规范（仅 enable_tools=True）
            4. workspace_guide.md — Workspace 使用规范
            5. context_budget_guide.md — 上下文预算说明
            6. memory_inject.md — 记忆注入（如有记忆）
            7. file_manifest.md — 批量文件清单（如有上传文件）

        Args:
            profile: 上下文档位配置。默认 standard。
            active_tools: 可用工具定义列表。
            user_memory: 用户记忆字符串列表。
            workspace_summary: Workspace 摘要信息。
            uploaded_files: 用户上传文件列表，每项为 dict 含 name, type, size 等。
            enable_tools: 是否注入工具调用规范。默认 False。
            base_version: 基础 Prompt 版本（v1, v2 等）。默认 v1。

        Returns:
            组装后的完整 System Prompt 字符串。
        """
        profile = profile or ContextProfile()
        active_tools = active_tools or []
        user_memory = user_memory or []
        workspace_summary = workspace_summary or {}
        uploaded_files = uploaded_files or []

        # 决定是否启用工具
        tools_enabled = self._is_tools_enabled(enable_tools)

        # ---- 1. 基础系统 Prompt ----
        base_template = self._load_base_prompt(version=base_version)

        # 工具能力说明语句
        if tools_enabled and active_tools:
            tool_capability_statement = (
                "当任务需要时，系统会为你提供相应的工具和环境。\n\n"
                "你具备执行操作的能力，当需要时会收到进一步指令。\n"
                f"当前可用工具数量：{len(active_tools)} 个。"
            )
        else:
            tool_capability_statement = (
                "你具备执行操作的能力，当需要时会收到进一步指令。"
            )

        # ---- 2. Markdown 输出规范 ----
        markdown_guide = self._load_markdown_guide()

        # ---- 3. 工具调用规范（Feature Flag 控制） ----
        tool_call_guide = ""
        if tools_enabled:
            tool_defs_md = "\n\n".join(t.to_markdown() for t in active_tools)
            tool_call_template = self._load_tool_call_guide()
            tool_call_guide = self._render_template(
                tool_call_template,
                max_tool_calls=self.DEFAULT_MAX_TOOL_CALLS,
                tool_definitions=tool_defs_md or "（暂无可用工具）",
            )
            tool_call_guide = f"\n\n---\n\n{tool_call_guide}"

        # ---- 4. Workspace 使用规范 ----
        workspace_guide = self._load_workspace_guide()

        # ---- 5. 上下文预算说明 ----
        context_budget_template = self._load_context_budget_guide()
        context_budget_guide = self._render_template(
            context_budget_template,
            max_input_tokens=profile.max_input_tokens,
            used_tokens=workspace_summary.get("used_tokens", 0),
            profile_name=profile.name,
            recent_turns=profile.recent_turns,
            memory_count=len(user_memory),
            file_count=len(uploaded_files),
        )

        # ---- 6. 记忆注入 ----
        memory_section = ""
        if user_memory:
            memory_lines = "\n\n".join(
                f"- [{i+1}] {mem}" for i, mem in enumerate(user_memory)
            )
            memory_template = self._load_template("context/memory_inject.md")
            memory_section = self._render_template(
                memory_template,
                recalled_memories=memory_lines,
            )
            memory_section = f"\n\n---\n\n{memory_section}"

        # ---- 7. 批量文件清单 ----
        file_manifest_section = ""
        if uploaded_files:
            file_manifest_md = self.build_file_manifest_prompt(uploaded_files)
            file_manifest_section = f"\n\n---\n\n{file_manifest_md}"

        # ---- 组装基础 Prompt 的变量 ----
        base_rendered = self._render_template(
            base_template,
            tool_capability_statement=tool_capability_statement,
            markdown_guide=markdown_guide,
            workspace_guide=workspace_guide,
            context_budget_guide=context_budget_guide,
        )

        # ---- 最终组装 ----
        parts = [
            base_rendered,
            tool_call_guide,
            memory_section,
            file_manifest_section,
        ]

        full_prompt = "\n\n".join(parts).strip()

        logger.info(
            "System prompt built: version=%s, tools_enabled=%s, "
            "tools_count=%d, memory_count=%d, file_count=%d",
            base_version,
            tools_enabled,
            len(active_tools),
            len(user_memory),
            len(uploaded_files),
        )

        return full_prompt

    def build_file_manifest_prompt(self, files: list[dict]) -> str:
        """
        构建批量文件注入 Prompt。

        Args:
            files: 文件信息列表，每项 dict 包含：
                - name: 文件名（相对路径）
                - type: MIME 类型或扩展名
                - size: 文件大小（字节）
                - summary: 内容摘要（可选）

        Returns:
            渲染后的文件清单 Prompt。
        """
        if not files:
            return ""

        # 构建文件清单表格
        manifest_lines = []
        manifest_lines.append("| # | 文件名 | 类型 | 大小 | 摘要 |")
        manifest_lines.append("|---|--------|------|------|------|")

        for i, f in enumerate(files, 1):
            name = f.get("name", "unknown")
            ftype = f.get("type", f.get("ext", "-"))
            size_raw = f.get("size", 0)
            size_str = self._human_readable_size(size_raw) if isinstance(size_raw, (int, float)) else str(size_raw)
            summary = f.get("summary", "")
            # 截断过长摘要
            if len(summary) > 100:
                summary = summary[:97] + "..."
            # 转义表格中的管道符
            summary = summary.replace("|", "\\|")
            name = name.replace("|", "\\|")
            manifest_lines.append(f"| {i} | {name} | {ftype} | {size_str} | {summary} |")

        manifest_table = "\n".join(manifest_lines)

        template = self._load_template("context/file_manifest.md")
        rendered = self._render_template(
            template,
            file_count=len(files),
            file_manifest=manifest_table,
        )
        return rendered

    def build_memory_inject_prompt(self, memories: list[str]) -> str:
        """
        构建记忆注入 Prompt。

        Args:
            memories: 记忆字符串列表。

        Returns:
            渲染后的记忆注入 Prompt。
        """
        if not memories:
            return ""

        memory_lines = "\n\n".join(
            f"- [{i+1}] {mem}" for i, mem in enumerate(memories)
        )

        template = self._load_template("context/memory_inject.md")
        rendered = self._render_template(
            template,
            recalled_memories=memory_lines,
        )
        return rendered

    def build_agent_loop_prompt(
        self,
        stage: str,
        context_budget: dict | None = None,
        tool_results: str | None = None,
    ) -> str:
        """
        构建 Agent Loop 阶段 Prompt。

        Args:
            stage: 阶段名称，可选 'start', 'continue', 'final'。
            context_budget: 上下文预算信息。
            tool_results: 工具执行结果（仅 continue 阶段需要）。

        Returns:
            对应阶段的 Prompt。
        """
        context_budget = context_budget or {}

        if stage == "start":
            template = self._load_agent_loop_start()
            budget_guide = self._load_context_budget_guide()
            budget_rendered = self._render_template(
                budget_guide,
                max_input_tokens=context_budget.get("max_input_tokens", 8192),
                used_tokens=context_budget.get("used_tokens", 0),
                profile_name=context_budget.get("profile_name", "standard"),
                recent_turns=context_budget.get("recent_turns", 4),
                memory_count=context_budget.get("memory_count", 0),
                file_count=context_budget.get("file_count", 0),
            )
            return self._render_template(
                template,
                context_budget_guide=budget_rendered,
            )

        elif stage == "continue":
            template = self._load_agent_loop_continue()
            return self._render_template(
                template,
                tool_results=tool_results or "（暂无工具执行结果）",
            )

        elif stage == "final":
            return self._load_agent_loop_final()

        else:
            raise ValueError(f"Unknown agent loop stage: {stage}")

    def build_self_check_prompt(self) -> str:
        """构建自检 Prompt。"""
        return self._load_agent_self_check()

    def build_tool_gating_prompt(self, max_tool_calls: int | None = None) -> str:
        """
        构建工具门控决策 Prompt。

        Args:
            max_tool_calls: 单次最大工具调用数。默认 5。

        Returns:
            渲染后的工具门控 Prompt。
        """
        template = self._load_template("tool/tool_gating.md")
        return self._render_template(
            template,
            max_tool_calls=max_tool_calls or self.DEFAULT_MAX_TOOL_CALLS,
        )

    def build_result_summary_prompt(self) -> str:
        """构建工具结果摘要 Prompt。"""
        return self._load_template("tool/result_summary.md")

    def build_result_format_prompt(self) -> str:
        """构建工具结果格式化 Prompt。"""
        return self._load_template("tool/result_format.md")

    def build_compression_trigger_prompt(
        self,
        recent_turns: int = 4,
        compressed_turns: int = 0,
        compression_method: str = "none",
    ) -> str:
        """
        构建压缩触发说明 Prompt。

        Args:
            recent_turns: 最近完整保留轮数。
            compressed_turns: 已压缩轮数。
            compression_method: 当前压缩方式。

        Returns:
            渲染后的压缩触发说明。
        """
        template = self._load_template("context/compression_trigger.md")
        return self._render_template(
            template,
            recent_turns=recent_turns,
            compressed_turns=compressed_turns,
            compression_method=compression_method,
        )

    def build_profile_switch_prompt(
        self,
        current_profile: str = "standard",
        recommended_profile: str = "standard",
        switch_reason: str = "",
    ) -> str:
        """
        构建档位切换说明 Prompt。

        Args:
            current_profile: 当前档位名称。
            recommended_profile: 建议档位名称。
            switch_reason: 切换原因说明。

        Returns:
            渲染后的档位切换说明。
        """
        template = self._load_template("context/profile_switch.md")
        return self._render_template(
            template,
            current_profile=current_profile,
            recommended_profile=recommended_profile,
            switch_reason=switch_reason or "当前档位满足需求",
        )

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _human_readable_size(size_bytes: int | float) -> str:
        """
        将字节大小转为人类可读格式。

        Args:
            size_bytes: 字节数。

        Returns:
            如 "1.5 KB", "3.2 MB" 等。
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def clear_cache(self) -> None:
        """清除模板缓存。用于开发热重载场景。"""
        self._cache.clear()
        logger.debug("Template cache cleared")

    def get_template_versions(self, category: str = "system") -> dict[str, str]:
        """
        获取某个类别下的模板版本信息。

        Args:
            category: 模板类别（system, agent, tool, context）。

        Returns:
            文件名 -> 版本号 的映射。
        """
        dir_map = {
            "system": self.system_dir,
            "agent": self.agent_dir,
            "tool": self.tool_dir,
            "context": self.context_dir,
        }
        target_dir = dir_map.get(category, self.prompts_dir / category)

        versions: dict[str, str] = {}
        if target_dir.exists():
            for f in sorted(target_dir.glob("*.md")):
                match = self.VERSION_PATTERN.search(f.name)
                versions[f.name] = match.group(1) if match else "unversioned"
        return versions


# ---------------------------------------------------------------------------
# 便捷函数（模块级）
# ---------------------------------------------------------------------------


def get_default_builder() -> PromptBuilder:
    """获取默认 PromptBuilder 实例（单例模式）。"""
    if not hasattr(get_default_builder, "_instance"):
        get_default_builder._instance = PromptBuilder()
    return get_default_builder._instance


def build_system_prompt(**kwargs: Any) -> str:
    """
    便捷函数：使用默认 builder 构建 System Prompt。

    Args:
        **kwargs: 传递给 PromptBuilder.build_system_prompt 的参数。

    Returns:
        完整的 System Prompt 字符串。
    """
    return get_default_builder().build_system_prompt(**kwargs)
