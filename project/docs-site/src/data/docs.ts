import { DocData } from '@/types';

export const docs: DocData = {
  'home': {
    title: '首页',
    content: `
# Agent 工作台系统

> 从普通聊天网页到完整 Agent 工作台的后端基建级重构。

## 架构概览

\`\`\`
project-root/
├── frontend/    # React 前端 Agent 工作台
├── backend/     # FastAPI Agent 引擎
├── docs/        # 项目文档
├── scripts/     # 工具脚本
├── examples/    # 示例代码
└── docker-compose.yml
\`\`\`

## 核心特性

### Agent 引擎
- **多轮 Agent Loop**：支持工具调用 → 执行 → 回填 → 再调用的完整循环
- **JSON Output 工具调用**：统一格式，支持多个工具并行调用
- **防循环机制**：指纹检测、重复限制、最大轮数/成本/时间限制
- **中断支持**：用户可随时中断生成

### 模型适配层
- **DeepSeek V4-Pro/Flash**：thinking + reasoning_content + JSON mode
- **Kimi K2.6/K2.5**：reasoning_content + Vision + 自动上下文缓存
- **统一接口**：\`stream_chat()\` 屏蔽提供商差异

### Context OS
- **六层上下文架构**：System Prompt + Memory + Workspace + Messages + Tools + Query
- **四档预算配置**：Cheap(32K) / Balanced(96K) / Max(256K) / Custom
- **渐进式压缩**：70%/80%/85%/90%/99% 五级阈值
- **向量召回 + RRF 融合**：Dense + BM25 混合检索

### Workspace 系统
- **会话级隔离**：每个会话独立工作区
- **双存储模式**：Server + Local 默认双写
- **路径沙箱**：防止 ../ 遍历、符号链接逃逸
- **快照/Diff**：每轮前后快照对比，文件变更追踪

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

## 核心原则

1. **先新建，后替换** — backend 独立运行，不破坏旧系统
2. **真实流式** — 模型原生 SSE，不是伪流式打字机
3. **完整上下文** — 数据库保存完整历史，Context Builder 动态组装
4. **工具 JSON 闭环** — JSON Output 统一工具调用，白名单校验
5. **双存储保障** — Server + Local 默认双写
6. **路径沙箱** — 所有文件操作限制在 Workspace 内
`,
  },

  'quickstart': {
    title: '快速开始',
    content: `
## 环境要求

- Python 3.12+
- PostgreSQL 14+（可选 pgvector）
- Node.js 20+（前端）
- Docker + Docker Compose（推荐）

## 后端启动

### 使用 Docker Compose（推荐）

\`\`\`bash
# 启动全部服务
docker-compose up -d

# 访问前端 http://localhost:3000
# 访问后端 API http://localhost:8000/docs
\`\`\`

### 手动安装后端

\`\`\`bash
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
\`\`\`

## 前端启动

\`\`\`bash
cd frontend
npm install
npm run build
# 或开发模式
npm run dev
\`\`\`

## 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| \`DATABASE_URL\` | PostgreSQL 连接字符串 | - |
| \`DEEPSEEK_API_KEY\` | DeepSeek API 密钥 | - |
| \`KIMI_API_KEY\` | Kimi API 密钥 | - |
| \`WORKSPACE_ROOT\` | 工作区根目录 | ./workspaces |
| \`REDIS_URL\` | Redis 连接（可选） | - |
| \`LOG_LEVEL\` | 日志级别 | INFO |

### API 文档

启动后访问：\`http://localhost:8000/docs\`

### 健康检查

\`\`\`bash
curl http://localhost:8000/api/health
\`\`\`
`,
  },

  'architecture': {
    title: '系统架构',
    content: `
## 系统架构

\`\`\`
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
\`\`\`

## 模块清单

### 1. Agent 引擎 (\`agent/\`)

Agent 引擎是系统的核心，负责模型交互、工具调用和多轮循环控制。

| 组件 | 文件 | 说明 |
|------|------|------|
| **Agent Loop** | \`agent_loop.py\` | 主循环控制器，管理 think → act → observe 循环 |
| **Model Adapter** | \`model_adapter.py\` | 统一 DeepSeek 和 Kimi 的调用接口 |
| **Tool Registry** | \`tool_registry.py\` | 工具白名单注册与发现 |
| **Tool Executor** | \`tool_executor.py\` | 工具调用执行引擎 |
| **Tool Parser** | \`tool_parser.py\` | 解析模型输出的 JSON 工具调用 |
| **Tool Lifecycle** | \`tool_lifecycle.py\` | 管理工具调用的完整生命周期 |

### 2. Context OS (\`context/\`)

Context OS 负责上下文的智能组装、预算管理和压缩。

| 组件 | 文件 | 说明 |
|------|------|------|
| **Context Builder** | \`context_builder.py\` | 六层上下文组装 |
| **Context Profile** | \`context_profile.py\` | 四档预算配置 |
| **Token Budget** | \`token_budget.py\` | 渐进式压缩阈值 |
| **Memory Selector** | \`memory_selector.py\` | 向量召回记忆选择 |
| **Compression Engine** | \`compression_engine.py\` | 智能压缩算法 |

### 3. Workspace (\`workspace/\`)

Workspace 提供会话级的文件管理和安全沙箱。

| 组件 | 文件 | 说明 |
|------|------|------|
| **Workspace Manager** | \`workspace_manager.py\` | 会话文件管理 |
| **Permissions** | \`permissions.py\` | 路径沙箱验证 |
| **Snapshot** | \`snapshot.py\` | 文件变更快照 |
| **Diff** | \`diff.py\` | 变更对比 |
| **Storage Providers** | \`local_provider.py\`, \`server_provider.py\` | 双存储模式 |

### 4. Services (\`services/\`)

Services 层提供上传、解析、嵌入、搜索和爬虫等业务能力。

| 组件 | 文件 | 说明 |
|------|------|------|
| **Upload Service** | \`upload_service.py\` | 批量文件上传处理 |
| **File Parser** | \`file_parser.py\` | 多格式文件解析 |
| **Embedding Service** | \`embedding_service.py\` | 文本向量化 |
| **Search Service** | \`search_service.py\` | 混合搜索 |
| **Crawl Service** | \`crawl_service.py\` | 网页爬取 |

## 数据流

### 聊天请求流

\`\`\`
用户输入
  → API Layer (/api/chat/{id}/stream)
    → Agent Loop
      → Context Builder 组装六层上下文
        → Model Adapter 流式调用模型
          ← 模型返回 thinking / content / tool_calls
        → Tool Parser 解析 tool_calls
        → Tool Executor 执行工具
        → 结果回填上下文
      ← 再次调用模型（闭环）
    ← SSE 事件流返回前端
\`\`\`

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
`,
  },

  'agent-loop': {
    title: 'Agent Loop',
    content: `
## Agent Loop 工作流

\`\`\`
┌─────────────────────────────────────────────────────────────┐
│                        Agent Loop                            │
│                                                              │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐  │
│  │  Start  │───►│ Think   │───►│  Act    │───►│ Observe │  │
│  │         │    │         │    │         │    │         │  │
│  │ - Load  │    │ - Build │    │ - Parse │    │ - Exec  │  │
│  │   ctx   │    │   prompt│    │   tools │    │   tools │  │
│  │ - Set   │    │ - Stream│    │ - Call  │    │ - Format│  │
│  │   budget│    │   model │    │   model │    │   result│  │
│  └─────────┘    └────┬────┘    └────┬────┘    └────┬────┘  │
│                      │              │              │        │
│                      ▼              │              │        │
│                 ┌─────────┐         │              │        │
│                 │  Done?  │─────────┘◄─────────────┘        │
│                 │         │                                  │
│                 │ No: Loop │                                 │
│                 │ Yes: End │                                 │
│                 └─────────┘                                  │
└──────────────────────────────────────────────────────────────┘
\`\`\`

## 详细流程

### 1. Start 阶段

- 加载会话上下文（Conversation Context）
- 设置 Token 预算（根据 Context Profile）
- 初始化工具注册表
- 构建六层上下文

### 2. Think 阶段

- Context Builder 组装完整上下文
  1. System Prompt（基础行为）
  2. Memory（长期记忆）
  3. Workspace（文件状态）
  4. Recent Messages（近期对话）
  5. Tool Definitions（可用工具）
  6. User Query（用户查询）
- 发送给模型，流式接收 thinking 内容

### 3. Act 阶段

- 解析模型输出的 tool_calls JSON
- 白名单校验（Tool Registry）
- 并行执行工具（Tool Executor）

### 4. Observe 阶段

- 收集工具执行结果
- 格式化为观察消息
- 回填到对话历史
- 检查终止条件（最大轮数/时间/成本）

## 防循环机制

| 机制 | 实现 | 阈值 |
|------|------|------|
| 指纹检测 | 工具调用参数指纹去重 | 3 次重复 |
| 最大轮数 | 循环计数器 | 50 轮 |
| 最大时间 | 超时计时器 | 5 分钟 |
| 最大成本 | Token 消耗估算 | 按 Profile 限制 |
| 用户中断 | 中断信号 | 即时 |

## 工具调用格式

模型输出的工具调用格式：

\`\`\`json
{
  "tool_calls": [
    {
      "name": "read_file",
      "arguments": {
        "path": "src/main.py"
      }
    }
  ]
}
\`\`\`

工具执行结果格式：

\`\`\`json
{
  "tool_results": [
    {
      "name": "read_file",
      "result": "file content...",
      "success": true
    }
  ]
}
\`\`\`

## 代码级验证

### 核心循环结构

\`\`\`python
# 多轮循环确保可以再次调用模型
for round_num in range(self.config.max_rounds):

    # 流式调用模型（带 tools 参数）
    async for chunk in adapter.stream_chat(
        messages=context.messages,
        system_prompt=context.system_prompt,
        tools=context.tools,          # <-- 工具定义注入
        ...
    ):
        yield sse_event(...)        # <-- 实时 SSE 输出

    # 解析模型输出中的 tool_calls
    parse_result = self._tool_parser.parse(accumulated_text)

    # 无工具调用则退出循环
    if not parse_result.has_tool_calls:
        break  # No tool calls - we're done

    # 执行工具调用
    tool_results = await self._execute_tool_calls(
        conversation_id, parse_result.calls
    )

    # CRITICAL - 工具结果写回上下文
    context = await self._update_context_with_results(
        context, accumulated_text, tool_results
    )

    # 循环继续 -> 模型再次调用，此时 messages 包含 tool 结果
\`\`\`
`,
  },

  'models': {
    title: '模型适配层',
    content: `
## 支持的模型

| 模型 | 版本 | 特性 | 状态 |
|------|------|------|------|
| **DeepSeek** | V4-Pro | thinking + reasoning_content + JSON mode | ✅ 已集成 |
| **DeepSeek** | V4-Flash | 快速响应，轻量推理 | ✅ 已集成 |
| **Kimi** | K2.6 | reasoning_content + Vision + 自动上下文缓存 | ✅ 已集成 |
| **Kimi** | K2.5 | 标准版本 | ✅ 已集成 |

## 统一接口

\`stream_chat()\` 方法屏蔽了不同提供商的差异：

\`\`\`python
async def stream_chat(
    self,
    messages: List[Message],
    system_prompt: Optional[str] = None,
    tools: Optional[List[ToolDefinition]] = None,
    enable_thinking: bool = True,
) -> AsyncIterator[ModelChunk]:
\`\`\`

### 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| \`messages\` | List[Message] | 对话历史消息 |
| \`system_prompt\` | str | 系统提示词 |
| \`tools\` | List[ToolDefinition] | 可用工具定义列表 |
| \`enable_thinking\` | bool | 是否启用思考模式 |

### 返回格式

\`\`\`python
class ModelChunk:
    type: Literal["thinking", "reasoning", "content", "tool_call"]
    content: str
\`\`\`

## DeepSeek 适配

### 特性
- **Thinking 模式**：独立的 thinking 内容流
- **Reasoning Content**：结构化的推理过程
- **JSON Mode**：原生支持 JSON 输出

### 配置

\`\`\`python
DEEPSEEK_API_KEY="sk-..."
DEEPSEEK_MODEL="deepseek-chat"  # V4-Pro
# 或
DEEPSEEK_MODEL="deepseek-reasoner"  # 推理模型
\`\`\`

## Kimi 适配

### 特性
- **Vision 支持**：图像输入理解
- **自动上下文缓存**：长对话优化
- **Reasoning Content**：推理过程展示

### 配置

\`\`\`python
KIMI_API_KEY="sk-..."
KIMI_MODEL="moonshot-v1-128k"
\`\`\`

## 工具调用规范

模型输出格式（OpenAI-compatible）：

\`\`\`json
{
  "type": "tool_calls",
  "calls": [
    {
      "tool": "tool_name",
      "arguments": {
        "param1": "value1"
      }
    }
  ]
}
\`\`\`
`,
  },

  'tools': {
    title: '工具运行时',
    content: `
## 工具注册

工具通过 \`ToolRegistry\` 进行白名单注册：

\`\`\`python
from agent.tool_registry import ToolRegistry, ToolDefinition

registry = ToolRegistry()

registry.register(ToolDefinition(
    name="list_workspace_files",
    description="List all files in the current conversation's workspace...",
    parameters={
        "type": "object",
        "properties": {
            "conversation_id": {"type": "string"},
            "subdir": {"type": "string", "default": ""},
        },
    },
    category="workspace",
))
\`\`\`

## 文件操作工具

### 已注册的 Workspace 工具

| 工具名称 | 说明 | 类别 |
|----------|------|------|
| \`list_workspace_files\` | 列出工作区文件 | workspace |
| \`read_workspace_file\` | 读取工作区文件内容 | workspace |
| \`get_workspace_summary\` | 获取工作区摘要统计 | workspace |

### 注册状态验证

- [x] \`list_workspace_files\` 已注册到 ToolRegistry
- [x] \`read_workspace_file\` 已注册
- [x] \`get_workspace_summary\` 已注册
- [x] JSON Schema 定义完整（含 \`conversation_id\` 自动注入）

## 添加新工具

### 步骤

1. **定义工具 Schema**

\`\`\`python
registry.register(ToolDefinition(
    name="my_new_tool",
    description="工具的详细描述...",
    parameters={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "参数说明"},
            "param2": {"type": "integer", "default": 10},
        },
        "required": ["param1"],
    },
    category="custom",
))
\`\`\`

2. **实现工具 Handler**

\`\`\`python
async def my_new_tool(param1: str, param2: int = 10):
    """工具实现"""
    try:
        result = do_something(param1, param2)
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
\`\`\`

3. **注册 Handler 到 Executor**

\`\`\`python
executor.register_handler("my_new_tool", my_new_tool)
\`\`\`

## Tool Executor 自动注入

\`\`\`python
# 自动注入 conversation_id
arguments = dict(validation_result.normalized_arguments)
if request.conversation_id and "conversation_id" not in arguments:
    arguments["conversation_id"] = request.conversation_id

# 确保 workspace 工具始终获得正确的 conversation_id
result = await asyncio.wait_for(
    handler(**arguments), timeout=self._default_timeout
)
\`\`\`

## 安全验证

| 安全检查项 | 实现 | 状态 |
|-----------|------|------|
| 路径遍历防护 (\`../\`) | \`PathSandbox._has_path_traversal()\` | ✅ |
| 绝对路径逃逸防护 | \`PathSandbox._check_within_workspace()\` | ✅ |
| 隐藏文件访问限制 | \`PathSandbox._is_hidden_path()\` | ✅ |
| 空字节注入防护 | \`PathSandbox._contains_null_bytes()\` | ✅ |
| 控制字符过滤 | \`PathSandbox._contains_control_chars()\` | ✅ |
| 路径长度限制 | \`PathSandbox._max_path_length = 4096\` | ✅ |
| 文件大小限制 | \`MAX_READ_SIZE = 5MB\` | ✅ |
| 异常不传播 | 所有工具返回 \`{"success": False, "error": ...}\` | ✅ |
`,
  },

  'context-os': {
    title: 'Context OS',
    content: `
## 设计理念

Context OS 是 Agent 工作台的上下文操作系统，负责智能组装发送给模型的完整上下文。它采用六层架构，从 System Prompt 到 User Query 逐层叠加，确保模型获得最相关、最精简的上下文信息。

核心设计目标：
- **智能组装**：根据对话状态动态选择需要的内容
- **预算管控**：严格控制 Token 使用量，避免超额
- **渐进压缩**：接近预算上限时自动压缩，而非截断
- **记忆召回**：通过向量检索引入相关历史记忆

## Context Builder

### 六层上下文架构

Context OS 采用六层架构组装发送给模型的完整上下文：

\`\`\`
┌──────────────────────────────────────────┐
│ Layer 6: User Query (用户查询)            │  ← 当前用户输入
├──────────────────────────────────────────┤
│ Layer 5: Tool Definitions (工具定义)      │  ← 可用工具 JSON Schema
├──────────────────────────────────────────┤
│ Layer 4: Recent Messages (近期消息)       │  ← 最近 N 轮对话
├──────────────────────────────────────────┤
│ Layer 3: Workspace State (工作区状态)     │  ← 文件列表 + 变更摘要
├──────────────────────────────────────────┤
│ Layer 2: Memory (长期记忆)                │  ← 向量召回的相关记忆
├──────────────────────────────────────────┤
│ Layer 1: System Prompt (系统提示)         │  ← 基础行为 + 格式规范
└──────────────────────────────────────────┘
\`\`\`

### 构建流程

1. **加载 System Prompt** — 从 Prompt Builder 获取基础行为模板
2. **召回 Memory** — 通过向量检索获取相关历史记忆
3. **加载 Workspace State** — 获取当前会话的文件列表和变更
4. **加载 Recent Messages** — 获取最近 N 轮对话历史
5. **加载 Tool Definitions** — 从 Tool Registry 获取可用工具定义
6. **附加 User Query** — 将当前用户输入放在最上层

## Token Budget

### 渐进式压缩

当上下文接近预算上限时，按阈值逐级压缩：

| 使用率 | 压缩策略 |
|--------|----------|
| 70% | 开始追踪 |
| 80% | 压缩旧消息摘要 |
| 85% | 减少历史轮数 |
| 90% | 激进压缩 |
| 99% | 仅保留系统提示 + 当前查询 |

### 四档预算配置

| Profile | max_tokens | 适用场景 |
|---------|------------|----------|
| **Cheap** | 32K | 简单问答、短对话 |
| **Balanced** | 96K | 一般开发任务 |
| **Max** | 256K | 大型项目分析 |
| **Custom** | 自定义 | 特殊需求 |

## Memory Selector

采用混合检索策略选择相关记忆：

1. **Dense Retrieval**: 向量相似度搜索（pgvector）
2. **BM25**: 关键词匹配
3. **RRF Fusion**: 倒数秩融合合并结果

## 压缩引擎

### 压缩策略

- **消息摘要**：将旧消息压缩为摘要形式
- **历史轮数裁剪**：保留最近 N 轮，压缩更早的
- **Token 截断**：最后手段，按优先级截断

### 压缩算法

\`\`\`python
class CompressionEngine:
    def compress(self, context: Context, budget: TokenBudget) -> Context:
        usage_ratio = budget.usage_ratio

        if usage_ratio < 0.7:
            return context  # 无需压缩

        if usage_ratio < 0.8:
            return self._compress_old_messages(context)

        if usage_ratio < 0.85:
            return self._reduce_history_rounds(context)

        if usage_ratio < 0.9:
            return self._aggressive_compress(context)

        # 紧急模式
        return self._emergency_compress(context)
\`\`\`

## 核心文件

| 文件 | 说明 |
|------|------|
| \`context_builder.py\` | 六层上下文组装 |
| \`context_profile.py\` | 四档预算配置 |
| \`token_budget.py\` | 渐进式压缩阈值 |
| \`memory_selector.py\` | 向量召回 + RRF |
| \`compression_engine.py\` | 压缩算法 |
`,
  },

  'workspace': {
    title: 'Workspace',
    content: `
## 文件管理

Workspace 提供会话级的文件管理和安全沙箱。

### 架构

\`\`\`
┌─────────────────────────────────────┐
│        Workspace Manager             │
│                                      │
│  ┌───────────┐    ┌──────────────┐  │
│  │  Server   │    │    Local     │  │
│  │  Storage  │◄──►│   Storage    │  │
│  │           │    │              │  │
│  └─────┬─────┘    └──────┬───────┘  │
│        │                  │          │
│  ┌─────▼──────────────────▼───────┐  │
│  │      Path Sandbox              │  │
│  │  (Permissions validation)      │  │
│  └─────┬────────────────────┬─────┘  │
│        │                    │        │
│  ┌─────▼─────┐      ┌──────▼──────┐ │
│  │ Snapshot  │      │    Diff     │ │
│  │ (per-turn)│      │ (track chg) │ │
│  └───────────┘      └─────────────┘ │
└─────────────────────────────────────┘
\`\`\`

### 会话级隔离

每个会话拥有独立的工作区目录：

\`\`\`
workspaces/
├── {conversation_id_1}/
│   ├── src/
│   ├── docs/
│   └── README.md
├── {conversation_id_2}/
│   └── ...
\`\`\`

## 路径沙箱

### 安全验证机制

- 阻止 \`../\` 目录遍历
- 阻止符号链接逃逸
- 所有路径解析为绝对路径后验证前缀

### 安全检查项

| 检查项 | 实现 | 状态 |
|-----------|------|------|
| 路径遍历防护 (\`../\`) | \`PathSandbox._has_path_traversal()\` | ✅ |
| 绝对路径逃逸防护 | \`PathSandbox._check_within_workspace()\` | ✅ |
| 隐藏文件访问限制 | \`PathSandbox._is_hidden_path()\` | ✅ |
| 空字节注入防护 | \`PathSandbox._contains_null_bytes()\` | ✅ |
| 控制字符过滤 | \`PathSandbox._contains_control_chars()\` | ✅ |
| 路径长度限制 | \`PathSandbox._max_path_length = 4096\` | ✅ |

## 快照与 Diff

### 双存储模式

- **Server Storage**: 服务器本地文件系统
- **Local Storage**: 可选本地存储同步
- 默认双写，确保数据安全

### 快照机制

每轮 Agent Loop 前后自动创建快照：
- 追踪文件创建、修改、删除
- 生成 Diff 摘要供模型参考

### Diff 格式

\`\`\`json
{
  "changes": [
    {
      "type": "created",
      "path": "src/main.py",
      "size": 1024
    },
    {
      "type": "modified",
      "path": "README.md",
      "diff": "..."
    },
    {
      "type": "deleted",
      "path": "old.txt"
    }
  ],
  "summary": "3 files changed, 1 created, 1 modified, 1 deleted"
}
\`\`\`

## 核心文件

| 文件 | 说明 |
|------|------|
| \`workspace_manager.py\` | 主管理器 |
| \`permissions.py\` | 路径沙箱验证 |
| \`snapshot.py\` | 快照管理 |
| \`diff.py\` | 变更对比 |
| \`local_provider.py\` | 本地存储提供者 |
| \`server_provider.py\` | 服务器存储提供者 |
| \`storage_provider.py\` | 存储抽象接口 |
| \`indexer.py\` | 文件索引 |
`,
  },

  'frontend': {
    title: '前端',
    content: `
## 组件清单

Agent 工作台采用深色极简风格（参考 Claude Code），主要区域：

- **顶部栏**：品牌名 "vonish Agent" + 窗口控制
- **左侧边栏**：可拖拽/可收起，含会话列表 + Workspace 文件树 + 搜索
- **主内容区**：消息流（文字 → Thinking Card → Tool Card → 文字）
- **底部 Composer**：输入框 + 附件 + 模型切换 + 上下文管理
- **左下角状态栏**：Language / Account / Settings

### 布局组件

| 组件 | 说明 | 状态 |
|------|------|------|
| **Layout** | 桌面端完整布局（侧边栏 + 主区域 + 状态栏） | ✅ |
| **MobileLayout** | 移动端响应式（抽屉式侧边栏 + 折叠布局） | ✅ |
| **ResizableSidebar** | 侧边栏可拖拽调整宽度（200-350px） | ✅ |
| **CollapsibleSidebar** | 侧边栏可完全收起 + 悬停临时展开 | ✅ |

### 聊天组件

| 组件 | 说明 | 状态 |
|------|------|------|
| **MessageStream** | 消息流式渲染 | ✅ |
| **MessageBubble** | 用户/AI 消息气泡区分 | ✅ |
| **ThinkingCard** | 可折叠思考过程展示 | ✅ |
| **ToolCard** | 工具调用时间线展示 | ✅ |
| **MarkdownRenderer** | 完整 Markdown 全家桶 | ✅ |
| **CodeBlock** | 代码块高亮 + 复制按钮 | ✅ |
| **DiffViewer** | Workspace Diff 展示 | ✅ |

### 输入组件

| 组件 | 说明 | 状态 |
|------|------|------|
| **Composer** | 多行输入框（自动增高，Enter 发送） | ✅ |
| **AttachmentBar** | 附件横向铺排 + 删除 | ✅ |
| **ModelSelector** | 模型切换下拉（DeepSeek / Kimi） | ✅ |
| **ContextPanel** | 上下文管理面板（Token 仪表盘 + Profile 切换） | ✅ |

## 状态管理

使用 Zustand 管理全局状态：

\`\`\`typescript
// stores/useConversationStore.ts
interface ConversationState {
  conversations: Conversation[];
  activeId: string | null;
  messages: Message[];
  isStreaming: boolean;
  
  // Actions
  setActive: (id: string) => void;
  sendMessage: (content: string) => Promise<void>;
  stopGeneration: () => void;
}
\`\`\`

### Store 划分

| Store | 职责 |
|-------|------|
| \`useConversationStore\` | 会话与消息管理 |
| \`useWorkspaceStore\` | 文件树与 Workspace 操作 |
| \`useUIStore\` | 侧边栏状态、主题、布局 |
| \`useContextStore\` | Token 预算、Profile 切换 |

### 已实现状态

- [x] Zustand 会话/消息/Workspace/UI 状态
- [x] Mock 数据（6+ 会话、8+ 消息、文件树）

## 技术栈

| 技术 | 用途 |
|------|------|
| React 18 | UI 框架 |
| TypeScript | 类型安全 |
| Vite | 构建工具 |
| Tailwind CSS | 样式 |
| Zustand | 状态管理 |
| shadcn/ui | UI 组件库 |
| react-markdown | Markdown 渲染 |
| remark-gfm | GFM 扩展 |
| rehype-katex | 数学公式 |

## 待完善

1. 真实 SSE 接入后端
2. 真实文件上传 API 对接
3. 真实工具调用闭环
4. 数学公式渲染（KaTeX）
5. Mermaid 图表渲染
`,
  },

  'api': {
    title: 'API 文档',
    content: `
## 认证

所有 API 请求需要在 Header 中携带认证信息：

\`\`\`
Authorization: Bearer {token}
\`\`\`

或使用 API Key：

\`\`\`
X-API-Key: {api_key}
\`\`\`

## 会话管理 (\`/api/conversations\`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | \`/api/conversations\` | 创建新会话 |
| GET | \`/api/conversations\` | 获取会话列表 |
| GET | \`/api/conversations/{id}\` | 获取会话详情 |
| DELETE | \`/api/conversations/{id}\` | 删除会话 |

### 创建会话

\`\`\`bash
curl -X POST http://localhost:8000/api/conversations \\
  -H "Authorization: Bearer {token}" \\
  -H "Content-Type: application/json" \\
  -d '{"title": "新会话"}'
\`\`\`

响应：

\`\`\`json
{
  "id": "conv_123456",
  "title": "新会话",
  "created_at": "2026-05-27T10:00:00Z",
  "updated_at": "2026-05-27T10:00:00Z"
}
\`\`\`

## 聊天 (\`/api/chat\`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | \`/api/chat/{id}/stream\` | SSE 流式聊天（核心接口） |
| POST | \`/api/chat/{id}/stop\` | 中断生成 |

### SSE 流式聊天

\`\`\`bash
curl -X POST http://localhost:8000/api/chat/conv_123/stream \\
  -H "Authorization: Bearer {token}" \\
  -H "Content-Type: application/json" \\
  -d '{"message": "你好，请帮我写一个 Python 函数"}'
\`\`\`

**SSE 事件类型**：

| 事件 | 说明 |
|------|------|
| \`thinking\` | 模型思考过程 |
| \`tool_call\` | 工具调用请求 |
| \`tool_result\` | 工具执行结果 |
| \`content\` | 内容片段 |
| \`done\` | 完成信号 |
| \`error\` | 错误信息 |

### 中断生成

\`\`\`bash
curl -X POST http://localhost:8000/api/chat/conv_123/stop \\
  -H "Authorization: Bearer {token}"
\`\`\`

## 文件上传 (\`/api/uploads\`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | \`/api/uploads/{conversation_id}\` | 批量文件上传 |

### 批量上传

\`\`\`bash
curl -X POST http://localhost:8000/api/uploads/conv_123 \\
  -H "Authorization: Bearer {token}" \\
  -F "files=@document.pdf" \\
  -F "files=@image.png"
\`\`\`

## Workspace (\`/api/workspaces\`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | \`/api/workspaces/{id}/files\` | 获取文件列表 |
| POST | \`/api/workspaces/{id}/files\` | 创建/写入文件 |
| GET | \`/api/workspaces/{id}/files/{path}\` | 读取文件内容 |
| DELETE | \`/api/workspaces/{id}/files/{path}\` | 删除文件 |

### 获取文件列表

\`\`\`bash
curl http://localhost:8000/api/workspaces/conv_123/files \\
  -H "Authorization: Bearer {token}"
\`\`\`

响应：

\`\`\`json
{
  "files": [
    {"name": "src", "type": "directory", "path": "src"},
    {"name": "main.py", "type": "file", "path": "src/main.py", "size": 1024}
  ]
}
\`\`\`

## 上下文管理 (\`/api/context\`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | \`/api/context/{id}/usage\` | Token 使用量统计 |

### Token 使用量

\`\`\`bash
curl http://localhost:8000/api/context/conv_123/usage \\
  -H "Authorization: Bearer {token}"
\`\`\`

响应：

\`\`\`json
{
  "profile": "balanced",
  "max_tokens": 96000,
  "used_tokens": 45230,
  "usage_ratio": 0.47,
  "layer_breakdown": {
    "system_prompt": 2048,
    "memory": 8192,
    "workspace": 1536,
    "messages": 32454,
    "tools": 1000
  }
}
\`\`\`

## 错误处理

统一的错误响应格式：

\`\`\`json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "details": {}
  }
}
\`\`\`

常见错误码：

| 状态码 | 错误码 | 说明 |
|--------|--------|------|
| 400 | \`INVALID_REQUEST\` | 请求参数错误 |
| 401 | \`UNAUTHORIZED\` | 未认证 |
| 403 | \`FORBIDDEN\` | 无权限 |
| 404 | \`NOT_FOUND\` | 资源不存在 |
| 429 | \`RATE_LIMITED\` | 请求过于频繁 |
| 500 | \`INTERNAL_ERROR\` | 服务器内部错误 |
`,
  },

  'deployment': {
    title: '部署',
    content: `
## Docker 部署

### 使用 Docker Compose（推荐）

\`\`\`yaml
# docker-compose.yml
version: '3.8'

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: agent_db
      POSTGRES_USER: agent
      POSTGRES_PASSWORD: agent_pass
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql://agent:agent_pass@db:5432/agent_db
      DEEPSEEK_API_KEY: \${DEEPSEEK_API_KEY}
      KIMI_API_KEY: \${KIMI_API_KEY}
    ports:
      - "8000:8000"
    depends_on:
      - db

  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - backend

volumes:
  pgdata:
\`\`\`

### 启动

\`\`\`bash
# 设置环境变量
export DEEPSEEK_API_KEY="sk-..."
export KIMI_API_KEY="sk-..."

# 启动全部服务
docker-compose up -d

# 查看日志
docker-compose logs -f backend
\`\`\`

### 构建镜像

\`\`\`bash
# 后端
cd backend
docker build -t vonish-agent-backend .

# 前端
cd frontend
docker build -t vonish-agent-frontend .
\`\`\`

## 环境变量

### 后端

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| \`DATABASE_URL\` | ✅ | - | PostgreSQL 连接字符串 |
| \`DEEPSEEK_API_KEY\` | ✅ | - | DeepSeek API 密钥 |
| \`KIMI_API_KEY\` | ✅ | - | Kimi API 密钥 |
| \`WORKSPACE_ROOT\` | - | ./workspaces | 工作区根目录 |
| \`REDIS_URL\` | - | - | Redis 连接 |
| \`LOG_LEVEL\` | - | INFO | 日志级别 |
| \`CORS_ORIGINS\` | - | ["*"] | 允许的 CORS 来源 |
| \`MAX_UPLOAD_SIZE\` | - | 100MB | 最大上传文件大小 |
| \`MAX_CONCURRENT_UPLOADS\` | - | 50 | 最大并发上传数 |

### 前端

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| \`VITE_API_BASE_URL\` | - | /api | API 基础路径 |
| \`VITE_WS_URL\` | - | - | WebSocket 地址 |
| \`VITE_DEFAULT_MODEL\` | - | deepseek-v4 | 默认模型 |

## 替换方案

### Phase 1: 并行运行（当前阶段）

\`\`\`
用户流量 → 旧后端（主）
         → backend（旁路/测试）
\`\`\`

- backend 独立部署（不同端口）
- 前端通过配置切换后端地址
- 仅内部测试使用 backend

### Phase 2: 灰度切换

\`\`\`
用户流量 → Feature Flag Router
         ├─ 90% → 旧后端
         └─ 10% → backend
\`\`\`

### Phase 3: 全量切换

\`\`\`
用户流量 → backend（主）
         → 旧后端（热备）
\`\`\`

### Phase 4: 旧系统退役

\`\`\`
用户流量 → backend（唯一）
旧后端 → 停止服务 → 代码归档
\`\`\`

### Feature Flag 实现

\`\`\`python
async def route_request(request):
    if settings.backend_enabled:
        user_hash = hash(request.user_id) % 100
        if user_hash < settings.backend_traffic_percent:
            return await backend_handle(request)
    return await legacy_backend_handle(request)
\`\`\`

环境变量：

\`\`\`bash
BACKEND_V2_ENABLED=true
BACKEND_V2_TRAFFIC_PERCENT=10  # 0-100
\`\`\`

## 验证清单

部署后验证以下功能：

- [ ] 普通聊天真实流式（SSE + 可中断）
- [ ] 上传文件后多轮回看
- [ ] 生成文件并展示 Diff
- [ ] 搜索并爬取资料
- [ ] 上下文压缩交互
- [ ] DeepSeek / Kimi 参数适配
- [ ] Markdown 流式结束不降级
- [ ] 前端布局与交互
- [ ] 工具调用 JSON 闭环
- [ ] 批量文件上传
`,
  },

  'faq': {
    title: '常见问题',
    content: `
## 常见问题

### 如何切换模型？

在前端 Composer 区域的模型选择器下拉菜单中，可以选择 DeepSeek V4-Pro 或 Kimi K2.6。切换后立即生效，后续请求会使用新模型。

### 上下文 Token 超限怎么办？

Context OS 会自动处理：

1. **70% 使用率**：开始追踪
2. **80% 使用率**：压缩旧消息为摘要
3. **85% 使用率**：减少历史轮数
4. **90% 使用率**：激进压缩
5. **99% 使用率**：仅保留系统提示 + 当前查询

也可以手动在 Context Panel 中切换 Profile（Cheap/Balanced/Max）来扩大预算。

### 如何添加自定义工具？

1. 在 \`tool_registry.py\` 中注册工具 Schema
2. 实现工具 handler 函数
3. 在 \`tool_executor.py\` 中注册 handler
4. 重启后端服务

详见 **工具系统 → 添加新工具** 章节。

### Workspace 文件如何持久化？

Workspace 采用双存储模式：
- **Server Storage**：服务器本地文件系统（主要存储）
- **Local Storage**：可选本地存储同步

默认双写，确保数据安全。文件存储在 \`WORKSPACE_ROOT/{conversation_id}/\` 目录下。

### 如何回滚 backend？

如果 backend 出现问题，可以通过 Feature Flag 秒级回滚：

\`\`\`bash
# 关闭 backend 流量
BACKEND_V2_ENABLED=false

# 重启路由层
systemctl restart router
\`\`\`

回滚时间约 10-30 秒。

### 支持哪些文件格式？

上传支持的格式：

| 类别 | 格式 |
|------|------|
| 文本 | PDF, DOCX, MD, TXT |
| 图像 | PNG, JPG, JPEG, WEBP |
| 代码 | PY, JS, TS, JSX, TSX, JAVA, GO, RS |

### 数据库迁移

如果需要迁移数据库：

\`\`\`bash
# 创建新数据库
createdb agent_db_v2

# 运行 Alembic 迁移
cd backend
alembic upgrade head

# 数据迁移
python scripts/migrate_from_legacy.py \\
    --from-db $LEGACY_DATABASE_URL \\
    --to-db $NEW_DATABASE_URL
\`\`\`

### 性能优化建议

1. **使用 Redis**：缓存会话数据，减少数据库查询
2. **调整 Profile**：根据任务复杂度选择合适的 Token 预算
3. **压缩策略**：默认的渐进式压缩已足够，无需手动调整
4. **Connection Pool**：PostgreSQL 连接池默认 20，可根据并发调整
`,
  },
};

