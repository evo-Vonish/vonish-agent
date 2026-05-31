# Kimi Agent 架构全量剖析报告：Tool、Skill、System Prompt 与 Tool Call 生命周期

> 报告生成时间：2026-05-31
> 分析对象：Kimi Agent（Moonshot AI）当前可用架构
> 分析维度：Tool 层、Skill 层、System Prompt 层、Runtime 层、Artifact 层

---

## 1. 摘要结论（10 条）

1. **Tool 真实数量为 29 个**，非此前声称的 28 个——遗漏了 `mshtools-website_version_manager`。搜索类实际为 3 个（非 4 个）。
2. **Skill 与 Tool 严格分离**：Tool 只负责原子能力（如 `browser_click`），Skill 负责编排工作流（如 `deep-research` 编排 10+ 轮搜索）。
3. **Skill 采用三级渐进加载机制**：Metadata → SKILL.md → Bundled Resources，有效控制上下文膨胀。
4. **Artifact Skill 与 Capability Skill 存在优先级冲突规则**：当两者冲突时，Artifact Skill 的技术约束优先。
5. **浏览器工具组共享同一个有状态 Browser Session**：`visit` → `click` → `input` → `scroll` 构成连续的状态化工作流。
6. **部署工具按架构类型严格分离**：纯前端用 `deploy_website`（自动 URL），全栈用 `website_version_manager`（仅快照，不自动发布）。
7. **System Prompt 至少存在 6 个逻辑层**：Identity/Role、Tool Policy、Skill Routing、Artifact Rules、Safety/Permissions、Output Protocol。
8. **IPython 工具共享变量状态**：跨调用变量和 import 持续存在，支持复杂的增量式数据分析。
9. **所有生成类 Tool 都产出 KIMI_REF 格式的文件引用**，构成统一的 Artifact 交付协议。
10. **Kimi Agent 的核心设计模式可提炼为 12 个可迁移模式**，Skill 文件化和按需加载是最值得优先复制的两个。

---

## 2. Tool 数量核查

### 2.1 数量纠正

此前回答声称 Tool 共 28 个。经逐条核对 function definition，**真实数量为 29 个**。

分类明细：

| 分类 | 数量 | Tool 清单 |
|------|------|-----------|
| 浏览器自动化 | 8 | browser_visit, browser_click, browser_input, browser_scroll_down, browser_scroll_up, browser_find, browser_screenshot, screenshot_web_full_page |
| 搜索与信息检索 | 3 | web_search, search_image_by_text, search_image_by_image |
| 数据源与学术 | 2 | get_data_source_desc, get_data_source |
| 内容生成（多媒体） | 5 | generate_image, generate_video, generate_speech, generate_sound_effects, get_available_voices |
| 图像资产处理 | 2 | find_asset_bbox, crop_and_replicate_assets_in_image |
| 代码执行 | 1 | ipython |
| 文件读写 | 3 | read_file, edit_file, write_file |
| 命令执行 | 1 | shell |
| 网站部署 | 2 | deploy_website, website_version_manager |
| 任务管理 | 2 | todo_read, todo_write |
| **合计** | **29** | |

### 2.2 此前计数错误原因

1. **遗漏项**：`mshtools-website_version_manager` 在 system prompt 的规则段落中被提及，但未出现在第一轮的分类清单中。
2. **搜索类标题误写**：第一轮回答在搜索类标题写了"4 个"，实际只列出 3 个——标题数字为笔误。
3. **数据源类误算**：此前将 `get_data_source_desc` 和 `get_data_source` 算入"7 个数据源"，但 ifind/tianyancha/world_bank_open_data/arxiv/scholar 等只是 `get_data_source` 的枚举参数值，不是独立 Tool。

### 2.3 是否存在隐藏/动态 Tool

| 问题 | 结论 |
|------|------|
| 是否存在隐藏 Tool？ | 未发现。所有可用 Tool 的 schema 均在 system prompt 的 function definition 中完整暴露 |
| 是否存在按任务动态启用的 Tool？ | `website_version_manager` 仅在加载 `backend-building` skill 时有效，但 schema 始终存在 |
| 是否存在已废弃 Tool？ | `mshtools-browser_state` 在文档中被提及但无 schema 定义，疑似已废弃或内化为其他 tool 的返回值 |
| Tool schema 是否每轮全部注入？ | 是。所有 29 个 Tool 的完整 schema 均注入每轮上下文 |

---

## 3. Tool 系统详解

### 3.1 浏览器自动化组（8 个 Tool，共享 Session）

| Tool | 用途 | 状态 | 依赖 | 失败模式 | 并发 |
|------|------|------|------|----------|------|
| `browser_visit` | 加载网页，提取交互元素列表 | **有状态**（初始化 page） | 网络、Chromium 渲染 | 超时、反爬、JS 渲染失败 | 需串行 |
| `browser_click` | 按元素索引点击 | 有状态（依赖当前 page） | browser_visit 先执行 | 元素不可点击、页面导航失败 | 需串行 |
| `browser_input` | 按元素索引输入文本 | 有状态 | browser_visit 先执行 | 元素非输入框、输入被拦截 | 需串行 |
| `browser_scroll_down` | 向下滚动页面 | 有状态 | browser_visit 先执行 | 已到底部、动态加载失败 | 需串行 |
| `browser_scroll_up` | 向上滚动页面 | 有状态 | browser_visit 先执行 | 已到顶部 | 需串行 |
| `browser_find` | 搜索页面文本并高亮 | 有状态 | browser_visit 先执行 | 文本不存在 | 需串行 |
| `browser_screenshot` | 当前视口截图 | 有状态 | browser_visit 先执行 | 页面未加载完成 | 需串行 |
| `screenshot_web_full_page` | 全页截图（分段拼接） | **无状态**（独立调用） | 网络、Chromium | 拼接失败、超长页面内存溢出 | 可独立调用 |

