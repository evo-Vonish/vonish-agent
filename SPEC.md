# SPEC.md — Agent 工作台系统 (backend_v2)

> **版本**: v1.0 | **日期**: 2026-05-27 | **状态**: 开发中

---

## 1. 项目架构总览

```
/mnt/agents/output/project/
├── backend_v2/                    # FastAPI 后端（核心）
│   ├── main.py                    # 应用入口
│   ├── api/                       # API 路由层
│   │   ├── chat.py                # 流式聊天 + 中断
│   │   ├── conversations.py       # 会话 CRUD
│   │   ├── workspace.py           # Workspace 文件管理
│   │   ├── uploads.py             # 文件上传
│   │   ├── tools.py               # 工具执行
│   │   ├── context.py             # 上下文管理
│   │   ├── memory.py              # 长期记忆
│   │   └── models.py              # 模型列表/切换
│   ├── core/                      # 核心基础设施
│   │   ├── config.py              # 配置管理 (Pydantic Settings)
│   │   ├── auth.py                # 认证占位 (JWT)
│   │   ├── security.py            # 安全工具
│   │   ├── streaming.py           # SSE 流式基础设施
│   │   ├── errors.py              # 全局异常处理
│   │   └── logging.py             # 结构化日志
│   ├── agent/                     # Agent 引擎
│   │   ├── agent_loop.py          # 多轮 Agent Loop
│   │   ├── tool_registry.py       # 工具注册表（白名单）
│   │   ├── tool_executor.py       # 工具执行器
│   │   ├── tool_parser.py         # JSON Output 工具调用解析
│   │   ├── tool_lifecycle.py      # 工具结果五级生命周期
│   │   └── model_adapter.py       # 模型适配层
│   ├── context/                   # Context OS
│   │   ├── context_builder.py     # 上下文构建器（六层架构）
│   │   ├── context_profile.py     # 上下文档位配置
│   │   ├── token_budget.py        # Token 预算管理
│   │   ├── memory_selector.py     # 记忆选择器（向量召回）
│   │   ├── compression_engine.py  # 智能压缩引擎
│   │   └── prompt_builder.py      # Prompt 组装
│   ├── workspace/                 # Workspace 系统
│   │   ├── workspace_manager.py   # 会话级 Workspace 管理
│   │   ├── storage_provider.py    # 双存储抽象
│   │   ├── local_provider.py      # 本地存储 Provider
│   │   ├── server_provider.py     # 服务端存储 Provider
│   │   ├── snapshot.py            # 快照管理
│   │   ├── diff.py                # Diff 生成
│   │   ├── indexer.py             # 文件索引
│   │   └── permissions.py         # 路径沙箱/权限
│   ├── skills/                    # Skill 框架
│   │   ├── __init__.py
│   │   ├── base.py                # BaseSkill 抽象类
│   │   ├── schema/                # JSON Schema
│   │   └── implementations/       # 具体实现（预留）
│   ├── services/                  # 业务服务层
│   │   ├── upload_service.py      # 上传处理服务
│   │   ├── file_parser.py         # 文件解析器
│   │   ├── embedding_service.py   # Embedding 服务
│   │   ├── search_service.py      # 搜索服务
│   │   ├── crawl_service.py       # 爬虫服务
│   │   └── export_service.py      # 导出服务
│   ├── db/                        # 数据层
│   │   ├── models.py              # SQLAlchemy ORM 模型
│   │   ├── session.py             # 数据库会话
│   │   ├── repositories/          # 仓储模式
│   │   └── migrations/            # Alembic 迁移
│   ├── prompts/                   # Prompt 工程
│   │   ├── system/
│   │   ├── agent/
│   │   ├── tool/
│   │   ├── context/
│   │   └── builder.py             # Prompt Builder 引擎
│   └── tests/                     # 测试
├── frontend/                      # React 前端
│   ├── src/
│   │   ├── components/            # 组件
│   │   ├── pages/                 # 页面
│   │   ├── hooks/                 # 自定义 Hooks
│   │   ├── services/              # API 服务
│   │   ├── stores/                # 状态管理
│   │   ├── types/                 # TypeScript 类型
│   │   └── utils/                 # 工具函数
│   └── public/
└── docs/                          # 文档
```

