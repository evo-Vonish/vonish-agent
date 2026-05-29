# Agent 工作台系统

> 从普通聊天网页到完整 Agent 工作台的后端基建级重构。
>
> **日期**: 2026-05-27 | **版本**: v1.0

---

## 架构概览

```
project-root/
├── frontend/    # React 前端 Agent 工作台
├── backend/     # FastAPI Agent 引擎
├── docs/        # 项目文档
├── scripts/     # 工具脚本
├── examples/    # 示例代码
└── docker-compose.yml
```

```
backend/
├── api/           # FastAPI 路由（8 个模块）
├── core/          # 基础设施（配置、认证、SSE、异常、日志）
├── agent/         # Agent 引擎（Loop、Tool、Model Adapter）
├── context/       # Context OS（Builder、Profile、Budget、Memory、Compression）
├── workspace/     # 文件系统（双存储、沙箱、快照、Diff）
├── skills/        # Skill 框架（基类、Schema、预留实现）
├── services/      # 业务服务（上传、解析、Embedding、搜索、爬虫）
├── db/            # 数据层（SQLAlchemy 模型、会话）
├── prompts/       # Prompt 工程（16 个模板、Builder 引擎）
└── tests/         # 测试
```

---

## 核心特性

### Agent 引擎
- **多轮 Agent Loop**：支持工具调用 -> 执行 -> 回填 -> 再调用的完整循环
- **JSON Output 工具调用**：统一格式，支持多个工具并行调用
- **防循环机制**：指纹检测、重复限制、最大轮数/成本/时间限制
- **中断支持**：用户可随时中断生成

### 模型适配层
- **DeepSeek V4-Pro/Flash**：thinking + reasoning_content + JSON mode
- **Kimi K2.6/K2.5**：reasoning_content + Vision + 自动上下文缓存
- **统一接口**：`stream_chat()` 屏蔽提供商差异

### Context OS
- **六层上下文架构**：System Prompt + Memory + Workspace + Recent Messages + Tool Definitions + Query
- **四档预算配置**：Cheap(32K) / Balanced(96K) / Max(256K) / Custom
- **渐进式压缩**：70%/80%/85%/90%/99% 五级阈值
- **向量召回 + RRF 融合**：Dense + BM25 混合检索

### Workspace 系统
- **会话级隔离**：每个会话独立工作区
- **双存储模式**：Server + Local 默认双写
- **路径沙箱**：防止 ../ 遍历、符号链接逃逸
- **快照/Diff**：每轮前后快照对比，文件变更追踪

### 文件上传与处理
- **批量上传**：支持 50+ 文件同时处理
- **多模态支持**：文本类(PDF/DOCX/MD) + 图像类(PNG/JPG)
- **处理管线**：解析 -> 摘要 -> 分块 -> Embedding -> 索引

### Prompt 工程
- **16 个结构化模板**：system/agent/tool/context 四层
- **Builder 引擎**：动态组装、变量替换、版本控制
- **Feature Flag**：工具调用规范默认关闭，接入后开启

---

## 快速开始

### 环境要求
- Python 3.12+
- PostgreSQL 14+（可选 pgvector）
- Node.js 20+（前端）
- Docker + Docker Compose（推荐）

### 使用 Docker Compose（推荐）

```bash
# 启动全部服务
docker-compose up -d

# 访问前端 http://localhost:3000
# 访问后端 API http://localhost:8000/docs
```

### 手动安装后端

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

### 手动安装前端

```bash
cd frontend
npm install
npm run build
# 或开发模式
npm run dev
```

### API 文档

启动后访问：`http://localhost:8000/docs`

---

## API 接口

| 模块 | 接口 | 说明 |
|------|------|------|
| 会话 | `POST /api/conversations` | 创建会话 |
| 聊天 | `POST /api/chat/{id}/stream` | SSE 流式聊天 |
| 中断 | `POST /api/chat/{id}/stop` | 停止生成 |
| 上传 | `POST /api/uploads/{id}` | 批量文件上传 |
| Workspace | `GET /api/workspaces/{id}/files` | 文件列表 |
| 上下文 | `GET /api/context/{id}/usage` | Token 使用量 |
| 记忆 | `GET /api/memory/user` | 用户记忆 |
| 模型 | `GET /api/models` | 模型列表 |

---

## 前端界面

### 布局
- **深色主题**（#0d0d0d）参考 Claude Code 风格
- **左下角菜单**：Language / Account / Settings
- **可收起侧边栏**：会话列表 + Workspace 文件树
- **输入区上方小组件**：上下文管理 / 导出 / 模型切换

### 组件
- **Thinking Card**：可折叠思考过程展示
- **Tool Card**：工具调用时间线展示
- **Context Manager Panel**：Token 仪表盘 + 档位切换
- **Markdown Renderer**：完整 Markdown 全家桶

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

## 文档导航

| 文档 | 路径 | 说明 |
|------|------|------|
| **项目地图** | [`docs/project-map.md`](docs/project-map.md) | **核心导航文档，快速定位代码** |
| 架构总览 | [`docs/architecture.md`](docs/architecture.md) | 系统架构设计 |
| API 文档 | [`docs/api.md`](docs/api.md) | REST API 详细说明 |
| Agent 工作流 | [`docs/agent-workflow.md`](docs/agent-workflow.md) | Agent 循环详细流程 |
| Context OS | [`docs/context-os.md`](docs/context-os.md) | 上下文操作系统 |
| Workspace | [`docs/workspace.md`](docs/workspace.md) | 文件管理与沙箱 |
| 前端说明 | [`docs/frontend-preview.md`](docs/frontend-preview.md) | 前端界面说明 |
| 迁移方案 | [`docs/migration.md`](docs/migration.md) | Feature Flag 灰度切换与回滚计划 |

---

## 核心原则

1. **先新建，后替换** — backend 独立运行，不破坏旧系统
2. **真实流式** — 模型原生 SSE，不是伪流式打字机
3. **完整上下文** — 数据库保存完整历史，Context Builder 动态组装
4. **工具 JSON 闭环** — JSON Output 统一工具调用，白名单校验
5. **双存储保障** — Server + Local 默认双写
6. **路径沙箱** — 所有文件操作限制在 Workspace 内