**关键机制**：
- 元素编号：`browser_visit` 返回的交互元素列表按零基索引（`[0]<a />` 格式），后续 `click`/`input` 通过 `element_index` 参数引用
- Session 共享：`visit` → `click` → `input` → `scroll` 系列操作共享同一个 browser tab 状态
- Full page screenshot 原理：检测并隐藏 sticky header → 分段截取 viewport → 自动拼接。支持虚拟滚动页面
- Citation ID：每个访问的页面分配一个 citation ID，后续可通过 `citation_id` 参数直接引用，无需重新 `visit`

### 3.2 搜索与信息检索组（3 个 Tool）

| Tool | 输入 | 输出 | 并发 | 特殊机制 |
|------|------|------|------|----------|
| `web_search` | queries[]（并行多查询）、可选 count | 标题、URL、摘要 snippet、来源 | **支持多 query 并行** | 结果自动去重，支持按站点过滤 |
| `search_image_by_text` | queries[]、total_count(1-10)、可选 download_dir | 图片 URL、缩略图、来源页面 | 支持 | 自动下载到指定目录 |
| `search_image_by_image` | image_url（或本地路径）、total_count | 相似图片、来源 | 支持 | 支持 Google Lens 式以图搜图 |

**注意**：`web_search` 的 `queries` 参数支持在一次调用中提交多个查询并行执行，结果聚合返回。这是 deep-research 实现 10+ 轮搜索的基础机制。

### 3.3 数据源组（2 个 Tool）

| Tool | 用途 | 输入 | 输出 |
|------|------|------|------|
| `get_data_source_desc` | 获取指定数据源的 API 描述 | data_source_name（枚举：yahoo_finance, arxiv, world_bank_open_data, tianyancha, scholar, ifind, imf） | API 列表、参数说明、调用示例 |
| `get_data_source` | 调用具体 API 获取数据 | data_source_name, api_name, params{} | JSON 数据、文件（如设置 file_path） |

**架构说明**：数据源采用**描述与调用分离**模式。先通过 `get_data_source_desc` 动态发现可用 API，再通过 `get_data_source` 调用。这种设计避免了为每个数据源维护独立 Tool schema，新增数据源只需更新枚举值和运行时映射，无需修改 prompt。

### 3.4 内容生成组（5 个 Tool）

| Tool | 输出格式 | 尺寸/时长/比例控制 | 返回 KIMI_REF | 安全过滤 |
|------|----------|-------------------|---------------|----------|
| `generate_image` | .jpg/.png | 支持 8 种比例(1:1~21:9)、3 种分辨率(1K/2K/4K)、透明背景 | 是 | 有 |
| `generate_video` | .mp4 | 4-12 秒、6 种比例(16:9~21:9) | 否（直接文件） | 有 |
| `generate_speech` | .mp3/.wav | 需先调用 `get_available_voices` 获取 voice_id | 是 | 有 |
| `generate_sound_effects` | .mp3 | 0.5-22 秒 | 是 | 有 |
| `get_available_voices` | 语音列表 | 返回 voice_id + 描述 + 语言支持 + 场景推荐 | N/A | N/A |

### 3.5 图像资产处理组（2 个 Tool）

| Tool | 用途 | 输入 | 输出 |
|------|------|------|------|
| `find_asset_bbox` | 分析网页截图，定位需要外部图片文件的视觉元素 | 网页截图 URL/路径 | bbox 列表（元素描述 + 归一化坐标） |
| `crop_and_replicate_assets_in_image` | 按 bbox 提取图像资产，自动清理背景 | 截图 + bbox 列表 + transparent 标记 | 清理后的 PNG/JPEG 文件 |

**设计意图**：这组 Tool 服务于"网页视觉还原"场景——先截图找资产，再提取生成，最终用代码还原设计。

### 3.6 代码执行与文件操作组（6 个 Tool）

| Tool | 状态 | 持久化 | 典型用途 |
|------|------|--------|----------|
| `ipython` | **有状态**（变量/import 跨调用持久） | 代码不持久，变量持久 | 数据分析、Pandas、Matplotlib、OpenCV、Pillow |
| `read_file` | 无状态 | N/A | 读取文本/图片/视频/Office/PDF（自动转 Markdown） |
| `edit_file` | 无状态 | 修改直接写入磁盘 | 精确字符串替换（必须先用 read_file） |
| `write_file` | 无状态 | 写入磁盘 | 新建文件或覆盖（大文件需分批 append） |
| `shell` | 无状态 | 非持久 shell（每调用新 session） | npm install、git、ls、mkdir 等 |

