# Backend_v2 替换方案与回滚计划

> **日期**: 2026-05-27 | **版本**: v1.0

---

## 1. 替换原则

**先新建，后替换。** 不要在旧代码上零碎修补。

- backend 作为独立模块运行
- 通过 Feature Flag 控制流量切换
- 旧系统保持运行直到 backend 完全验证
- 逐步替换，不是一次性切换

---

## 2. 替换步骤

### Phase 1: 并行运行（当前阶段）

```
用户流量 → 旧后端（主）
         → backend（旁路/测试）
```

- backend 独立部署（不同端口）
- 前端通过配置切换后端地址
- 仅内部测试使用 backend

### Phase 2: 灰度切换

```
用户流量 → Feature Flag Router
         ├─ 90% → 旧后端
         └─ 10% → backend
```

- 实现 Feature Flag 路由层
- 按用户 ID hash 分配流量
- 监控 backend 错误率和性能

### Phase 3: 全量切换

```
用户流量 → backend（主）
         → 旧后端（热备）
```

- backend 处理 100% 流量
- 旧后端保持运行但不接收新请求
- 观察 1-2 周无问题后进入 Phase 4

### Phase 4: 旧系统退役

```
用户流量 → backend（唯一）
旧后端 → 停止服务 → 代码归档
```

- 旧后端代码移入 `legacy/` 目录
- 保留 1 个月后删除
- 数据库保持兼容（如结构不同需迁移）

---

## 3. Feature Flag 实现

```python
# router.py
from core.config import settings

async def route_request(request):
    if settings.backend_enabled:
        # 按用户 ID hash 决定是否使用 v2
        user_hash = hash(request.user_id) % 100
        if user_hash < settings.backend_traffic_percent:
            return await backend_handle(request)
    return await legacy_backend_handle(request)
```

环境变量：
```bash
BACKEND_V2_ENABLED=true
BACKEND_V2_TRAFFIC_PERCENT=10  # 0-100
```

---

## 4. 数据库迁移

### 如果旧数据库与 backend 兼容

直接使用同一数据库，无需迁移。

### 如果需要迁移

```bash
# 1. 创建新数据库
createdb agent_db_v2

# 2. 运行 Alembic 迁移
cd backend
alembic upgrade head

# 3. 数据迁移脚本
python scripts/migrate_from_legacy.py \
    --from-db $LEGACY_DATABASE_URL \
    --to-db $NEW_DATABASE_URL

# 4. 验证数据完整性
python scripts/verify_migration.py
```

### 迁移内容

| 旧表 | backend 表 | 迁移策略 |
|------|--------------|---------|
| users | users | 直接迁移 |
| conversations | conversations | 迁移 + 新增字段默认值 |
| messages | messages | 迁移，content 转为 JSONB |
| uploads | workspace_files | 迁移 + 重命名 |
| memories | user_memories | 迁移 + 新增字段 |

---

## 5. 回滚方案

### 触发条件

- backend 错误率 > 1%（持续 5 分钟）
- P95 延迟 > 10 秒（持续 5 分钟）
- 核心功能不可用（聊天/上传/文件管理）
- 数据丢失或损坏

### 回滚步骤

```bash
# 1. 立即切换 Feature Flag
BACKEND_V2_ENABLED=false

# 2. 重启路由层
systemctl restart router

# 3. 确认流量回到旧后端
# 检查监控面板

# 4. 排查 backend 问题
# 查看日志
tail -f /var/log/backend/error.log

# 5. 修复后重新灰度
```

### 回滚时间

- Feature Flag 切换：~10 秒
- 完全生效：~30 秒（等待活跃连接完成）

---

## 6. 验证清单

在每次推进前必须验证：

- [ ] 普通聊天真实流式（SSE + 可中断）
- [ ] 上传文件后多轮回看
- [ ] 生成文件并展示 Diff
- [ ] 搜索并爬取资料
- [ ] 上下文档位切换
- [ ] 上下文压缩交互
- [ ] DeepSeek / Kimi 参数适配
- [ ] Markdown 流式结束不降级
- [ ] 前端布局与交互
- [ ] 工具调用 JSON 闭环
- [ ] 批量文件上传
- [ ] 图像上传与模型切换

---

## 7. 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| backend 性能问题 | 高 | Feature Flag 秒级回滚 |
| 数据库不兼容 | 高 | 保持旧库只读，新库双写 |
| API 接口变化 | 中 | 前端兼容层适配 |
| 模型适配错误 | 高 | 快速切换到旧模型适配 |
| Context OS 压缩过度 | 中 | 调整 profile 阈值 |
| Workspace 数据丢失 | 高 | 双存储模式保障 |
