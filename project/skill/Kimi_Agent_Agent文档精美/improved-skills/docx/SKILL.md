# DOCX Skill — VonishAgent Artifact Engine

## 路由

| 路径 | 触发条件 | 读取文件 |
|------|----------|----------|
| WIR | 存在目标.docx且格式重要 | `references/wir-reference.md` |
| md2docx | 子代理返回.md需转换 | `references/md2docx-reference.md` |
| Create | 其他情况 | `references/openxml-sdk-reference.md` |

`.doc`格式先转换：`libreoffice --headless --convert-to docx`

## 执行

读取 `procedure.yaml` 获取完整步骤图。
读取 `design_tokens.yaml` 获取配色/字体/间距令牌。
读取 `validators.yaml` 了解验证门槛。
读取 `recovery.yaml` 了解错误修复。

### 快速执行流程

```
S1: 读取Artifact Plan → S2: 读取Design Tokens → S3: 生成封面背景
→ S4: 编写C#代码 → S5: 编译(build) → S6: 视觉验收 → S7: 交付
```

构建命令：`./scripts/docx build`

### 优先级速查

| 级别 | 规则示例 | 不通过时 |
|------|----------|----------|
| P0 | RunFonts必须是第一个子元素；表格宽度匹配；无占位符 | **禁止交付** |
| P1 | 输出.docx；内容符合Plan；语言一致 | 向用户说明 |
| P2 | 封面有背景；配色用预设；页眉页脚完整 | 建议修复 |
| P3 | 首行缩进；交替行颜色 | 不阻塞 |

### 精美度检查清单

- [ ] 封面有独特背景（渐变/几何/模糊）
- [ ] 三级颜色层级清晰（标题/正文/注释）
- [ ] 表格使用三线表或自定义表头
- [ ] 页眉页脚完整，页码正确
- [ ] 中文正文首行缩进2字符
- [ ] 无占位符文本

## 文件树

```
docx/
├── SKILL.md              # 本文件（路由+快速参考）
├── procedure.yaml        # 完整执行步骤图
├── validators.yaml       # P0-P3验证门槛
├── recovery.yaml         # 错误恢复手册
├── design_tokens.yaml    # 配色/字体/间距令牌
└── references/           # 详细参考（按需读取）
    ├── openxml-sdk-reference.md
    ├── wir-reference.md
    └── md2docx-reference.md
```
