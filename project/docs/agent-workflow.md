# Agent Workflow

> **系统**: Agent 工作台系统

---

## Agent Loop 工作流

```
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
```

---

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

---

## 防循环机制

| 机制 | 实现 | 阈值 |
|------|------|------|
| 指纹检测 | 工具调用参数指纹去重 | 3 次重复 |
| 最大轮数 | 循环计数器 | 50 轮 |
| 最大时间 | 超时计时器 | 5 分钟 |
| 最大成本 | Token 消耗估算 | 按 Profile 限制 |
| 用户中断 | 中断信号 | 即时 |

---

## 工具调用格式

模型输出的工具调用格式:

```json
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
```

工具执行结果格式:

```json
{
  "tool_results": [
    {
      "name": "read_file",
      "result": "file content...",
      "success": true
    }
  ]
}
```