// Navigation structure
export const navigation = [
  { id: 'home', label: '首页', href: '/' },
  {
    id: 'quickstart',
    label: '快速开始',
    href: '/quickstart',
    children: [
      { id: 'quickstart', label: '环境准备', href: '/quickstart' },
      { id: 'quickstart', label: '后端启动', href: '/quickstart' },
      { id: 'quickstart', label: '前端启动', href: '/quickstart' },
      { id: 'quickstart', label: '配置说明', href: '/quickstart' },
    ],
  },
  {
    id: 'architecture',
    label: '架构概览',
    href: '/architecture',
    children: [
      { id: 'architecture', label: '系统架构', href: '/architecture' },
      { id: 'architecture', label: '模块清单', href: '/architecture' },
      { id: 'architecture', label: '数据流', href: '/architecture' },
    ],
  },
  {
    id: 'agent',
    label: 'Agent 引擎',
    href: '/agent-loop',
    children: [
      { id: 'agent-loop', label: 'Agent Loop', href: '/agent-loop' },
      { id: 'models', label: '模型适配层', href: '/models' },
      { id: 'tools', label: '工具运行时', href: '/tools' },
    ],
  },
  {
    id: 'context-os',
    label: 'Context OS',
    href: '/context-os',
    children: [
      { id: 'context-os', label: '设计理念', href: '/context-os' },
      { id: 'context-os', label: 'Context Builder', href: '/context-os' },
      { id: 'context-os', label: 'Token Budget', href: '/context-os' },
      { id: 'context-os', label: '压缩引擎', href: '/context-os' },
      { id: 'context-os', label: '档位配置', href: '/context-os' },
    ],
  },
  {
    id: 'workspace',
    label: 'Workspace',
    href: '/workspace',
    children: [
      { id: 'workspace', label: '文件管理', href: '/workspace' },
      { id: 'workspace', label: '路径沙箱', href: '/workspace' },
      { id: 'workspace', label: '快照与 Diff', href: '/workspace' },
    ],
  },
  {
    id: 'frontend',
    label: '前端',
    href: '/frontend',
    children: [
      { id: 'frontend', label: '组件清单', href: '/frontend' },
      { id: 'frontend', label: '状态管理', href: '/frontend' },
    ],
  },
  {
    id: 'api',
    label: 'API 文档',
    href: '/api',
    children: [
      { id: 'api', label: '认证', href: '/api' },
      { id: 'api', label: '会话管理', href: '/api' },
      { id: 'api', label: '聊天', href: '/api' },
      { id: 'api', label: '文件上传', href: '/api' },
      { id: 'api', label: 'Workspace', href: '/api' },
      { id: 'api', label: '上下文管理', href: '/api' },
    ],
  },
  {
    id: 'deployment',
    label: '部署',
    href: '/deployment',
    children: [
      { id: 'deployment', label: 'Docker 部署', href: '/deployment' },
      { id: 'deployment', label: '环境变量', href: '/deployment' },
      { id: 'deployment', label: '替换方案', href: '/deployment' },
    ],
  },
  {
    id: 'faq',
    label: 'FAQ',
    href: '/faq',
  },
];
