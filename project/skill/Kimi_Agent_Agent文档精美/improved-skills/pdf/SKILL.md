# PDF Skill — VonishAgent Artifact Engine

## 路由

| 路由 | 触发条件 | 读取文件 |
|------|----------|----------|
| HTML | 默认（所有PDF创建） | `routes/html.md` |
| LaTeX | 用户明确要求LaTeX/.tex | `routes/latex.md` |
| Process | 处理现有PDF（合并/提取等） | `routes/process.md` |

**默认走HTML路由**。先读对应route文件再写代码。

## 执行

读取 `procedure.yaml` 获取完整步骤图。
读取 `design_tokens.yaml` 获取配色/CSS变量。

### 快速执行流程

```
S1: 读取Artifact Plan → S2: 读取Design Tokens → S3: 读取HTML路由参考
→ S4: 编写HTML → S5: CSS Counter审计 → S6: Mermaid高度检查
→ S7: 转换为PDF → S8: 视觉验收 → S9: 交付
```

转换命令：`./scripts/pdf.sh html input.html --output output.pdf`

### 绝对红线（P0）

| 规则 | 违反后果 |
|------|----------|
| 禁止CSS Counter | Paged.js重排导致编号归零 |
| body{ margin:0 } + @page:first{ margin:0 } + .cover{ margin:0 } | 封面有白边 |
| Mermaid图表≤8节点 | 分页破坏 |
| 使用data-*属性编号 | 编号不连续 |

### 优先级速查

| 级别 | 规则示例 | 不通过时 |
|------|----------|----------|
| P0 | 无CSS Counter；Mermaid≤8节点；文件可生成 | **禁止交付** |
| P1 | 输出.pdf；内容完整；语言一致 | 向用户说明 |
| P2 | 封面占满；三线表规范；页眉页脚 | 建议修复 |
| P3 | 封面风格匹配；字体加载优化 | 不阻塞 |

### 精美度检查清单

- [ ] 封面占满整页（三重零边距）
- [ ] 正文11pt，行高1.7
- [ ] 三线表（顶粗底粗头细）
- [ ] 页眉页脚完整
- [ ] 无编号异常（data-*属性）
- [ ] Mermaid图表≤8节点

## 文件树

```
pdf/
├── SKILL.md              # 本文件
├── procedure.yaml        # 完整步骤图
├── validators.yaml       # P0-P3验证门槛
├── recovery.yaml         # 错误恢复手册
├── design_tokens.yaml    # 配色/CSS变量
└── routes/
    ├── html.md           # HTML路由（默认）
    ├── latex.md          # LaTeX路由
    └── process.md        # Process路由
```
