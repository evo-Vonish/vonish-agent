# VonishAgent

AI Agent Workbench — a complete development environment where AI models execute tools, manage file workspaces, render documents, accept inline prompts, and collaborate with humans through structured agent loops.

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Tools Reference](#tools-reference)
- [API Overview](#api-overview)
- [Development](#development)
- [Documentation](#documentation)

## Features

### Agent Core

- **Multi-model** — DeepSeek (V4 Pro / Flash) and Kimi with extensible adapter
- **Agent Loop** — Multi-round tool execution with native function calling and structured execution segments
- **24 SSE Events** — text, thinking, tool_call, tool_result, segment_start/update/end, step_start/delta/end, workflow_error, context_usage
- **SQLite Persistence** — Conversations, messages, tool calls survive restarts
- **Token Budget** — Per-component allocation with 4 compression tiers
- **Context Memory** — Persistent cross-conversation memory with auto-compaction
- **Minimal Context Mode** — Stripped system prompt for low-token quick tasks

### Agent IDE Workbench

- **Workbench Panel** — Multi-tab file editor with toolbar and status bar
- **Rich Renderers** — Code editor, Markdown/HTML preview, PDF/DOCX/PPTX/XLSX viewers, Image/Binary renderers
- **Workbench Tabs** — Open, close, reorder file tabs with dirty state tracking
- **Selection System** — Text selection with action toolbar (explain, fix, improve, refactor)
- **Inline AI Prompt** — Select code, press shortcut, AI edits in-place
- **Proposed Edit Bar** — Review diffs before applying suggested changes

### Workspace & Tools (22 tools)

| Category | Tools |
|---|---|
| File Ops | `file_read`, `edit_file`, `write_to_file`, `delete_file`, `apply_patch` |
| Workspace | `list_directory`, `list_workspace_files`, `read_workspace_file`, `get_workspace_summary`, `snapshot`, `search_workspace`, `create_directories` |
| Git | `git_status`, `git_diff`, `git_history` |
| Shell | `shell_command` |
| Python | `ipython` (persistent kernel, multi-session, artifact collection) |
| Web | `web_search`, `web_fetch`, `research_search`, `research_fetch`, `deep_research`, `research_status` |
| System | `set_todo_list`, `ask_user_question`, `request_approval` |

### Human Interaction

- **set_todo_list** — Task tracking with weak/strong reminders in system prompt
- **ask_user_question** — Pause agent, render option cards above input
- **request_approval** — Approval gate for risky operations with approve/reject/custom
- **Interaction Bar** — Composer transforms into interaction UI during agent pause

### Context Intelligence

- **Context Toast** — Toast notifications for profile switches, compaction, dissonance events
- **Dissonance Field** — Visual warning when context exceeds safe thresholds
- **Context Bar** — Real-time component breakdown in composer toolbar
- **Profile Switching** — `minimal` / `balanced` / `max` with live token gauge
- **Context Memory** — Agent remembers facts across conversations

### UI/UX

- **6-Language i18n** — zh-CN, en-US, ja-JP, ko-KR, fr-FR, de-DE with hot-switch
- **Dark Theme** — Developer-oriented, Codex-inspired aesthetic
- **Codex Settings** — Bottom-left single-entry settings popover with sub-panels
- **Config Panel** — Model / Context / Task / Permission accessible from input row
- **Conversation Sidebar** — Search, rename, delete, export (MD/TXT), workspace file tree
- **Export** — Full conversation export with tool results, thinking, execution steps
- **Welcome Screen** — Typewriter cycle with task prompts
- **Tool Management** — Enable/disable per tool with category grouping

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- API Key — DeepSeek or Kimi

### One-Click Start

```cmd
# Windows — double-click or run:
project\scripts\start.bat
```

### Manual

```bash
# Terminal 1 — Backend
cd project/backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
python main.py
# → http://127.0.0.1:8000

# Terminal 2 — Frontend
cd project/frontend
npm install
npm run dev
# → http://127.0.0.1:5173
```

## Architecture

```
VonishAgent/
├── README.md
├── project/
│   ├── backend/
│   │   ├── agent/                  # Agent loop, tool registry, model adapter
│   │   │   ├── agent_loop.py       # Multi-round agent with structured segments
│   │   │   ├── tool_executor.py    # Tool dispatch, error recovery, sandbox
│   │   │   ├── tool_registry.py    # 22-tool registry with JSON Schema validation
│   │   │   └── model_adapter.py    # DeepSeek / Kimi adapter with streaming
│   │   ├── api/
│   │   │   ├── chat.py             # SSE streaming, interaction resume
│   │   │   ├── conversations.py    # CRUD, search, export (MD/TXT)
│   │   │   ├── workspace.py        # File listing, reading, git
│   │   │   ├── tools.py            # Tool config, add/delete/enable
│   │   │   ├── uploads.py          # Multi-file upload with parsing
│   │   │   ├── context.py          # Context usage, profiles, compaction
│   │   │   └── prompt.py           # Prompt preview, tool descriptions
│   │   ├── context/
│   │   │   ├── context_builder.py      # Full context assembly
│   │   │   ├── context_memory.py       # Cross-conversation memory
│   │   │   ├── minimal_context.py      # Low-token quick mode
│   │   │   ├── token_budget.py         # Per-component allocation
│   │   │   ├── context_profile.py      # Profile management
│   │   │   └── model_capability.py     # Model-specific limits
│   │   ├── core/                   # Config, auth, SSE streaming, errors
│   │   ├── db/                     # SQLAlchemy ORM models + session
│   │   ├── prompt/                 # Modular prompt builder, tool registry
│   │   ├── services/               # Upload, parser, context tracker, document preview
│   │   ├── tools/                  # IPython runtime, research runtime client
│   │   └── workspace/              # Per-conversation isolated sandbox
│   ├── frontend/
│   │   └── src/
│   │       ├── components/
│   │       │   ├── chat/           # MessageBubble, MessageStream, ToolCard,
│   │       │   │                   # ThinkingCard, ExecutionSegmentCard, InteractionCard,
│   │       │   │                   # WorkflowErrorCard, TodoCard, MarkdownRenderer,
│   │       │   │                   # WelcomeScreen, SmoothStreamingText
│   │       │   ├── composer/       # Composer, ConfigPanel, SessionOptionsRow,
│   │       │   │                   # InteractionBar, AttachmentBar, ComposerContextBar,
│   │       │   │                   # ReferenceBar
│   │       │   ├── layout/         # MainLayout, AgentIDEShell, TopBar, Sidebar,
│   │       │   │                   # StatusBar, ContextToastHost, DissonanceField,
│   │       │   │                   # WorkbenchRightPanel, Logo
│   │       │   ├── workbench/      # WorkbenchPanel, WorkbenchTabs, CodeEditor,
│   │       │   │                   # FileRenderer, 8 format renderers, InlineAIPrompt,
│   │       │   │                   # ProposedEditBar, SelectionToolbar, SettingsTab
│   │       │   ├── tools/          # ToolCard, ToolCategorySection, AddToolModal
│   │       │   └── ui/             # Progress, Tooltip
│   │       ├── i18n/               # 6-language dictionaries + profiles
│   │       ├── pages/              # ToolsPage
│   │       ├── services/           # API client with 40+ endpoints
│   │       ├── stores/             # 13 Zustand stores
│   │       └── types/              # TypeScript interfaces
│   ├── scripts/                    # Startup scripts, Docker, migration
│   └── workspaces/                 # Runtime workspace data (gitignored)
```

### Data Flow

```
User Input → Composer → chatStore.sendMessage()
  → POST /api/chat/{id}/stream
  → Agent Loop
    → Build Context (history + system prompt + todo + memory + workspace)
    → Model API (native function calling)
    → SSE Stream with 24 event types
      → Frontend renders segments, steps, tool cards, interactions
    → Tool Execution with error recovery
      → Results feed back to context
    → Next round or message_end
  → Persist to SQLite
```

## Configuration

### API Key

Configure via left-sidebar Settings button → API Config panel, or environment:

```env
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_API_BASE=https://api.deepseek.com
```

### Context Profiles

| Profile | Budget | Compression | Use Case |
|---|---|---|---|
| minimal | 16K | aggressive | Quick one-shot tasks |
| balanced | 32K | medium | Default general purpose |
| max | 64K | light | Complex multi-step research |

### Workspace Isolation

Each conversation gets an isolated workspace directory under `project/workspaces/{conversation_id}/`. File tools are sandboxed to this directory. Workspace persists across conversations unless manually cleaned.

## Tools Reference

### File Operations

| Tool | Description | Confirmation |
|---|---|---|
| `file_read` | Read file with encoding (utf-8/base64) + line pagination | Suggest |
| `write_to_file` | Create or overwrite a file | Required |
| `edit_file` | Targeted search/replace within a file | Required |
| `delete_file` | Delete with content hash for recovery | Required |
| `apply_patch` | Apply unified diff (transactional, multi-file) | Required |

### Workspace & Git

| Tool | Description |
|---|---|
| `list_directory` | Recursive file listing |
| `list_workspace_files` | Full workspace file manifest |
| `read_workspace_file` | Read by path (text or base64) |
| `get_workspace_summary` | Total files, sizes, type breakdown |
| `snapshot` | File tree with sizes and modification times |
| `search_workspace` | Grep with regex, globs, context lines |
| `create_directories` | Cross-platform mkdir |
| `git_status` | Staged, modified, untracked |
| `git_diff` | Working tree, staged, per-file, per-commit |
| `git_history` | Log and blame modes |

### Execution & Web

| Tool | Description |
|---|---|
| `shell_command` | Shell with cwd, timeout, output capture |
| `ipython` | Persistent kernel, multi-session, charts, artifacts |
| `web_search` | Multi-engine search + crawl + evidence |
| `web_fetch` | Deep page extraction (static/dynamic) |
| `research_search` | Intent-routed multi-engine search |
| `research_fetch` | Single URL fetch with summaries |
| `deep_research` | Full pipeline: search → crawl → dedup → evidence |
| `research_status` | Health check for research runtime |

### Interaction

| Tool | Description |
|---|---|
| `set_todo_list` | Multi-item task tracking with statuses |
| `ask_user_question` | Ask clarification, pause agent |
| `request_approval` | Plan approval gate, configurable risk levels |

## API Overview

### Chat

```
POST /api/chat/{id}/stream           SSE streaming (24 event types)
POST /api/chat/{id}/stop             Stop generation
POST /api/polish                     LLM text refinement
POST /api/conversations/{id}/export  Export to Markdown/TXT
```

### Conversations

```
POST   /api/conversations              Create session
GET    /api/conversations              List with pagination
GET    /api/conversations/{id}         Get details
DELETE /api/conversations/{id}         Delete + clean workspace
POST   /api/conversations/{id}/clear   Clear messages
GET    /api/conversations/{id}/messages Get message history
GET    /api/conversations/search?q=     Full-text search
```

### Workspace & Uploads

```
GET  /api/workspaces/{id}/files          List workspace files
GET  /api/workspaces/{id}/files/{path}   Read file
GET  /api/workspaces/{id}/git/status     Git status
GET  /api/workspaces/{id}/git/diff       Git diff
GET  /api/workspaces/{id}/git/history    Git history
POST /api/uploads/{id}                   Upload + parse files
```

### Tools & Context

```
GET  /api/tools                        List all tools with schemas
POST /api/tools/                       Add custom tool
DELETE /api/tools/{id}                 Remove tool
POST /api/tools/{name}/enable          Enable tool
POST /api/tools/{name}/disable         Disable tool
GET  /api/context/{id}/usage           Token usage snapshot
POST /api/context/{id}/profile         Switch context profile
POST /api/context/{id}/compact         Trigger compression
```

## Development

### Backend

```bash
cd project/backend
pip install -r requirements.txt
pytest tests/ -q
python main.py
```

### Frontend

```bash
cd project/frontend
npm install
npm run dev       # Dev server with HMR
npm run build     # Production build
npm run lint      # ESLint
```

### Key Dependencies

**Backend**: FastAPI, SQLAlchemy (async), OpenAI SDK, jupyter_client, python-pptx, python-docx, PyPDF2, openpyxl

**Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Zustand, Lucide Icons, Monaco Editor

## Documentation

Detailed documentation in `project/docs/`:

| Document | Description |
|---|---|
| [architecture.md](project/docs/architecture.md) | System architecture and design |
| [api.md](project/docs/api.md) | Complete API reference |
| [agent-workflow.md](project/docs/agent-workflow.md) | Agent loop and tool execution |
| [context-os.md](project/docs/context-os.md) | Context management system |
| [workspace.md](project/docs/workspace.md) | Workspace isolation design |
| [SPEC.md](project/docs/SPEC.md) | Technical specification |
| [project-map.md](project/docs/project-map.md) | Code navigation guide |

## License

MIT