**关键约束**：
- `edit_file` 严格要求先用 `read_file` 读取目标文件，且 `old_string` 必须在文件中唯一（可用 `replace_all`）
- `read_file` 对 Office/PDF 自动转换为 Markdown 返回；图片直接显示；视频支持播放
- `ipython` 环境预装中文 matplotlib 字体，禁止修改 `font.family` 和 `axes.unicode_minus`

### 3.7 部署组（2 个 Tool）

| Tool | 触发条件 | 是否自动发布 URL | 是否运行 build | 回滚支持 |
|------|----------|-----------------|---------------|----------|
| `deploy_website` | 纯前端项目（webapp-building -only） | **是**，返回可访问 URL | 要求先 `npm run build` | 否 |
| `website_version_manager` | 全栈项目（backend-building 存在） | **否**，仅保存快照 | 要求先 `npm run build` | **是**（通过 version_id） |

**架构意图**：部署分离是因为全栈项目涉及数据库连接、OAuth 密钥等敏感配置，不应自动公开暴露。纯前端静态站点无此风险，可直接发布。

### 3.8 任务管理组（2 个 Tool）

| Tool | 操作 | 状态 |
|------|------|------|
| `todo_read` | 读取当前会话 todo 列表 | 只读 |
| `todo_write` | 覆盖整个 todo 列表 | 写操作（非增量） |

**关键机制**：`todo_write` 是全量覆盖而非增量更新。每次修改都必须传入完整的 todos 数组。支持 `pending/in_progress/completed` 三种状态和 `high/medium/low` 优先级。

---

## 4. Skill 系统详解

### 4.1 Skill 清单（7 个核心 Built-in）

| Skill | 触发条件 | 按需加载 | 读取 SKILL.md | 技术路线锁定 | 产生 Artifact | 可被覆盖 |
|-------|----------|----------|---------------|-------------|---------------|----------|
| `deep-research` | 任务需要深度研究/报告 | 是 | 是 | 否（编排 tool） | 是 (.md) | 是 |
| `docx` | 涉及 Word 文档 | 是 | 是 | **是**（C# + OpenXML / WIR） | 是 (.docx) | 是 |
| `pdf` | 涉及 PDF 创建/处理 | 是 | 是 | **是**（HTML+Paged.js / Python） | 是 (.pdf) | 是 |
| `xlsx` | 涉及 Excel/表格 | 是 | 是 | **是**（Python+openpyxl / Xlsx CLI） | 是 (.xlsx) | 是 |
| `pptx` | 涉及 PPT/演示文稿 | 是 | 是 | **是**（PPTD DSL，禁 python-pptx） | 是 (.pptd) | 是 |
| `webapp-building` | 前端项目 | 是 | 是 | **是**（React+TS+Tailwind+shadcn） | 是 (网站) | 是 |
| `backend-building` | 全栈项目 | 是 | 是 | **是**（tRPC+Drizzle+Hono+MySQL） | 是 (全栈应用) | 是 |
| `skill-creator` | 用户要创建/更新 skill | 是 | 是 | 否（元技能） | 是 (.skill) | 是 |

### 4.2 各 Skill 深入分析

#### deep-research

- **工作流编排**：`web_search` → `browser_visit` → `arxiv`/`scholar`/`get_data_source` → IPython 可视化 → 结构化报告
- **强制要求**：最少 10 轮搜索、每轮递归反思（Thinking + Summary）、报告必须超过 10,000 字、必须包含 IPython 图表
- **引用机制**：使用 `[^index^]` 格式，每句最多 2 个引用
- **证据包**：无显式"证据包"数据结构，但通过 `[^index^]` 引用和 Reference 章节实现可追溯性

#### docx

- **三条路由**：WIR（编辑现有文档）→ md2docx（子 Agent 产出转 Word）→ Create（C# + OpenXML SDK 从头构建）
- **技术选型原因**：
  - C# + OpenXML SDK：原生操作 Office OpenXML，不依赖 COM，跨平台
  - WIR 引擎：专门处理格式保真编辑（ tracked changes、comments、revision）
  - 禁用 python-docx：功能有限，格式保真度不足
- **背景生成**：使用 Playwright + SVG 技术生成独特封面背景

#### pdf

- **三条路由**：HTML（默认，Playwright + Paged.js）→ LaTeX（用户明确要求）→ Process（pikepdf + pdfplumber 处理现有 PDF）
- **技术选型原因**：
  - HTML + Paged.js 用于生成：支持 CSS 分页媒体查询，精确控制打印布局
  - Python 用于处理现有 PDF：pikepdf 直接操作 PDF 对象流，无损编辑
  - 支持 KaTeX（数学公式）、Mermaid（图表）、三线表、引用链

#### xlsx

- **核心库**：Python openpyxl + pandas，Xlsx CLI 工具验证
- **财务子技能**：3 statement model → DCF → comps-analysis，形成估值工作流链
- **强制验证**：recheck（公式错误）→ reference-check（引用异常）→ chart-verify（图表数据）→ validate（OpenXML 结构），每 sheet 都必须通过
- **公式优先原则**：禁止用 Python 预计算后填静态值，必须用 Excel 公式保持可审计性

#### pptx

