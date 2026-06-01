# VonishAgent Handover

> **日期**: 2026-06-02 | **状态**: 活跃开发 | **GitHub**: `evo-Vonish/vonish-agent`

## 1. 项目概述

AI Agent 工作台 — 多模型、多工具、流式 SSE、Workspace 隔离、人机交互暂停/恢复。

### 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.12 + FastAPI + SQLAlchemy (async) + SQLite |
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS + Zustand |
| 模型 | DeepSeek V4 Pro (主), Kimi (备) |
| 依赖 | openai SDK, jupyter_client, python-pptx, python-docx, PyPDF2 |

## 2. 启动方式

```bash
# 后端
cd project/backend
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
# 健康检查: http://127.0.0.1:8000/health

# 前端
cd project/frontend
npm install
npm run dev
# UI: http://127.0.0.1:5173

# 构建
npm run build   # dist/ 输出，后端可挂载静态文件

# 测试
cd project/backend && pytest tests/ -q  # 16 passed
```

**注意**：Vite 代理配置在 `vite.config.ts` — `/api` → `http://127.0.0.1:8000`。后端必须以 `127.0.0.1` 启动，不能用 `localhost`。

## 3. 关键文件结构

```
VonishAgent/
  README.md
  HANDOVER.md
  SPEC.md -> project/docs/SPEC.md
  project/
    backend/
      agent/
        agent_loop.py          # Agent 循环、context 构建、SSE 流、pause/resume
        tool_executor.py       # 工具调度 + 所有 handler
        tool_registry.py       # 工具注册 (16 个工具)
        model_adapter.py       # DeepSeek/Kimi 适配器
        interaction_tools.py   # ask_user_question/request_approval/set_todo_list
        tool_handlers/
          search_workspace.py  # grep 工具
      api/
        chat.py                # 聊天流、SSE、暂停/恢复、润色
        conversations.py       # CRUD、搜索、导出
        workspace.py           # 文件列表/读取
        uploads.py             # 文件上传
        tools.py               # 工具配置 API
        prompt.py              # 工具白名单 (_tool_configs) + prompt 预览
        context.py             # Context usage API
      core/
        streaming.py           # SSE_EVENT_TYPES (24 事件) + sse_event()
        config.py              # 配置 (workspace_root 等)
      prompt/
        prompt_blocks.py       # 固定 prompt 块 (FIXED_HEADER, TODO_RULES, BEHAVIOR_RULES...)
        prompt_builder.py      # Prompt 组装
      services/
        upload_service.py      # 上传保存 + metadata
        file_parser.py         # PDF/DOCX/PPTX 解析
        context_tracker.py     # Token 统计
        git_service.py         # Git 操作 (新增)
      tools/
        ipython_runtime/       # IPython kernel, sandbox, artifact
      workspace/
        workspace_manager.py   # Workspace 管理 + 沙箱

    frontend/src/
      components/
        chat/
          WelcomeScreen.tsx    # 首页打字机动画 + 任务卡片
          MessageBubble.tsx    # 消息气泡
          MessageStream.tsx    # 消息流 + 空状态
          TodoCard.tsx         # Todo 渲染
          InteractionCard.tsx  # Ask/Approval 卡片 (旧)
        composer/
          Composer.tsx         # 输入框 + 工具栏
          ContextButton.tsx    # 上下文面板按钮 (输入框上方)
          TodoIndicator.tsx    # Todo 指示器 (输入框上方)
          InteractionBar.tsx   # 交互面板 (Ask/Approval，接管输入区)
          AttachmentBar.tsx    # 附件栏
          ModelSelector.tsx    # 模型选择
        layout/
          Sidebar.tsx          # 侧边栏 (会话列表、删除/重命名/导出、文件树)
          TopBar.tsx           # 顶部栏
          StatusBar.tsx        # 底部栏 (Account/Settings/Language)
          MainLayout.tsx       # 布局 + 可拖拽面板
        tools/
          ToolCard.tsx, ToolCategorySection.tsx, AddToolModal.tsx
      i18n/
        dictionaries/          # 6 语言 (zh-CN, en-US, ja-JP, ko-KR, fr-FR, de-DE)
        profiles.ts            # 语言风格 profile
        useI18n.ts             # useI18n() hook
      stores/
        chatStore.ts           # 核心状态 (消息、会话、context、pendingInteraction)
        useToolStore.ts        # 工具状态
        languageStore.ts       # 语言
        uiStore.ts, workspaceStore.ts
```

## 4. 工具清单 (16 个)