---

## 2. 技术栈

### 后端
- **框架**: FastAPI + Uvicorn
- **数据库**: PostgreSQL + SQLAlchemy 2.0 + Alembic
- **向量存储**: ChromaDB (embedding 召回)
- **缓存**: Redis (可选，本地可用内存缓存兜底)
- **HTTP 客户端**: httpx (异步)
- **配置**: Pydantic Settings
- **任务队列**: asyncio (本阶段不使用 Celery)

### 前端
- **框架**: React 19 + TypeScript
- **构建**: Vite v7.2.4
- **样式**: Tailwind CSS v3.4.19
- **UI 组件**: shadcn/ui
- **状态**: Zustand
- **路由**: React Router v7
- **SSE**: EventSource API

---

## 3. 数据库 Schema

### 3.1 核心表

```sql
-- 用户表
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE,
    avatar_url TEXT,
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 会话表
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    title VARCHAR(255) DEFAULT '新对话',
    model VARCHAR(50) DEFAULT 'deepseek-v4-pro',
    context_profile VARCHAR(20) DEFAULT 'balanced',
    workspace_path TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 消息表（支持 content blocks）
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,  -- 'user' | 'assistant' | 'system' | 'tool'
    content JSONB NOT NULL,  -- content blocks 数组
    thinking_content TEXT,  -- thinking/reasoning 内容
    token_usage JSONB,  -- {input_tokens, output_tokens, cached_tokens}
    model VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Workspace 文件表
CREATE TABLE workspace_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,  -- workspace 内相对路径
    file_size BIGINT,
    mime_type VARCHAR(100),
    resource_id VARCHAR(100) UNIQUE,
    status VARCHAR(20) DEFAULT 'uploaded',  -- uploaded/parsing/parsed/indexed/failed
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 资源表（上传文件/工具生成的资源）
CREATE TABLE resources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    resource_type VARCHAR(50) NOT NULL,  -- 'upload' | 'tool_output' | 'crawl_result'
    uri TEXT NOT NULL,  -- resource://workspace/...
    mime_type VARCHAR(100),
    title TEXT,
    summary TEXT,
    token_count INTEGER,
    status VARCHAR(20) DEFAULT 'active',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 资源分块表（向量召回用）
CREATE TABLE resource_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_id UUID REFERENCES resources(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1536),
    token_count INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 工具调用记录表
CREATE TABLE tool_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    message_id UUID REFERENCES messages(id),
    tool_name VARCHAR(100) NOT NULL,
    arguments JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',  -- pending/running/completed/failed
    result JSONB,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 用户长期记忆表
CREATE TABLE user_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    memory_type VARCHAR(50) NOT NULL,  -- 'preference' | 'fact' | 'profile' | 'task'
    content TEXT NOT NULL,
    embedding VECTOR(1536),
    confidence FLOAT DEFAULT 1.0,
    is_active BOOLEAN DEFAULT TRUE,
    source VARCHAR(100),  -- 'extracted' | 'user_defined' | 'inferred'
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 会话级记忆表
CREATE TABLE conversation_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    memory_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1536),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Workspace 快照表
CREATE TABLE workspace_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    snapshot_type VARCHAR(20) NOT NULL,  -- 'before' | 'after'
    file_manifest JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Token 使用记录表
CREATE TABLE token_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    message_id UUID REFERENCES messages(id),
    model VARCHAR(50) NOT NULL,
    cached_input_tokens INTEGER DEFAULT 0,
    uncached_input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd DECIMAL(10,6),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 上下文构建记录表
CREATE TABLE context_builds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    profile VARCHAR(20) NOT NULL,
    total_tokens INTEGER NOT NULL,
    max_tokens INTEGER NOT NULL,
    components JSONB NOT NULL,  -- 各组件占用详情
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 4. API 接口定义

### 4.1 会话管理
```
POST   /api/conversations              # 创建会话
GET    /api/conversations              # 获取会话列表
GET    /api/conversations/{id}         # 获取会话详情
DELETE /api/conversations/{id}         # 删除会话
POST   /api/conversations/{id}/clear   # 清空会话消息
```

### 4.2 聊天（流式）
```
POST   /api/chat/{conversation_id}/stream   # SSE 流式聊天
POST   /api/chat/{conversation_id}/stop     # 中断生成
```

### 4.3 文件上传
```
POST   /api/uploads/{conversation_id}                    # 批量上传 multipart
GET    /api/uploads/{conversation_id}/{file_id}/status   # 上传状态查询
```

### 4.4 Workspace
```
GET    /api/workspaces/{conversation_id}/files
GET    /api/workspaces/{conversation_id}/files/{path}
POST   /api/workspaces/{conversation_id}/files
DELETE /api/workspaces/{conversation_id}/files/{path}
POST   /api/workspaces/{conversation_id}/snapshot
GET    /api/workspaces/{conversation_id}/diff
```

### 4.5 上下文管理
```
GET    /api/context/{conversation_id}/preview    # 上下文预览
GET    /api/context/{conversation_id}/usage      # Token 使用量
POST   /api/context/{conversation_id}/rebuild    # 重建上下文
POST   /api/context/{conversation_id}/profile    # 切换档位
```

### 4.6 记忆管理
```
GET    /api/memory/user              # 获取用户记忆
POST   /api/memory/user              # 添加记忆
DELETE /api/memory/user/{memory_id}  # 删除记忆
```

### 4.7 工具与模型
```
GET    /api/tools              # 获取可用工具列表
POST   /api/tools/execute      # 直接执行工具
GET    /api/models             # 获取模型列表
POST   /api/models/select      # 切换模型
```

### 4.8 导出
```
POST   /api/export/conversation/{conversation_id}  # 导出会话
```

---

## 5. SSE 事件协议

```typescript
// 基础事件结构
interface SSEEvent {
    event: string;
    data: Record<string, any>;
}