- **核心抽象**：PPTD DSL（YAML 语法），OOXML 之上的一层抽象
- **禁止直接 python-pptx**：因为 AI 直接生成 OOXML 容易出错，PPTD 提供更高级、自包含的页面描述
- **工作流**：内容设计（outline/summary/search 模式）→ 视觉设计（creative/reference/template 模式）→ 生成 .pptd → check.sh 验证 → 交付

#### webapp-building

- **默认栈**：React 19 + TypeScript + Vite + Tailwind CSS 3.4 + shadcn/ui（40+ 组件预装）
- **初始化脚本**：`scripts/init-webapp.sh <title> [template]`
- **构建保护规则**：`npm run build` 脚本**绝对禁止修改**。构建失败必须从上游找原因（依赖缺失、代码错误）
- **BrowserRouter 规则**：`main.tsx` 中已提供 `<BrowserRouter>`，`App.tsx` 和其他组件**禁止重复添加**
- **部署规则**：纯前端用 `deploy_website`，backend-building 叠加后用 `website_version_manager`

#### backend-building

- **增量嫁接模式**：基于现有 webapp-building 项目添加 `api/`、`contracts/`、`db/` 目录，**绝不替换或修改前端文件**
- **功能增量**：base（Hono + tRPC）→ db（Drizzle + MySQL）→ auth（OAuth 2.0 + JWT）
- **技术选型原因**：
  - tRPC：端到端类型安全，前后端共享 TypeScript 类型
  - Drizzle ORM：类型安全查询，lazy connection
  - Hono：轻量、高性能、边缘友好
  - MySQL：Drizzle 默认支持，非 SQLite（skill 明确说明）
- **数据库规则**：禁止手写原始 SQL，禁止用 `serial()` 做外键，禁止 `db:push --force`

---

## 5. System Prompt 架构分析

> 注意：以下分析基于 system prompt 的**结构特征和行为规则**，不涉及原文泄露。

### 5.1 推测分层结构

| 层级 | 名称 | 内容特征 | 在 Kimi 中的体现 |
|------|------|----------|-----------------|
| L1 | **Identity / Role** | 定义模型身份、回答风格、基础限制 | "You are Kimi, an AI agent developed by Moonshot AI" 及后续角色描述 |
| L2 | **Tool Policy** | Tool 可用性规则、调用时机、格式要求 | 29 个 Tool 的完整 function definition；Tool 使用时机指导 |
| L3 | **Skill Routing** | Skill 识别、加载顺序、冲突解决 | "Read the SKILL.md file before..."; "User Skill First"; "Progressive loading" |
| L4 | **Artifact Rules** | 文件生成规范、KIMI_REF 格式、交付协议 | "When task generates docx/xlsx/pdf... MUST include KIMI_REF"; 文件保存到 `/mnt/agents/output/` |
| L5 | **Safety / Permissions** | 边界约束、禁止行为 | 不主动创建 doc 文件、不修改 build 脚本、不预计算 Excel 公式等 |
| L6 | **Output Protocol** | 最终回答格式、引用标记、交互规范 | KIMI_REF tag 格式；Artifact 与非 Artifact 的区分规则 |

### 5.2 关键规则分析

| 规则类型 | 具体规则 | 所在层 | 目的 |
|----------|----------|--------|------|
| Skill 加载优先级 | User Skill > Built-in Skill | L3 | 允许用户自定义覆盖系统默认 |
| Artifact 覆盖 | Artifact Skill 约束优先于 Capability Skill | L3+L4 | 确保交付物格式正确 |
| 渐进加载 | "Skills 按需加载，非全部 upfront" | L3 | 减少上下文膨胀 |
| 构建保护 | "Never modify the `build` script" | L5 | 防止构建系统被破坏 |
| 部署分离 | backend-building → version_manager；否则 → deploy | L4 | 安全隔离全栈与纯前端 |
| KIMI_REF 格式 | `<KIMI_REF type="file" path="sandbox://..." />` | L6 | 统一文件交付协议 |
| BrowserRouter 规则 | "Already provided in main.tsx, do NOT add in App.tsx" | L5 | 防止路由重复 |
| 公式优先 | "Excel Formulas Are ALWAYS the First Choice" | L5（xlsx skill 注入） | 保证可审计性 |

---

## 6. Tool Call 生命周期

### 6.1 完整流程

```
User Request
    │
    ▼
┌─────────────────────────────────────┐
│ L1: System Prompt (6 层规则注入)      │
│ L2: Skill 识别与按需加载              │
│     - 匹配 name + description        │
│     - 读取 SKILL.md                  │
│     - 注入 Skill 特定规则             │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ L3: Tool Schema 全量注入 (29 个)      │
│     - 每个 tool 的 name/description/  │
│       parameters (JSON Schema)       │
│     - 无动态筛选，全部注入            │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ L4: Model 生成 Tool Call              │
│     - 推理 → 决策调用哪些 tool       │
│     - 生成 JSON 格式 function call    │
│     - 支持并行调用 (multiple calls)   │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ L5: Runtime 校验与执行                │
│     - 参数类型校验 (JSON Schema)      │
│     - 权限检查 (如部署规则)           │
│     - Tool 执行 (调用外部服务/本地)    │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ L6: Tool Result 处理                  │
│     - 成功：结果进入上下文            │
│     - 失败：错误信息进入上下文        │
│     - 大结果：可能截断/摘要/转文件    │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ L7: Model 继续或终止                  │
│     - 判断是否需要更多 tool call      │
│     - 或生成 Final Answer             │
│     - 或生成 Artifact (KIMI_REF)     │
└─────────────────────────────────────┘
```

