# VonishAgent Artifact Engine 落地说明书

## 一、这是什么

一套让 Agent 稳定产出精美文档的工作流系统。覆盖 DOCX / XLSX / PDF / PPTX 四种格式。

核心能力：**路由 → 规划 → 执行 → 验证 → 修复 → 交付**

---

## 二、文件清单（26个文件）

```
improved-skills-v2/
├── ARCHITECTURE.md              # 系统架构文档（按需阅读）
│
├── shared/                      # 跨格式共享层（所有Skill共用）
│   ├── skill.json               # Skill注册表（Router读取）
│   ├── PRIORITY_SYSTEM.md       # P0-P3规则优先级
│   ├── ARTIFACT_PLAN.md         # 跨格式统一计划规范
│   ├── VISUAL_REVIEW.md         # 视觉验收清单
│   └── CONTEXT_RECALL.md        # 上下文召回机制
│
├── docx/                        # Word 文档
│   ├── SKILL.md                 # 入口文件（Agent先读这个）
│   ├── procedure.yaml           # 执行步骤图
│   ├── validators.yaml          # 验证门槛（P0-P3）
│   ├── recovery.yaml            # 错误恢复手册
│   └── design_tokens.yaml       # 配色/字体/间距令牌
│
├── xlsx/                        # Excel 表格（结构同docx）
│   ├── SKILL.md
│   ├── procedure.yaml
│   ├── validators.yaml
│   ├── recovery.yaml
│   └── design_tokens.yaml
│
├── pdf/                         # PDF 文档（结构同docx）
│   ├── SKILL.md
│   ├── procedure.yaml
│   ├── validators.yaml
│   ├── recovery.yaml
│   └── design_tokens.yaml
│
└── pptx/                        # PPT 演示文稿（结构同docx）
    ├── SKILL.md
    ├── procedure.yaml
    ├── validators.yaml
    ├── recovery.yaml
    └── design_tokens.yaml
```

### 每个文件是干什么的

| 文件 | 给谁看 | 什么时候读 |
|------|--------|-----------|
| `SKILL.md` | Agent | Skill触发时第一时间读 |
| `procedure.yaml` | Agent | 需要知道执行步骤时 |
| `validators.yaml` | Agent | 验证阶段 |
| `recovery.yaml` | Agent | 出错时 |
| `design_tokens.yaml` | Agent | 设计阶段 |
| `PRIORITY_SYSTEM.md` | 开发者 | 集成时配置 |
| `ARTIFACT_PLAN.md` | Agent | 多格式任务时 |
| `VISUAL_REVIEW.md` | Agent | 交付前验收 |
| `CONTEXT_RECALL.md` | 开发者 | 集成Recall机制时 |
| `skill.json` | Router | 路由决策时 |

---

## 三、集成步骤

### Step 1: 接入 Skill Router

把 `skill.json` 注册到 VonishAgent 的 Skill Registry：

```json
{
  "skill": "docx",
  "trigger": ["Word", "docx", "文档", "报告"],
  "entry": "improved-skills-v2/docx/SKILL.md",
  "priority": 1
}
```

四个 Skill 各自独立注册，互不影响。

### Step 2: 配置 Priority System

把 `PRIORITY_SYSTEM.md` 的核心逻辑接入 Agent 的决策层：

```python
# 伪代码：交付前检查
def can_deliver(validation_results):
    # P0: 全部通过
    if not all_p0_passed(validation_results):
        return False, "P0未通过，禁止交付"
    
    # P1: 全部通过
    if not all_p1_passed(validation_results):
        return True, "P1未通过，需向用户说明"
    
    # P2: 80%通过
    p2_ratio = p2_passed / p2_total
    if p2_ratio < 0.8:
        return True, f"P2通过率{p2_ratio}，建议改进"
    
    # P3: 不阻塞
    return True, "交付通过"
```

### Step 3: 接入 Artifact Plan（多格式任务必需）

当用户请求涉及多个格式时，先执行 Plan 生成：

```
用户: "给我一套融资路演材料"
→ 检测多格式关键词（"一套" / "套装" / "PPT+表格"）
→ 读取 ARTIFACT_PLAN.md
→ 生成统一计划（pptx + xlsx + docx）
→ 各 Skill 按 Plan 执行
```

### Step 4: 接入 Context Recall

在 Agent 的关键决策点插入召回检查：

| 检查点 | 插入位置 | 召回内容 |
|--------|----------|----------|
| CP1 | 任何Skill的S1步骤前 | 用户需求 + Artifact Plan |
| CP2 | 写入正文内容前 | 研究数据 + 来源引用 |
| CP3 | 生成图表前 | 原始数据 + 单位 |
| CP4 | 格式转换前 | 源内容 + 目标格式约束 |
| CP5 | 最终交付前 | 原始请求 + 验证结果 |

### Step 5: 接入 Visual Review

技术验证通过后，执行视觉验收：

```
validate通过
  → 读取 VISUAL_REVIEW.md
    → 执行通用检测（模板感/拥挤度/对比度/专业感）
      → 执行格式特定检测（各格式清单）
        → 全部通过 → 交付
        → 未通过 → 按 recovery.yaml 修复
```

---

## 四、Agent 执行时的读取顺序

### 单格式任务（如"创建一个Excel"）

```
1. Router 选择 xlsx Skill
2. 读取 xlsx/SKILL.md（<100行，快速加载）
3. SKILL.md 引用 procedure.yaml → 读取
4. SKILL.md 引用 design_tokens.yaml → 读取
5. 按 procedure.yaml 步骤执行
6. 执行到验证步骤 → 读取 validators.yaml
7. 出错 → 读取 recovery.yaml
8. 交付前 → 读取 VISUAL_REVIEW.md
```

