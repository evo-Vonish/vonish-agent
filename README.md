# VonishAgent

AI-powered agent workbench with tool execution, conversation management, and workspace context.

## Features

- **Multi-model support** — DeepSeek, Kimi, with extensible adapter
- **16 built-in tools** — file ops, web search/fetch, IPython execution, shell, grep, todo, human approval
- **Streaming SSE** — real-time text, thinking, tool calls, and interaction events
- **SQLite persistence** — conversations and messages survive restarts
- **Workspace isolation** — per-conversation file system with safety sandbox
- **6-language i18n** — zh-CN, en-US, ja-JP, ko-KR, fr-FR, de-DE
- **Context management** — token budget, compression tiers, profile switching
- **Human interaction** — ask_user_question, request_approval with pause/resume
- **File upload** — multi-file, text extraction (PDF/DOCX/PPTX/TXT/MD), workspace storage
- **Export** — conversation export to Markdown/TXT with anonymization

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- DeepSeek API key (or Kimi)

### Backend

```bash
cd project/backend
pip install -r requirements.txt
python main.py
# API: http://127.0.0.1:8000
```

### Frontend

```bash
cd project/frontend
npm install
npm run dev
# UI: http://127.0.0.1:5173
```

## Architecture

```
backend/
  agent/          — Agent loop, tool registry, model adapter, SSE streaming
  api/            — FastAPI routes (chat, conversations, workspace, tools, uploads)
  context/        — Token budget, compression, profile management
  core/           — Config, auth, streaming infrastructure
  db/             — SQLAlchemy ORM, session management
  prompt/         — Prompt builder, blocks, tool prompt registry
  services/       — Upload, file parsing, context tracking, LLM summary
  tools/          — IPython runtime, file tools
  workspace/      — Workspace manager, sandbox, storage

frontend/
  src/
    components/   — React components (chat, composer, layout, tools)
    i18n/         — 6-language dictionaries
    services/     — API client
    stores/       — Zustand state management
```

## Tools

| Category | Tools |
|----------|-------|
| File Ops | file_read, edit_file, write_to_file, delete_file, apply_patch |
| Workspace | list_directory, snapshot, search_workspace |
| Shell | shell_command |
| Python | ipython |
| Web | web_search, web_fetch |
| System | set_todo_list, ask_user_question, request_approval |

## License

MIT
