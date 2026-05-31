# VonishAgent

AI-powered agent workbench — a complete development workstation where AI models execute tools, manage workspaces, and collaborate with humans through structured interactions.

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Tools Reference](#tools-reference)
- [API Overview](#api-overview)
- [Development](#development)
- [Documentation](#documentation)
- [License](#license)

## Features

### Agent Core

- **Multi-model** — DeepSeek (V4 Pro) and Kimi with extensible adapter
- **Agent Loop** — Multi-round tool execution with native function calling
- **Streaming SSE** — 24 event types: text, thinking, tool calls, interactions, context usage
- **SQLite Persistence** — Conversations and messages survive restarts
- **Prompt Builder** — Modular prompt blocks with token estimation and preview

### Workspace & Tools (15 tools)

| Category | Tools |
|----------|-------|
| File Ops | `file_read`, `edit_file`, `write_to_file`, `delete_file`, `apply_patch` |
| Workspace | `list_directory`, `snapshot`, `search_workspace` |
| Shell | `shell_command` |
| Python | `ipython` (persistent kernel, artifact collection) |
| Web | `web_search`, `web_fetch` |
| System | `set_todo_list`, `ask_user_question`, `request_approval` |

- **Workspace Isolation** — Per-conversation directory with path sandbox
- **search_workspace** — Grep across files with regex, globs, context preview
- **File Upload** — Multi-file, text extraction (PDF, DOCX, PPTX, TXT, MD)
- **Tool Management** — Enable/disable tools per category, sync to backend

### Human Interaction

- **set_todo_list** — Task tracking with weak/strong reminders in system prompt
- **ask_user_question** — Pause agent, render option cards above input
- **request_approval** — Approval gate for risky operations with approve/reject/custom
- **Pause/Resume** — Agent loop state machine with SSE interaction events

### Context Management

- **Token Budget** — Per-component allocation with compression tiers
- **Live Monitoring** — Gauge, stats, component breakdown in composer toolbar
- **Profile Switching** — `minimal` / `balanced` / `max` / `custom`
- **Compression** — `none` / `light` / `medium` / `aggressive`

### UI/UX

- **6-Language i18n** — zh-CN, en-US, ja-JP, ko-KR, fr-FR, de-DE with hot-switch
- **Dark Theme** — Developer-oriented, VS Code/Claude Code aesthetic
- **Composer Toolbar** — Model selector, context gauge, todo indicator, polish button
- **Sidebar** — Conversations with rename, delete confirmation, export, workspace file tree
- **Export** — Conversation to Markdown/TXT with anonymization and save picker
- **Polish** — LLM-powered text refinement with revert

## Quick Start

### Prerequisites

- **Python** 3.12+
- **Node.js** 20+
- **API Key** — DeepSeek or Kimi

### Backend

```bash
cd project/backend
python -m venv .venv
.venv\Scripts\activate     # Windows
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
python main.py
# API: http://127.0.0.1:8000
# Health: http://127.0.0.1:8000/health
```

### Frontend

```bash
cd project/frontend
npm install
npm run dev
# UI: http://127.0.0.1:5173
```

### Production Build

```bash
cd project/frontend && npm run build
# Static files served by backend at :8000
```

## Architecture

```
VonishAgent/
├── README.md
├── project/
│   ├── backend/
│   │   ├── agent/              # Agent loop, tool registry, model adapter, interaction tools
│   │   │   └── tool_handlers/  # Individual tool implementations
│   │   ├── api/                # FastAPI routes
│   │   │   ├── chat.py         # Chat stream, polish, interaction resume
│   │   │   ├── conversations.py # CRUD, search, export
│   │   │   ├── workspace.py    # File listing, reading
│   │   │   ├── tools.py        # Tool config, execution
│   │   │   ├── uploads.py      # File upload, parsing
│   │   │   ├── context.py      # Context usage, profiles
│   │   │   └── prompt.py       # Prompt preview, tool configs
│   │   ├── context/            # Token budget, compression, model capability
│   │   ├── core/               # Config, auth, streaming (SSE events)
│   │   ├── db/                 # SQLAlchemy ORM, session
│   │   ├── prompt/             # Prompt builder, blocks, registry
│   │   ├── services/           # Upload, file parser, context tracker, LLM summary
│   │   ├── tools/              # IPython runtime (kernel, sandbox, artifact)
│   │   ├── workspace/          # Workspace manager, sandbox policy
│   │   └── tool_runtimes/      # web_search Node.js pipeline
│   ├── frontend/
│   │   └── src/
│   │       ├── components/
│   │       │   ├── chat/       # MessageBubble, MessageStream, TodoCard, ThinkingCard
│   │       │   ├── composer/   # Composer, ModelSelector, ContextButton, TodoIndicator,
│   │       │   │               # InteractionBar, AttachmentBar, PolishButton
│   │       │   ├── layout/     # TopBar, Sidebar, StatusBar, MainLayout
│   │       │   ├── tools/      # ToolCard, ToolCategorySection, AddToolModal
│   │       │   └── ui/         # Progress, Tooltip, Toggle
│   │       ├── i18n/           # 6-language dictionaries + profiles
│   │       ├── pages/          # ToolsPage
│   │       ├── services/       # API client, SSE parser, mock data
│   │       ├── stores/         # Zustand: chat, UI, tools, workspace, language
│   │       └── types/          # TypeScript interfaces
│   ├── docs/                   # Project documentation
│   ├── scripts/                # Startup scripts, migration, docker
│   └── workspaces/             # Runtime workspace data (gitignored)
```

### Data Flow

```
User Input → Composer → chatStore.sendMessage()
  → POST /api/chat/{id}/stream
  → Agent Loop
    → Build Context (history + system prompt + todo status)
    → Model API (DeepSeek/Kimi native function calling)
    → SSE Stream → Frontend renders messages/tools/interactions
    → Tool Execution → Results feed back → Next round
  → message_end → Persist to SQLite
```

## Configuration

### API Key

Configure in the Settings panel (gear icon → API tab) or via environment:

```env
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_API_BASE=https://api.deepseek.com
```

### Context Profiles

| Profile | Input Tokens | Output Reserved | Description |
|---------|-------------|-----------------|-------------|
| minimal | 16K | 4K | Quick tasks, low latency |
| balanced | 32K | 8K | Default, general purpose |
| max | 64K | 16K | Complex multi-step tasks |

### Tool Management

All tools are enabled by default. Disable unused tools in Settings → Tools to reduce prompt size and token consumption.

## Tools Reference

### File Operations

| Tool | Description | Confirmation |
|------|-------------|-------------|
| `file_read` | Read file with encoding (utf-8/base64) and pagination | Suggest |
| `write_to_file` | Create or overwrite a file | Required |
| `edit_file` | Search/replace within a file | Required |
| `delete_file` | Delete a file (with hash for recovery) | Required |
| `apply_patch` | Apply unified diff patch (transactional) | Required |

### Workspace

| Tool | Description |
|------|-------------|
| `list_directory` | List files, supports recursive |
| `snapshot` | File tree with sizes and modification times |
| `search_workspace` | Grep with regex, globs, context lines |

### Execution

| Tool | Description |
|------|-------------|
| `shell_command` | Execute shell with cwd and timeout |
| `ipython` | Persistent IPython kernel, session modes, artifact collection |

### Web

| Tool | Description |
|------|-------------|
| `web_search` | DuckDuckGo search with page crawling |
| `web_fetch` | Deep page extraction (static/dynamic) |

### Interaction

| Tool | Description |
|------|-------------|
| `set_todo_list` | Create/update task list, persists to workspace/.agent/ |
| `ask_user_question` | Ask clarification, pause until user responds |
| `request_approval` | Request plan approval before risky operations |

## API Overview

### Chat

```
POST /api/chat/{id}/stream          SSE streaming chat
POST /api/chat/{id}/stop            Stop generation
POST /api/polish                    Polish/refine text
POST /api/agent-runs/{id}/interactions/{iid}/resume   Resume from interaction
```

### Conversations

```
POST   /api/conversations              Create
GET    /api/conversations              List (paginated)
GET    /api/conversations/{id}         Get details
DELETE /api/conversations/{id}         Delete (cleans workspace)
POST   /api/conversations/{id}/clear   Clear messages
GET    /api/conversations/{id}/messages Get history
POST   /api/conversations/{id}/export  Export to MD/TXT
```

### Workspace

```
GET  /api/workspaces/{id}/files          List files
GET  /api/workspaces/{id}/files/{path}   Read file
POST /api/uploads/{id}                   Upload & parse files
```

### Tools & Context

```
GET  /api/tools                    List all tools with schemas
GET  /api/tools/config             Tool enable states
POST /api/tools/{name}/enable      Enable tool
POST /api/tools/{name}/disable     Disable tool
GET  /api/context/{id}/usage       Token usage snapshot
POST /api/context/{id}/profile     Switch context profile
POST /api/context/{id}/compact     Trigger compression
```

## Development

### Backend

```bash
cd project/backend
pip install -r requirements.txt
pytest tests/ -q          # Run tests
python -m py_compile ...  # Quick syntax check
```

### Frontend

```bash
cd project/frontend
npm run dev      # Dev server with HMR
npm run build    # Production build
npm run lint     # ESLint
```

### Key Dependencies

**Backend**: FastAPI, SQLAlchemy (async), OpenAI SDK, jupyter_client, python-pptx, python-docx, PyPDF2

**Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Zustand, Lucide Icons

## Documentation

Detailed documentation in `project/docs/`:

| Document | Description |
|----------|-------------|
| [architecture.md](project/docs/architecture.md) | System architecture and design decisions |
| [api.md](project/docs/api.md) | Complete API reference |
| [agent-workflow.md](project/docs/agent-workflow.md) | Agent loop and tool execution flow |
| [context-os.md](project/docs/context-os.md) | Context management and token budgeting |
| [workspace.md](project/docs/workspace.md) | Workspace isolation and file management |
| [SPEC.md](project/docs/SPEC.md) | Technical specification |
| [project-map.md](project/docs/project-map.md) | Code navigation guide |
| [migration.md](project/docs/migration.md) | Migration from legacy codebase |
| [tool-loop-demo.md](project/docs/tool-loop-demo.md) | Tool execution examples |
| [kimi_agent_architecture_analysis.md](project/docs/kimi_agent_architecture_analysis.md) | Kimi model adapter analysis |

## License

MIT