### 多格式任务（如"给我一套报告"）

```
1. 检测多格式需求
2. 读取 shared/ARTIFACT_PLAN.md
3. 生成 Artifact Plan YAML
4. 并行启动各 Format Skill
5. 每个 Skill 按"单格式读取顺序"执行
6. 所有 Skill 完成后统一 Visual Review
7. 套装交付
```

---

## 五、Priority System 使用指南

### 规则冲突时怎么办

P0 > P1 > P2 > P3，高优先级覆盖低优先级。

```
场景: 用户说"简单做"，但P2要求封面有背景
→ "简单做"是P1用户契约
→ "封面有背景"是P2质量标准
→ P1 > P2，执行"简单做"，省略封面背景
→ 交付时注明: "已按您要求的简化风格生成"
```

### 各格式的P0红线

| 格式 | P0红线 | 违反后果 |
|------|--------|----------|
| DOCX | RunFonts不是第一个子元素 / 表格宽度不匹配 | 文件打不开 |
| XLSX | 公式错误(#VALUE!/#REF!) / Python预计算 | 打开即报错 |
| PDF | CSS Counter / Mermaid>8节点 | 编号归零/分页破坏 |
| PPTX | check.sh errors / 文字溢出遮挡 | 幻灯片损坏 |

---

## 六、Context Recall 接入方式

在 Agent 的系统提示中加入：

```
## Context Recall 规则

在以下节点必须执行显式召回：

[Recall CP1] 开始任何文件生成前
→ 召回: 用户原始请求、Artifact Plan

[Recall CP2] 写入正文内容前
→ 召回: 研究数据、来源引用

[Recall CP3] 生成图表前
→ 召回: 原始数据、单位、图表类型偏好

[Recall CP4] 格式转换前
→ 召回: 源内容、目标格式约束

[Recall CP5] 最终交付前
→ 召回: 原始请求、验证结果、扫描占位符

召回失败时:
- 核心数据缺失 → 暂停生成，重新搜索
- 来源信息缺失 → 标注"来源待补充"，继续
- 格式细节缺失 → 使用默认值，交付说明中注明
```

---

## 七、Visual Review 接入方式

在 Agent 的系统提示中加入：

```
## Visual Review 规则

技术验证通过后，执行视觉自检：

1. 默认模板感检测
   - 配色是否AI典型（紫/渐变紫蓝/纯蓝）
   - 是否像未修改的默认模板
   → 失败: 换 design_tokens.yaml 中的预设配色

2. 拥挤度检测
   - 页边距是否充足
   - 行距是否舒适
   → 失败: 增大边距20%或精简内容

3. 对比度检测
   - 文字与背景对比度
   - 标题与正文字号差异
   → 失败: 调整颜色或字号

4. 专业感检测
   - 对齐是否精准
   - 图表是否有解释力
   → 失败: 按 recovery.yaml 修复
```

---

## 八、实战示例

### 示例1: 用户说"做一个季度销售报告Excel"

```
1. Router → xlsx Skill
2. 读取 xlsx/SKILL.md
3. 读取 xlsx/procedure.yaml → 执行步骤
4. 读取 xlsx/design_tokens.yaml → 选corporate配色
5. 执行Per-Sheet循环:
   Sheet1 Cover: Plan → Write → Style → Save → Recheck → Fix
   Sheet2 Data:  Plan → Write → Style → Save → Recheck → Fix
   Sheet3 Charts: Plan → Write → Style → Save → Recheck → Chart-verify
6. 最终验证: ./scripts/Xlsx validate
7. Visual Review
8. 交付
```

### 示例2: 用户说"给我一套融资路演材料"

```
1. 检测多格式 → 读取 ARTIFACT_PLAN.md
2. 生成 Plan:
   outputs: [pptx(primary), xlsx(primary), docx(secondary)]
   visual: { palette: ocean, cover_style: hero }
3. 并行启动三个Skill，共享同一个Plan
4. pptx Skill: 读取pptx/SKILL.md → 按Plan生成路演PPT
5. xlsx Skill: 读取xlsx/SKILL.md → 按Plan生成财务模型
6. docx Skill: 读取docx/SKILL.md → 按Plan生成详细报告
7. 统一Visual Review
8. 套装交付
```

---

## 九、定制指南

### 添加新配色

编辑 `design_tokens.yaml`，在 palettes 下新增：

```yaml
my_brand:
  primary: "#1A237E"
  secondary: "#283593"
  accent: "#FF6F00"
  dark: "#0D47A1"
  light: "#90CAF9"
  border: "#E8EAF6"
  bg: "#F5F5F5"
```

### 添加新布局模式（PPTX）

编辑 `pptx/design_tokens.yaml`，在 layout_patterns 下新增：

```yaml
my_pattern:
  name: "我的模式"
  structure: "描述结构"
  use_for: "适用场景"
```

### 调整验证严格度

编辑 `validators.yaml` 的 execution_flow：

```yaml
P2_policy:
  min_pass_ratio: 0.6  # 从0.8降到0.6，更宽松
```

### 添加新的Context Recall检查点

编辑 `CONTEXT_RECALL.md`，在对应位置新增检查项。

---

## 十、文件交付

本次交付的所有文件位于：

```
/mnt/agents/output/improved-skills-v2/
```

共26个文件，直接复制到 VonishAgent 的 skills 目录即可使用。

**不需要额外依赖**。这套系统是纯配置（YAML + Markdown），不引入新的运行时或库。