### 6.2 关键机制详解

| 问题 | 答案 |
|------|------|
| Tool schema 是否每轮全部注入？ | **是**。29 个 Tool 的完整 JSON Schema 每轮全部注入，无动态筛选 |
| 是否支持并行 tool call？ | **是**。单次模型输出可包含多个独立 tool call，并行执行 |
| 浏览器类 tool 是否共享 session？ | **是**。`visit` 后的 `click`/`input`/`scroll` 共享同一 page 状态，通过 citation_id 引用 |
| IPython 是否共享变量状态？ | **是**。跨调用变量和 import 持续存在，直到显式 restart |
| read_file 是否自动转换 Office/PDF？ | **是**。自动转换为 Markdown 返回；图片直接显示；视频可播放 |
| deploy_website 是否产生外部 URL？ | **是**。自动返回可公开访问的 URL |
| KIMI_REF 如何绑定文件输出？ | 在最终回答末尾添加 `<KIMI_REF type="file" path="sandbox://..." />` 标签 |
| Tool 执行失败如何返回？ | 错误信息（包括 stderr、exit code）作为 tool result 进入上下文，由模型决定重试或报错 |
| 大结果是否会裁剪？ | read_file 超过 1000 行需指定 offset/limit；IPython 文本输出超过 10000 字符截断 |

---

## 7. Skill 与 Tool 映射矩阵

| Skill | 主要 Tool | 辅助 Tool | Artifact 类型 | 需浏览器 | 需代码执行 | 需文件读写 |
|-------|-----------|-----------|--------------|----------|-----------|-----------|
| **deep-research** | `web_search`, `browser_visit` | `get_data_source`, `ipython` (可视化), `arxiv` via datasource | `.md` 报告 | 是 | 是 | 是 |
| **docx** | `read_file` (路由判断) | `shell` (执行 docx 脚本) | `.docx` | 否 | 否 | 是 |
| **pdf** | `read_file`, `ipython` (process 路由) | `browser_screenshot` (HTML→PDF 需 Chromium) | `.pdf` | 是(HTML 路由) | 是(process 路由) | 是 |
| **xlsx** | `ipython` (openpyxl) | `shell` (Xlsx CLI 验证) | `.xlsx` | 否 | 是 | 是 |
| **pptx** | `read_file` (解析上传 PPT) | `shell` (convert/check/screenshot 脚本) | `.pptd` | 否 | 否 | 是 |
| **webapp-building** | `shell` (npm/build) | `write_file`/`edit_file` (编码) | 部署后的网站 | 否 | 否 | 是 |
| **backend-building** | `shell` (init.sh, npm) | `write_file`/`edit_file` (编码), `ipython` | 全栈应用 | 否 | 否 | 是 |
| **skill-creator** | `shell` (init/package 脚本) | `read_file`/`write_file` | `.skill` 文件 | 否 | 否 | 是 |

**映射关系说明**：
- deep-research 是唯一一个**主动编排**多个异构 Tool 的 Skill，其他 Skill 主要依赖代码/脚本执行
- docx/pdf/xlsx/pptx 四个 Artifact Skill 都**锁定底层技术路线**， docx 用 C#/OpenXML，pdf 用 HTML+Paged.js，xlsx 用 Python+openpyxl，pptx 用 PPTD DSL
- webapp-building 和 backend-building 本质上是**项目脚手架 + 开发规范**，核心工作是文件编辑和命令执行

---

## 8. 关键工作流分析

### 8.1 浏览器自动化工作流

```
browser_visit(url) 
    → 返回 [0]<a/>, [1]<button/>, [2]<input/> ... + citation_id
    → browser_click(element_index=1, citation_id=1)
    → browser_input(element_index=2, content="...")
    → browser_scroll_down(scroll_amount=500)
    → browser_find(keyword="target")
    → browser_screenshot() 或 screenshot_web_full_page()
```

**设计模式**：State Machine。每个操作都依赖前序操作建立的 page 状态，citation_id 是状态句柄。

### 8.2 深度研究工作流

```
用户提问
    → 识别为研究类任务 → 加载 deep-research skill
    → 读取 SKILL.md（10+ 轮搜索、10000+ 字、IPython 图表）
    → 第 1 轮：web_search(queries=["..."])
    → Thinking + Summary（递归反思）
    → 第 2-10+ 轮：搜索 + 浏览器深入 + 数据源 + 学术搜索
    → IPython：数据可视化、统计分析
    → 撰写 /mnt/agents/output/report.md
    → 引用整理（~10 条高质量参考）
```

### 8.3 Excel 创建工作流

