# Artifact Plan 规范

## 设计哲学

用户说"给我一套报告+PPT+表格"时，三份东西不能各唱各的调。

Artifact Plan 是一个跨格式的**统一元模型**，在动手创建任何文件之前，先生成这个计划，
然后各格式的Skill只负责把计划翻译成各自的格式。

---

## 1. Artifact Plan 结构

```yaml
artifact_plan:
  version: "1.0"
  
  # === 项目元信息 ===
  project:
    title: "项目标题"
    description: "一句话描述"
    language: "zh"  # zh / en / mixed
    audience: "business"  # business / academic / investor / student / general
    
  # === 输出格式清单 ===
  outputs:
    - format: "docx"
      purpose: "详细报告全文"
      priority: "primary"  # primary / secondary / optional
      required: true
      
    - format: "pptx"
      purpose: "路演演示"
      priority: "primary"
      required: true
      
    - format: "xlsx"
      purpose: "数据表格与图表"
      priority: "secondary"
      required: false
      
  # === 内容大纲 ===
  content:
    title: "报告主标题"
    subtitle: "副标题"
    
    sections:
      - id: "executive_summary"
        title: "执行摘要"
        formats: ["docx", "pptx"]
        key_points: 3
        
      - id: "market_analysis"
        title: "市场分析"
        formats: ["docx", "pptx", "xlsx"]
        key_points: 5
        data_sources: ["行业报告", "公司财报"]
        
      - id: "financial_forecast"
        title: "财务预测"
        formats: ["docx", "pptx", "xlsx"]
        key_points: 4
        charts_required: ["bar", "line"]
        
  # === 视觉规范 ===
  visual:
    palette: "ocean"  # ocean/sunset/forest/berry/vibrant/corporate/pastel/earth
    density: "medium"  # low / medium / high
    cover_style: "swiss_grid"  # swiss_grid / hero / magazine / minimal
    
  # === 验证要求 ===
  validation:
    require_sources: true
    require_charts: true
    require_visual_review: true
    formula_audit: true  # xlsx特有
    
  # === 召回检查点 ===
  recall_checkpoints:
    - stage: "before_writing"
      items: ["user_requirements", "research_data", "outline"]
      
    - stage: "before_chart_generation"
      items: ["raw_data", "units", "chart_type_preferences"]
      
    - stage: "before_delivery"
      items: ["original_request", "artifact_plan", "validation_results"]
```

---

## 2. Artifact Plan 生成流程

```
用户请求
  → 解析需求（格式、受众、场景）
    → 选择visual profile（palette + density + cover_style）
      → 定义content sections（每section标注输出格式）
        → 生成完整Artifact Plan YAML
          → 用户确认（可选）
            → 各格式Skill按Plan执行
```

---

## 3. Format Skill 如何读取 Artifact Plan

每个格式的Skill在执行前必须：

1. **读取Artifact Plan**（如果存在）
2. **筛选自己的sections** — 只处理 `formats` 包含自己格式的section
3. **遵循visual规范** — 使用plan中定义的palette、cover_style
4. **在validation gate中检查** — 验证plan中require_xxx为true的项

### 读取示例（DOCX）

```
1. 读取 artifact_plan.yaml
2. 筛选 sections where formats contains "docx"
   → executive_summary, market_analysis, financial_forecast
3. 使用 visual.palette="ocean" 选择配色
4. 使用 visual.cover_style="swiss_grid" 设计封面
5. 为 market_analysis 和 financial_forecast 插入图表
6. 验证: require_sources=true → 确保有来源引用
7. 验证: require_charts=true → 确保图表已生成
```

### 读取示例（PPTX）

```
1. 读取 artifact_plan.yaml
2. 筛选 sections where formats contains "pptx"
   → executive_summary, market_analysis, financial_forecast
3. 使用 visual.density="medium" 控制信息密度
4. 每页一个section，图表优先于文字
5. 验证: require_visual_review=true → 截图检查
```

### 读取示例（XLSX）

```
1. 读取 artifact_plan.yaml
2. 筛选 sections where formats contains "xlsx"
   → market_analysis, financial_forecast
3. 创建对应数据表
4. 生成 charts_required: ["bar", "line"]
5. 验证: formula_audit=true → 运行recheck
6. 验证: require_sources=true → Sources工作表
```

---

## 4. 单格式任务的Artifact Plan

即使只生成一个格式，也建议生成简化的Artifact Plan：

```yaml
artifact_plan:
  version: "1.0"
  project:
    title: "月度销售报告"
    language: "zh"
    audience: "business"
  outputs:
    - format: "xlsx"
      purpose: "销售数据分析"
      priority: "primary"
      required: true
  content:
    title: "2025年6月销售报告"
    sections:
      - id: "sales_overview"
        title: "销售概览"
        formats: ["xlsx"]
        key_points: 3
  visual:
    palette: "corporate"
    density: "medium"
  validation:
    require_sources: false
    require_charts: true
    formula_audit: true
```

---

## 5. 跨格式一致性保障

当多个格式从同一个Artifact Plan生成时，确保一致性：

| 维度 | 一致性检查 |
|------|------------|
| 配色 | 所有格式使用同一palette |
| 标题 | DOCX/PPT/PDF标题完全一致 |
| 数据 | XLSX中的数据与DOCX/PPTX中的数据一致 |
| 来源 | 所有格式引用相同的来源 |
| 图表 | 同一数据在不同格式中图表类型一致 |

---

## 6. 快速生成模板

### 场景1: 融资路演套装

```yaml
project:
  title: "A轮融资路演"
  audience: "investor"
outputs:
  - { format: "pptx", priority: "primary", required: true }
  - { format: "xlsx", priority: "primary", required: true }
  - { format: "docx", priority: "secondary", required: false }
visual:
  palette: "ocean"
  density: "medium"
  cover_style: "hero"
validation:
  require_sources: true
  require_charts: true
  require_visual_review: true
```

### 场景2: 学术研究套装

```yaml
project:
  title: "论文研究报告"
  audience: "academic"
outputs:
  - { format: "docx", priority: "primary", required: true }
  - { format: "pdf", priority: "primary", required: true }
  - { format: "xlsx", priority: "secondary", required: false }
visual:
  palette: "corporate"
  density: "high"
  cover_style: "minimal"
validation:
  require_sources: true
  require_charts: false
  require_visual_review: false
```

### 场景3: 企业年度总结

```yaml
project:
  title: "2025年度总结报告"
  audience: "business"
outputs:
  - { format: "docx", priority: "primary", required: true }
  - { format: "pptx", priority: "primary", required: true }
  - { format: "xlsx", priority: "primary", required: true }
visual:
  palette: "sunset"
  density: "medium"
  cover_style: "swiss_grid"
validation:
  require_sources: true
  require_charts: true
  require_visual_review: true
```