// 事件类型定义
type EventType =
    | 'message_start'        // 开始生成
    | 'thinking_start'       // 开始思考
    | 'thinking_delta'       // 思考内容片段
    | 'thinking_end'         // 思考结束
    | 'text_delta'           // 正文文本片段
    | 'markdown_delta'       // Markdown 片段
    | 'tool_call_start'      // 开始调用工具
    | 'tool_call_delta'      // 工具参数流式填充
    | 'tool_call_end'        // 工具调用确认
    | 'tool_result'          // 工具执行结果
    | 'file_created'         // Workspace 新增文件
    | 'file_modified'        // Workspace 文件修改
    | 'workspace_snapshot'   // Workspace 快照
    | 'workspace_diff'       // Workspace 变更 Diff
    | 'context_usage'        // 上下文占用更新
    | 'message_end'          // 消息生成完毕
    | 'error'                // 错误
    | 'aborted';             // 用户中断
```

---

## 6. 模块接口契约

### 6.1 Model Adapter (agent/model_adapter.py)

```python
class ModelAdapter(ABC):
    @abstractmethod
    async def stream_chat(
        self,
        messages: list[MessageBlock],
        system_prompt: str | None = None,
        tools: list[ToolDefinition] | None = None,
        enable_thinking: bool = True,
        json_mode: bool = False,
    ) -> AsyncGenerator[StreamChunk, None]: ...

    @abstractmethod
    def get_capabilities(self) -> ModelCapability: ...

class StreamChunk(TypedDict):
    type: Literal["thinking_delta", "text_delta", "tool_call", "usage", "done"]
    content: str | dict | None
    usage: TokenUsage | None

class ModelCapability(TypedDict):
    provider: str
    model_id: str
    context_window: int
    max_output_tokens: int
    supports_vision: bool
    supports_json_mode: bool
    supports_thinking: bool
    supports_context_cache: bool
```

### 6.2 Context Builder (context/context_builder.py)

```python
class ContextBuilder:
    async def build(
        self,
        conversation_id: str,
        current_query: str,
        profile: ContextProfile,
        model_cap: ModelCapability,
    ) -> BuiltContext: ...

    async def get_usage(self, conversation_id: str) -> ContextUsage: ...

@dataclass
class BuiltContext:
    messages: list[MessageBlock]
    system_prompt: str
    total_tokens: int
    components: dict[str, int]  # 各组件 token 占用