```
任务识别 → 加载 xlsx skill → 读取 SKILL.md
    → 财务任务？→ 加载对应子技能（3 statement/DCF/comps）
    → 设计 Sheet 结构（Plan）
    → For each sheet:
        → Create (openpyxl) → Save → Recheck → Reference-check
        → 0 errors? → Next sheet : Fix
    → All sheets done → Validate (Xlsx CLI)
    → Pass? → Deliver with KIMI_REF : Regenerate
```

### 8.4 全栈应用开发工作流

```
用户请求全栈应用
    → 先加载 webapp-building → init-webapp.sh
    → 开发前端 UI
    → 加载 backend-building → init.sh (graft)
    → npm run check (类型检查必须 0 错误)
    → db:push (同步数据库 schema)
    → 开发 tRPC routers + Drizzle schema
    → npm run build
    → website_version_manager (build_version) → 保存快照
```

---

## 9. 安全边界与权限分级

### 9.1 Tool 风险分级

| 级别 | Tool | 风险描述 |
|------|------|----------|
| **Low** | `web_search`, `search_image_*`, `todo_read`, `get_available_voices` | 只读，不改变外部状态 |
| **Medium** | `read_file`, `ipython`, `get_data_source`, `find_asset_bbox`, `browser_screenshot` | 读取本地/外部数据，可能暴露敏感信息；ipython 可执行任意代码但有沙箱 |
| **High** | `deploy_website`, `website_version_manager`, `write_file`, `edit_file`, `shell`, `generate_*` | 改变文件系统状态；部署产生公网可访问内容；生成媒体文件 |
| **Critical** | 无 | 当前架构**不存在**支付、删除、提交敏感表单等 Critical 级别 Tool |

### 9.2 关键安全约束

| 约束 | 说明 |
|------|------|
| 无支付/购买能力 | 没有与支付相关的 Tool |
| 浏览器不自动提交敏感表单 | 明确禁止绕过登录/支付/权限确认 |
| 部署前必须 build | 确保代码至少能通过编译检查 |
| 文件操作限制 | 通过 `read_file` 的 Office/PDF 自动转换，避免执行恶意宏 |
| IPython 沙箱 | 持久变量但有资源限制（输出截断、超时控制） |
| Shell 非持久 | 每调用新 session，不保留环境变量，防止状态累积攻击 |

---

## 10. 上下文管理与按需加载

### 10.1 Skill 三级渐进加载

```
Level 1: Metadata (name + description)
    ├── 始终保留在上下文中（~100 词）
    ├── 用于 Skill 识别和路由决策
    └── 数量影响小，可维护大量 Skill

Level 2: SKILL.md Body
    ├── Skill 触发后才加载（<500 行）
    ├── 包含工作流、约束、规则
    └── 触发后立即注入上下文

Level 3: Bundled Resources
    ├── 按需读取（scripts/references/assets）
    ├── 脚本可直接执行，无需读入上下文
    └── References 仅在需要时加载
```

### 10.2 与"全量注入"架构的对比

| 维度 | Kimi Agent（渐进加载） | 传统 Agent（全量注入） |
|------|----------------------|----------------------|
| Skill 数量 | 可支持数百个（实际 >200 个 built-in） | 通常 <20 个（上下文限制） |
| 上下文膨胀 | 线性可控（仅活跃 Skill 展开） | 随 Skill 数量指数增长 |
| 响应延迟 | 低（只需加载相关 Skill） | 高（每轮处理大量无关规则） |
| 冲突概率 | 低（按需加载减少交叉） | 高（全部规则同时存在） |
| 用户自定义 | 高（User Skill 优先覆盖） | 中（需修改系统配置） |

### 10.3 实际效果

Kimi 实际部署了 **200+ 个 built-in skills**（见 `/app/.agents/skills/` 目录），但单个对话会话通常只加载 1-3 个相关 Skill。这种设计使得大规模 Skill 库成为可能，而不受上下文窗口限制。

---

## 11. 架构优势

1. **Tool 原子化程度高**：29 个 Tool 职责单一、边界清晰，便于组合和故障定位
2. **Skill-Tool 分离**：工作流（Skill）与原子能力（Tool）解耦，新增工作流无需新增 Tool
3. **技术路线锁定**：Artifact Skill 强制特定技术栈，保证交付物质量一致性
4. **渐进加载**：三级加载机制支持数百 Skill 而不膨胀上下文
5. **User Skill 优先**：用户可无缝覆盖系统默认行为，扩展性极强
6. **状态化浏览器**：连续操作共享 session，支持复杂的网页交互任务
7. **统一交付协议**：KIMI_REF 格式统一了所有 Artifact 的引用方式
8. **部署分离**：纯前端/全栈的部署策略分离，安全性与便利性兼顾
9. **强制验证链**：xlsx 的 recheck→reference-check→validate 链保证了交付物质量
10. **数据源抽象**：描述与调用分离，新增数据源无需修改 Tool schema

---

## 12. 架构不足

