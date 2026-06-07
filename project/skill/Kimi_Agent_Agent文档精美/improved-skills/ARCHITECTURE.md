# VonishAgent Artifact Engine v2 — 架构文档

## 设计哲学

从"工艺法典"进化为"工厂流水线"。

不是给模型看长教程，而是让它：
- **会路由** — Skill Router选择技能
- **会召回** — Context Recall防止失忆
- **会执行** — Procedure Graph驱动步骤
- **会验收** — Validation Gate分层验证
- **会修错** — Recovery Playbook自动修复
- **会审美** — Visual Review视觉审判

---

## 系统架构

```
用户请求
  │
  ▼
┌─────────────────────────────────────┐
│  Skill Router                       │
│  根据触发词选择 docx/xlsx/pdf/pptx  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Artifact Plan Generator            │
│  统一元模型（格式/受众/风格/内容）   │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Format Skill Engine                │
│  ┌─────────┬─────────┬──────────┐  │
│  │  DOCX   │  XLSX   │   PDF    │  │
│  │ Engine  │ Engine  │ Engine   │  │
│  └─────────┴─────────┴──────────┘  │
│  ┌───────────────────────────────┐  │
│  │         PPTX Engine            │  │
│  └───────────────────────────────┘  │
└──────────────┬──────────────────────┘
               │
        ┌──────┴──────┐
        ▼             ▼
┌──────────────┐ ┌──────────────┐
│  Validation  │ │   Visual     │
│    Gates     │ │   Review     │
│  (P0-P3)     │ │              │
└──────┬───────┘ └──────┬───────┘
       │                │
       └────────┬───────┘
                ▼
┌─────────────────────────────────────┐
│  Recovery Playbook                  │
│  P0自动修复 / P1警告用户 / P2建议   │
└─────────────────────────────────────┘
```

---

## 核心组件

### 1. Skill Router

```
docx → C# + OpenXML SDK
xlsx → Python + openpyxl
pdf  → HTML + Paged.js（默认）
pptx → PPTD中间格式
```

每个Skill独立，通过统一的Artifact Plan协调。

### 2. Artifact Plan

跨格式的统一元模型。用户说"给我一套报告+PPT+表格"时，
Artifact Plan确保三份东西不各唱各的调。

关键字段：
- `outputs` — 输出格式清单（含优先级）
- `content.sections` — 内容大纲（标注输出格式）
- `visual` — 配色/密度/封面风格
- `validation` — 验证要求

### 3. Procedure Graph

每个Skill的 `procedure.yaml` 定义机器可执行步骤：

```yaml
steps:
  - id: "S1"
    name: "步骤名"
    action: "动作"
    tool: "工具"
    validation_gate: "VG1"  # 关联验证门
    recall_checkpoint: "CP1" # 关联召回点
```

### 4. Priority System (P0-P3)

| 级别 | 名称 | 不通过时 | 示例 |
|------|------|----------|------|
| P0 | Safety Gate | **禁止交付** | 文件打不开/公式错误 |
| P1 | User Contract | 向用户说明 | 格式不对/缺少section |
| P2 | Quality Standard | 建议修复 | 无封面/配色非预设 |
| P3 | Style Preference | 不阻塞 | 字间距/交替行 |

### 5. Validation Gates

每个Skill的 `validators.yaml` 定义：
- 验证项列表（id/name/check/tool/fail_action）
- 执行策略（all_must_pass / min_pass_ratio）
- 验证门（组合多个验证项）

### 6. Recovery Playbook

每个Skill的 `recovery.yaml` 定义：
- 错误模式（error/cause/fix/prevention）
- 通用恢复模式（REGENERATE/CODE_FIX/CONTENT_FIX）
- 决策树（if P0 fail → stop; if P2 <80% → suggest）

### 7. Context Recall

5个检查点（CP1-CP5）：
- CP1: 生成前 — 召回用户需求和Plan
- CP2: 内容写作 — 召回研究数据
- CP3: 图表生成 — 召回原始数据和单位
- CP4: 格式转换 — 召回源内容和目标约束
- CP5: 交付前 — 召回原始请求和验证结果

### 8. Visual Review

技术验证通过后，进行视觉自检：
- 默认模板感检测
- 拥挤度检测
- 对比度检测
- 专业感检测
- AI典型问题快速修复

---

## 文件结构

```
improved-skills-v2/
├── shared/                          # 跨格式共享
│   ├── skill.json                   # Skill注册表
│   ├── PRIORITY_SYSTEM.md           # P0-P3优先级
│   ├── ARTIFACT_PLAN.md             # 跨格式计划规范
│   ├── VISUAL_REVIEW.md             # 视觉验收清单
│   ├── CONTEXT_RECALL.md            # 上下文召回机制
│   ├── examples/                    # 示例文件
│   └── references/                  # 详细参考（按需）
│
├── docx/                            # Word文档
│   ├── SKILL.md                     # 入口（精简<100行）
│   ├── procedure.yaml               # 步骤图
│   ├── validators.yaml              # 验证门槛
│   ├── recovery.yaml                # 错误恢复
│   └── design_tokens.yaml           # 视觉令牌
│
├── xlsx/                            # Excel表格
│   ├── SKILL.md
│   ├── procedure.yaml
│   ├── validators.yaml
│   ├── recovery.yaml
│   └── design_tokens.yaml
│
├── pdf/                             # PDF文档
│   ├── SKILL.md
│   ├── procedure.yaml
│   ├── validators.yaml
│   ├── recovery.yaml
│   └── design_tokens.yaml
│
└── pptx/                            # 演示文稿
    ├── SKILL.md
    ├── procedure.yaml
    ├── validators.yaml
    ├── recovery.yaml
    └── design_tokens.yaml
```

---

## 使用流程

### 单格式任务

```
用户: "创建一个销售报告Excel"
→ Skill Router选择xlsx
→ 读取xlsx/SKILL.md（路由+快速参考）
→ 读取xlsx/procedure.yaml（步骤图）
→ 读取xlsx/design_tokens.yaml（配色）
→ 执行Per-Sheet创建循环
→ 每层验证（recheck → reference-check → validate）
→ Visual Review
→ 交付
```

### 多格式任务

```
用户: "给我一套融资路演材料"
→ Skill Router识别多格式需求
→ 生成Artifact Plan（pptx+xlsx+docx）
→ 并行执行各Format Skill
  → pptx: 路演PPT
  → xlsx: 财务模型
  → docx: 详细报告
→ 所有格式共享同一Artifact Plan的visual和content
→ 统一Visual Review
→ 套装交付
```

---

## 从v1到v2的变化

| 维度 | v1 | v2 |
|------|-----|-----|
| 架构 | 超长prompt教程 | 可执行工作流脚本 |
| Skill.md | 500+行完整规则 | <100行入口+引用YAML |
| 规则组织 | 自然语言MUST/CRITICAL | P0-P3分层 |
| 验证 | 文末检查清单 | 验证门+自动修复 |
| 视觉 | 设计规则多 | 设计规则+视觉验收 |
| 跨格式 | 建议统一 | Artifact Plan强制统一 |
| 上下文 | 无保护 | 5个召回检查点 |
| 执行 | 线性读取 | Procedure Graph驱动 |
