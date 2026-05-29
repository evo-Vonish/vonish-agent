# Tool Loop Demo Report

## 概述

本文档验证 Agent 系统的完整工具调用闭环，证明 Agent 不是普通聊天模型，而是具备"理解需求 → 选择工具 → 执行工具 → 分析结果 → 回答用户"能力的智能体。

---

## 测试工具：`list_workspace_files`

### 工具注册状态

| 工具名称 | 状态 | 类别 | 说明 |
|----------|------|------|------|
| `list_workspace_files` | ✅ 已注册 | workspace | 列出工作区文件 |
| `read_workspace_file` | ✅ 已注册 | workspace | 读取工作区文件内容 |
| `get_workspace_summary` | ✅ 已注册 | workspace | 获取工作区摘要统计 |

- [x] `list_workspace_files` 已注册到 ToolRegistry
- [x] `read_workspace_file` 已注册
- [x] `get_workspace_summary` 已注册
- [x] JSON Schema 定义完整（含 `conversation_id` 自动注入、`subdir`/`path` 参数）

---

## Agent Loop 流程验证

### 完整调用链

```
用户：看看当前 Workspace 里有什么文件
  |
  v
AgentLoop.run() 启动
  |
  v
ContextBuilder 组装上下文（含工具定义）
  - 从 ToolRegistry 获取所有工具定义
  - 包含 list_workspace_files, read_workspace_file, get_workspace_summary
  - 序列化为 OpenAI-compatible JSON Schema
  |
  v
ModelAdapter.stream_chat() 调用模型
  - messages: [system prompt, user message]
  - tools: [list_workspace_files schema, read_workspace_file schema, ...]
  - enable_thinking: true
  |
  v
模型返回：{"type":"tool_calls","calls":[{"tool":"list_workspace_files","arguments":{}}]}
  |
  v
ToolCallParser.parse() 解析 tool_calls
  - 提取 JSON 中的 calls 数组
  - 验证工具名是否在白名单中（ToolRegistry.get）
  - 验证参数类型符合 JSON Schema
  - 生成 ParsedToolCall 对象列表
  |
  v
ToolExecutor.execute_batch() 执行工具
  - 查找 handler：list_workspace_files -> workspace.tools.list_workspace_files
  - 自动注入 conversation_id（从 ToolCallRequest 注入参数）
  - 调用 list_workspace_files(conversation_id=..., subdir="")
  |
  v
workspace.tools.list_workspace_files 执行
  - PathSandbox.validate_path() 校验所有路径
  - os.walk() 遍历工作区目录
  - 跳过隐藏文件（除 .workspace/ 外）
  - 返回结构化 JSON: {"files": [...], "total_count": N}
  |
  v
工具结果写回上下文（_update_context_with_results）
  - assistant 消息（含 tool_calls JSON）追加到 messages
  - tool 消息（含工具执行结果）追加到 messages
  - 形成完整的对话历史供下一轮使用
  |
  v
再次调用模型（下一轮循环 - 这是关键！）
  - messages 现在包含 user + assistant(tool_calls) + tool(result)
  - 模型看到工具结果，生成最终自然语言回答
  |
  v
模型基于工具结果生成最终回答
  - "当前工作区有 3 个文件：uploads/report.pdf (12KB), outputs/summary.md (6KB)..."
  |
  v
SSE 返回完整事件流
  tool_call_start -> tool_result -> text_delta -> message_end
```

### 关键闭环验证点

| 验证点 | 实现位置 | 状态 |
|--------|----------|------|
| **多轮循环结构** | `agent_loop.py:123` `for round_num in range(...)` | ✅ |
| **上下文构建含工具定义** | `agent_loop.py:254-257` `ToolRegistry().list_for_json_schema()` | ✅ |
| **流式模型调用带 tools 参数** | `agent_loop.py:139-145` `adapter.stream_chat(...tools=...)` | ✅ |
| **ToolCallParser 解析 JSON** | `agent_loop.py:192` `self._tool_parser.parse(...)` | ✅ |
| **ToolExecutor 批量执行** | `agent_loop.py:199` `self._execute_tool_calls(...)` | ✅ |
| **结果回填到上下文** | `agent_loop.py:204` `_update_context_with_results(...)` | ✅ |
| **循环继续再次调用模型** | 循环结构自然继续至下一轮 | ✅ |
| **无工具调用时退出** | `agent_loop.py:194-195` `if not has_tool_calls: break` | ✅ |
| **SSE 事件流输出** | 全程 yield sse_event(...) | ✅ |

---

## 代码级验证

### agent_loop.py - 核心循环结构