1. **Tool schema 全量注入**：29 个 Tool 的完整 schema 每轮全部注入，无动态筛选机制，长对话后期有上下文压力
2. **无 Tool 间依赖注入**：Skill 需手动编排 Tool 调用顺序，无法声明式定义依赖图
3. **Skill 无版本管理**：`website_version_manager` 仅管理 website 项目，不管理 Skill 本身版本
4. **数据源强耦合供应商**：ifind/tianyancha 等是具体供应商，无通用 DataSource 抽象层便于替换
5. **浏览器工具无等待机制**：需手动 `scroll`/`find` 等待动态内容，无显式 wait-for-element 能力
6. **Todo 无持久化**：`todo_read`/`todo_write` 仅限当前会话，跨会话丢失
7. **无显式缓存机制**：`web_search` 结果、`read_file` 内容无跨调用缓存，重复读取浪费资源
8. **Skill 冲突解决较粗糙**：仅"Artifact Skill 优先"一条规则，复杂冲突场景可能不够

---

## 13. 可迁移到 VonishAgent 的设计模式（12 项）

### 模式 1：Skill 文件化

- **设计说明**：将领域工作流封装为自包含的 `SKILL.md` 文件，置于 `skills/<name>/` 目录
- **解决的问题**：避免通用 Agent 的"万能提示词"膨胀，让特定领域的知识按需加载
- **Kimi 体现**：7 个核心 Skill + 200+ 扩展 Skill，每个都有独立的 SKILL.md
- **VonishAgent 借鉴**：实现 `skills/<name>/SKILL.md` 目录结构，YAML frontmatter 定义触发条件
- **优先级**：P0

### 模式 2：Skill 按需加载（三级渐进）

- **设计说明**：Metadata 常驻 → SKILL.md 触发后加载 → Bundled Resources 按需读取
- **解决的问题**：上下文窗口有限，无法全量注入所有 Skill
- **Kimi 体现**：支持 200+ Skill，单会话通常只加载 1-3 个
- **VonishAgent 借鉴**：实现 Skill 路由层，根据用户意图匹配并加载相关 Skill
- **优先级**：P0

### 模式 3：Tool 与 Skill 分离

- **设计说明**：Tool = 原子能力（如 `browser_click`）；Skill = 工作流手册（如 `deep-research` 编排搜索）
- **解决的问题**：避免为每个工作流创建新 Tool，保持 Tool 层稳定
- **Kimi 体现**：29 个 Tool 支撑 200+ Skill 的无限组合
- **VonishAgent 借鉴**：先构建稳定的 Tool 层（10-30 个原子 Tool），所有工作流在 Skill 层编排
- **优先级**：P0

### 模式 4：Artifact Skill 技术路线锁定

- **设计说明**：每个 Artifact 类型强制使用特定技术栈，禁止绕过
- **解决的问题**：保证交付物质量一致性，避免"用最熟悉工具凑合"导致的质量波动
- **Kimi 体现**：docx → C#/OpenXML，xlsx → Python+openpyxl，pptx → PPTD DSL
- **VonishAgent 借鉴**：为每个 Artifact 类型选定最佳技术栈，在 Skill 中强制约束
- **优先级**：P1

### 模式 5：User Skill 优先覆盖 Built-in

- **设计说明**：用户自定义 Skill 在加载优先级上高于系统内置 Skill
- **解决的问题**：允许用户自定义行为而不修改系统核心
- **Kimi 体现**：`/app/.user/skills/` 优先于 `/app/.agents/skills/`
- **VonishAgent 借鉴**：实现 Skill 加载的双层查找（user → built-in），同名 Skill 用户优先
- **优先级**：P1

### 模式 6：浏览器自动化状态化

- **设计说明**：浏览器操作共享 session，通过 citation_id 维持状态链
- **解决的问题**：支持复杂的连续网页交互（登录 → 导航 → 操作 → 提取）
- **Kimi 体现**：`visit` → `click` → `input` → `scroll` 共享 page 状态
- **VonishAgent 借鉴**：为 web_fetch 工具组设计 session 机制，支持连续操作
- **优先级**：P1

### 模式 7：read_file 自动文档转换

- **设计说明**：单一 `read_file` 工具自动识别格式并转换为统一表征（Markdown）
- **解决的问题**：无需为每种文件格式维护独立的读取 Tool
- **Kimi 体现**：Office/PDF → Markdown，图片 → 显示，视频 → 播放
- **VonishAgent 借鉴**：统一文件读取接口，后端自动做格式识别和转换
- **优先级**：P2

### 模式 8：KIMI_REF 文件交付协议

- **设计说明**：统一的文件引用标记格式，前端解析后提供下载/预览
- **解决的问题**：Agent 与前端之间的文件交付标准化
- **Kimi 体现**：`<KIMI_REF type="file" path="sandbox://..." />`
- **VonishAgent 借鉴**：设计类似的文件引用标记，让前端知道哪些输出是文件
- **优先级**：P2

### 模式 9：部署与版本管理分离

- **设计说明**：纯前端自动部署（URL 立即可访问），全栈仅保存快照（需手动发布）
- **解决的问题**：全栈应用涉及敏感配置，不应自动公开
- **Kimi 体现**：`deploy_website` vs `website_version_manager`
- **VonishAgent 借鉴**：根据项目类型选择部署策略，全栈项目增加确认环节
- **优先级**：P2

### 模式 10：Todo 作为任务状态

- **设计说明**：显式的 todo 工具维护当前任务状态，支持 pending/in_progress/completed + 优先级
- **解决的问题**：长任务的中断恢复、多步骤进度追踪
- **Kimi 体现**：`todo_read`/`todo_write` 在长时间任务中频繁调用
- **VonishAgent 借鉴**：实现任务状态工具，让 Agent 显式管理多步骤任务进度
- **优先级**：P2

