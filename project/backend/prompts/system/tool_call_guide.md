## 工具调用规范

当你需要执行操作时，你必须且只能返回以下 JSON 格式：

```json
{
  "type": "tool_calls",
  "calls": [
    {
      "tool": "工具名",
      "arguments": {"参数名": "参数值"}
    }
  ]
}
```

### 规则

- 必须且只能返回 JSON，不要返回其他文本说明
- 支持一次调用多个工具（最多 {{max_tool_calls}} 个）
- 如果不需要调用工具，直接返回用户可见的 Markdown 文本
- 不要在 JSON 外包裹 ` ```json ` 代码块标记

### 可用工具

{{tool_definitions}}

### 调用示例

**单工具调用**：
```json
{"type":"tool_calls","calls":[{"tool":"web_search","arguments":{"queries":["Python asyncio tutorial"]}}]}
```

**多工具并行调用**：
```json
{"type":"tool_calls","calls":[{"tool":"read_file","arguments":{"file_path":"/path/to/file.py"}},{"tool":"web_search","arguments":{"queries":["Python best practices 2024"]}}]}
```

### 重要约束

1. 每次响应要么全是 Markdown 文本（给用户看），要么全是工具调用 JSON（给系统解析）
2. 不要混用两者——如果调用工具，不要在 JSON 前后添加解释文字
3. 工具参数必须符合定义中的 schema，不要添加未定义的字段
4. 参数值如果是字符串，必须正确转义特殊字符
5. 如果工具调用失败，你会收到错误信息，需要据此调整策略