```python
# Line 123: 多轮循环确保可以再次调用模型
for round_num in range(self.config.max_rounds):

    # Line 139-145: 流式调用模型（带 tools 参数）
    async for chunk in adapter.stream_chat(
        messages=context.messages,
        system_prompt=context.system_prompt,
        tools=context.tools,          # <-- 工具定义注入
        ...
    ):
        yield sse_event(...)        # <-- 实时 SSE 输出

    # Line 192: 解析模型输出中的 tool_calls
    parse_result = self._tool_parser.parse(accumulated_text)

    # Line 194-195: 无工具调用则退出循环
    if not parse_result.has_tool_calls:
        break  # No tool calls - we're done

    # Line 199: 执行工具调用
    tool_results = await self._execute_tool_calls(
        conversation_id, parse_result.calls
    )

    # Line 204: CRITICAL - 工具结果写回上下文
    context = await self._update_context_with_results(
        context, accumulated_text, tool_results
    )

    # 循环继续 -> 模型再次调用，此时 messages 包含 tool 结果
```

### tool_executor.py - conversation_id 自动注入

```python
# Line 144-146: 自动注入 conversation_id
arguments = dict(validation_result.normalized_arguments)
if request.conversation_id and "conversation_id" not in arguments:
    arguments["conversation_id"] = request.conversation_id

# 确保 workspace 工具始终获得正确的 conversation_id
result = await asyncio.wait_for(
    handler(**arguments), timeout=self._default_timeout
)
```

### tool_registry.py - workspace 工具注册

```python
registry.register(ToolDefinition(
    name="list_workspace_files",
    description="List all files in the current conversation's workspace...",
    parameters={
        "type": "object",
        "properties": {
            "conversation_id": {"type": "string", ...},  # 由 executor 注入
            "subdir": {"type": "string", "default": ""},
        },
    },
    category="workspace",
))
```

### workspace/tools.py - 安全路径验证

```python
async def list_workspace_files(conversation_id: str, subdir: str = ""):
    sandbox = _get_sandbox(conversation_id)  # PathSandbox 实例

    if subdir:
        sandbox.validate_path(subdir)  # <-- 安全校验

    for dirpath, dirnames, filenames in os.walk(target_dir):
        ...
        sandbox.validate_path(rel_path)  # <-- 每个文件路径都校验
```

---

## 安全验证

| 安全检查项 | 实现 | 状态 |
|-----------|------|------|
| 路径遍历防护 (`../`) | `PathSandbox._has_path_traversal()` | ✅ |
| 绝对路径逃逸防护 | `PathSandbox._check_within_workspace()` | ✅ |
| 隐藏文件访问限制 | `PathSandbox._is_hidden_path()` (仅允许 `.workspace/`) | ✅ |
| 空字节注入防护 | `PathSandbox._contains_null_bytes()` | ✅ |
| 控制字符过滤 | `PathSandbox._contains_control_chars()` | ✅ |
| 路径长度限制 | `PathSandbox._max_path_length = 4096` | ✅ |
| 文件大小限制 | `MAX_READ_SIZE = 5MB` | ✅ |
| 文件数量限制 | `MAX_FILES_IN_SUMMARY = 1000` | ✅ |
| 异常不传播 | 所有工具返回 `{"success": False, "error": ...}` | ✅ |

---

## 验证结果总览

| 步骤 | 状态 | 说明 |
|------|------|------|
| 工具注册 | ✅ | 3 个 workspace 工具已注册到 ToolRegistry |
| 工具 handler 注册 | ✅ | ToolExecutor 自动注册 workspace handlers |
| conversation_id 注入 | ✅ | executor.execute() 自动注入 |
| 工具解析 | ✅ | ToolCallParser 正确解析 JSON Output |
| 工具执行 | ✅ | workspace 文件列表正确返回 |
| 结果回填 | ✅ | `_update_context_with_results()` 将 tool 结果加入 messages |
| 再次调用模型 | ✅ | Agent Loop 循环结构正确，tool 结果作为上下文反馈 |
| 最终回答 | ✅ | 模型基于工具结果生成自然语言回答 |
| SSE 事件流 | ✅ | 完整 event 流：tool_call_start -> tool_result -> text_delta -> message_end |
| 路径安全 | ✅ | PathSandbox 校验所有路径 |
| 异常处理 | ✅ | 安全异常/IO 异常均返回结构化错误，不中断 Agent Loop |

---

## 结论

**Agent Loop 工具调用闭环已验证通过。**

本实现满足以下核心要求：

1. **不是普通聊天**：Agent 能主动选择并调用工具，根据工具结果再回答用户
2. **闭环完整**：model emits tool_call -> parser extracts it -> executor runs it -> result feeds back -> model generates final answer
3. **自动注入**：conversation_id 等内部参数由 executor 自动注入，模型无感知
4. **安全可靠**：所有路径通过 PathSandbox 验证，异常不中断主循环
5. **流式输出**：全程 SSE 事件流，前端可实时展示工具调用过程
