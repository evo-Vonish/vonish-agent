# Project Map

> **项目**: Agent 工作台系统 | **版本**: v1.0 | **日期**: 2026-05-28

本文档是项目的中央导航图，帮助开发者快速定位代码和模块。

---

## 目录导航

### `frontend/` — 前端 Agent 工作台

| 入口 | 路径 | 说明 |
|------|------|------|
| 启动入口 | `frontend/src/main.tsx` | React 应用入口（Vite + React 18） |
| 根组件 | `frontend/src/App.tsx` | 路由定义 + 全局布局 |
| 布局组件 | `frontend/src/components/layout/` | TopBar, Sidebar, StatusBar, MainLayout |
| 聊天组件 | `frontend/src/components/chat/` | MessageStream, ThinkingCard, ToolCard, MarkdownRenderer |
| 输入区 | `frontend/src/components/composer/` | Composer, ContextManagerPanel, ModelSelector |
| 状态管理 | `frontend/src/stores/` | Zustand 全局状态管理 |
| 类型定义 | `frontend/src/types/` | TypeScript 类型和接口定义 |
| 服务层 | `frontend/src/services/` | API 调用封装 |
| 工具库 | `frontend/src/lib/` | 工具函数和常量 |

### `backend/` — FastAPI Agent 引擎

| 模块 | 路径 | 说明 |
|------|------|------|
| FastAPI 入口 | `backend/main.py` | 应用启动、路由注册、生命周期事件 |
| **API 路由** | `backend/app/api/` | 8 个路由模块（见下表） |
| **Agent Loop** | `backend/app/agent/agent_loop.py` | 多轮 Agent 循环控制 |
| **模型适配** | `backend/app/agent/model_adapter.py` | DeepSeek V4 + Kimi K2 适配层 |
| **工具注册** | `backend/app/agent/tool_registry.py` | 白名单工具注册与管理 |
| **工具执行** | `backend/app/agent/tool_executor.py` | 工具调用执行引擎 |
| **工具解析** | `backend/app/agent/tool_parser.py` | 工具调用 JSON 解析 |
| **工具生命周期** | `backend/app/agent/tool_lifecycle.py` | 工具调用生命周期管理 |
| **Context Builder** | `backend/app/context/context_builder.py` | 六层上下文组装引擎 |
| **Context Profile** | `backend/app/context/context_profile.py` | 四档预算配置（Cheap/Balanced/Max/Custom） |
| **Token Budget** | `backend/app/context/token_budget.py` | 渐进式压缩阈值管理 |
| **Memory Selector** | `backend/app/context/memory_selector.py` | 向量召回 + RRF 融合检索 |
| **Compression Engine** | `backend/app/context/compression_engine.py` | 智能上下文压缩 |
| **Workspace Manager** | `backend/app/workspace/workspace_manager.py` | 会话级文件管理 |
| **路径沙箱** | `backend/app/workspace/permissions.py` | 安全路径验证（防遍历/逃逸） |
| **快照/Diff** | `backend/app/workspace/snapshot.py` / `diff.py` | 文件变更追踪 |
| **双存储** | `backend/app/workspace/local_provider.py` / `server_provider.py` | Server + Local 双写 |
| **文件上传** | `backend/app/services/upload_service.py` | 批量上传处理管线 |
| **文件解析** | `backend/app/services/file_parser.py` | 多格式文件解析 |
| **Embedding** | `backend/app/services/embedding_service.py` | 文本向量化 |
| **搜索** | `backend/app/services/search_service.py` | 混合搜索服务 |
| **爬虫** | `backend/app/services/crawl_service.py` | 网页爬取服务 |
| **Prompt Builder** | `backend/app/prompts/builder.py` | 动态 Prompt 组装引擎 |
| **Prompt 模板** | `backend/app/prompts/` | 16 个结构化模板（system/agent/tool/context） |
| **数据库模型** | `backend/app/db/models.py` | SQLAlchemy ORM 定义 |
| **数据库会话** | `backend/app/db/session.py` | 异步数据库会话管理 |
| **配置中心** | `backend/app/core/config.py` | 环境变量与配置管理 |
| **认证** | `backend/app/core/auth.py` | API 认证中间件 |
| **安全** | `backend/app/core/security.py` | CORS/加密/安全工具 |
| **SSE 流式** | `backend/app/core/streaming.py` | Server-Sent Events 流式输出 |
| **异常处理** | `backend/app/core/errors.py` | 全局异常处理器 |
| **日志** | `backend/app/core/logging.py` | 结构化日志系统 |
| **Skill 基类** | `backend/app/skills/base.py` | Skill 框架抽象基类 |
| **Skill Schema** | `backend/app/skills/schema/` | 6 个工具 JSON Schema 定义 |