### 模式 11：数据源描述与调用分离

- **设计说明**：先通过描述工具发现 API，再通过调用工具执行，参数动态传入
- **解决的问题**：新增数据源无需修改 Tool schema
- **Kimi 体现**：`get_data_source_desc` → `get_data_source`
- **VonishAgent 借鉴**：统一数据源网关，描述和调用分离开
- **优先级**：P3

### 模式 12：多模态生成统一 Artifact 化

- **设计说明**：图片/视频/音频/文档的生成工具都输出文件并通过统一协议交付
- **解决的问题**：多模态输出的标准化管理
- **Kimi 体现**：所有 generate_* 工具 + read_file/write_file 都产出 KIMI_REF
- **VonishAgent 借鉴**：所有生成类工具统一输出文件引用，前端统一渲染
- **优先级**：P3

---

## 14. VonishAgent 推荐改造路线

### P0（立即实施）

| 改造项 | 具体行动 |
|--------|----------|
| Skill 目录结构 | 创建 `skills/<name>/SKILL.md` 规范，YAML frontmatter + Markdown body |
| Skill 按需加载 | 实现 Skill 路由层：意图识别 → Skill 匹配 → SKILL.md 加载 |
| Tool-Skill 分离 | 定义 10-30 个原子 Tool，所有工作流在 Skill 层用自然语言 + Tool 调用来编排 |
| 文件交付协议 | 定义 VonishAgent 的文件引用标记格式（类似 KIMI_REF） |

### P1（短期）

| 改造项 | 具体行动 |
|--------|----------|
| Artifact 技术锁定 | 为 docx/xlsx/pdf/pptx 分别选定并锁定技术栈 |
| User Skill 优先 | 实现用户 Skill 目录，加载时优先查找用户层 |
| 浏览器状态化 | 为网页抓取工具组设计 session 和 citation_id 机制 |
| 数据源抽象 | 设计统一数据源网关，支持描述-调用分离 |

### P2（中期）

| 改造项 | 具体行动 |
|--------|----------|
| 自动文档转换 | read_file 工具支持 Office/PDF 自动转 Markdown |
| 部署策略分离 | 纯前端自动部署 vs 全栈快照管理 |
| Todo 状态工具 | 实现任务管理工具，支持长任务状态维护 |
| 验证链 | 为关键 Artifact 类型（如 Excel）添加强制验证步骤 |

### P3（长期）

| 改造项 | 具体行动 |
|--------|----------|
| Tool schema 动态筛选 | 根据当前 Skill 只注入相关 Tool schema，减少上下文压力 |
| Skill 版本管理 | 为 Skill 添加版本控制，支持回滚 |
| 跨调用缓存 | web_search 结果、文件内容添加缓存层 |
| 复杂冲突解决 | 设计更精细的 Skill 冲突解决规则 |

---

## 附录：完整 Tool 清单（29 个）

| # | Tool 名称 | 分类 |
|---|-----------|------|
| 1 | `mshtools-browser_visit` | 浏览器自动化 |
| 2 | `mshtools-browser_click` | 浏览器自动化 |
| 3 | `mshtools-browser_input` | 浏览器自动化 |
| 4 | `mshtools-browser_scroll_down` | 浏览器自动化 |
| 5 | `mshtools-browser_scroll_up` | 浏览器自动化 |
| 6 | `mshtools-browser_find` | 浏览器自动化 |
| 7 | `mshtools-browser_screenshot` | 浏览器自动化 |
| 8 | `mshtools-screenshot_web_full_page` | 浏览器自动化 |
| 9 | `mshtools-web_search` | 搜索 |
| 10 | `mshtools-search_image_by_text` | 搜索 |
| 11 | `mshtools-search_image_by_image` | 搜索 |
| 12 | `mshtools-get_data_source_desc` | 数据源 |
| 13 | `mshtools-get_data_source` | 数据源 |
| 14 | `mshtools-generate_image` | 内容生成 |
| 15 | `mshtools-generate_video` | 内容生成 |
| 16 | `mshtools-generate_speech` | 内容生成 |
| 17 | `mshtools-generate_sound_effects` | 内容生成 |
| 18 | `mshtools-get_available_voices` | 内容生成 |
| 19 | `mshtools-find_asset_bbox` | 图像资产 |
| 20 | `mshtools-crop_and_replicate_assets_in_image` | 图像资产 |
| 21 | `mshtools-ipython` | 代码执行 |
| 22 | `mshtools-read_file` | 文件读写 |
| 23 | `mshtools-edit_file` | 文件读写 |
| 24 | `mshtools-write_file` | 文件读写 |
| 25 | `mshtools-shell` | 命令执行 |
| 26 | `mshtools-deploy_website` | 部署 |
| 27 | `mshtools-website_version_manager` | 部署 |
| 28 | `mshtools-todo_read` | 任务管理 |
| 29 | `mshtools-todo_write` | 任务管理 |

---

*报告结束。本报告基于对 Kimi Agent 当前 system prompt、skill 文件和 tool schema 的完整分析，所有结论均有具体证据支撑。*
