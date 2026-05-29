# Agent 工作台系统重构 — 执行计划

## 项目概述
将普通聊天网页重构为具备 Agent Loop、Workspace、Context OS、多模型适配的完整 Agent 工作台。
- **后端**: FastAPI (backend_v2/) — 全新建设，不修补旧代码
- **前端**: React + TypeScript — Agent 工作台 UI（深色极简风格，参考 Claude Code）

## 技能加载策略
- **Stage 1 (架构)**: 无技能，自主设计
- **Stage 2 (后端核心)**: `vibecoding-general-swarm` — Python/FastAPI 后端
- **Stage 3 (前端)**: `vibecoding-webapp-swarm` — React/TypeScript 前端
- **Stage 4 (联调与测试)**: 双技能结合

---

## Stage 1: 项目骨架与架构设计（串行）

### 1.1 项目总体架构设计
- 设计 backend_v2/ 完整目录结构
- 设计前端目录结构
- 定义模块接口契约
- 输出架构文档

### 1.2 数据库 Schema 设计
- 设计所有表结构（users, conversations, messages, workspaces, files, resources, tool_calls, memories 等）
- SQLAlchemy models
- Alembic migration

### 1.3 项目骨架搭建
- FastAPI 主应用 + 路由注册
- 配置系统 (config.py)
- 日志系统 (logging.py)
- 错误处理 (errors.py)
- 认证占位 (auth.py)
- 前端 React + Vite + TypeScript 骨架

**交付**: 可运行的空骨架（前后端）

---

## Stage 2: 后端核心模块（backend_v2）— 多 Agent 并行

### 2A: SSE Streaming + API 路由（Agent B）
- SSE 事件协议实现（全部 18 种事件类型）
- Streaming 基础设施
- 全部 API 路由（chat, conversations, workspace, uploads, files, tools, context, memory, models）
- 中断机制 (POST /api/chat/{id}/stop)

### 2B: Model Adapter（Agent C）
- 爬取 Kimi + DeepSeek 官方文档
- ModelCapabilityRegistry
- DeepSeek V4-Pro/Flash 适配器
- Kimi K2.6/K2.5 适配器
- 统一 stream_chat() 接口
- reasoning_content / content 分流解析
- JSON Output 模式工具调用解析
- 上下文缓存优化

### 2C: Context OS（Agent D）
- ContextBuilder（六层上下文组装）
- ContextProfile（Cheap/Balanced/Max/Custom 四档）
- TokenBudget（预算管理 + 渐进式压缩阈值）
- MemorySelector（向量召回 + RRF 融合）
- CompressionEngine（智能压缩）
- ToolResultLifecycle（五级状态机）

### 2D: Workspace 系统（Agent E）
- WorkspaceManager（会话级隔离）
- StorageProvider（Server + Local 双写）
- 路径沙箱（防 ../ 逃逸）
- Snapshot / Diff
- Workspace 工具组（10 个工具）

### 2E: 文件上传与资源索引（Agent F）
- multipart 批量上传
- 文本类处理管线（PDF/DOCX/MD/TXT/代码）
- 图像类处理（缩略图、仅 Kimi 注入）
- 批量文件 manifest 生成
- 摘要/Chunk/Embedding 管线

### 2F: Tool Runtime + Skill 框架（Agent G）
- ToolRegistry（白名单）
- ToolExecutor
- search_and_crawl 内置工具
- workspace tools 内置工具
- skills/ 目录框架（base.py, schema/, implementations/）

### 2G: Agent Loop（Agent H）
- 多轮 Agent Loop（六阶段循环）
- JSON Output 工具调用解析（支持多个）
- 工具执行回填
- 中断支持
- 防循环机制（指纹检测 + 重复限制）
- 成本/步数/时间限制

### 2H: Prompt 工程（Agent K）
- prompts/system/ 目录（base_v1.md, markdown_guide.md, tool_call_guide.md, workspace_guide.md, context_budget_guide.md）
- prompts/agent/ 目录（loop_start.md, loop_continue.md, loop_final.md, self_check.md）
- prompts/tool/ 目录（tool_gating.md, result_summary.md, result_format.md）
- prompts/context/ 目录（memory_inject.md, compression_trigger.md, profile_switch.md, file_manifest.md）
- prompts/builder.py（Prompt Builder 引擎）

**交付**: backend_v2 完整可运行后端

---

## Stage 3: 前端 Agent 工作台（串行 → 并行组件）

### 3.1 核心布局框架
- 深色主题 (#0d0d0d)
- 顶部极简栏
- 左侧可拖拽/可收起侧边栏（会话列表 + Workspace 文件树 + Skills + Search）
- 左下角状态栏菜单（Language / Account / Settings）
- 主内容区

### 3.2 输入区组件
- 输入框上方小组件（删除对话 / 上下文管理 / 导出 / 模型切换▼）
- 附件横向铺排（含转圈圈状态、小叉号删除）
- 多行输入框 Composer
- 文件上传（📎）+ 发送按钮

### 3.3 消息流式渲染
- 真实 SSE 流式接收（非伪流式）
- 自适应打字速度算法
- Markdown 全家桶渲染（含数学公式、Mermaid 图表）
- 思考卡片（Thinking Card）— 可折叠
- 工具卡片（Tool Card）— 可展开
- Workspace Diff 展示

### 3.4 交互面板
- 上下文管理窗口（Context Manager Panel）— Token 仪表盘、档位切换、压缩按钮
- 设置页面（Settings Modal）— 模型/Agent/Workspace/记忆/隐私
- Account 浮层
- 模型切换下拉

### 3.5 API 对接
- 对接所有 backend_v2 API
- SSE 事件处理
- 文件上传进度

**交付**: 完整前端代码，对接 backend_v2

---

## Stage 4: 联调、测试与替换方案（串行）

### 4.1 集成测试
- 12 个验收场景全部跑通
- 真实流式验证
- 工具调用 JSON 闭环
- Markdown Bug 回归测试
- 模型切换测试
- 批量上传测试

### 4.2 替换方案
- Feature Flag 切换
- 旧系统退役计划
- 回滚方案

**最终交付**: 完整的 backend_v2 + 前端 Agent 工作台 + 测试报告 + 替换方案