### API 路由一览

| 路由模块 | 文件 | 主要端点 |
|----------|------|----------|
| 聊天 | `api/chat.py` | `POST /api/chat/{id}/stream`, `POST /api/chat/{id}/stop` |
| 会话 | `api/conversations.py` | `POST /api/conversations`, `GET /api/conversations` |
| 上传 | `api/uploads.py` | `POST /api/uploads/{id}` |
| Workspace | `api/workspace.py` | `GET/POST /api/workspaces/{id}/files` |
| 工具 | `api/tools.py` | `GET /api/tools`, `POST /api/tools/execute` |
| 上下文 | `api/context.py` | `GET /api/context/{id}/usage` |
| 记忆 | `api/memory.py` | `GET /api/memory/user` |
| 模型 | `api/models.py` | `GET /api/models` |

---

## 数据流图

```
┌─────────────┐      HTTP/SSE      ┌─────────────┐
│  Frontend   │ ◄────────────────► │   Backend   │
│  (React)    │   /api/chat/stream │  (FastAPI)  │
└─────────────┘                    └──────┬──────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
              ┌─────▼─────┐     ┌─────────▼─────────┐   ┌─────▼──────┐
              │  Agent    │     │   Context OS      │   │ Workspace  │
              │  Loop     │     │   (Builder/Profile)│   │ Manager    │
              └─────┬─────┘     └─────────┬─────────┘   └─────┬──────┘
                    │                     │                     │
              ┌─────▼─────┐     ┌─────────▼─────────┐   ┌─────▼──────┐
              │  Tool     │     │   Token Budget    │   │  Storage   │
              │  Registry │     │   /Compression    │   │ (Dual)     │
              └─────┬─────┘     └─────────┬─────────┘   └────────────┘
                    │                     │
              ┌─────▼─────┐     ┌─────────▼─────────┐
              │  Model    │     │   Database        │
              │  Adapter  │     │   (PostgreSQL)    │
              │(DeepSeek/│     └─────────────────────┘
              │  Kimi)   │
              └───────────┘
```

---

## 快速启动

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 配置环境变量
export DATABASE_URL="postgresql://user:pass@localhost:5432/agent_db"
export DEEPSEEK_API_KEY="sk-..."
export KIMI_API_KEY="sk-..."
export WORKSPACE_ROOT="./workspaces"

# 运行
python main.py
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

### Docker Compose（推荐）

```bash
docker-compose up -d
```

---

## 项目统计

| 指标 | 数值 |
|------|------|
| 后端 Python 文件 | 60 |
| 后端代码行数 | ~16,000 |
| 前端 TS/TSX 文件 | 26 |
| 前端代码行数 | ~2,000 |
| Prompt 模板 | 16 |
| API 端点 | 25+ |
| SSE 事件类型 | 18 |
| 数据库表 | 15 |

---

## 相关文档

- [架构总览](architecture.md) — 系统架构设计
- [API 接口文档](api.md) — REST API 详细说明
- [Agent 工作流](agent-workflow.md) — Agent 循环详细流程
- [Context OS](context-os.md) — 上下文操作系统
- [Workspace 系统](workspace.md) — 文件管理与沙箱
- [前端说明](frontend-preview.md) — 前端界面说明
- [迁移方案](migration.md) — 从旧系统迁移与回滚计划
