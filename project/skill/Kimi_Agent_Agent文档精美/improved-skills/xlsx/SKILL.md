# XLSX Skill — VonishAgent Artifact Engine

## 技术栈

- **创建**: Python + openpyxl/pandas（ipython工具）
- **验证**: `./scripts/Xlsx` CLI（shell工具）
- **PivotTable**: 专用工具，先读 `references/pivot-table.md`

## 执行

读取 `procedure.yaml` 获取完整步骤图（含Per-Sheet验证循环）。
读取 `design_tokens.yaml` 获取配色/布局令牌。

### 快速执行流程

```
S1: 读取Artifact Plan → S2: 读取Design Tokens → S3: 规划Sheets
→ S4: 逐Sheet创建（Plan→Write→Style→Save→Recheck→Fix循环）
→ S5: 创建图表 → S6: 最终验证 → S7: 视觉验收 → S8: 交付
```

### Per-Sheet验证（MANDATORY）

每个Sheet创建后立即：
```bash
./scripts/Xlsx recheck output.xlsx
./scripts/Xlsx reference-check output.xlsx
# 修复所有错误后才创建下一个Sheet
```

### 验证命令速查

| 命令 | 用途 | 何时运行 |
|------|------|----------|
| `recheck` | 检测公式错误 | 每Sheet后 |
| `reference-check` | 检测引用异常 | 每Sheet后 |
| `validate` | OpenXML结构验证 | 最终交付前 |
| `chart-verify` | 图表数据检查 | 有图表时 |

### 优先级速查

| 级别 | 规则示例 | 不通过时 |
|------|----------|----------|
| P0 | 无公式错误；无隐式数组；无Python预计算 | **禁止交付** |
| P1 | 输出.xlsx；内容符合Plan；外部数据有来源 | 向用户说明 |
| P2 | 隐藏网格线；从B2开始；表头深色+白字 | 建议修复 |
| P3 | 条件格式；完整封面页 | 不阻塞 |

### 精美度检查清单

- [ ] 网格线已隐藏
- [ ] 内容从B2开始
- [ ] 表头深色背景+白字
- [ ] 交替行颜色（白/#F9F9F9）
- [ ] 图表有标题和轴标签
- [ ] 外部数据有来源引用

## 文件树

```
xlsx/
├── SKILL.md              # 本文件
├── procedure.yaml        # 完整步骤图（含Per-Sheet循环）
├── validators.yaml       # P0-P3验证门槛
├── recovery.yaml         # 错误恢复手册
├── design_tokens.yaml    # 配色/布局令牌
└── references/
    ├── pivot-table.md
    └── 3_statement_model_skill.md
```
