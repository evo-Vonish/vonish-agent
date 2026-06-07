# Context Recall 上下文召回机制

## 设计哲学

复杂文档生成通常是长链条：
```
搜索资料 → 读取文件 → 提取证据 → 生成表格 → 生成图表 → 写报告 → 做PPT → 验证 → 修改
```

如果tool_result被压缩，Agent到写报告阶段时容易丢失证据。

**召回机制**确保：在关键节点前，Agent必须主动召回相关上下文。

---

## 召回检查点（Recall Checkpoints）

### CP1: 生成前召回（Before Generation）

**触发**: 任何格式开始创建文件前

```yaml
recall_checkpoint_1:
  name: "生成前召回"
  trigger: "before_any_generation"
  
  must_recall:
    - item: "user_original_request"
      why: "确保不偏离用户最初需求"
      action: "重新阅读用户第一条消息"
      
    - item: "artifact_plan"
      why: "确保按Plan执行，不遗漏section"
      action: "重新阅读artifact_plan.yaml"
      
    - item: "visual_profile"
      why: "确保配色/布局不临时改变"
      action: "重新阅读design_tokens.yaml"
```

### CP2: 内容写作召回（Before Content Writing）

**触发**: 写入正文内容前

```yaml
recall_checkpoint_2:
  name: "内容写作召回"
  trigger: "before_content_writing"
  
  must_recall:
    - item: "research_findings"
      why: "确保数据准确、不编造"
      action: "召回搜索和研究的tool_result"
      
    - item: "data_sources"
      why: "确保来源引用完整"
      action: "检查是否有Source Name和Source URL"
      
    - item: "user_uploaded_files"
      why: "确保用户素材已使用"
      action: "确认所有上传文件已读取"
```

### CP3: 图表生成召回（Before Chart Generation）

**触发**: 生成图表/数据可视化前

```yaml
recall_checkpoint_3:
  name: "图表生成召回"
  trigger: "before_chart_generation"
  
  must_recall:
    - item: "raw_data"
      why: "确保图表数据准确"
      action: "召回数据源tool_result或原始数据"
      
    - item: "units_and_scales"
      why: "确保轴标签单位正确"
      action: "检查数据单位（万/亿/%/元）"
      
    - item: "chart_type_preferences"
      why: "确保图表类型匹配数据"
      action: "根据数据特征选图表（趋势→折线，对比→柱状）"
```

### CP4: 格式转换召回（Before Format Conversion）

**触发**: 从一个格式转换到另一个格式前

```yaml
recall_checkpoint_4:
  name: "格式转换召回"
  trigger: "before_format_conversion"
  
  must_recall:
    - item: "source_artifact_content"
      why: "确保转换内容完整"
      action: "重新阅读源文件的全部内容"
      
    - item: "target_format_constraints"
      why: "确保符合目标格式限制"
      action: "阅读目标格式的validators.yaml"
      
    - item: "visual_consistency"
      why: "确保跨格式视觉一致"
      action: "对照artifact_plan的visual部分"
```

### CP5: 交付前召回（Before Delivery）

**触发**: 最终交付前

```yaml
recall_checkpoint_5:
  name: "交付前召回"
  trigger: "before_delivery"
  
  must_recall:
    - item: "original_request"
      why: "最后一次确认需求满足"
      action: "对照用户最初需求逐项检查"
      
    - item: "artifact_plan"
      why: "确认所有required输出已生成"
      action: "检查plan中required=true的格式是否都有"
      
    - item: "validation_results"
      why: "确认所有验证已通过"
      action: "检查P0/P1验证结果"
      
    - item: "placeholder_scan"
      why: "确认无占位符残留"
      action: "扫描所有文件中的[TODO]、[Company Name]等"
```

---

## 召回执行协议

### 协议1: 显式声明

每次到达召回检查点时，Agent必须**显式声明**正在执行召回：

```
[Recall CP3] 正在执行图表生成召回...
- ✓ 召回 raw_data: 数据来源已确认
- ✓ 召回 units: 单位为"亿元"
- ✓ 召回 chart_type: 时间序列数据 → 折线图
```

### 协议2: 缺失处理

如果某项上下文无法召回：

| 严重程度 | 处理方式 |
|----------|----------|
| 核心数据缺失 | 暂停生成，重新搜索/询问用户 |
| 来源信息缺失 | 标注"来源待补充"，继续生成 |
| 格式细节缺失 | 使用默认值，在交付说明中注明 |

### 协议3: 压缩保护

当tool_result被压缩时，使用**关键信息提取**模式：

```
tool_result被压缩 → 
  1. 提取关键数据点（数字、百分比、日期）
  2. 提取来源信息（作者、机构、URL）
  3. 提取结论性语句
  4. 将提取结果写入临时摘要文件
  5. 后续步骤读取摘要文件而非原始tool_result
```

---

## 格式特定召回规则

### DOCX

| 召回时机 | 召回内容 | 原因 |
|----------|----------|------|
| 写封面时 | artifact_plan.project.title | 确保标题完全一致 |
| 写表格时 | 数据来源和数值 | 防止数据错误 |
| 插入图片时 | 图片路径和尺寸 | 防止图片缺失或变形 |
| 最终验证时 | P0验证清单 | 确保无致命错误 |

### XLSX

| 召回时机 | 召回内容 | 原因 |
|----------|----------|------|
| 写公式时 | 上游数据位置 | 防止#REF!错误 |
| 创建图表时 | 数据范围和单位 | 防止空图表或错误轴 |
| 设置条件格式时 | 阈值定义 | 防止格式不触发 |
| 最终验证时 | recheck + reference-check结果 | 确保0 errors |

### PDF

| 召回时机 | 召回内容 | 原因 |
|----------|----------|------|
| 写CSS时 | design_tokens配色 | 防止颜色不一致 |
| 插入图表时 | Mermaid节点数 | 防止分页破坏 |
| 设置编号时 | data-*属性值 | 防止CSS Counter异常 |
| 最终验证时 | 分页检查结果 | 确保无内容截断 |

### PPTX

| 召回时机 | 召回内容 | 原因 |
|----------|----------|------|
| 写outline时 | artifact_plan.sections | 确保不遗漏section |
| 写design.md时 | visual_profile | 确保配色一致 |
| 生成.page时 | 数据点和高亮项 | 确保数据准确 |
| 最终验证时 | check.sh结果 | 确保0 errors 0 warnings |

---

## 召回失败保护

如果召回机制本身失败（无法读取文件、上下文丢失）：

```
1. 降级模式: 使用默认值继续
   - 配色 → corporate（最安全）
   - 布局 → 标准网格
   - 字体 → MiSans + Inter
   
2. 标记风险: 在交付说明中注明
   "⚠️ 部分上下文召回失败，使用默认配置"
   
3. 建议用户: 如果结果不理想，提供调整方向
   "如需调整配色/布局，请告知具体要求"
```
