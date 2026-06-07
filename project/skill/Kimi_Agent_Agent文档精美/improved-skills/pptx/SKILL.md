# PPTX Skill — VonishAgent Artifact Engine

## 定义

使用PPTD中间格式（YAML语法）生成演示文稿，禁止直接操作.pptx。
用户在前端预览.pptd，点击"Export"转为.pptx。

## 路由

| 模式 | 触发条件 | 读取文件 |
|------|----------|----------|
| Creative | 默认（无参考PPT） | `guideline/design/creative_mode.md` + `design_tokens.yaml`的profile |
| Reference | 用户上传参考PPT | `guideline/design/reference_mode.md` |
| Template | 用户提供模板 | `guideline/design/template_mode.md` |

## 执行

读取 `procedure.yaml` 获取完整步骤图。
读取 `design_tokens.yaml` 获取配色/布局模式/内容规则。

### 快速执行流程

```
S1: 读取Artifact Plan → S2: 读取Design Tokens → S3: 选择Profile
→ S4: 创建Outline → S5: 创建Design → S6: 生成.page文件（并行）
→ S7: 创建.pptd → S8: 运行check.sh → S9: 修复问题 → S10: 视觉验收 → S11: 交付
```

检查命令：`scripts/check.sh presentation.pptd`

### 布局模式速查

| 模式 | 用途 | 结构 |
|------|------|------|
| 宫格亮点 | 核心卖点 | 3×2卡片 |
| 双图表 | 数据对比 | 左右并列 |
| 对比流程 | 竞争分析 | 箭头+表格 |
| 战略支柱 | 公司定位 | 标签+要点 |
| 三栏矩阵 | 优势展示 | 三列+图标 |
| 上下对比 | 技术差异 | 流程+标注 |
| 图片网格 | 产品展示 | 三栏图片 |
| 总结横幅 | 结论强调 | 底部全宽 |

### 优先级速查

| 级别 | 规则示例 | 不通过时 |
|------|----------|----------|
| P0 | check.sh 0 errors；无溢出/遮挡；正文≥18px | **禁止交付** |
| P1 | 输出.pptd；所有section有page；字体在允许列表 | 向用户说明 |
| P2 | 无AI配色；封面有冲击力；字号差异≥8px | 建议修复 |
| P3 | 目录非列表；正文≤50汉字 | 不阻塞 |

### 精美度检查清单

- [ ] check.sh: 0 errors, 0 warnings
- [ ] 无AI典型配色（紫/渐变紫蓝）
- [ ] 封面有"第一眼震撼"
- [ ] 标题与正文字号差异显著
- [ ] 一页一个核心信息
- [ ] 每页3-6个高亮数据点

## 文件树

```
pptx/
├── SKILL.md              # 本文件
├── procedure.yaml        # 完整步骤图
├── validators.yaml       # P0-P3验证门槛
├── recovery.yaml         # 错误恢复手册
├── design_tokens.yaml    # 配色/布局模式/内容规则
└── guideline/
    ├── generate_slides.md
    ├── edit_user_slides.md
    └── design/
        ├── creative_mode.md
        ├── reference_mode.md
        └── profiles/       # 场景档案
```
