# Architecture Overview

> **系统**: Agent 工作台系统 | **版本**: v1.0

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (Frontend)                       │
│  React 18 + Vite + TypeScript + Tailwind CSS + Zustand      │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Layout   │  │ Chat     │  │ Composer │  │ Context   │  │
│  │ (TopBar, │  │ (Message │  │ (Input + │  │ Manager   │  │
│  │ Sidebar, │  │ Stream,  │  │ Model    │  │ Panel)    │  │
│  │ Status)  │  │ Thinking)│  │ Selector)│  │           │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬─────┘  │
└───────┼─────────────┼─────────────┼──────────────┼────────┘
        │             │             │              │
        └─────────────┴──────┬──────┴──────────────┘
                             │ HTTP / SSE
┌────────────────────────────▼──────────────────────────────┐
│                      后端 (Backend)                        │
│              FastAPI + SQLAlchemy + PostgreSQL             │
│                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ API Layer    │  │ Agent Engine │  │ Context OS      │  │
│  │ (8 routers)  │  │ (Loop/Tool/  │  │ (Builder/Profile│  │
│  │              │  │  Model Adap) │  │ /Budget/Compress)│  │
│  └──────┬───────┘  └──────┬─────┘  └────────┬────────┘  │
│         │                 │                   │           │
│  ┌──────▼───────┐  ┌─────▼──────┐  ┌─────────▼────────┐  │
│  │ Services     │  │ Workspace  │  │ Prompts          │  │
│  │ (Upload/     │  │ (Manager/  │  │ (16 Templates/   │  │
│  │  Parse/Embed/│  │  Storage/  │  │  Builder Engine) │  │
│  │  Search/Crawl)│ │  Snapshot) │  │                  │  │
│  └──────┬───────┘  └─────┬──────┘  └──────────────────┘  │
│         │                │                                 │
│  ┌──────▼───────┐  ┌─────▼──────┐                         │
│  │ Core         │  │ Database   │                         │
│  │ (Config/Auth/│  │ (Models/   │                         │
│  │  Security/SSE│  │  Session)  │                         │
│  │  /Errors/Log)│  │            │                         │
│  └──────────────┘  └────────────┘                         │
└────────────────────────────────────────────────────────────┘
```

---

## 核心模块说明

### 1. Agent 引擎 (`agent/`)

Agent 引擎是系统的核心，负责模型交互、工具调用和多轮循环控制。

**关键组件**:
- **Agent Loop** (`agent_loop.py`): 主循环控制器，管理 think -> act -> observe 循环
- **Model Adapter** (`model_adapter.py`): 统一 DeepSeek 和 Kimi 的调用接口
- **Tool Registry** (`tool_registry.py`): 工具白名单注册与发现
- **Tool Executor** (`tool_executor.py`): 工具调用执行引擎
- **Tool Parser** (`tool_parser.py`): 解析模型输出的 JSON 工具调用
- **Tool Lifecycle** (`tool_lifecycle.py`): 管理工具调用的完整生命周期

### 2. Context OS (`context/`)

Context OS 负责上下文的智能组装、预算管理和压缩。

**关键组件**:
- **Context Builder** (`context_builder.py`): 六层上下文组装
- **Context Profile** (`context_profile.py`): 四档预算配置
- **Token Budget** (`token_budget.py`): 渐进式压缩阈值
- **Memory Selector** (`memory_selector.py`): 向量召回记忆选择
- **Compression Engine** (`compression_engine.py`): 智能压缩算法

### 3. Workspace (`workspace/`)

Workspace 提供会话级的文件管理和安全沙箱。

**关键组件**:
- **Workspace Manager** (`workspace_manager.py`): 会话文件管理
- **Permissions** (`permissions.py`): 路径沙箱验证
- **Snapshot** (`snapshot.py`): 文件变更快照
- **Diff** (`diff.py`): 变更对比
- **Storage Providers** (`local_provider.py`, `server_provider.py`): 双存储模式

### 4. Services (`services/`)

Services 层提供上传、解析、嵌入、搜索和爬虫等业务能力。

**关键组件**:
- **Upload Service** (`upload_service.py`): 批量文件上传处理
- **File Parser** (`file_parser.py`): 多格式文件解析
- **Embedding Service** (`embedding_service.py`): 文本向量化
- **Search Service** (`search_service.py`): 混合搜索
- **Crawl Service** (`crawl_service.py`): 网页爬取

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | React 18 + TypeScript |
| 构建工具 | Vite |
| 样式 | Tailwind CSS |
| 状态管理 | Zustand |
| UI 组件 | shadcn/ui |
| Markdown | react-markdown + remark-gfm + rehype-katex |
| 后端框架 | FastAPI |
| ORM | SQLAlchemy (async) |
| 数据库 | PostgreSQL 16 |
| 向量搜索 | pgvector |
| 模型 API | DeepSeek V4, Kimi K2 |
| 部署 | Docker + Docker Compose |