| 分类 | 工具 |
|------|------|
| 文件 | `file_read`, `edit_file`, `write_to_file`, `delete_file`, `apply_patch` |
| 工作区 | `list_directory`, `snapshot`, `search_workspace`, `create_directories` |
| 终端 | `shell_command` |
| Python | `ipython` |
| Web | `web_search`, `web_fetch` |
| 系统 | `set_todo_list`, `ask_user_question`, `request_approval` |

工具白名单在 `api/prompt.py` 的 `_tool_configs`，启动时自动与 `tool_registry.py` 同步。

## 5. 核心数据流

```
用户输入 → Composer → chatStore.sendMessage()
  → POST /api/chat/{id}/stream
  → Agent Loop
    → 构建 Context (历史 + system_prompt + todo 状态 + 上传文件列表)
    → Model API (DeepSeek 原生 function calling)
    → SSE Stream → 前端渲染
    → 工具执行 → 结果反馈 → 下一轮
    → 交互暂停 (ask/approval) → 前端 InteractionBar → 用户响应 → 继续
  → message_end → 持久化到 SQLite
```

## 6. SSE 事件 (24 个)

```
message_start, thinking_start/delta/end, text_delta, markdown_delta,
tool_call_start/delta/end, tool_result,
file_created/modified, workspace_snapshot/diff,
context_usage, message_end, error, aborted,
interaction_required, agent_paused, agent_resumed,
todo_updated, approval_requested, ask_requested,
workflow_failure
```

## 7. 已知坑

### 7.1 `<tool_calls>` XML 泄露
- **症状**: 模型输出 `<tool_calls>`/`<invoke>`/`<parameter>` 伪代码到聊天流
- **原因**: `reasoning_effort: "max"` 让 DeepSeek 疯狂自语
- **修复**: `agent_loop.py` text_delta 发出前用正则过滤；system prompt 明确禁止
- **注意**: 用户要求保留 `reasoning_effort: "max"`，不要改成 medium

### 7.2 工具分类不一致
- `ToolsPage.tsx` 用 `CATEGORY_ORDER`，`ContextManagerPanel.tsx` 用 `toolCategoryOrder`
- 两处都要包含全部 6 个分类：`file_ops, workspace, python_ops, web_ops, shell_ops, system`

### 7.3 启动后端用 127.0.0.1 不用 localhost
- Vite 代理用 `127.0.0.1:8000`，不用 `localhost:8000`

### 7.4 `showSaveFilePicker` 兼容性
- 导出功能优先用 `showSaveFilePicker`（Chrome/Edge），fallback 到 `a.click()`

### 7.5 Windows cmd 引号问题
- `git commit -m "message with spaces"` 在 cmd 里会炸
- 用 `echo msg > _cm && git commit -F _cm && del _cm`

## 8. 当前状态

| 检查项 | 状态 |
|--------|------|
| 所有更改已提交 | ✅ |
| 已推送到 GitHub | ✅ |
| 后端编译/测试 | ✅ 16 passed |
| 前端构建 | ✅ |
| 前后端服务 | ⚠️ 需要手动启动 |

## 9. 待办 / 下一个任务

1. **前端 toast 系统** — `workflow_failure` SSE 事件已注册，但前端还未消费它显示 toast
2. **InteractionBar 构建验证** — 上次构建有 TS2657 错误，Fragment 已包但未重新构建确认
3. **DOCX 导出** — 第二阶段，目前只有 MD/TXT
4. **文件预览页面** — 点击文件卡片没有专门预览
5. **`write_to_file` 被禁用** — `_tool_configs` 中默认 true，但 `syncFromBackend` 可能覆盖

## 10. 关键配置

### backend/.env 或 API 设置面板
```env
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_API_BASE=https://api.deepseek.com
```

### workspace_root
默认 `project/workspaces/`，在 `core/config.py`，按需调整

### 数据库
`project/backend/local_agent.db` (SQLite)，已 gitignored

## 11. Git 仓库

- **URL**: https://github.com/evo-Vonish/vonish-agent
- **用户名**: evo-Vonish
- **邮箱**: kk13132424@outlook.com
- **Token**: 系统内已有过 `ghp_Aapi...` (已从 remote URL 清除，push 时会用到 credential manager)
- **分支**: main (唯一)
- **总 commit**: 46 个

## 12. 快速命令

```bash
# 构建
cd project/frontend && npm run build

# 启动后端
cd project/backend && .venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000

# 启动前端
cd project/frontend && npm run dev

# 测试
cd project/backend && .venv\Scripts\python.exe -m pytest tests/ -q

# 查看工具
cd project/backend && .venv\Scripts\python.exe -c "from agent.tool_registry import register_default_tools, ToolRegistry; register_default_tools(); print(sorted(ToolRegistry().list_all()))"

# 提交 (Windows cmd)
echo msg > _cm && git add -A && git commit -F _cm && del _cm && git push
```
