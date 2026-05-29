# API Documentation

> **系统**: Agent 工作台系统 | **基础路径**: `/api`

---

## 接口列表

### 会话管理 (`/api/conversations`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/conversations` | 创建新会话 |
| GET | `/api/conversations` | 获取会话列表 |
| GET | `/api/conversations/{id}` | 获取会话详情 |
| DELETE | `/api/conversations/{id}` | 删除会话 |

### 聊天 (`/api/chat`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/{id}/stream` | SSE 流式聊天（核心接口） |
| POST | `/api/chat/{id}/stop` | 中断生成 |

**SSE 事件类型**:
- `thinking` - 模型思考过程
- `tool_call` - 工具调用请求
- `tool_result` - 工具执行结果
- `content` - 内容片段
- `done` - 完成信号
- `error` - 错误信息

### 文件上传 (`/api/uploads`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/uploads/{conversation_id}` | 批量文件上传 |

### Workspace (`/api/workspaces`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/workspaces/{id}/files` | 获取文件列表 |
| POST | `/api/workspaces/{id}/files` | 创建/写入文件 |
| GET | `/api/workspaces/{id}/files/{path}` | 读取文件内容 |
| DELETE | `/api/workspaces/{id}/files/{path}` | 删除文件 |

### 工具 (`/api/tools`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tools` | 获取可用工具列表 |
| POST | `/api/tools/execute` | 直接执行工具 |

### 上下文 (`/api/context`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/context/{id}/usage` | Token 使用量统计 |

### 记忆 (`/api/memory`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/memory/user` | 获取用户记忆 |

### 模型 (`/api/models`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/models` | 获取可用模型列表 |

---

## 认证

所有 API 请求需要在 Header 中携带认证信息:

```
Authorization: Bearer {token}
```

或使用 API Key:

```
X-API-Key: {api_key}
```

---

## 错误处理

统一的错误响应格式:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "details": {}
  }
}
```

常见错误码:

| 状态码 | 错误码 | 说明 |
|--------|--------|------|
| 400 | `INVALID_REQUEST` | 请求参数错误 |
| 401 | `UNAUTHORIZED` | 未认证 |
| 403 | `FORBIDDEN` | 无权限 |
| 404 | `NOT_FOUND` | 资源不存在 |
| 429 | `RATE_LIMITED` | 请求过于频繁 |
| 500 | `INTERNAL_ERROR` | 服务器内部错误 |