@dataclass
class ContextUsage:
    total_tokens: int
    max_tokens: int
    profile: str
    recent_turns: int
    memory_items: int
    workspace_refs: int
    tool_defs: int
```

### 6.3 Tool Registry (agent/tool_registry.py)

```python
class ToolRegistry:
    def register(self, skill: SkillDefinition) -> None: ...
    def get(self, name: str) -> SkillDefinition | None: ...
    def list_for_context(self, task_type: str = "default") -> list[ToolDefinition]: ...
    def validate_call(self, tool_name: str, arguments: dict) -> ValidationResult: ...
```

### 6.4 Workspace Manager (workspace/workspace_manager.py)

```python
class WorkspaceManager:
    async def create_workspace(self, conversation_id: str, user_id: str) -> Workspace: ...
    async def read_file(self, workspace_id: str, path: str) -> bytes: ...
    async def write_file(self, workspace_id: str, path: str, data: bytes) -> None: ...
    async def delete_file(self, workspace_id: str, path: str) -> None: ...
    async def list_files(self, workspace_id: str) -> list[FileInfo]: ...
    async def create_snapshot(self, workspace_id: str) -> Snapshot: ...
    async def get_diff(self, workspace_id: str, before: str, after: str) -> WorkspaceDiff: ...
```

### 6.5 Agent Loop (agent/agent_loop.py)

```python
class AgentLoop:
    async def run(
        self,
        conversation_id: str,
        user_input: str,
        resources: list[ResourceRef] | None = None,
    ) -> AsyncGenerator[SSEEvent, None]: ...

    async def stop(self, conversation_id: str) -> None: ...
```

---

## 7. Context Profile 配置

```python
CONTEXT_PROFILES = {
    "cheap": {
        "max_input_tokens": 32000,
        "recent_turns": 6,
        "tool_result_mode": "summary",
        "multimodal_mode": "caption_only",
        "memory_recall_top_k": 5,
        "compression_strategy": "aggressive",
    },
    "balanced": {
        "max_input_tokens": 96000,
        "recent_turns": 16,
        "tool_result_mode": "hybrid",
        "multimodal_mode": "caption_plus_refs",
        "memory_recall_top_k": 12,
        "compression_strategy": "balanced",
    },
    "max": {
        "max_input_tokens": 256000,
        "recent_turns": 50,
        "tool_result_mode": "verbose",
        "multimodal_mode": "rich",
        "memory_recall_top_k": 30,
        "compression_strategy": "minimal",
    },
    "custom": {
        # 用户自定义
    },
}
```

---

## 8. 模型配置

```python
MODEL_CONFIGS = {
    "deepseek-v4-pro": {
        "provider": "deepseek",
        "context_window": 1_000_000,
        "max_output_tokens": 8192,
        "supports_vision": False,
        "supports_json_mode": True,
        "supports_thinking": True,
        "default_thinking_effort": "max",
        "supports_context_cache": True,
    },
    "deepseek-v4-flash": {
        "provider": "deepseek",
        "context_window": 1_000_000,
        "max_output_tokens": 8192,
        "supports_vision": False,
        "supports_json_mode": True,
        "supports_thinking": True,
        "default_thinking_effort": "high",
        "supports_context_cache": True,
    },
    "kimi-k2-6": {
        "provider": "kimi",
        "context_window": 256_000,
        "max_output_tokens": 8192,
        "supports_vision": True,
        "supports_json_mode": True,
        "supports_thinking": True,
        "supports_context_cache": True,  # 自动
    },
    "kimi-k2-5": {
        "provider": "kimi",
        "context_window": 256_000,
        "max_output_tokens": 8192,
        "supports_vision": True,
        "supports_json_mode": True,
        "supports_thinking": True,
        "supports_context_cache": True,
    },
}
```

---

## 9. 工具调用 JSON 格式

```json
{
    "type": "tool_calls",
    "calls": [
        {
            "tool": "read_file",
            "arguments": {"path": "uploads/report.pdf"}
        },
        {
            "tool": "web_search",
            "arguments": {"query": "关键词"}
        }
    ]
}
```

硬上限: `max_tool_calls_per_step = 4` (balanced 档)

---

## 10. 环境变量

```bash
# 数据库
DATABASE_URL=postgresql://user:pass@localhost:5432/agent_db

