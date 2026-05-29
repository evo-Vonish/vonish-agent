# Workspace System

> **系统**: Agent 工作台系统

---

## 架构

Workspace 提供会话级的文件管理和安全沙箱：

```
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
```

---

## 核心特性

### 会话级隔离

每个会话拥有独立的工作区目录:
```
workspaces/
├── {conversation_id_1}/
│   ├── src/
│   ├── docs/
│   └── README.md
├── {conversation_id_2}/
│   └── ...
```

### 双存储模式

- **Server Storage**: 服务器本地文件系统
- **Local Storage**: 可选本地存储同步
- 默认双写，确保数据安全

### 路径沙箱

安全验证机制:
- 阻止 `../` 目录遍历
- 阻止符号链接逃逸
- 所有路径解析为绝对路径后验证前缀

### 快照/Diff

每轮 Agent Loop 前后自动创建快照:
- 追踪文件创建、修改、删除
- 生成 Diff 摘要供模型参考

---

## 核心文件

- `workspace_manager.py` — 主管理器
- `permissions.py` — 路径沙箱验证
- `snapshot.py` — 快照管理
- `diff.py` — 变更对比
- `local_provider.py` — 本地存储提供者
- `server_provider.py` — 服务器存储提供者
- `storage_provider.py` — 存储抽象接口
- `indexer.py` — 文件索引
