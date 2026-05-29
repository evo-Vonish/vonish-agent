# Agent 工作台系统 — 项目转交书

> **版本**: v1.0 | **日期**: 2026-05-28 | **状态**: 可部署
>
> 本文档面向接手该项目的开发者。假设你有 Python/FastAPI、React、PostgreSQL 的基础经验，但完全不熟悉本项目。按照本文档逐步操作，你应该能在 30 分钟内将项目完整跑起来。

---

## 目录

1. [项目概述](#1-项目概述)
2. [环境要求](#2-环境要求)
3. [克隆与初始化](#3-克隆与初始化)
4. [后端部署](#4-后端部署)
5. [前端部署](#5-前端部署)
6. [Docker 部署（可选）](#6-docker-部署可选)
7. [项目结构导航](#7-项目结构导航)
8. [核心模块速查](#8-核心模块速查)
9. [配置速查表](#9-配置速查表)
10. [常见问题](#10-常见问题)
11. [测试](#11-测试)
12. [已知限制](#12-已知限制)
13. [下一步工作](#13-下一步工作)

---

## 1. 项目概述

### 1.1 这是什么

**Agent 工作台系统** — 一个基于大语言模型的智能体（Agent）交互平台。用户通过前端界面与 AI Agent 对话，Agent 能够自主调用工具（文件读写、搜索、代码执行等）、管理上下文、操作用户工作区文件，完成复杂的多步骤任务。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| **Agent Loop** | 多轮工具调用闭环：Think -> Act -> Observe -> Repeat，支持最多 10 轮自动迭代 |
| **Context OS** | 六层上下文架构（System + Memory + Workspace + History + Tools + Query），四档预算配置，智能压缩 |
| **Workspace** | 会话级文件沙箱，支持双存储（Server + Local），路径安全校验，文件变更快照/Diff |
| **Tool Runtime** | 文件操作工具集（read/write/edit/delete/patch），JSON 格式工具调用，白名单校验 |
| **多模型支持** | DeepSeek V4-Pro/Flash + Kimi K2.6/K2.5，统一适配接口 |
| **文件上传处理** | 批量上传（50+ 文件），PDF/DOCX/MD/PNG/JPG 解析，Embedding 索引 |
| **流式响应** | 原生 SSE 流式输出，支持 thinking/reasoning_content 折叠展示 |

### 1.3 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | React 19 + TypeScript 5.7 |
| 构建工具 | Vite 6 |
| 样式 | Tailwind CSS 3.4 + shadcn/ui |
| 状态管理 | Zustand 5 |
| Markdown | react-markdown + remark-gfm + rehype-katex |
| 后端框架 | FastAPI 0.115 + Uvicorn |
| ORM | SQLAlchemy 2.0 (async) + Alembic |
| 数据库 | PostgreSQL 16 |
| 向量存储 | ChromaDB + pgvector (预留) |
| 模型 API | DeepSeek V4 + Kimi K2 |

### 1.4 项目规模

| 指标 | 数值 |
|------|------|
| 后端 Python 文件 | 71 |
| 后端代码行数 | ~20,000 |
| 前端 TS/TSX 文件 | 26 |
| 前端代码行数 | ~2,000 |
| Prompt 模板 | 16 |
| API 端点 | 25+ |
| SSE 事件类型 | 18 |
| 数据库表 | 11 |
| Git 提交数 | 16 |

---

## 2. 环境要求

### 2.1 操作系统

| 系统 | 兼容性 | 备注 |
|------|--------|------|
| Linux | 原生支持 | 推荐 Ubuntu 22.04+ |
| macOS | 原生支持 | 推荐 macOS 14+ |
| Windows | WSL2 支持 | **不建议直接在 Windows 上运行** |

### 2.2 依赖软件

| 软件 | 最低版本 | 用途 |
|------|----------|------|
| Python | 3.12 | 后端运行时 |
| Node.js | 20 | 前端构建 |
| PostgreSQL | 14 | 主数据库（推荐 16） |
| Git | 2.40 | 版本控制 |

### 2.3 可选软件

| 软件 | 用途 |
|------|------|
| Redis | 缓存 / 分布式锁（当前未强制使用） |
| Docker + Docker Compose | 一键部署 |
| pgvector | 向量检索（当前用 ARRAY(Float) 兼容方案） |

---

## 3. 克隆与初始化

```bash
# 克隆仓库
git clone <repo-url>
cd project

# 项目结构预览
ls -la
# 应有：backend/  frontend/  docs/  docker-compose.yml  README.md
```

---

## 4. 后端部署

### 4.1 数据库设置

#### macOS (Homebrew)

```bash
brew install postgresql@16
brew services start postgresql@16

# 创建数据库和用户
createdb agent_db
createuser -P agent_user   # 按提示设置密码
psql -c "GRANT ALL PRIVILEGES ON DATABASE agent_db TO agent_user;"
```

#### Ubuntu/Debian

```bash
sudo apt update
sudo apt install postgresql-16 postgresql-contrib
sudo systemctl start postgresql

# 切换到 postgres 用户操作
sudo -u postgres psql <<EOF
CREATE DATABASE agent_db;
CREATE USER agent_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE agent_db TO agent_user;
ALTER DATABASE agent_db OWNER TO agent_user;
EOF
```

#### 验证连接

```bash
psql postgresql://agent_user:your_password@localhost:5432/agent_db -c "\dt"
```

### 4.2 虚拟环境与依赖

```bash
cd backend

# 创建虚拟环境
python -m venv .venv

# 激活（Linux/macOS）
source .venv/bin/activate

# 激活（Windows CMD）
# .venv\Scripts\activate.bat

# 激活（Windows PowerShell）
# .venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

`requirements.txt` 包含的主要依赖：

| 包 | 版本 | 用途 |
|----|------|------|
| fastapi | >=0.115.0 | Web 框架 |
| uvicorn | >=0.32.0 | ASGI 服务器 |
| sqlalchemy | >=2.0.0 | ORM |
| alembic | >=1.13.0 | 数据库迁移 |
| asyncpg | >=0.30.0 | 异步 PostgreSQL 驱动 |
| httpx | >=0.27.0 | HTTP 客户端 |
| pydantic | >=2.7.0 | 数据校验 |
| pydantic-settings | >=2.2.0 | 配置管理 |
| PyMuPDF | >=1.24.0 | PDF 解析 |
| python-docx | >=1.1.0 | DOCX 解析 |
| chromadb | >=0.5.0 | 向量数据库 |

### 4.3 环境变量

```bash
# 从模板复制
cp .env.example .env

# 编辑 .env
nano .env   # 或 vim/code 等你喜欢的编辑器
```

**必须填写的变量：**

```dotenv
# Database — 必须
DATABASE_URL=postgresql://agent_user:your_password@localhost:5432/agent_db

# 至少配置一个模型 API Key — 必须
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
KIMI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# Workspace 根目录 — 建议保持默认
WORKSPACE_ROOT=./workspaces

# 日志级别 — 开发时建议 DEBUG，生产用 INFO
LOG_LEVEL=INFO
```

**可选变量：**

```dotenv
# Redis（可选）
REDIS_URL=redis://localhost:6379/0

# Sentry 错误追踪（可选）
SENTRY_DSN=

# 安全密钥 — 生产环境务必修改
SECRET_KEY=dev-secret-key-change-in-production

# 服务器配置
HOST=0.0.0.0
PORT=8000
RELOAD=false
```

> **获取 API Key**：
> - DeepSeek: https://platform.deepseek.com/
> - Kimi (Moonshot): https://platform.moonshot.cn/

### 4.4 数据库初始化

本项目在启动时会自动创建数据表（通过 `init_db()` lifespan 事件）。如果你需要手动初始化：

```bash
cd backend

# 方式一：直接运行（会自动建表）
python main.py

# 方式二：如果方式一报错，手动创建表
python -c "
import asyncio
from db.session import engine
from db.models import Base
async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
asyncio.run(init())
"
```

> **注意**：本项目目前没有 Alembic 迁移脚本（FIXME）。首次启动会自动 `create_all()`。后续 schema 变更需要手动处理或补充 Alembic 迁移。

### 4.5 启动后端

```bash
cd backend
source .venv/bin/activate

# 方式一：直接运行（推荐开发）
python main.py

# 方式二：使用 uvicorn（推荐生产）
uvicorn main:app --host 0.0.0.0 --port 8000

# 方式三：热重载开发模式
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

启动成功后应看到：

```
============================================================
Agent Backend v2 Starting Up...
Environment: INFO
Database: localhost:5432/agent_db
Workspace Root: ./workspaces
============================================================
Database initialized.
Default tools registered.
Agent Backend v2 is ready!
```

**验证服务**：

```bash
# 健康检查
curl http://localhost:8000/health
# 应返回：{"status":"healthy","version":"1.0.0","service":"agent-backend-v2"}

# API 文档（浏览器打开）
open http://localhost:8000/docs
```

---

## 5. 前端部署

### 5.1 安装依赖

```bash
cd frontend

# 安装 npm 包
npm install
```

### 5.2 开发模式

```bash
cd frontend
npm run dev
```

默认启动在 http://localhost:5173。打开浏览器访问即可。

### 5.3 生产构建

```bash
cd frontend
npm run build
```

构建产物输出到 `frontend/dist/` 目录。可以用以下方式预览：

```bash
npm run preview   # 默认在 localhost:4173
```

### 5.4 与后端联调

前端默认通过代理或相对路径访问后端 API。如果后端不在 `localhost:8000`，修改 `frontend/vite.config.ts` 中的代理配置：

```typescript
// vite.config.ts
export default defineConfig({
  // ...
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',  // 修改为你的后端地址
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
```

---

## 6. Docker 部署（可选）

项目根目录已包含 `docker-compose.yml`，可一键启动全栈。

### 6.1 前置准备

```bash
# 确保安装了 Docker + Docker Compose
docker --version
docker compose version

# 在项目根目录下创建 .env 文件
cat > .env << 'EOF'
DEEPSEEK_API_KEY=sk-your-deepseek-key
KIMI_API_KEY=sk-your-kimi-key
EOF
```

### 6.2 docker-compose.yml 说明

```yaml
version: '3.8'

services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: agent_db
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/agent_db
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - KIMI_API_KEY=${KIMI_API_KEY}
    volumes:
      - ./workspaces:/app/workspaces
    depends_on:
      - db

  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - backend

volumes:
  postgres_data:
```

### 6.3 启动

```bash
cd /mnt/agents/output/project

# 启动所有服务
docker compose up -d

# 查看日志
docker compose logs -f

# 停止
docker compose down

# 停止并删除数据卷
docker compose down -v
```

### 6.4 访问

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:3000 |
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |

---

## 7. 项目结构导航

```
project/
|
├── backend/                    # FastAPI 后端 (~20,000 行)
│   ├── main.py                 # 应用入口：路由注册、生命周期、CORS
│   ├── requirements.txt        # Python 依赖
│   ├── .env.example            # 环境变量模板
│   │
│   ├── agent/                  # Agent 引擎核心
│   │   ├── agent_loop.py       # 多轮 Agent 循环控制器
│   │   ├── model_adapter.py   # DeepSeek + Kimi 统一适配
│   │   ├── tool_registry.py   # 工具白名单注册
│   │   ├── tool_executor.py   # 工具执行引擎
│   │   ├── tool_parser.py     # JSON 工具调用解析
│   │   └── tool_lifecycle.py  # 工具调用生命周期
│   │
│   ├── context/                # Context OS v2
│   │   ├── context_builder.py # 六层上下文组装
│   │   ├── context_profile.py # 四档预算配置
│   │   ├── token_budget.py    # Token 预算管理
│   │   ├── compression_engine.py  # 智能压缩
│   │   ├── memory_selector.py # 向量召回
│   │   └── workspace_context.py  # 工作区上下文
│   │
│   ├── workspace/              # 文件管理 + 沙箱
│   │   ├── workspace_manager.py  # 会话文件管理
│   │   ├── permissions.py     # 路径沙箱校验
│   │   ├── snapshot.py        # 文件快照
│   │   ├── diff.py            # 变更对比
│   │   ├── local_provider.py  # 本地存储
│   │   └── server_provider.py # 服务端存储
│   │
│   ├── tools/                  # 工具实现
│   │   ├── file_tools.py      # 文件操作工具
│   │   ├── schemas.py         # 工具 JSON Schema
│   │   └── registry.py        # 工具注册
│   │
│   ├── api/                    # FastAPI 路由 (8 模块)
│   │   ├── chat.py            # SSE 流式聊天
│   │   ├── conversations.py   # 会话 CRUD
│   │   ├── workspace.py       # 文件管理
│   │   ├── uploads.py         # 批量上传
│   │   ├── tools.py           # 工具列表/执行
│   │   ├── context.py         # 上下文用量
│   │   ├── memory.py          # 记忆管理
│   │   └── models.py          # 模型列表
│   │
│   ├── db/                     # 数据层
│   │   ├── models.py          # SQLAlchemy ORM (11 张表)
│   │   ├── session.py         # 异步会话管理
│   │   └── repositories/      # 仓库模式（预留）
│   │
│   ├── core/                   # 基础设施
│   │   ├── config.py          # Pydantic Settings 配置
│   │   ├── auth.py            # 认证中间件
│   │   ├── security.py        # CORS/加密
│   │   ├── streaming.py       # SSE 流式输出
│   │   ├── errors.py          # 全局异常处理
│   │   └── logging.py         # 结构化日志
│   │
│   ├── services/               # 业务服务
│   │   ├── upload_service.py  # 上传处理管线
│   │   ├── file_parser.py     # 文件解析
│   │   ├── embedding_service.py  # 文本向量化
│   │   ├── search_service.py  # 混合搜索
│   │   └── crawl_service.py   # 网页爬取
│   │
│   ├── prompts/                # Prompt 工程 (16 模板)
│   │   ├── builder.py         # 动态组装引擎
│   │   ├── system/            # 系统级模板
│   │   ├── agent/             # Agent 循环模板
│   │   ├── context/           # 上下文模板
│   │   └── tool/              # 工具结果模板
│   │
│   ├── skills/                 # Skill 框架（预留）
│   │   ├── base.py            # 抽象基类
│   │   ├── schema/            # JSON Schema 定义
│   │   └── implementations/   # 预留实现
│   │
│   └── tests/                  # 测试
│       ├── unit/
│       └── integration/
│
├── frontend/                   # React 19 前端 (~2,000 行)
│   ├── package.json            # npm 依赖
│   ├── vite.config.ts          # Vite 配置
│   ├── tailwind.config.js      # Tailwind 配置
│   │
│   ├── src/
│   │   ├── main.tsx            # React 入口
│   │   ├── App.tsx             # 根组件 + 路由
│   │   ├── index.css           # 全局样式
│   │   │
│   │   ├── components/
│   │   │   ├── layout/         # 布局组件
│   │   │   │   ├── MainLayout.tsx
│   │   │   │   ├── Sidebar.tsx      # 会话列表 + 文件树
│   │   │   │   ├── TopBar.tsx       # 顶部工具栏
│   │   │   │   └── StatusBar.tsx    # 底部状态栏
│   │   │   │
│   │   │   ├── chat/           # 聊天展示组件
│   │   │   │   ├── MessageStream.tsx   # 消息流容器
│   │   │   │   ├── MessageBubble.tsx   # 消息气泡
│   │   │   │   ├── ThinkingCard.tsx    # 可折叠思考过程
│   │   │   │   ├── ToolCard.tsx        # 工具调用卡片
│   │   │   │   └── MarkdownRenderer.tsx  # Markdown 渲染
│   │   │   │
│   │   │   ├── composer/       # 输入区组件
│   │   │   │   ├── Composer.tsx           # 输入框主体
│   │   │   │   ├── ContextManagerPanel.tsx  # Token 仪表盘
│   │   │   │   ├── ModelSelector.tsx       # 模型切换
│   │   │   │   ├── AttachmentBar.tsx       # 附件栏
│   │   │   │   └── InputWidgets.tsx        # 输入区小工具
│   │   │   │
│   │   │   └── ui/             # 通用 UI 组件
│   │   │       ├── Progress.tsx
│   │   │       └── Tooltip.tsx
│   │   │
│   │   ├── stores/             # Zustand 状态管理
│   │   │   ├── chatStore.ts    # 聊天状态
│   │   │   └── uiStore.ts      # UI 状态
│   │   │
│   │   ├── types/              # TypeScript 类型
│   │   │   └── index.ts
│   │   │
│   │   ├── services/           # API 调用
│   │   │   └── mockData.ts
│   │   │
│   │   └── lib/                # 工具函数
│   │       └── utils.ts
│   │
│   └── dist/                   # 构建产物
│
├── docs/                       # 项目文档 (13 文件)
│   ├── HANDOVER.md            # 本文档
│   ├── architecture.md        # 架构总览
│   ├── project-map.md         # 代码导航地图
│   ├── api.md                 # API 接口文档
│   ├── agent-workflow.md      # Agent 循环流程
│   ├── context-os.md          # Context OS 设计
│   ├── context-os-review.md   # Context OS 评审
│   ├── workspace.md           # Workspace 系统
│   ├── tool-loop-demo.md      # 工具调用 Demo
│   ├── workflow-test-report.md # 验收测试报告
│   ├── frontend-preview.md    # 前端说明
│   ├── migration.md           # 迁移方案
│   └── screenshots/           # 截图
│
├── scripts/                    # 工具脚本
│   ├── migrate_from_legacy.py
│   └── verify_migration.py
│
├── examples/                   # 示例代码
│   └── echo_tool_demo.py
│
├── docker-compose.yml          # Docker 编排
└── README.md                   # 项目说明
```

---

## 8. 核心模块速查

| 模块 | 路径 | 一句话说明 |
|------|------|-----------|
| **Agent Loop** | `backend/agent/agent_loop.py` | 多轮对话控制器：接收输入→构建上下文→流式调用模型→解析工具调用→执行→回填结果→循环，直到无工具调用或达上限 |
| **Model Adapter** | `backend/agent/model_adapter.py` | 统一 DeepSeek 和 Kimi 的调用接口，屏蔽 provider 差异，支持 thinking/reasoning_content/JSON mode |
| **Tool Registry** | `backend/agent/tool_registry.py` | 工具白名单注册中心，启动时自动注册默认工具集（文件读写编辑删除等） |
| **Tool Executor** | `backend/agent/tool_executor.py` | 工具调用执行引擎，负责分派工具函数、捕获异常、格式化结果 |
| **Tool Parser** | `backend/agent/tool_parser.py` | 解析模型输出的 JSON 格式工具调用，校验参数 schema |
| **Context Builder** | `backend/context/context_builder.py` | 六层上下文组装：System Prompt + Memory + Workspace + Recent Messages + Tool Definitions + Query |
| **Context Profile** | `backend/context/context_profile.py` | 四档预算配置 Cheap(32K)/Balanced(96K)/Max(256K)/Custom，控制资源分配策略 |
| **Token Budget** | `backend/context/token_budget.py` | 渐进式压缩阈值管理，70%/80%/85%/90%/99% 五级触发 |
| **Compression Engine** | `backend/context/compression_engine.py` | 智能上下文压缩算法，按优先级和时效性选择性压缩 |
| **Memory Selector** | `backend/context/memory_selector.py` | 向量召回 + RRF 融合检索，从长期记忆中选择相关内容 |
| **Workspace Manager** | `backend/workspace/workspace_manager.py` | 会话级文件管理器，提供文件列表、读写、快照、Diff 能力 |
| **Path Sandbox** | `backend/workspace/permissions.py` | 路径安全校验：阻止 `../` 遍历、符号链接逃逸、绝对路径越界 |
| **File Tools** | `backend/tools/file_tools.py` | 文件操作工具实现：read_file/write_file/edit_file/delete_file/patch_file |
| **API Routes** | `backend/api/` | 8 个路由模块，覆盖聊天/会话/上传/Workspace/工具/上下文/记忆/模型 |
| **DB Models** | `backend/db/models.py` | 11 张表：User/Conversation/Message/WorkspaceFile/Resource/ResourceChunk/ToolCall/UserMemory/ConversationMemory/WorkspaceSnapshot/TokenUsage/ContextBuild |
| **Prompt Builder** | `backend/prompts/builder.py` | 动态 Prompt 组装引擎，支持变量替换和版本控制 |
| **Frontend** | `frontend/src/` | React 19 + Vite + Tailwind，组件化架构，Zustand 状态管理 |

---

## 9. 配置速查表

### 9.1 后端环境变量

| 变量名 | 默认值 | 必填 | 说明 |
|--------|--------|------|------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@localhost:5432/agent_db` | 是 | PostgreSQL 连接串 |
| `DEEPSEEK_API_KEY` | （空） | 至少一个 | DeepSeek API 密钥 |
| `KIMI_API_KEY` | （空） | 至少一个 | Kimi API 密钥 |
| `WORKSPACE_ROOT` | `/mnt/agents/output/project/workspaces` | 否 | 工作区根目录 |
| `WORKSPACE_LOCAL_CACHE` | `/mnt/agents/output/project/workspace_cache` | 否 | 本地缓存目录 |
| `REDIS_URL` | `redis://localhost:6379/0` | 否 | Redis 连接串（可选） |
| `SENTRY_DSN` | （空） | 否 | Sentry 错误追踪 |
| `LOG_LEVEL` | `INFO` | 否 | 日志级别：DEBUG/INFO/WARNING/ERROR |
| `SECRET_KEY` | `dev-secret-key-change-in-production` | 否 | JWT 签名密钥 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080`（7天） | 否 | Token 过期时间 |
| `HOST` | `0.0.0.0` | 否 | 监听地址 |
| `PORT` | `8000` | 否 | 监听端口 |
| `RELOAD` | `false` | 否 | 热重载（仅开发） |

### 9.2 支持的模型

| 模型 ID | 提供商 | 上下文窗口 | 特性 |
|---------|--------|-----------|------|
| `deepseek-v4-pro` | DeepSeek | 1M | thinking + JSON mode + context cache |
| `deepseek-v4-flash` | DeepSeek | 1M | 同上，更快更便宜 |
| `kimi-k2-6` | Kimi | 256K | thinking + vision + JSON mode |
| `kimi-k2-5` | Kimi | 256K | 同上 |

### 9.3 Context Profile 配置

| Profile | 输入 Token | 最近轮数 | 工具结果 | 记忆召回 | 压缩策略 |
|---------|-----------|----------|----------|----------|----------|
| `cheap` | 32K | 6 | summary | 5 | aggressive |
| `balanced` | 96K | 16 | hybrid | 12 | balanced |
| `max` | 256K | 50 | verbose | 30 | minimal |
| `custom` | 96K | 16 | hybrid | 12 | balanced |

---

## 10. 常见问题

### Q1: 数据库连接失败

**现象**：启动时报 `Connection refused` 或 `FATAL: database "agent_db" does not exist`

**排查步骤**：

```bash
# 1. 确认 PostgreSQL 服务运行中
sudo systemctl status postgresql  # Linux
brew services list | grep postgresql  # macOS

# 2. 确认数据库存在
psql -U agent_user -l | grep agent_db

# 3. 确认用户密码正确
psql postgresql://agent_user:password@localhost:5432/agent_db -c "SELECT 1"

# 4. 检查 .env 中 DATABASE_URL 格式是否正确
# 正确格式：postgresql://user:password@host:port/dbname
# 不需要加 asyncpg 驱动（程序会自动处理）
```

**解决方案**：
- 如果数据库不存在：`createdb agent_db`
- 如果用户不存在：`createuser -P agent_user && psql -c "GRANT ALL PRIVILEGES ON DATABASE agent_db TO agent_user;"`
- 如果是权限问题：检查 `pg_hba.conf` 中是否允许本地连接

---

### Q2: 后端启动报 `ModuleNotFoundError`

**现象**：`ModuleNotFoundError: No module named 'xxx'`

**排查步骤**：

```bash
cd backend

# 1. 确认虚拟环境已激活
which python   # 应显示 .venv/bin/python

# 2. 确认依赖已安装
pip list | grep fastapi

# 3. 如果缺少，重新安装
pip install -r requirements.txt
```

**常见缺失包**：
- `asyncpg` — 异步 PostgreSQL 驱动
- `PyMuPDF` — PDF 解析（安装时可能需要系统依赖）
- `chromadb` — 向量数据库（体积较大，安装较慢）

---

### Q3: 前端 Build 失败

**现象**：`npm run build` 报错

**排查步骤**：

```bash
cd frontend

# 1. 确认 Node.js 版本
node --version   # 需要 v20+

# 2. 删除 lock 和 node_modules 重新安装
rm -rf node_modules package-lock.json
npm install

# 3. 如果 TypeScript 类型错误，检查 tsconfig.json
npx tsc --noEmit
```

**常见问题**：
- `Cannot find module 'xxx'` — 删除 `node_modules` 重装
- TypeScript 类型错误 — 检查 `@types/react` 版本是否与 `react` 一致
- 内存溢出 — `NODE_OPTIONS="--max-old-space-size=4096" npm run build`

---

### Q4: API Key 无效

**现象**：聊天时返回 `401 Unauthorized` 或模型无响应

**排查步骤**：

```bash
# 1. 确认环境变量已设置
echo $DEEPSEEK_API_KEY
echo $KIMI_API_KEY

# 2. 如果通过 .env 文件加载，确认文件位置和格式
cat backend/.env

# 3. 直接测试 API Key 是否有效
curl https://api.deepseek.com/chat/completions \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}]}'
```

**解决方案**：
- 检查 Key 是否过期或额度已用完
- 确认使用的是正确的 API Base URL（不同提供商不同）
- 如果只有一个 Key，确保前端选择的模型与 Key 匹配

---

### Q5: Workspace 权限问题

**现象**：文件操作报错 `Permission denied` 或 `Path outside workspace`

**排查步骤**：

```bash
# 1. 确认工作区目录存在且有写权限
ls -la ./workspaces

# 2. 如果不存在，创建并赋权
mkdir -p ./workspaces
chmod 755 ./workspaces

# 3. 检查 WORKSPACE_ROOT 配置
grep WORKSPACE_ROOT backend/.env
```

**解决方案**：
- 权限不足：`chmod -R 755 ./workspaces`
- 路径越界（`Path outside workspace`）— 这是安全机制正常行为，确认文件路径在 workspace 内
- Docker 中权限问题：检查 volume 挂载的宿主机目录权限

---

### Q6: 前端无法连接到后端

**现象**：页面加载但无法发送消息，控制台报 `Connection refused` 或 CORS 错误

**排查步骤**：

```bash
# 1. 确认后端在运行
curl http://localhost:8000/health

# 2. 检查 CORS 配置（backend/core/security.py）
# 确认允许了前端的 origin

# 3. 检查前端代理配置（vite.config.ts）
# 确认 proxy target 指向正确的后端地址
```

**解决方案**：
- 后端没启动：`cd backend && python main.py`
- CORS 问题：在 `backend/core/security.py` 中添加前端 origin
- 代理问题：开发模式下确保 Vite 的 proxy 配置正确

---

### Q7: 数据库表未创建

**现象**：API 调用报 `relation "xxx" does not exist`

**排查步骤**：

```bashn# 1. 查看数据库中的表
psql postgresql://agent_user:password@localhost:5432/agent_db -c "\dt"

# 2. 如果为空，手动创建
cd backend
python -c "
import asyncio
from db.session import engine
from db.models import Base
async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
asyncio.run(init())
"

# 3. 重新查看
psql postgresql://agent_user:password@localhost:5432/agent_db -c "\dt"
```

---

## 11. 测试

### 运行测试

```bash
cd backend
source .venv/bin/activate

# 运行所有测试
pytest tests/ -v

# 运行单元测试
pytest tests/unit/ -v

# 运行集成测试
pytest tests/integration/ -v

# 带覆盖率报告
pytest tests/ --cov=app --cov-report=term-missing
```

### 添加新测试

测试文件放在对应目录下，命名遵循 `test_*.py`：

```python
# tests/unit/test_example.py
def test_example():
    assert True
```

---

## 12. 已知限制

| # | 限制 | 影响 | 解决方向 |
|---|------|------|----------|
| 1 | **Skill 框架未接入 Agent Loop** | `skills/` 目录已预留基类、Schema 和实现骨架，但 Agent Loop 中不调用 Skill | 在 Agent Loop 中集成 Skill 调用逻辑 |
| 2 | **语音输入 UI 占位** | 前端输入区有语音按钮但无实际功能 | 接入语音识别 API（如 Whisper） |
| 3 | **数学公式渲染待完善** | rehype-katex 已配置但复杂公式可能渲染异常 | 升级 katex 版本，添加更多 math 扩展 |
| 4 | **Mermaid 图表不支持** | Markdown 中 mermaid 代码块不会渲染为图表 | 添加 react-markdown 的 mermaid 插件 |
| 5 | **缺少 Alembic 迁移脚本** | 首次启动自动 create_all，后续 schema 变更需手动处理 | 初始化 Alembic 并创建迁移脚本 |
| 6 | **pgvector 未完全集成** | ResourceChunk 和 UserMemory 使用 ARRAY(Float) 存向量 | 安装 pgvector 扩展并改用 VECTOR 类型 |
| 7 | **用户认证为占位实现** | auth.py 有基础 JWT 逻辑，但无完整的注册/登录流程 | 补全用户注册、登录、权限管理 |
| 8 | **ChromaDB 集成待验证** | embedding_service.py 依赖 ChromaDB，但未在 Agent Loop 中使用 | 确认向量检索链路完整性 |

---

## 13. 下一步工作

按优先级排序的建议开发方向：

### P0 — 修复与完善

1. **补充 Alembic 数据库迁移** — 当前自动 `create_all()` 不够安全，需要正式的迁移脚本
2. **完成 Skill 框架集成** — 将 `skills/` 接入 Agent Loop，实现真正的 Skill 调用
3. **完善错误处理** — 增加更多的边界 case 处理和用户友好的错误提示

### P1 — 功能增强

4. **实现语音输入** — 接入 Whisper 等语音识别 API，完成前端语音按钮功能
5. **完善 Mermaid 和数学公式渲染** — 提升 Markdown 渲染的完整度
6. **用户认证系统** — 完整的注册/登录/会话管理
7. **pgvector 集成** — 替换 ARRAY(Float) 为 VECTOR 类型，提升向量检索性能

### P2 — 优化与扩展

8. **Redis 缓存层** — 实现上下文缓存、分布式锁、会话存储
9. **多 Agent 支持** — 支持多个 Agent 配置和切换
10. **性能优化** — 数据库查询优化、连接池调优、SSE 性能优化
11. **监控与可观测性** — 接入 Prometheus/Grafana，完善日志追踪

### P3 — 文档与工程化

12. **补充 API 测试** — 增加集成测试覆盖率
13. **CI/CD 流水线** — GitHub Actions 自动测试、构建、部署
14. **完善项目文档** — 补充开发者文档、API 变更日志

---

## 附录：快速启动清单

首次部署时按此清单操作：

```
[ ] 1. 克隆仓库
[ ] 2. 安装 PostgreSQL 并创建数据库/用户
[ ] 3. 安装 Python 3.12+ 和 Node.js 20+
[ ] 4. 配置后端 .env（DATABASE_URL + API Keys）
[ ] 5. 安装后端依赖并启动
[ ] 6. 验证 /health 端点
[ ] 7. 安装前端依赖并启动
[ ] 8. 打开浏览器测试对话
[ ] 9. 测试文件上传功能
[ ] 10. 测试工具调用（如文件读写）
```

---

> 如果在部署过程中遇到本文档未覆盖的问题，请查阅 `docs/` 目录下的专项文档，或查看代码中的 docstring 注释。