# 模型 API Key
DEEPSEEK_API_KEY=sk-...
KIMI_API_KEY=sk-...

# 可选: Embedding
OPENAI_API_KEY=sk-...  # 用于 embedding

# Workspace
WORKSPACE_ROOT=/mnt/agents/output/project/workspaces
WORKSPACE_LOCAL_CACHE=/mnt/agents/output/project/workspace_cache

# 可选: Redis
REDIS_URL=redis://localhost:6379/0

# 可选: Sentry
SENTRY_DSN=

# 日志级别
LOG_LEVEL=INFO
```

---

## 11. 安全要求

1. **Workspace 路径沙箱**: 所有文件操作限制在 `/workspaces/{user_id}/{conversation_id}/` 内
2. **路径归一化**: 解析前调用 `os.path.normpath`，禁止 `../` 模式
3. **符号链接检测**: 拒绝跟随符号链接
4. **文件大小限制**: 单次上传最大 50MB
5. **文件类型白名单**: 仅允许配置的 MIME 类型
6. **工具参数校验**: JSON Schema 严格校验
7. **认证占位**: 所有 API 需 Bearer Token（当前可 mock）

---

## 12. 前端架构

### 12.1 布局结构
```
┌──────────────────────────────────────────────────────┐
│  [≡]  vonish Agent                            [○]    │  ← TopBar
├──────────┬───────────────────────────────────────────┤
│          │                                           │
│  Sidebar │         Main Content Area                 │
│  (collapsible) │     (Message Stream)               │
│          │                                           │
│  - New   │     Input Area Widgets                  │
│  - Skills│     [删除][上下文][导出][模型▼]          │
│  - Search│                                           │
│  - Conv  │     📄file.pdf ❌  🖼️img.png ❌         │
│    List  │     ⏳data.csv (处理中...)                │
│  - File  │                                           │
│    Tree  │     ┌────────────────────────────┐       │
│          │     │  Type your message...      │       │
│          │     │  [🎤]                      │       │
│          │     └────────────────────────────┘       │
│          │                       [📎] [➤]          │
├──────────┴───────────────────────────────────────────┤
│  [Language] [Account] [Settings] [Status...]         │  ← StatusBar
└──────────────────────────────────────────────────────┘
```

### 12.2 组件清单
- **TopBar**: 品牌名 + 窗口控制
- **Sidebar**: 可拖拽/可收起，含会话列表、Workspace 文件树、Skills、Search
- **StatusBar**: 左下角菜单（Language/Account/Settings）
- **MessageStream**: 消息流式渲染区
- **ThinkingCard**: 思考卡片（可折叠）
- **ToolCard**: 工具卡片（可展开）
- **Composer**: 输入框 + 附件铺排 + 上传按钮
- **InputWidgets**: 删除对话 / 上下文管理 / 导出 / 模型切换
- **ContextManagerPanel**: 上下文管理抽屉/面板
- **SettingsModal**: 设置页面
- **WorkspaceDiff**: Diff 展示组件

### 12.3 状态管理 (Zustand)
- `useConversationStore`: 会话列表、当前会话
- `useMessageStore`: 消息流、SSE 连接
- `useWorkspaceStore`: 文件树、上传状态
- `useContextStore`: Context Profile、Token 使用量
- `useUIStore`: 侧边栏状态、主题、设置面板
- `useModelStore`: 模型列表、当前模型

---

## 13. 验收场景

1. 普通聊天真实流式（SSE + 可中断 + Markdown 保持）
2. 上传 PDF 后多轮回看（Workspace + 工具调用）
3. 生成文件并展示 Diff（Snapshot/Diff）
4. 搜索并爬取资料（search_and_crawl 工具）
5. 上下文档位切换（Cheap/Balanced/Max）
6. 上下文压缩交互（Compression Engine）
7. DeepSeek/Kimi 参数适配与缓存
8. Markdown Bug 回归测试
9. 前端布局与交互验证（左下角菜单、上下文管理、附件铺排、模型切换）
10. 工具调用 JSON 闭环（多个工具并行）
11. 批量文件上传与文本处理（50 文件）
12. 图像上传与模型切换（Vision ↔ Caption 降级）
